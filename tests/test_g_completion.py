"""Coverage and completion regressions for the finished travel planner."""
from datetime import date,timedelta
import pytest
from app.database import get_connection
from app.services.timed_itinerary import _custom_schedule


def test_small_catalogue_is_spread_across_five_days():
    prefs={'activity_start_time':'09:00','bed_time':'21:00','hotel_arrival_time':'08:00','hotel_departure_time':'21:00','free_blocks':[],'final_day_activities':True}
    activities=[{'id':str(i),'name':f'Place {i}','category':'culture_history','duration_minutes':60} for i in range(5)]
    days=_custom_schedule(activities,5,'balanced',prefs)
    counts=[d['activities_count'] for d in days]
    assert counts==[1,1,1,1,1]
    ids=[s['activity_id'] for d in days for s in d['slots'] if s['slot_type']=='activity']
    assert len(ids)==len(set(ids))==5


def test_empty_day_explains_shortage_without_fabricating_attractions():
    prefs={'activity_start_time':'09:00','bed_time':'21:00','hotel_arrival_time':'08:00','hotel_departure_time':'21:00','free_blocks':[],'final_day_activities':True}
    days=_custom_schedule([],3,'balanced',prefs,{})
    for day in days:
        assert 'No unused places' in day['note']
        assert any(s['slot_type']=='unplanned' for s in day['slots'])
        assert not any(s.get('activity_id') for s in day['slots'])


def test_deep_profile_required_before_trip_creation(client,demo_user):
    start=date.today()+timedelta(days=7)
    payload={'destination_id':'manali_spiti_india','start_date':str(start),'end_date':str(start+timedelta(days=4)),'total_budget':30000,'travellers_count':1}
    rejected=client.post('/api/trips/'+demo_user,json=payload)
    assert rejected.status_code==403 and rejected.json()['code']=='DEEP_PROFILE_INCOMPLETE'
    from conftest import complete_deep_profile
    complete_deep_profile(client,demo_user)
    created=client.post('/api/trips/'+demo_user,json=payload)
    assert created.status_code==200,created.text


def test_generator_does_not_exhaust_places_on_first_two_days(client,deep_user):
    start=date.today()+timedelta(days=7)
    trip=client.post('/api/trips/'+deep_user,json={'destination_id':'manali_spiti_india','start_date':str(start),'end_date':str(start+timedelta(days=4)),
        'total_budget':60000,'travellers_count':1,'hotel_checkin_time':'08:00','hotel_checkout_time':'21:00','final_day_activities':True,
        'schedule_prefs':{'hotel_arrival_time':'08:00','hotel_departure_time':'21:00'}})
    assert trip.status_code==200,trip.text
    trip=trip.json()
    with get_connection() as conn:
        for i in range(8):
            conn.execute('''INSERT INTO destination_activities(id,destination_id,name,category,neighborhood,latitude,longitude,duration_minutes,cost_tier,cost_amount,physical_intensity,crowd_level,opening_time,closing_time,tags,avoidance_triggers,description)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(f'coverage-{i}','manali_spiti_india',f'Manali place {i}','culture_history','Manali',32.243+i*.001,77.189,45,'budget',100,'low','low','09:00','20:00','[]','[]','Test catalogue venue'))
    response=client.post('/api/itinerary/generate/'+trip['id']+'?user_id='+deep_user)
    assert response.status_code==200,response.text
    view=client.get('/api/trip-actions/'+trip['id']+'/timed-view').json()
    counts=[sum(s['type'] in ('activity','shopping') for s in d['timeline']) for d in view['days']]
    assert len(counts)==5 and all(n>0 for n in counts),counts


def test_balance_preview_preserves_protected_stops_and_is_idempotent(client,deep_user):
    from test_integration_upgrade import planned
    trip,_=planned(client,deep_user);base='/api/trip-actions/'+trip['id']
    with get_connection() as conn:
        rows=[dict(r) for r in conn.execute('SELECT ia.* FROM itinerary_activities ia JOIN itineraries i ON ia.itinerary_id=i.id WHERE i.trip_id=? ORDER BY ia.id',(trip['id'],))]
        protected=rows[0]['id'];conn.execute("UPDATE itinerary_activities SET status='accepted',is_pinned=1 WHERE id=?",(protected,))
        before=[tuple(r) for r in conn.execute('SELECT id,day_number,order_index FROM itinerary_activities WHERE itinerary_id=? ORDER BY id',(rows[0]['itinerary_id'],))]
    preview=client.post(base+'/preview',json={'operation':'rebalance'})
    assert preview.status_code==200,preview.text
    with get_connection() as conn:
        assert [tuple(r) for r in conn.execute('SELECT id,day_number,order_index FROM itinerary_activities WHERE itinerary_id=? ORDER BY id',(rows[0]['itinerary_id'],))]==before
    token=preview.json()['preview']['token']
    assert client.post(base+'/confirm',json={'token':token}).status_code==200
    assert client.post(base+'/confirm',json={'token':token}).status_code==200
    with get_connection() as conn:
        assert conn.execute('SELECT day_number FROM itinerary_activities WHERE id=?',(protected,)).fetchone()[0]==rows[0]['day_number']
    assert client.post(base+'/undo',json={'token':token}).status_code==200


def test_budget_options_contain_full_itineraries_without_mutating_saved_trip(client,deep_user):
    from test_integration_upgrade import planned
    trip,_=planned(client,deep_user)
    before=client.get('/api/trip-actions/'+trip['id']+'/timed-view').json()
    options=client.post('/api/trips/'+trip['id']+'/budget-options',json={'max_additional_budget_inr':10000,'priorities':['stay_comfort']})
    assert options.status_code==200,options.text
    for option in options.json()['options']:
        assert len(option['itinerary']['days'])==3
        assert option['additional_cost_inr']<=10000
        assert option['comparison_basis']['destination_id']==trip['destination_id']
    assert client.get('/api/trip-actions/'+trip['id']+'/timed-view').json()==before


def test_concrete_budget_alternative_previews_confirms_and_undoes(client,deep_user,monkeypatch):
    from test_integration_upgrade import planned
    trip,_=planned(client,deep_user)
    base='/api/trip-actions/'+trip['id']
    with get_connection() as conn:
        source=dict(conn.execute('''SELECT da.* FROM destination_activities da JOIN itinerary_activities ia ON da.id=ia.activity_id
            JOIN itineraries i ON i.id=ia.itinerary_id WHERE i.trip_id=? ORDER BY ia.day_number,ia.order_index LIMIT 1''',(trip['id'],)).fetchone())
        source.update(id='budget-comparison-alternative',name='Alternative local experience',cost_amount=100)
        conn.execute('INSERT INTO destination_activities ('+','.join(source)+') VALUES ('+','.join('?' for _ in source)+')',tuple(source.values()))
    monkeypatch.setattr('app.itinerary_generator.get_slot_alternatives',lambda *args:[source])
    before=client.get(base+'/timed-view').json()
    result=client.post('/api/trips/'+trip['id']+'/budget-options',json={'max_additional_budget_inr':10000})
    assert result.status_code==200,result.text
    options=result.json()['options']
    assert 2<=len(options)<=3
    option=next(o for o in options if o['id'].startswith('experience-'))
    assert any(s['title']==source['name'] for d in option['itinerary']['days'] for s in d['timeline'])
    assert client.get(base+'/timed-view').json()==before
    proposal=client.post(base+'/preview',json=option['preview_request'])
    assert proposal.status_code==200,proposal.text
    token=proposal.json()['preview']['token']
    assert client.post(base+'/confirm',json={'token':token}).status_code==200
    assert client.post(base+'/confirm',json={'token':token}).status_code==200
    with get_connection() as conn:
        assert conn.execute('SELECT count(*) FROM itinerary_activities ia JOIN itineraries i ON i.id=ia.itinerary_id WHERE i.trip_id=? AND ia.activity_id=?',(trip['id'],source['id'])).fetchone()[0]==1
    assert client.post(base+'/undo',json={'token':token}).status_code==200
    assert client.get(base+'/timed-view').json()==before


def test_less_walking_options_preview_existing_preferences_and_enforce_stage(client,deep_user):
    from test_integration_upgrade import planned
    trip,_=planned(client,deep_user)
    result=client.get('/api/trips/'+trip['id']+'/day-options?day_number=1&goal=less_walking')
    assert result.status_code==200,result.text
    option=next(o for o in result.json()['day_options'] if o['id']=='vehicle-transfers')
    response=client.post('/api/trip-actions/'+trip['id']+'/preview',json=option['preview_request'])
    assert response.status_code==200,response.text
    token=response.json()['preview']['token']
    assert client.post('/api/trip-actions/'+trip['id']+'/confirm',json={'token':token}).status_code==200
    with get_connection() as conn:
        import json
        prefs=json.loads(conn.execute('SELECT trip_preferences_json FROM trips WHERE id=?',(trip['id'],)).fetchone()[0])
        assert prefs['transport_preferences']==['cab']
    assert client.post('/api/trips/'+trip['id']+'/finalize',json={'user_id':deep_user}).status_code==200
    assert client.get('/api/trips/'+trip['id']+'/day-options?day_number=1&goal=less_walking').status_code==409


def test_zero_transfer_walking_limit_selects_vehicle_instead_of_hidden_walking():
    prefs={'activity_start_time':'09:00','bed_time':'21:00','hotel_arrival_time':'08:00','hotel_departure_time':'21:00','free_blocks':[],'final_day_activities':True,'walking_limit_km':0}
    acts=[{'id':str(i),'name':str(i),'category':'culture_history','duration_minutes':30,'latitude':18.52+i*.001,'longitude':73.85} for i in range(2)]
    day=_custom_schedule(acts,1,'balanced',prefs)[0]
    transfers=[s for s in day['slots'] if s['slot_type']=='transit']
    assert transfers and all(s['provenance'].get('mode')=='cab' for s in transfers)
    assert day['transfer_walking_km']==0


def test_assistant_credit_failure_is_readable_and_does_not_change_trip(client,deep_user,monkeypatch):
    from test_f_experience_integration import provider
    request=provider(monkeypatch,{})
    request.return_value.status_code=429
    request.return_value.json.return_value={'error':{'code':'credit_balance_exhausted','message':'private provider diagnostics'}}
    response=client.post('/api/assistant/chat',json={'message':'Suggest a trip'})
    assert response.status_code==503
    assert response.json()['code']=='ASSISTANT_CREDITS_UNAVAILABLE'
    assert 'private provider diagnostics' not in response.text


def test_free_assistant_works_without_key_and_never_calls_provider(client,deep_user,monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE','local');monkeypatch.setenv('OPENAI_API_KEY','')
    def forbidden(*args,**kwargs):raise AssertionError('Free mode must not contact a paid model provider')
    monkeypatch.setattr('app.recommendation_budget.requests.post',forbidden)
    caps=client.get('/api/experience/capabilities').json()
    assert caps['assistant_chat'] and caps['assistant_mode']=='local'
    response=client.post('/api/assistant/chat',json={'message':'Help me choose a destination'})
    assert response.status_code==200,response.text
    assert response.json()['assistant_mode']=='local'
    assert response.json()['answer'] and response.json()['trip_mutated'] is False


def test_free_assistant_budget_is_authoritative_and_proposals_need_confirmation(client,deep_user,monkeypatch):
    from test_integration_upgrade import planned
    monkeypatch.setenv('ASSISTANT_MODE','local')
    trip,_=planned(client,deep_user)
    body={'trip_id':trip['id'],'message':'How much budget remains?'}
    response=client.post('/api/assistant/chat',json=body)
    assert response.status_code==200,response.text
    assert 'INR 30,000' in response.json()['answer']
    before=client.get('/api/trip-actions/'+trip['id']+'/timed-view').json()
    suggestion=client.post('/api/assistant/chat',json={**body,'message':'Suggest more downtime'})
    assert suggestion.status_code==200,suggestion.text
    assert suggestion.json()['confirmation_required'] is True
    assert client.get('/api/trip-actions/'+trip['id']+'/timed-view').json()==before


def test_discovery_applies_indicative_time_limit_for_known_origin(client,demo_user):
    response=client.post('/api/discovery/suggestions',json={'origin':'Pune','duration_days':3,'comfortable_budget_inr':500000,'party_size':1,'trip_type':'solo','transport':'driving','max_travel_minutes':240})
    assert response.status_code==200,response.text
    body=response.json();assert body['estimated_travel_filter_applied'] is True
    assert all(d['estimated_travel_minutes']<=240 and d['travel_time_minutes'] is None and d['travel_estimate_is_verified'] is False for d in body['recommendations'])
