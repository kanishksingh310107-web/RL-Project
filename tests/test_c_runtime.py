"""Person C: lifecycle, ordering, ownership and persistence regressions."""
import json
import sqlite3
import uuid
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.database import get_connection
from app.modules import live


@pytest.fixture
def c_trip(client):
    from app.db_migrations_a import migrate_a
    migrate_a()
    auth=client.post('/api/account/guest',json={'guest_id':'person_c_runtime_test_identity'})
    assert auth.status_code==200,auth.text
    demo_user=auth.json()['user_id']
    client.headers['Authorization']='Bearer '+auth.json()['token']
    profile=client.post('/api/profile/'+demo_user,json={'travel_goals':['culture'],
        'place_interests':['historic'],'preferred_climate':'cool','budget_tier':'mid_range','companions':'partner'})
    assert profile.status_code==200,profile.text
    tid,iid=uuid.uuid4().hex,uuid.uuid4().hex
    with get_connection() as conn:
        conn.execute('''INSERT INTO trips(id,user_id,destination_id,destination_name,start_date,end_date,duration_days,total_budget)
            VALUES(?,?,'kyoto_japan','Kyoto','2026-11-26','2026-11-27',2,26000)''',(tid,demo_user))
        conn.execute("INSERT INTO itineraries(id,trip_id,user_id,title,total_days,status) VALUES(?,?,?,'C test itinerary',2,'active')",(iid,tid,demo_user))
        for sid,day,order,aid in [('c-first',1,0,'kyoto_fushimi_inari'),('c-food',1,1,'kyoto_gion_tea_ceremony'),('c-last',2,0,'kyoto_fushimi_inari')]:
            activity=conn.execute('SELECT * FROM destination_activities WHERE id=?',(aid,)).fetchone()
            conn.execute('''INSERT INTO itinerary_activities(id,itinerary_id,day_number,time_slot,activity_id,title,category,
                neighborhood,latitude,longitude,duration_minutes,cost_estimate,order_index)
                VALUES(?,?,?,'morning',?,?,?,?,?,?,90,500,?)''',
                (sid,iid,day,aid,activity['name'],activity['category'],activity['neighborhood'],activity['latitude'],activity['longitude'],order))
        conn.commit()
    return {'trip_id':tid,'user_id':demo_user,'itinerary_id':iid}


def call(client,trip,path,body=None,expected=200):
    response=client.post(f"/api/trips/{trip['trip_id']}{path}?user_id={trip['user_id']}",json=body or {})
    assert response.status_code==expected,response.text
    data=response.json()
    if expected>=400:
        assert isinstance(data['detail'],str)
        assert data['code'] and 'field' in data
    return data


def snapshot(client,trip):
    response=client.get(f"/api/trips/{trip['trip_id']}/runtime?user_id={trip['user_id']}")
    assert response.status_code==200,response.text
    return response.json()


def start(client,trip):
    call(client,trip,'/finalize')
    return call(client,trip,'/start')


def end_review(client,trip,action='keep',outcome='completed'):
    current=snapshot(client,trip)['current_activity']
    ended=call(client,trip,f"/activities/{current['id']}/end",{'outcome':outcome})
    ratings={key:4 for key in current['applicable_rating_keys']} if outcome not in ('skipped','not_done') else {}
    reviewed=call(client,trip,f"/activities/{current['id']}/review",{'ratings':ratings,'action':action,'notes':'  <b>Nice</b> visit  '})
    return ended,reviewed


def finish(client,trip):
    start(client,trip)
    end_review(client,trip)
    end_review(client,trip)
    call(client,trip,'/days/1/end',{'dispositions':{}})
    call(client,trip,'/days/2/start')
    end_review(client,trip)
    call(client,trip,'/days/2/end',{'dispositions':{}})
    return call(client,trip,'/end')


def feedback(**overrides):
    return dict(ratings={key:4 for key in live.C_RATING_KEYS},trip_type='couple',would_revisit='yes',
                liked='Gardens',disliked='Queues',notes="  <script>alert('x')</script> O'Brien  ",**overrides)


def test_c_full_path_resume_labels_feedback_and_learning(client,c_trip):
    trip=c_trip
    assert snapshot(client,trip)['phase']=='draft'
    call(client,trip,'/start',expected=409)
    finalized=call(client,trip,'/finalize')
    assert finalized['status']=='finalized'
    call(client,trip,'/finalize',expected=409)
    current=call(client,trip,'/start')
    assert current['status']=='live' and current['runtime']['started_at']
    assert current['current_activity']['id']=='c-first'
    assert current['end_activity_label']=='End activity'
    call(client,trip,'/activities/c-first/start',expected=409)
    call(client,trip,'/activities/c-food/end',expected=409)
    ended=call(client,trip,'/activities/c-first/end',{'outcome':'early_ended'})
    assert ended['phase']=='activity_review' and ended['pending_review']['run']['ended_at']
    from main import app
    reloaded=TestClient(app).get(f"/api/trips/{trip['trip_id']}/runtime?user_id={trip['user_id']}",headers=dict(client.headers)).json()
    assert reloaded==ended
    call(client,trip,'/activities/c-food/start',expected=409)
    ratings={key:5 for key in ended['pending_review']['applicable_rating_keys']}
    reviewed=call(client,trip,'/activities/c-first/review',{'ratings':ratings,'action':'keep','notes':' <b>Safe</b> '})
    assert reviewed['current_activity']['id']=='c-food'
    assert reviewed['end_activity_label']=='End day'
    with get_connection() as conn:
        run=conn.execute("SELECT * FROM activity_runs WHERE itinerary_activity_id='c-first'").fetchone()
        assert run['action']=='keep' and run['notes']=='Safe' and run['learning_applied']==1
        assert json.loads(run['ratings_json'])==ratings
        assert conn.execute('SELECT SUM(pull_count) FROM rl_user_policies WHERE user_id=?',(trip['user_id'],)).fetchone()[0]>0
    call(client,trip,'/activities/c-first/review',{'ratings':ratings,'action':'keep'},expected=409)
    call(client,trip,'/days/2/start',expected=409)
    _,last_today=end_review(client,trip)
    assert last_today['phase']=='awaiting_day_end'
    day_summary=call(client,trip,'/days/1/end',{'dispositions':{}})
    assert day_summary['phase']=='day_summary'
    assert snapshot(client,trip)==day_summary
    call(client,trip,'/days/1/end',{'dispositions':{}},expected=409)
    next_day=call(client,trip,'/days/2/start')
    assert next_day['current_activity']['id']=='c-last'
    assert next_day['end_activity_label']=='End trip'
    call(client,trip,'/days/2/start',expected=409)
    call(client,trip,'/end',expected=409)
    end_review(client,trip)
    call(client,trip,'/days/2/end',{'dispositions':{}})
    complete=call(client,trip,'/end')
    assert complete['status']=='completed' and complete['runtime']['ended_at']
    assert complete['feedback_required'] and not complete['closed_out']
    call(client,trip,'/activities/c-last/start',expected=409)
    call(client,trip,'/end',expected=409)
    draft=call(client,trip,'/post-feedback',{'draft':True,'notes':'Resume here','ratings':{'overall':4}})
    assert draft['post_feedback']['submitted_at'] is None
    assert snapshot(client,trip)['post_feedback']['notes']=='Resume here'
    submitted=call(client,trip,'/post-feedback',feedback())
    assert submitted['closed_out'] and not submitted['feedback_required']
    again=call(client,trip,'/post-feedback',feedback())
    assert again['post_feedback']['submitted_at']==submitted['post_feedback']['submitted_at']
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM post_trip_feedback WHERE trip_id=?',(trip['trip_id'],)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM live_postrip WHERE trip_id=?',(trip['trip_id'],)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM activity_runs WHERE trip_id=?',(trip['trip_id'],)).fetchone()[0]==3
        assert conn.execute('SELECT COUNT(*) FROM core_trip_feedback WHERE trip_id=?',(trip['trip_id'],)).fetchone()[0]==1


def test_c_finalize_empty_and_edit_lock(client,c_trip):
    trip=c_trip
    call(client,trip,'/finalize')
    for path,method,body in [
        (f"/api/itinerary/generate/{trip['trip_id']}?user_id={trip['user_id']}",'post',{}),
        (f"/api/trip-actions/{trip['trip_id']}/activity/c-first?user_id={trip['user_id']}",'delete',None),
        (f"/api/trips/{trip['trip_id']}?user_id={trip['user_id']}",'patch',{'total_budget':30000}),
        (f"/api/itinerary/feedback/{trip['user_id']}",'post',{'itinerary_id':trip['itinerary_id'],'activity_id':'kyoto_fushimi_inari','action_type':'reject'}),
    ]:
        response=client.request(method.upper(),path,json=body)
        assert response.status_code==409,response.text
        assert response.json()['code']=='ITINERARY_LOCKED'
    assert call(client,trip,'/unfinalize')['status']=='draft'
    with get_connection() as conn:
        conn.execute('DELETE FROM itinerary_activities WHERE itinerary_id=?',(trip['itinerary_id'],));conn.commit()
    assert call(client,trip,'/finalize',expected=409)['code']=='EMPTY_ITINERARY'


def test_c_explicit_skips_no_silent_day_jump(client,c_trip):
    start(client,c_trip)
    response=call(client,c_trip,'/days/1/end',{'dispositions':{}},expected=409)
    assert response['code']=='UNFINISHED_ACTIVITIES'
    call(client,c_trip,'/days/2/start',expected=409)
    call(client,c_trip,'/days/1/end',{'dispositions':{'wrong':'skipped'}},expected=404)
    result=call(client,c_trip,'/days/1/end',{'dispositions':{'c-first':'skipped','c-food':'not_done'}})
    assert result['phase']=='day_summary' and result['current_activity'] is None
    assert {r['outcome'] for r in result['runs']}=={'skipped','not_done'}
    call(client,c_trip,'/activities/c-food/start',expected=409)
    call(client,c_trip,'/days/1/start',expected=409)
    assert call(client,c_trip,'/days/2/start')['current_activity']['id']=='c-last'


@pytest.mark.parametrize('path,body',[
    ('/finalize',{}),('/start',{}),('/activities/c-first/start',{}),('/activities/c-first/end',{}),
    ('/activities/c-first/review',{'ratings':{'overall':4},'action':'keep'}),('/days/1/end',{'dispositions':{}}),
    ('/days/2/start',{}),('/end',{}),('/post-feedback',{'draft':True}),
])
def test_c_ownership_every_action(client,c_trip,path,body):
    wrong=dict(c_trip,user_id='someone-else')
    call(client,wrong,path,body,expected=403)


def test_c_unknown_ids_and_ambiguous_catalogue_ids(client,c_trip):
    unknown=dict(c_trip,trip_id='unknown')
    call(client,unknown,'/finalize',expected=404)
    call(client,c_trip,'/activities/not-in-this-trip/end',expected=404)
    call(client,c_trip,'/days/9/start',expected=404)
    call(client,c_trip,'/days/0/end',{'dispositions':{}},expected=404)
    call(client,c_trip,'/activities/kyoto_fushimi_inari/start',expected=422)


@pytest.mark.parametrize('body',[
    {},{'ratings':{},'action':'unknown'}, {'ratings':{'overall':0},'action':'keep'},
    {'ratings':{'overall':6},'action':'keep'}, {'ratings':{'overall':4.5},'action':'keep'},
    {'ratings':{'overall':'4'},'action':'keep'}, {'ratings':{'overall':True},'action':'keep'},
    {'ratings':{'made_up':4},'action':'keep'}, {'ratings':{'overall':4},'action':'keep','notes':'x'*1001},
    {'ratings':{'overall':4},'action':'keep','status':'completed'},
])
def test_c_review_invalid_input(client,c_trip,body):
    start(client,c_trip)
    call(client,c_trip,'/activities/c-first/end')
    call(client,c_trip,'/activities/c-first/review',body,expected=422)
    assert snapshot(client,c_trip)['phase']=='activity_review'


def test_c_review_applicability_and_notes(client,c_trip):
    start(client,c_trip)
    call(client,c_trip,'/activities/c-first/end')
    call(client,c_trip,'/activities/c-first/review',{'ratings':{'overall':4},'action':'keep'},expected=422)
    keys=snapshot(client,c_trip)['pending_review']['applicable_rating_keys']
    ratings={key:4 for key in keys}; ratings['stay_quality']=5
    call(client,c_trip,'/activities/c-first/review',{'ratings':ratings,'action':'keep'},expected=422)
    ratings.pop('stay_quality')
    result=call(client,c_trip,'/activities/c-first/review',{'ratings':ratings,'action':'keep','notes':" <b>O'Brien</b> <img src=x onerror=alert(1)> "})
    assert result['runs'][0]['notes']=="O'Brien"


@pytest.mark.parametrize('patch',[
    {'ratings':{}},{'trip_type':'business'},{'would_revisit':'always'}, {'liked':'   '},
    {'ratings':{'overall':True}}, {'ratings':{**{key:3 for key in live.C_RATING_KEYS},'injected':4}},
    {'notes':'x'*2001}, {'draft':'false'}, {'user_id':'   '}, {'travel_history':[]},
])
def test_c_post_feedback_invalid(client,c_trip,patch):
    finish(client,c_trip)
    body=feedback(); body.update(patch)
    # A blank body actor is invalid even if a valid query actor is present.
    call(client,c_trip,'/post-feedback',body,expected=422)
    assert snapshot(client,c_trip)['feedback_required']


def test_c_feedback_before_end_and_foreign_place(client,c_trip):
    call(client,c_trip,'/post-feedback',feedback(),expected=409)
    finish(client,c_trip)
    body=feedback(); body['per_place_ratings']=[{'activity_id':'foreign-slot','ratings':{'overall':4}}]
    call(client,c_trip,'/post-feedback',body,expected=404)


@pytest.mark.parametrize('action',['enhance','change'])
def test_c_decision_downstream_preview_and_failure(client,c_trip,monkeypatch,action):
    start(client,c_trip)
    _,reviewed=end_review(client,c_trip,action)
    assert reviewed['phase']=='itinerary_decision' and reviewed['current_activity'] is None
    call(client,c_trip,'/activities/c-food/start',expected=409)
    downstream=AsyncMock(return_value={'alternatives':[{'id':'kyoto_arashiyama_bamboo','name':'Bamboo grove'}]})
    monkeypatch.setattr(live,'c_call_existing',downstream)
    response=client.get(f"/api/trips/{c_trip['trip_id']}/suggestions?user_id={c_trip['user_id']}")
    assert response.status_code==200,response.text
    assert '/replan?' in downstream.call_args.args[2]
    preview=call(client,c_trip,'/adjustments/preview',{'target_activity_id':'c-food','operation':'swap','replacement_activity_id':'kyoto_arashiyama_bamboo'})
    token=preview['preview']['token']
    assert snapshot(client,c_trip)['preview']['token']==token
    failed=AsyncMock(side_effect=HTTPException(503,detail={'detail':'Mocked replan failure','code':'DOWNSTREAM_UNAVAILABLE','field':None}))
    monkeypatch.setattr(live,'c_call_existing',failed)
    call(client,c_trip,'/adjustments/confirm',{'token':token},expected=503)
    after=snapshot(client,c_trip)
    assert not after['runtime']['operation_in_flight'] and after['preview']['token']==token
    assert after['current_activity'] is None
    success=AsyncMock(return_value={'status':'success'})
    monkeypatch.setattr(live,'c_call_existing',success)
    changed=call(client,c_trip,'/adjustments/confirm',{'token':token})
    assert success.call_args.args[1]=='POST' and success.call_args.args[2].endswith('/replan')
    assert success.call_args.args[3]['itinerary_activity_id']=='c-food'
    assert changed['current_activity']['id']=='c-food'
    call(client,c_trip,'/adjustments/confirm',{'token':token})
    assert success.await_count==1


def test_c_keep_does_not_call_replan_change_remove_uses_existing_endpoint(client,c_trip,monkeypatch):
    downstream=AsyncMock(return_value={})
    monkeypatch.setattr(live,'c_call_existing',downstream)
    start(client,c_trip)
    end_review(client,c_trip,'keep')
    assert downstream.await_count==0
    end_review(client,c_trip,'change')
    # A repeated place already visited cannot be removed through the legacy
    # group-removal API, since that would also remove a completed occurrence.
    call(client,c_trip,'/adjustments/preview',{'target_activity_id':'c-last','operation':'remove'},expected=409)
    assert call(client,c_trip,'/continue')['phase']=='awaiting_day_end'


def test_c_database_failure_is_readable(client,c_trip,monkeypatch):
    def broken(): raise sqlite3.OperationalError('private connection details')
    monkeypatch.setattr(live,'get_connection',broken)
    response=client.get(f"/api/trips/{c_trip['trip_id']}/runtime?user_id={c_trip['user_id']}")
    assert response.status_code==503,response.text
    assert response.json()['code']=='DATABASE_UNAVAILABLE'
    assert 'private' not in response.text


def test_c_migration_idempotent(c_trip):
    from app.db_migrations_c import migrate_c
    migrate_c();migrate_c()
    with get_connection() as conn:
        assert {'trip_runtime','activity_runs','post_trip_feedback'} <= {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_c_actual_remove_calls_existing_endpoint_without_starting_next_day(client,c_trip):
    start(client,c_trip)
    end_review(client,c_trip,'change')
    preview=call(client,c_trip,'/adjustments/preview',{'target_activity_id':'c-food','operation':'remove'})
    result=call(client,c_trip,'/adjustments/confirm',{'token':preview['preview']['token']})
    assert result['phase']=='awaiting_day_end'
    assert result['runtime']['current_day']==1 and result['current_activity'] is None
    assert [s['id'] for s in result['schedule']]==['c-first','c-last']
    call(client,c_trip,'/days/2/start',expected=409)


def test_c_actual_swap_preserves_other_occurrences_and_started_context(client,c_trip):
    start(client,c_trip)
    end_review(client,c_trip,'change')
    with get_connection() as conn:
        before=tuple(conn.execute("SELECT * FROM itinerary_activities WHERE id='c-first'").fetchone())
        saved=conn.execute("SELECT context_json FROM activity_runs WHERE itinerary_activity_id='c-first'").fetchone()[0]
    suggestions=client.get(f"/api/trips/{c_trip['trip_id']}/suggestions?user_id={c_trip['user_id']}").json()
    assert suggestions['alternatives']
    replacement=suggestions['alternatives'][0]['id']
    preview=call(client,c_trip,'/adjustments/preview',{'target_activity_id':'c-food','operation':'swap','replacement_activity_id':replacement})
    result=call(client,c_trip,'/adjustments/confirm',{'token':preview['preview']['token']})
    assert result['current_activity']['catalogue_activity_id']==replacement
    with get_connection() as conn:
        assert tuple(conn.execute("SELECT * FROM itinerary_activities WHERE id='c-first'").fetchone())==before
        assert conn.execute("SELECT context_json FROM activity_runs WHERE itinerary_activity_id='c-first'").fetchone()[0]==saved


def test_c_failed_learning_rolls_back_review(client,c_trip,monkeypatch):
    start(client,c_trip)
    ended=call(client,c_trip,'/activities/c-first/end')
    def fail(*args): raise sqlite3.OperationalError('test failed persistence')
    monkeypatch.setattr(live,'save_user_policy',fail)
    ratings={key:4 for key in ended['pending_review']['applicable_rating_keys']}
    call(client,c_trip,'/activities/c-first/review',{'ratings':ratings,'action':'keep'},expected=503)
    result=snapshot(client,c_trip)
    assert result['phase']=='activity_review' and result['current_activity'] is None
    assert result['pending_review']['run']['action'] is None


def test_c_raw_replan_failure_keeps_preview_and_recovers_crashed_request(client,c_trip,monkeypatch):
    start(client,c_trip)
    end_review(client,c_trip,'change')
    preview=call(client,c_trip,'/adjustments/preview',{'target_activity_id':'c-food','operation':'remove'})
    monkeypatch.setattr(live,'c_call_existing',AsyncMock(side_effect=RuntimeError('private service trace')))
    failure=call(client,c_trip,'/adjustments/confirm',{'token':preview['preview']['token']},expected=503)
    assert 'private' not in failure['detail']
    with get_connection() as conn:
        conn.execute("UPDATE trip_runtime SET operation_in_flight=1,operation_started_at='2000-01-01T00:00:00+00:00' WHERE trip_id=?",(c_trip['trip_id'],));conn.commit()
    resumed=snapshot(client,c_trip)
    assert resumed['runtime']['operation_in_flight']==0
    assert resumed['preview']['token']==preview['preview']['token']
    assert resumed['phase']=='itinerary_decision'


def test_c_double_click_start_and_double_submit_post(client,c_trip):
    from concurrent.futures import ThreadPoolExecutor
    call(client,c_trip,'/finalize')
    url=f"/api/trips/{c_trip['trip_id']}"
    def send(path,body): return client.post(f"{url}{path}?user_id={c_trip['user_id']}",json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:send('/start',{}),range(2)))
    assert sorted(r.status_code for r in responses)==[200,409]
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM activity_runs WHERE trip_id=?',(c_trip['trip_id'],)).fetchone()[0]==1
    end_review(client,c_trip);end_review(client,c_trip)
    call(client,c_trip,'/days/1/end',{'dispositions':{}})
    call(client,c_trip,'/days/2/start');end_review(client,c_trip)
    call(client,c_trip,'/days/2/end',{'dispositions':{}});call(client,c_trip,'/end')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:send('/post-feedback',feedback()),range(2)))
    assert all(r.status_code in (200,409) for r in responses)
    assert any(r.status_code==200 for r in responses)
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM post_trip_feedback WHERE trip_id=?',(c_trip['trip_id'],)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM live_postrip WHERE trip_id=?',(c_trip['trip_id'],)).fetchone()[0]==1


def test_c_feedback_failure_keeps_resumable_draft(client,c_trip,monkeypatch):
    finish(client,c_trip)
    monkeypatch.setattr(live,'c_call_existing',AsyncMock(side_effect=RuntimeError('failed bridge')))
    call(client,c_trip,'/post-feedback',feedback(),expected=503)
    result=snapshot(client,c_trip)
    assert result['post_feedback']['liked']=='Gardens'
    assert result['feedback_required'] and result['post_feedback']['submitted_at'] is None
    assert result['runtime']['operation_in_flight']==0


def test_c_invalid_and_out_of_order_disruption(client,c_trip):
    start(client,c_trip)
    url=f"/api/live/{c_trip['trip_id']}/simulate"
    body={'user_id':c_trip['user_id'],'condition_type':'heavy_rain','day_number':2}
    assert client.post(url,json=body).status_code==409
    body['day_number']=1;body['condition_type']='invented'
    invalid=client.post(url,json=body)
    assert invalid.status_code==422 and invalid.json()['code']=='INVALID_INPUT'
    body['condition_type']='heavy_rain';body['day_number']=99
    assert client.post(url,json=body).status_code==404


@pytest.mark.parametrize('body',[
    {'target_activity_id':'   ','operation':'remove'},
    {'target_activity_id':'c-food','operation':'swap'},
    {'target_activity_id':'c-food','operation':'delete'},
])
def test_c_adjustment_tampered_payloads(client,c_trip,body):
    start(client,c_trip);end_review(client,c_trip,'enhance')
    call(client,c_trip,'/adjustments/preview',body,expected=422)


def test_c_no_history_or_profile_writes_and_post_place_ratings(client,c_trip):
    with get_connection() as conn:
        before=[tuple(r) for r in conn.execute('SELECT * FROM traveller_profiles WHERE user_id=?',(c_trip['user_id'],))]
        history=[tuple(r) for r in conn.execute('SELECT * FROM past_trips WHERE user_id=?',(c_trip['user_id'],))]
    finish(client,c_trip)
    body=feedback();body['per_place_ratings']=[{'activity_id':'c-food','ratings':{'overall':4,'food':5}}]
    result=call(client,c_trip,'/post-feedback',body)
    assert result['closed_out']
    with get_connection() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM traveller_profiles WHERE user_id=?',(c_trip['user_id'],))]==before
        assert [tuple(r) for r in conn.execute('SELECT * FROM past_trips WHERE user_id=?',(c_trip['user_id'],))]==history
        assert conn.execute('SELECT learning_applied FROM activity_runs WHERE itinerary_activity_id=?',('c-food',)).fetchone()[0]==1


def test_c_reload_after_learning_delivery_reconciles_without_duplicate(client,c_trip):
    finish(client,c_trip)
    submitted=call(client,c_trip,'/post-feedback',feedback())
    assert submitted['closed_out']
    with get_connection() as conn:
        conn.execute('UPDATE post_trip_feedback SET submitted_at=NULL WHERE trip_id=?',(c_trip['trip_id'],))
        conn.execute("UPDATE trip_runtime SET operation_in_flight=1,operation_started_at='2000-01-01T00:00:00+00:00' WHERE trip_id=?",(c_trip['trip_id'],))
        conn.commit()
    reloaded=snapshot(client,c_trip)
    assert reloaded['closed_out'] and not reloaded['feedback_required']
    call(client,c_trip,'/post-feedback',feedback())
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM live_postrip WHERE trip_id=?',(c_trip['trip_id'],)).fetchone()[0]==1


def test_c_missing_actor_body_and_invalid_outcome(client,c_trip):
    response=client.post(f"/api/trips/{c_trip['trip_id']}/finalize",json={})
    assert response.status_code==422 and response.json()['field']=='user_id'
    response=client.post(f"/api/trips/{c_trip['trip_id']}/activities/c-first/end?user_id={c_trip['user_id']}")
    assert response.status_code==409
    start(client,c_trip)
    call(client,c_trip,'/activities/c-first/end',{'outcome':'pretend_completed'},expected=422)
    assert snapshot(client,c_trip)['phase']=='activity'


def test_c_learning_summary_includes_occurrence_reviews(client,c_trip):
    start(client,c_trip);end_review(client,c_trip)
    response=client.get(f"/api/live/{c_trip['user_id']}/learning-summary?caller_user_id={c_trip['user_id']}")
    assert response.status_code==200,response.text
    assert response.json()['total_evaluations_processed']==1


def test_c_session_required_and_owner_id_cannot_be_forged(client,c_trip):
    url=f"/api/trips/{c_trip['trip_id']}/runtime?user_id={c_trip['user_id']}"
    token=client.headers.pop('Authorization')
    missing=client.get(url)
    assert missing.status_code==403 and missing.json()['code']=='AUTH_REQUIRED'
    other=client.post('/api/account/guest',json={'guest_id':'different_c_account_identity'}).json()
    client.headers['Authorization']='Bearer '+other['token']
    forged=client.get(url)
    assert forged.status_code==403 and forged.json()['code']=='NOT_OWNER'
    client.headers['Authorization']=token
    assert client.get(url).status_code==200
    with get_connection() as conn:
        conn.execute('UPDATE auth_sessions SET expires_at=? WHERE user_id=?',('2000-01-01T00:00:00+00:00',c_trip['user_id']))
    expired=client.get(url)
    assert expired.status_code==403 and expired.json()['code']=='SESSION_EXPIRED'


def test_c_draft_not_published_to_history_until_submission(client,c_trip):
    finish(client,c_trip)
    body=feedback(draft=True)
    call(client,c_trip,'/post-feedback',body)
    assert snapshot(client,c_trip)['post_feedback']['liked']=='Gardens'
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM post_trip_feedback WHERE trip_id=?',(c_trip['trip_id'],)).fetchone()[0]==0
    history=client.get('/api/profile/history')
    assert history.status_code==200,history.text
    assert not any(row.get('trip_id')==c_trip['trip_id'] for row in history.json()['entries'])
    call(client,c_trip,'/post-feedback',feedback())
    assert any(row.get('trip_id')==c_trip['trip_id'] for row in client.get('/api/profile/history').json()['entries'])


def test_c_migration_preserves_unpublished_feedback(client,c_trip):
    from app.db_migrations_c import migrate_c
    finish(client,c_trip)
    with get_connection() as conn:
        conn.execute('INSERT INTO post_trip_feedback(trip_id,user_id,notes) VALUES(?,?,?)',
                     (c_trip['trip_id'],c_trip['user_id'],'Preserve my unfinished answer'))
    migrate_c();migrate_c()
    assert snapshot(client,c_trip)['post_feedback']['notes']=='Preserve my unfinished answer'
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM post_trip_feedback WHERE trip_id=?',(c_trip['trip_id'],)).fetchone()[0]==0


def test_c_lost_delivery_response_publishes_once_on_reload(client,c_trip,monkeypatch):
    finish(client,c_trip)
    original=live.c_call_existing
    async def delivered_then_disconnected(*args,**kwargs):
        await original(*args,**kwargs)
        raise RuntimeError('response disconnected after commit')
    monkeypatch.setattr(live,'c_call_existing',delivered_then_disconnected)
    call(client,c_trip,'/post-feedback',feedback(),expected=503)
    assert snapshot(client,c_trip)['closed_out']
    call(client,c_trip,'/post-feedback',feedback())
    with get_connection() as conn:
        for table in ('post_trip_feedback','live_postrip','core_trip_feedback'):
            assert conn.execute(f'SELECT COUNT(*) FROM {table} WHERE trip_id=?',(c_trip['trip_id'],)).fetchone()[0]==1


@pytest.mark.parametrize('operation',['swap','remove'])
def test_c_lost_adjustment_response_resumes_committed_change(client,c_trip,monkeypatch,operation):
    start(client,c_trip);end_review(client,c_trip,'change')
    body={'target_activity_id':'c-food','operation':operation}
    if operation=='swap':
        suggestions=client.get(f"/api/trips/{c_trip['trip_id']}/suggestions?user_id={c_trip['user_id']}").json()
        body['replacement_activity_id']=suggestions['alternatives'][0]['id']
    preview=call(client,c_trip,'/adjustments/preview',body)['preview']
    original=live.c_call_existing
    async def committed_then_disconnected(*args,**kwargs):
        await original(*args,**kwargs)
        raise RuntimeError('response disconnected after commit')
    downstream=AsyncMock(side_effect=committed_then_disconnected)
    monkeypatch.setattr(live,'c_call_existing',downstream)
    result=call(client,c_trip,'/adjustments/confirm',{'token':preview['token']})
    assert result['preview'] is None and result['pending_decision'] is None
    assert result['runtime']['operation_in_flight']==0
    assert result['runtime']['last_confirmation_token']==preview['token']
    if operation=='swap':
        assert result['current_activity']['catalogue_activity_id']==body['replacement_activity_id']
    else:
        assert result['current_activity'] is None and result['phase']=='awaiting_day_end'
    assert snapshot(client,c_trip)==result
    call(client,c_trip,'/adjustments/confirm',{'token':preview['token']})
    assert downstream.await_count==1
