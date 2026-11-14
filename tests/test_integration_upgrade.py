"""Real API contracts between the merged trip planner and workspace."""
from datetime import date, timedelta
from unittest.mock import AsyncMock

from app.database import get_connection


def planned(client, user):
    start=date.today()+timedelta(days=10)
    trip=client.post('/api/trips/'+user,json={
        'destination_id':'jaipur_jodhpur_india','start_date':str(start),'end_date':str(start+timedelta(days=2)),
        'party':{'adults':2,'children':0,'seniors':0},'trip_type':'family','total_budget':30000,
        'schedule_prefs':{'hotel_arrival_time':'08:00','hotel_departure_time':'11:00'},
        'destination_arrival_time':'07:00','hotel_checkin_time':'08:00','hotel_checkout_time':'11:00',
        'final_day_activities':True,'departure_transport_mode':'flight','transport_departure_time':'18:00',
        'terminal_arrival_buffer_minutes':120,'terminal_journey_minutes':60,
        'lunch_start_time':'13:00','lunch_end_time':'14:00','lunch_duration_minutes':45})
    assert trip.status_code==200,trip.text
    trip=trip.json()
    response=client.post(f"/api/itinerary/generate/{trip['id']}?user_id={user}")
    assert response.status_code==200,response.text
    view=client.get(f"/api/trip-actions/{trip['id']}/timed-view")
    assert view.status_code==200,view.text
    return trip,view.json()


def test_complete_planning_schema_and_caps(client,deep_user):
    trip,view=planned(client,deep_user)
    assert trip['trip_type']=='family'
    assert trip['party']=={'adults':2,'children':0,'seniors':0}
    assert trip['transport_departure_time']=='18:00'
    assert trip['lunch_start_time']=='13:00'
    assert trip['lunch_duration_minutes']==45
    caps=client.get('/api/trip-experience/capabilities').json()
    assert all(caps[k] for k in ['schedule_preferences_v2','occurrence_acceptance','itinerary_preview'])
    final=[b for b in view['days'][-1]['timeline'] if b['type']=='activity']
    assert all(b['time_range'].split(' – ')[1]<='15:00' for b in final)


def test_acceptance_changes_only_one_occurrence(client,deep_user):
    trip,view=planned(client,deep_user)
    blocks=[b for d in view['days'] for b in d['timeline'] if b['type']=='activity']
    assert len(blocks)>1
    first=blocks[0]
    response=client.post(f"/api/trip-actions/{trip['id']}/acceptance",json={
        'itinerary_activity_id':first['id'],'action':'accept'})
    assert response.status_code==200,response.text
    with get_connection() as conn:
        rows=conn.execute('SELECT id,status FROM itinerary_activities WHERE itinerary_id=?',(view['itinerary']['id'],)).fetchall()
    assert [r['id'] for r in rows if r['status']=='accepted']==[first['id']]


def test_pin_preview_confirm_idempotency_and_undo(client,deep_user):
    trip,view=planned(client,deep_user)
    first=next(b for d in view['days'] for b in d['timeline'] if b['type']=='activity')
    path=f"/api/trip-actions/{trip['id']}"
    before=client.get(path+'/timed-view').json()
    preview=client.post(path+'/preview',json={'operation':'pin','target_activity_id':first['id']})
    assert preview.status_code==200,preview.text
    token=preview.json()['preview']['token']
    with get_connection() as conn:
        assert conn.execute('SELECT is_pinned FROM itinerary_activities WHERE id=?',(first['id'],)).fetchone()[0]==0
    for _ in range(2):
        result=client.post(path+'/confirm',json={'token':token})
        assert result.status_code==200,result.text
    with get_connection() as conn:
        assert conn.execute('SELECT is_pinned FROM itinerary_activities WHERE id=?',(first['id'],)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM trip_edit_history WHERE id=?',(token,)).fetchone()[0]==1
    undo=client.post(path+'/undo',json={'token':token})
    assert undo.status_code==200,undo.text
    with get_connection() as conn:
        assert conn.execute('SELECT is_pinned FROM itinerary_activities WHERE id=?',(first['id'],)).fetchone()[0]==0
    assert client.post(path+'/undo',json={'token':token}).status_code==409


def test_failed_preview_leaves_real_itinerary_unchanged(client,deep_user,monkeypatch):
    trip,view=planned(client,deep_user)
    first=next(b for d in view['days'] for b in d['timeline'] if b['type']=='activity')
    from app import trip_preview
    with get_connection() as conn:
        before=[tuple(r) for r in conn.execute('SELECT * FROM itinerary_activities ORDER BY id')]
    monkeypatch.setattr(trip_preview,'c_call_existing',AsyncMock(side_effect=RuntimeError('private provider failure')))
    # The public error must be readable and the database transaction must stay untouched.
    response=client.post(f"/api/trip-actions/{trip['id']}/preview",json={'operation':'remove','target_activity_id':first['id']})
    assert response.status_code==503,response.text
    assert 'private provider' not in response.text
    with get_connection() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM itinerary_activities ORDER BY id')]==before


def test_preview_invalid_custom_and_unknown_activity(client,deep_user):
    trip,_=planned(client,deep_user)
    path=f"/api/trip-actions/{trip['id']}/preview"
    assert client.post(path,json={'operation':'remove','target_activity_id':'unknown'}).status_code==404
    assert client.post(path,json={'operation':'add_custom','target_day':2,'activity':{'title':'','duration_minutes':-1}}).status_code==422


def test_remove_preview_undo_restores_recommendation_exclusions(client,deep_user):
    trip,view=planned(client,deep_user)
    first=next(b for d in view['days'] for b in d['timeline'] if b['type']=='activity')
    path=f"/api/trip-actions/{trip['id']}"
    with get_connection() as conn:
        before=[tuple(r) for r in conn.execute('SELECT * FROM rl_feedback_log WHERE trip_id=? ORDER BY id',(trip['id'],))]
    preview=client.post(path+'/preview',json={'operation':'remove','target_activity_id':first['id']})
    assert preview.status_code==200,preview.text
    token=preview.json()['preview']['token']
    confirmed=client.post(path+'/confirm',json={'token':token})
    assert confirmed.status_code==200,confirmed.text
    with get_connection() as conn:
        assert conn.execute('SELECT status FROM itinerary_activities WHERE id=?',(first['id'],)).fetchone()[0]=='rejected'
    undone=client.post(path+'/undo',json={'token':token})
    assert undone.status_code==200,undone.text
    with get_connection() as conn:
        assert conn.execute('SELECT status FROM itinerary_activities WHERE id=?',(first['id'],)).fetchone()[0]=='proposed'
        assert [tuple(r) for r in conn.execute('SELECT * FROM rl_feedback_log WHERE trip_id=? ORDER BY id',(trip['id'],))]==before
