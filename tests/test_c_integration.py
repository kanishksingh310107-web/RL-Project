"""Regression checks across the merged account, scheduling and runtime flows."""
import json
import pytest
from app.database import get_connection
from app.schedule_preferences import normalize_schedule_preferences
from test_c_runtime import c_trip, call, snapshot, start, end_review


def test_profile_gate_rechecks_edits_and_returns_flat_error(client,demo_user):
    changed=client.post('/api/profile/'+demo_user,json={'travel_goals':['nature'],'place_interests':['mountains']})
    assert changed.status_code==200,changed.text
    response=client.post('/api/trips/'+demo_user,json={'destination_id':'jaipur_india','start_date':'2027-03-01','end_date':'2027-03-03'})
    assert response.status_code==403
    assert response.json()['detail']=='Complete your personalization questionnaire first'
    assert response.json()['code']=='PROFILE_INCOMPLETE'
    dynamic=client.post('/api/places/plan-dynamic',json={'user_id':demo_user,'city':'Jaipur'})
    assert dynamic.status_code==403 and dynamic.json()['code']=='PROFILE_INCOMPLETE'


def test_shared_invalid_input_is_readable(client,demo_user):
    response=client.post('/api/trips/'+demo_user,json={'destination_id':'jaipur_india','start_date':'2027-03-01','end_date':'2027-03-03','travellers_count':0})
    assert response.status_code==422
    assert isinstance(response.json()['detail'],str)
    assert response.json()['field']=='travellers_count'
    assert response.json()['code']=='INVALID_INPUT'


@pytest.mark.parametrize('prefs',[
    {'hotel_departure_time':'05:00'},
    {'hotel_arrival_time':'23:30'},
    {'hotel_departure_time':'11:00','free_blocks':[{'day':3,'start':'09:00','end':'10:00','label':'Reserved'}]},
])
def test_hotel_buffers_and_free_time_must_leave_an_activity(prefs):
    with pytest.raises(ValueError,match='activity window'):
        normalize_schedule_preferences(prefs,3)


def test_custom_timeline_and_runtime_use_the_same_places(client,c_trip):
    from app.db_migrations_b import migrate_b
    prefs=normalize_schedule_preferences({'hotel_arrival_time':'10:00','hotel_departure_time':'18:00',
        'free_blocks':[{'day':1,'start':'12:00','end':'13:00','label':'My reserved time'}]},2)
    with get_connection() as conn:
        migrate_b(conn)
        conn.execute('INSERT INTO trip_schedule_prefs VALUES(?,?,?,?,?,?,?)',
            (c_trip['trip_id'],prefs['hotel_arrival_time'],prefs['hotel_departure_time'],prefs['wake_time'],
             prefs['bed_time'],prefs['activity_start_time'],json.dumps(prefs['free_blocks'])))
    response=client.get(f"/api/trip-actions/{c_trip['trip_id']}/timed-view")
    assert response.status_code==200,response.text
    timeline=response.json()['days']
    first=timeline[0]
    assert first['arrival_marker']=='10:00'
    assert any(block['type']=='free_time' and block['title']=='My reserved time' for block in first['timeline'])
    activities=[(day['day_number'],block) for day in timeline for block in day['timeline'] if block['type']=='activity']
    assert activities
    planned={(day,block['id']) for day,block in activities}
    assert {(slot['day_number'],slot['id']) for slot in snapshot(client,c_trip)['schedule']}==planned
    for day,block in activities:
        begin,end=block['time_range'].split(' – ')
        if day==1:
            assert begin>='11:00'
            assert not (begin<'13:00' and end>'12:00')
        else:
            assert end<='17:00'
    active=start(client,c_trip)
    assert (1,active['current_activity']['id']) in planned
    # Raw timed regeneration cannot edit a finalized/live itinerary.
    locked=client.post(f"/api/itinerary/timed/generate/{c_trip['trip_id']}?user_id={c_trip['user_id']}")
    assert locked.status_code==409
    end_review(client,c_trip,'change')
    assert snapshot(client,c_trip)['current_activity'] is None
    preview=call(client,c_trip,'/adjustments/preview',{'operation':'remove','target_activity_id':'c-food'})
    result=call(client,c_trip,'/adjustments/confirm',{'token':preview['preview']['token']})
    assert not any(slot['id']=='c-food' for slot in result['schedule'])
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM timed_itinerary_slots WHERE trip_id=? AND activity_id='kyoto_gion_tea_ceremony'",(c_trip['trip_id'],)).fetchone()[0]==0


@pytest.mark.parametrize('field,value',[
    ('accommodation_tier','unknown'),('travel_pace','unknown'),('transit_pref','unknown'),('travellers_count',True),
])
def test_tampered_trip_options_are_rejected(client,demo_user,field,value):
    response=client.post('/api/trips/'+demo_user,json={'destination_id':'jaipur_india','start_date':'2027-03-01','end_date':'2027-03-03',field:value})
    assert response.status_code==422,response.text
    assert response.json()['field']==field
