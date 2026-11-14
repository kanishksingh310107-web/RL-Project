"""Atomic planning previews, reusing existing mutation endpoints in isolation."""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, StrictInt

from app.database import CONNECTION_OVERRIDE, get_connection
from app.modules.live import c_call_existing
from app.modules.trip_actions import _require_trip_owner, CustomActivityCreate

router = APIRouter()


def error(status, message, code='INVALID_INPUT', field=None):
    raise HTTPException(status, {'detail':message,'code':code,'field':field})


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: Literal['swap','remove','reschedule','move_day','reorder','pin','must_visit','set_priority','add_custom','budget_allocation']
    target_activity_id: Optional[str] = Field(None,min_length=1,max_length=100)
    replacement_activity_id: Optional[str] = Field(None,min_length=1,max_length=100)
    before_activity_id: Optional[str] = Field(None,min_length=1,max_length=100)
    direction: Literal['earlier','later'] = 'later'
    target_day: Optional[int] = Field(None,ge=1,le=90,strict=True)
    activity: Optional[dict] = None
    budget_total_inr: Optional[StrictInt] = Field(None,ge=0,le=1_000_000_000)
    budget_allocations: Optional[dict[str,dict]] = None
    planning_priority: Optional[Literal['must_do','nice_to_do','avoid']] = None


class Token(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=1,max_length=100)


class AtomicConnection:
    """Inner endpoint commits stay inside the outer confirmation transaction."""
    def __init__(self, conn): self.conn = conn
    def __getattr__(self, name): return getattr(self.conn,name)
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def commit(self): pass
    def rollback(self): pass


def state(conn, trip_id):
    itinerary=conn.execute('SELECT id FROM itineraries WHERE trip_id=?',(trip_id,)).fetchone()
    if not itinerary: error(404,'Generate an itinerary first.','ITINERARY_NOT_FOUND')
    rows=[dict(r) for r in conn.execute('SELECT * FROM itinerary_activities WHERE itinerary_id=? ORDER BY day_number,order_index,id',(itinerary['id'],))]
    trip=dict(conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone())
    prefs=conn.execute('SELECT * FROM trip_schedule_prefs WHERE trip_id=?',(trip_id,)).fetchone()
    budget=conn.execute('SELECT * FROM trip_budget_allocations WHERE trip_id=?',(trip_id,)).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trip_budget_allocations'").fetchone() else None
    fingerprint=hashlib.sha256(json.dumps([trip,dict(prefs) if prefs else None,rows,dict(budget) if budget else None],sort_keys=True,default=str).encode()).hexdigest()
    return itinerary['id'], rows, fingerprint


def budget_state(conn, trip_id):
    trip = conn.execute('SELECT total_budget FROM trips WHERE id=?',(trip_id,)).fetchone()
    row = conn.execute('SELECT * FROM trip_budget_allocations WHERE trip_id=?',(trip_id,)).fetchone()
    return {'trip_total_budget':trip['total_budget'] if trip else None,
            'allocation':dict(row) if row else None}


def require_draft(conn,trip_id):
    runtime=conn.execute('SELECT status FROM trip_runtime WHERE trip_id=?',(trip_id,)).fetchone()
    if runtime and runtime['status']!='draft': error(409,'Only draft itineraries can be edited.','ITINERARY_LOCKED')


async def apply(request,trip_id,actor,payload):
    with get_connection() as conn:
        itinerary,rows,_=state(conn,trip_id)
        target=next((r for r in rows if r['id']==payload.target_activity_id),None)
        requires_target=payload.operation not in ('add_custom','budget_allocation')
        if requires_target and not target: error(404,'Activity occurrence not found.','ACTIVITY_NOT_FOUND')
        if target and (target['is_fixed_booking'] or target['is_pinned']) and payload.operation not in ('pin','must_visit'):
            error(409,'Unpin this activity before moving or replacing it.','PINNED_ACTIVITY')
        if payload.target_day and payload.target_day>conn.execute('SELECT duration_days FROM trips WHERE id=?',(trip_id,)).fetchone()[0]:
            error(404,'Trip day not found.','DAY_NOT_FOUND')
        base=f'/api/trip-actions/{trip_id}'
        if payload.operation=='budget_allocation':
            if payload.budget_total_inr is None or payload.budget_allocations is None:
                error(422,'A proposed total and category allocations are required.','INVALID_BUDGET','budget_allocations')
            allowed={'accommodation','food','intercity_travel','local_transport','activities','shopping','emergency_reserve','other'}
            if set(payload.budget_allocations)-allowed:
                error(422,'Unknown planned budget category.','INVALID_BUDGET','budget_allocations')
            allocations={}
            for key,line in payload.budget_allocations.items():
                if set(line)-{'planned_inr','basis','unit_amount_inr','people','days','rooms','nights'}:
                    error(422,'Unsupported allocation fields.','INVALID_BUDGET','budget_allocations')
                amount=line.get('planned_inr')
                if isinstance(amount,bool) or not isinstance(amount,int) or amount<0:
                    error(422,'Allocation amounts must be whole non-negative INR values.','INVALID_BUDGET','budget_allocations')
                allocations[key]=line
            reserved=allocations.get('emergency_reserve',{}).get('planned_inr',0)
            normal=sum(line['planned_inr'] for key,line in allocations.items() if key!='emergency_reserve')
            if normal+reserved>payload.budget_total_inr:
                error(422,'Allocations exceed the proposed total budget.','BUDGET_ALLOCATION_EXCEEDS_TOTAL','budget_total_inr')
            conn.execute('''INSERT INTO trip_budget_allocations(trip_id,user_id,total_budget_inr,allocations_json,updated_at)
                VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(trip_id) DO UPDATE SET user_id=excluded.user_id,
                total_budget_inr=excluded.total_budget_inr,allocations_json=excluded.allocations_json,updated_at=CURRENT_TIMESTAMP''',
                (trip_id,actor,payload.budget_total_inr,json.dumps(allocations)))
            conn.execute('UPDATE trips SET total_budget=? WHERE id=? AND user_id=?',(payload.budget_total_inr,trip_id,actor))
        elif payload.operation=='add_custom':
            a=payload.activity or {}
            custom=CustomActivityCreate(user_id=actor,title=a.get('title',''),day_number=payload.target_day or 1,
                location_name=a.get('location'),duration_minutes=a.get('duration_minutes'),cost_estimate_inr=a.get('cost',0))
            await c_call_existing(request,'POST',base+'/activities',custom.model_dump())
        elif payload.operation=='swap':
            if not payload.replacement_activity_id:error(422,'Choose an alternative.','INVALID_INPUT','replacement_activity_id')
            await c_call_existing(request,'POST',base+f"/activity/{target['id']}/swap",{'user_id':actor,'occurrence_id':target['id'],'replacement_activity_id':payload.replacement_activity_id,'is_trip_specific':True})
        elif payload.operation=='remove':
            await c_call_existing(request,'DELETE',base+f"/activity/{target['id']}?user_id={actor}")
        elif payload.operation in ('reschedule','move_day'):
            await c_call_existing(request,'POST',base+f"/activity/{target['id']}/reschedule",{'user_id':actor,'occurrence_id':target['id'],'direction':payload.direction,'target_day':payload.target_day})
        elif payload.operation=='reorder':
            before=next((r for r in rows if r['id']==payload.before_activity_id),None)
            if not before:error(404,'The destination activity was not found.','ACTIVITY_NOT_FOUND')
            if before['day_number']!=target['day_number']:error(422,'Use Move day to change days.','INVALID_INPUT','before_activity_id')
            ordered=[r['id'] for r in rows if r['day_number']==target['day_number'] and r['id']!=target['id']]
            ordered.insert(ordered.index(before['id']),target['id'])
            for index,identifier in enumerate(ordered):conn.execute('UPDATE itinerary_activities SET order_index=? WHERE id=?',(index,identifier))
        elif payload.operation=='set_priority':
            if payload.planning_priority not in ('must_do','nice_to_do','avoid'):
                error(422,'Choose must_do, nice_to_do, or avoid.','INVALID_PRIORITY','planning_priority')
            conn.execute('UPDATE itinerary_activities SET planning_priority=? WHERE id=?',(payload.planning_priority,target['id']))
        else:
            column='is_pinned' if payload.operation=='pin' else 'must_visit'
            if target['is_fixed_booking'] and column=='is_pinned':error(409,'Fixed bookings stay pinned.','FIXED_BOOKING')
            conn.execute(f'UPDATE itinerary_activities SET {column}=? WHERE id=?',(not target[column],target['id']))
        if payload.operation!='budget_allocation':
            from app.services.timed_itinerary import regenerate_timed_itinerary_for_trip
            regenerate_timed_itinerary_for_trip(conn,trip_id,actor)


@router.get('/api/trip-experience/capabilities')
def capabilities():
    from app.recommendation_budget import experience_capabilities
    return dict(experience_capabilities(), schedule_preferences_v2=True,explicit_trip_type=True,occurrence_acceptance=True,
                itinerary_preview=True,custom_activities=True,expenses=True,readonly_sharing=True,live_adjustments=True)


@router.post('/api/trip-actions/{trip_id}/preview')
async def preview(trip_id: str,payload: Preview,request: Request):
    _,actor=_require_trip_owner(request,trip_id)
    with get_connection() as conn:
        require_draft(conn,trip_id)
        _,before,fingerprint=state(conn,trip_id)
        clone=sqlite3.connect(':memory:',check_same_thread=False);clone.row_factory=sqlite3.Row
        conn.backup(clone)
    override=CONNECTION_OVERRIDE.set(AtomicConnection(clone))
    try:
        await apply(request,trip_id,actor,payload)
        view=await c_call_existing(request,'GET',f'/api/trip-actions/{trip_id}/timed-view?user_id={actor}')
        _,after,_=state(clone,trip_id)
    except ValidationError as exc:
        error(422,exc.errors()[0]['msg'].removeprefix('Value error, '),'INVALID_INPUT','activity')
    except HTTPException:
        raise
    except Exception:
        error(503,'The itinerary preview could not be prepared. Your saved trip is unchanged; please retry.','PREVIEW_UNAVAILABLE')
    finally:
        CONNECTION_OVERRIDE.reset(override);clone.close()
    token=uuid.uuid4().hex
    difference=sum(r['cost_estimate'] or 0 for r in after if r['status']!='rejected')-sum(r['cost_estimate'] or 0 for r in before if r['status']!='rejected')
    result={'token':token,'summary':payload.operation.replace('_',' ').capitalize()+' upcoming activity',
            'budget_impact':f'Activity cost change: INR {difference:,.0f}',
            'timeline':[dict(b,day_number=d['day_number']) for d in view['days'] for b in d['timeline']],
            'warnings':[d['note'] for d in view['days'] if d.get('note')]}
    if payload.operation=='budget_allocation':
        result.update(summary='Change the trip budget allocation',budget_total_inr=payload.budget_total_inr,
            budget_allocations=payload.budget_allocations,budget_impact='Updates the budget plan only; no payments or bookings are made.')
    with get_connection() as conn:
        require_draft(conn,trip_id)
        if state(conn,trip_id)[2]!=fingerprint:error(409,'The itinerary changed. Request another preview.','STALE_PREVIEW')
        conn.execute('INSERT INTO trip_edit_previews VALUES(?,?,?,?,?,?,NULL)',(token,trip_id,actor,fingerprint,payload.model_dump_json(),json.dumps(result)))
    return {'preview':result}


@router.post('/api/trip-actions/{trip_id}/confirm')
async def confirm(trip_id: str,payload: Token,request: Request):
    _,actor=_require_trip_owner(request,trip_id)
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE');require_draft(conn,trip_id)
        row=conn.execute('SELECT * FROM trip_edit_previews WHERE token=? AND trip_id=? AND user_id=?',(payload.token,trip_id,actor)).fetchone()
        if not row:error(404,'Preview not found.','PREVIEW_NOT_FOUND')
        if row['confirmed_at']:return {'status':'confirmed','token':payload.token}
        _,before,fingerprint=state(conn,trip_id)
        before_feedback=[r[0] for r in conn.execute('SELECT id FROM rl_feedback_log WHERE trip_id=? AND user_id=?',(trip_id,actor))]
        before_budget=budget_state(conn,trip_id)
        if fingerprint!=row['fingerprint']:error(409,'The itinerary changed. Request another preview.','STALE_PREVIEW')
        override=CONNECTION_OVERRIDE.set(AtomicConnection(conn))
        try:
            await apply(request,trip_id,actor,Preview.model_validate_json(row['payload_json']))
            _,after,_=state(conn,trip_id)
        except HTTPException:
            raise
        except Exception:
            error(503,'The itinerary change could not be saved. Your previous trip is kept; please retry.','CONFIRM_UNAVAILABLE')
        finally:CONNECTION_OVERRIDE.reset(override)
        after_feedback=[r[0] for r in conn.execute('SELECT id FROM rl_feedback_log WHERE trip_id=? AND user_id=?',(trip_id,actor))]
        after_budget=budget_state(conn,trip_id)
        conn.execute('INSERT INTO trip_edit_history(id,trip_id,user_id,before_json,after_json) VALUES(?,?,?,?,?)',
                     (payload.token,trip_id,actor,json.dumps({'activities':before,'feedback_ids':before_feedback,'budget':before_budget}),json.dumps({'activities':after,'feedback_ids':after_feedback,'budget':after_budget})))
        conn.execute('UPDATE trip_edit_previews SET confirmed_at=? WHERE token=?',(datetime.now(timezone.utc).isoformat(),payload.token))
    return {'status':'confirmed','token':payload.token}


@router.post('/api/trip-actions/{trip_id}/undo')
def undo(trip_id: str,payload: Token,request: Request):
    _,actor=_require_trip_owner(request,trip_id)
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE');require_draft(conn,trip_id)
        row=conn.execute('SELECT * FROM trip_edit_history WHERE trip_id=? AND user_id=? AND undone_at IS NULL ORDER BY created_at DESC,rowid DESC LIMIT 1',(trip_id,actor)).fetchone()
        if not row or row['id']!=payload.token:error(409,'Only the latest change can be undone.','STALE_UNDO')
        after_doc=json.loads(row['after_json'])
        after=after_doc.get('activities')
        current_budget=budget_state(conn,trip_id)
        if after is None or state(conn,trip_id)[1]!=after or current_budget!=after_doc.get('budget'):
            error(409,'The itinerary or budget changed after this edit.','STALE_UNDO')
        before=json.loads(row['before_json'])['activities']
        itinerary=state(conn,trip_id)[0]
        conn.execute('DELETE FROM itinerary_activities WHERE itinerary_id=?',(itinerary,))
        for activity in before:
            keys=list(activity)
            conn.execute('INSERT INTO itinerary_activities('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',tuple(activity[k] for k in keys))
        before_budget=json.loads(row['before_json']).get('budget') or {}
        before_allocation=before_budget.get('allocation')
        if before_allocation:
            conn.execute('''INSERT INTO trip_budget_allocations(trip_id,user_id,total_budget_inr,allocations_json,updated_at)
                VALUES(?,?,?,?,?) ON CONFLICT(trip_id) DO UPDATE SET user_id=excluded.user_id,total_budget_inr=excluded.total_budget_inr,
                allocations_json=excluded.allocations_json,updated_at=excluded.updated_at''',
                (trip_id,actor,before_allocation['total_budget_inr'],before_allocation['allocations_json'],before_allocation['updated_at']))
        else:
            conn.execute('DELETE FROM trip_budget_allocations WHERE trip_id=?',(trip_id,))
        if before_budget.get('trip_total_budget') is not None:
            conn.execute('UPDATE trips SET total_budget=? WHERE id=?',(before_budget['trip_total_budget'],trip_id))
        added_feedback=set(json.loads(row['after_json']).get('feedback_ids',[]))-set(json.loads(row['before_json']).get('feedback_ids',[]))
        for identifier in added_feedback:
            conn.execute('DELETE FROM rl_feedback_log WHERE id=? AND trip_id=? AND user_id=?',(identifier,trip_id,actor))
        override=CONNECTION_OVERRIDE.set(AtomicConnection(conn))
        try:
            from app.services.timed_itinerary import regenerate_timed_itinerary_for_trip
            regenerate_timed_itinerary_for_trip(AtomicConnection(conn),trip_id,actor)
        finally:CONNECTION_OVERRIDE.reset(override)
        conn.execute('UPDATE trip_edit_history SET undone_at=? WHERE id=?',(datetime.now(timezone.utc).isoformat(),row['id']))
    return {'status':'undone'}


class Acceptance(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['accept','reject','accept_all']
    itinerary_activity_id: Optional[str] = Field(None,min_length=1,max_length=100)
    occurrence_ids: list[str] = Field(default_factory=list,max_length=2000)


@router.post('/api/trip-actions/{trip_id}/acceptance')
async def acceptance(trip_id: str,payload: Acceptance,request: Request):
    _,actor=_require_trip_owner(request,trip_id)
    with get_connection() as conn:
        require_draft(conn,trip_id)
        itinerary,rows,_=state(conn,trip_id)
        target=next((r for r in rows if r['id']==payload.itinerary_activity_id),None)
    if payload.action=='accept_all':
        if set(payload.occurrence_ids)-{r['id'] for r in rows}:error(404,'Activity occurrence not found.','ACTIVITY_NOT_FOUND')
        return await c_call_existing(request,'POST',f'/api/itinerary/{itinerary}/accept-all?user_id={actor}',{'itinerary_id':itinerary})
    if not target:error(404,'Activity occurrence not found.','ACTIVITY_NOT_FOUND')
    return await c_call_existing(request,'POST',f'/api/itinerary/feedback/{actor}',{
        'itinerary_id':itinerary,'activity_id':target['activity_id'],'occurrence_id':target['id'],
        'action_type':payload.action,'is_trip_specific':True})


@router.get('/api/trip-actions/{trip_id}/occurrences/{occurrence_id}/alternatives')
async def alternatives(trip_id: str,occurrence_id: str,request: Request):
    _,actor=_require_trip_owner(request,trip_id)
    with get_connection() as conn:
        itinerary,rows,_=state(conn,trip_id)
        target=next((r for r in rows if r['id']==occurrence_id),None)
        if not target:error(404,'Activity occurrence not found.','ACTIVITY_NOT_FOUND')
    return await c_call_existing(request,'GET',f"/api/itinerary/alternatives/{itinerary}/{target['activity_id']}?user_id={actor}")
