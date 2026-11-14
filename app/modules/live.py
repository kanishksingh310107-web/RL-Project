"""During-trip support and post-trip learning module (Person B).
Completes the lifecycle: pre-trip -> during -> post-trip -> learning.
"""
import json
import sqlite3
import numpy as np
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database import get_connection
from app.modules.common import get_trip, get_user_context, get_itinerary
from app.itinerary_generator import get_slot_alternatives
from app.rl_planner import (
    process_activity_feedback,
    extract_context_vector,
    is_activity_safe_and_valid,
    load_user_policy,
    save_user_policy,
    CANONICAL_ARMS
)

MODULE = {
    "id": "live",
    "title": "During & Post Trip",
    "icon": "fa-location-dot",
    "owner": "B"
}

router = APIRouter(prefix="/api/live", tags=["live"])

VALID_STATUSES = {"upcoming", "in_progress", "completed", "skipped", "delayed"}
VALID_CONDITIONS = {
    "heavy_rain",
    "extreme_heat",
    "closure",
    "traffic_delay",
    "strike",
    "fatigue",
    "unexpected_crowding"
}
MAX_ALERTS_PER_DAY = 3

# Person C: canonical runtime API. The original /api/live interfaces below are
# retained for existing clients; runtime-enrolled trips use the guarded flow.
import hashlib
import html
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timezone
from typing import Literal, Annotated
import httpx
from fastapi import Body, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ConfigDict, StrictInt, StrictStr, ValidationError, field_validator, model_validator
from starlette.middleware.base import BaseHTTPMiddleware

C_RATING_KEYS = {'scenery','food','safety','value_for_money','crowds','accessibility','stay_quality','overall'}
C_MUTATION_CAPABILITY = ContextVar('c_runtime_mutation', default=None)
CScore = Annotated[StrictInt, Field(ge=1, le=5)]


def c_error(status_code, message, code='STATE_CONFLICT', field=None):
    raise HTTPException(status_code, detail={'detail':message,'code':code,'field':field})


def c_error_response(exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {
        'detail':str(exc.detail),'code':'REQUEST_ERROR','field':None}
    return JSONResponse(detail,status_code=exc.status_code)


class CRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def guarded(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                item = exc.errors()[0]
                field = '.'.join(str(v) for v in item['loc'] if v not in ('body','query','path')) or None
                if field is None:
                    message=item['msg'].lower()
                    field=next((key for key in ('trip_type','would_revisit','liked','disliked','replacement_activity_id') if key in message),None)
                    if field is None and ('rate ' in message or 'rating' in message): field='ratings'
                return JSONResponse({'detail':item['msg'].removeprefix('Value error, '),
                    'code':'INVALID_INPUT','field':field},status_code=422)
            except HTTPException as exc:
                return c_error_response(exc)
            except sqlite3.Error:
                return JSONResponse({'detail':'The trip could not be saved. Please retry; your entries have been kept.',
                    'code':'DATABASE_UNAVAILABLE','field':None},status_code=503)
        return guarded


runtime_router = APIRouter(prefix='/api/trips',tags=['C runtime'],route_class=CRoute)


class CActor(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: Optional[StrictStr] = Field(None,min_length=1,max_length=100)

    @field_validator('user_id',mode='before')
    @classmethod
    def clean_identity(cls,value):
        return value.strip() if isinstance(value,str) else value

    @field_validator('*',mode='before')
    @classmethod
    def clean_identifiers(cls,value,info):
        if info.field_name in ('target_activity_id','replacement_activity_id','token') and isinstance(value,str):
            return value.strip()
        return value


def c_clean_text(value):
    if not isinstance(value,str):
        return value
    # Plain text storage and escaped rendering; SQL always uses bound parameters.
    value = re.sub(r'<[^>]*>','',html.unescape(value))
    return ''.join(c for c in value if c in '\n\t' or ord(c)>=32).strip()


class CReview(CActor):
    ratings: Dict[str,CScore]
    action: Literal['keep','enhance','change']
    notes: StrictStr = Field('',max_length=1000)

    @field_validator('notes',mode='before')
    @classmethod
    def clean_note(cls,value):
        return c_clean_text(value)

    @field_validator('ratings')
    @classmethod
    def valid_keys(cls,value):
        if set(value)-C_RATING_KEYS:
            raise ValueError('Use only the shared rating keys: '+', '.join(sorted(C_RATING_KEYS)))
        return value


class CEndActivity(CActor):
    outcome: Literal['completed','early_ended','skipped','not_done'] = 'completed'


class CEndDay(CActor):
    dispositions: Dict[str,Literal['skipped','not_done']] = Field(default_factory=dict)


class CPreview(CActor):
    target_activity_id: StrictStr = Field(min_length=1,max_length=200)
    operation: Literal['swap','remove']
    replacement_activity_id: Optional[StrictStr] = Field(None,min_length=1,max_length=200)

    @model_validator(mode='after')
    def replacement_required(self):
        if self.operation=='swap' and not self.replacement_activity_id:
            raise ValueError('Select a replacement activity before previewing a swap.')
        if self.operation=='remove' and self.replacement_activity_id is not None:
            raise ValueError('A remove operation cannot contain a replacement.')
        return self


class CConfirm(CActor):
    token: StrictStr = Field(min_length=1,max_length=100)


class CPlaceRating(BaseModel):
    model_config = ConfigDict(extra='forbid')
    activity_id: StrictStr = Field(min_length=1,max_length=200)
    ratings: Dict[str,CScore]

    @field_validator('activity_id',mode='before')
    @classmethod
    def clean_id(cls,value):
        return value.strip() if isinstance(value,str) else value

    @field_validator('ratings')
    @classmethod
    def valid_keys(cls,value):
        if not value or set(value)-C_RATING_KEYS:
            raise ValueError('Per-place ratings must use shared parameter keys.')
        return value


class CPostFeedback(CActor):
    draft: bool = Field(False,strict=True)
    ratings: Dict[str,CScore] = Field(default_factory=dict)
    trip_type: Optional[Literal['solo','couple','friends','family']] = None
    would_revisit: Optional[Literal['yes','no','maybe']] = None
    liked: Optional[StrictStr] = Field(None,max_length=2000)
    disliked: Optional[StrictStr] = Field(None,max_length=2000)
    notes: StrictStr = Field('',max_length=2000)
    per_place_ratings: List[CPlaceRating] = Field(default_factory=list,max_length=200)

    @field_validator('trip_type','would_revisit',mode='before')
    @classmethod
    def clean_enum(cls,value):
        return value.strip().lower() if isinstance(value,str) else value

    @field_validator('liked','disliked','notes',mode='before')
    @classmethod
    def clean_text(cls,value):
        return c_clean_text(value)

    @model_validator(mode='after')
    def valid_submission(self):
        if set(self.ratings)-C_RATING_KEYS:
            raise ValueError('Ratings contain an unknown shared parameter.')
        if not self.draft:
            if set(self.ratings)!=C_RATING_KEYS:
                raise ValueError('Rate overall and every shared trip parameter before submitting.')
            for key in ('would_revisit','liked','disliked'):
                if not getattr(self,key):
                    raise ValueError(f'{key} is required before submitting. Save a draft to resume later.')
        ids = [row.activity_id for row in self.per_place_ratings]
        if len(ids)!=len(set(ids)):
            raise ValueError('Provide only one review per itinerary occurrence.')
        return self


def c_actor(request,payload=None):
    values = request.query_params.getlist('user_id')
    if len(values)>1:
        c_error(422,'Provide one user_id.','INVALID_INPUT','user_id')
    query = values[0].strip() if values else None
    body = payload.user_id if payload else None
    if query and body and query!=body:
        c_error(422,'The user_id in the query and body must match.','INVALID_INPUT','user_id')
    actor = body or query
    if not actor or len(actor)>100:
        c_error(422,'A non-empty user_id is required.','INVALID_INPUT','user_id')
    authorization = request.headers.get('authorization', '')
    if not authorization.startswith('Bearer '):
        c_error(403,'Sign in to continue.','AUTH_REQUIRED')
    with get_connection() as conn:
        session = conn.execute('SELECT user_id FROM auth_sessions WHERE token_hash=? AND expires_at>?',
            (hashlib.sha256(authorization[7:].strip().encode()).hexdigest(), c_now())).fetchone()
    if not session:
        c_error(403,'Your session has expired. Please sign in again.','SESSION_EXPIRED')
    if session['user_id'] != actor:
        c_error(403,'This trip belongs to another user.','NOT_OWNER')
    return actor


def c_publish_feedback(conn, draft, submitted_at):
    fields = ('trip_id','user_id','ratings_json','trip_type','would_revisit','liked','disliked','notes',
              'per_place_ratings_json','delivery_started_at')
    conn.execute('INSERT OR IGNORE INTO post_trip_feedback(' + ','.join(fields) + ',submitted_at) VALUES(' +
                 ','.join('?' for _ in range(len(fields)+1)) + ')',
                 tuple(draft.get(key) for key in fields)+(submitted_at,))
    conn.execute('UPDATE trip_runtime SET post_feedback_draft_json=NULL WHERE trip_id=?',(draft['trip_id'],))


@contextmanager
def c_transaction(trip_id,actor):
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        trip = conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone()
        if not trip:
            c_error(404,'Trip not found.','TRIP_NOT_FOUND')
        if trip['user_id']!=actor:
            c_error(403,'This trip belongs to another user.','NOT_OWNER')
        conn.execute('INSERT OR IGNORE INTO trip_runtime(trip_id) VALUES(?)',(trip_id,))
        runtime=c_runtime(conn,trip_id)
        if runtime['operation_in_flight'] and runtime['operation_started_at']:
            started=datetime.fromisoformat(runtime['operation_started_at'])
            if (datetime.now(timezone.utc)-started).total_seconds()>60:
                # Recover a request interrupted by a process restart. Any old
                # preview is revalidated against the current itinerary on retry.
                conn.execute('UPDATE trip_runtime SET operation_in_flight=0,operation_started_at=NULL WHERE trip_id=?',(trip_id,))
        runtime=c_runtime(conn,trip_id)
        if runtime['status']=='live' and not runtime['operation_in_flight'] and runtime['preview_json']:
            preview=json.loads(runtime['preview_json'])
            if preview.get('confirmed') and c_adjustment_applied(conn,trip_id,preview):
                c_log_adjustment(conn,trip_id,preview)
                c_finish_adjustment(conn,trip_id,preview['token'])
        if runtime['status']=='completed' and not runtime['operation_in_flight']:
            saved=conn.execute('SELECT submitted_at,delivery_started_at FROM post_trip_feedback WHERE trip_id=?',(trip_id,)).fetchone()
            if saved and saved['delivery_started_at'] and not saved['submitted_at']:
                delivered=conn.execute('SELECT submitted_at FROM live_postrip WHERE trip_id=?',(trip_id,)).fetchone()
                if delivered:
                    # Learning committed immediately before a connection/process
                    # failure: reconcile completion, never send the ratings twice.
                    conn.execute('UPDATE post_trip_feedback SET submitted_at=? WHERE trip_id=?',(delivered['submitted_at'],trip_id))
            draft=json.loads(runtime['post_feedback_draft_json']) if runtime['post_feedback_draft_json'] else None
            if draft and draft.get('delivery_started_at'):
                delivered=conn.execute('SELECT submitted_at FROM live_postrip WHERE trip_id=?',(trip_id,)).fetchone()
                if delivered:
                    c_publish_feedback(conn,draft,delivered['submitted_at'])
        yield conn,dict(trip)


def c_runtime(conn,trip_id):
    return dict(conn.execute('SELECT * FROM trip_runtime WHERE trip_id=?',(trip_id,)).fetchone())


def c_schedule(conn,trip_id):
    rows = [dict(row) for row in conn.execute('''SELECT ia.* FROM itinerary_activities ia
        JOIN itineraries i ON i.id=ia.itinerary_id WHERE i.trip_id=? AND ia.status!='rejected'
        ORDER BY ia.day_number,ia.order_index,ia.id''',(trip_id,))]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trip_schedule_prefs'").fetchone():
        custom = conn.execute('SELECT 1 FROM trip_schedule_prefs WHERE trip_id=?',(trip_id,)).fetchone()
        timed = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='timed_itineraries'").fetchone()
        if custom and timed and conn.execute('SELECT 1 FROM timed_itineraries WHERE trip_id=?',(trip_id,)).fetchone():
            scheduled = {(r[0],r[1]) for r in conn.execute("SELECT day_number,activity_id FROM timed_itinerary_slots WHERE trip_id=? AND slot_type IN ('activity','shopping')",(trip_id,))}
            # Historical runs survive later changes to the remaining schedule.
            rows = [row for row in rows if (row['day_number'],row['activity_id']) in scheduled or
                    row.get('is_pinned') or row.get('is_fixed_booking') or c_run(conn,trip_id,row['id'])]
    return rows


def c_slot(conn,trip_id,activity_id):
    schedule = c_schedule(conn,trip_id)
    exact = next((s for s in schedule if s['id']==activity_id),None)
    if exact:
        return exact
    matches = [s for s in schedule if s['activity_id']==activity_id]
    if len(matches)==1:
        return matches[0]
    if matches:
        c_error(422,'This place occurs more than once. Use its itinerary occurrence ID.','AMBIGUOUS_ACTIVITY','activity_id')
    c_error(404,'Activity not found in this trip.','ACTIVITY_NOT_FOUND','activity_id')


def c_applicable(slot):
    keys = {'overall','safety','value_for_money','crowds','accessibility'}
    category = slot.get('category','')
    if category=='food_dining': keys.add('food')
    elif category in ('stay','accommodation'): keys.add('stay_quality')
    else: keys.add('scenery')
    return sorted(keys)


def c_run(conn,trip_id,slot_id):
    row = conn.execute('SELECT * FROM activity_runs WHERE trip_id=? AND itinerary_activity_id=?',(trip_id,slot_id)).fetchone()
    return dict(row) if row else None


def c_now():
    return datetime.now(timezone.utc).isoformat()


def c_require_live(runtime):
    if runtime['status']!='live':
        c_error(409,'This action requires a live trip. Finalize and start it first.','NOT_LIVE')
    if runtime['operation_in_flight']:
        c_error(409,'An itinerary update is already in progress. Please wait.','UPDATE_IN_PROGRESS')


class CDisruption(CActor):
    condition_type: Literal['heavy_rain','extreme_heat','closure','traffic_delay','strike','fatigue','unexpected_crowding']
    day_number: Annotated[StrictInt,Field(ge=1)]
    severity: Literal['low','moderate','high'] = 'moderate'
    description: Optional[StrictStr] = Field(None,max_length=1000)
    target_activity_id: Optional[StrictStr] = Field(None,min_length=1,max_length=200)

    @field_validator('description',mode='before')
    @classmethod
    def clean_description(cls,value): return c_clean_text(value)


def c_start_slot(conn,trip_id,slot):
    if c_run(conn,trip_id,slot['id']):
        c_error(409,'This activity has already been started or marked not done.','ALREADY_STARTED')
    stamp = c_now()
    trip=dict(conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone())
    context=get_user_context(trip['user_id'])
    profile=dict(context.get('basic') or {},**(context.get('detailed') or {}))
    vector=extract_context_vector(profile,trip,slot['day_number'],trip['duration_days'],slot['time_slot'],
        dict(slot,cost_amount=slot.get('cost_estimate') or 0)).tolist()
    conn.execute('''INSERT INTO activity_runs(id,trip_id,activity_id,itinerary_activity_id,day_number,started_at,context_json)
        VALUES(?,?,?,?,?,?,?)''',(str(uuid.uuid4()),trip_id,slot['activity_id'],slot['id'],slot['day_number'],stamp,json.dumps(vector)))
    conn.execute('UPDATE trip_runtime SET current_activity_id=?,version=version+1 WHERE trip_id=?',(slot['id'],trip_id))


def c_pending_review(conn,trip_id):
    row = conn.execute('SELECT * FROM activity_runs WHERE trip_id=? AND ended_at IS NOT NULL AND action IS NULL ORDER BY ended_at LIMIT 1',(trip_id,)).fetchone()
    return dict(row) if row else None


def c_advance(conn,trip_id):
    runtime = c_runtime(conn,trip_id)
    if runtime['day_ended'] or runtime['current_activity_id'] or c_pending_review(conn,trip_id):
        return
    slots = [s for s in c_schedule(conn,trip_id) if s['day_number']==runtime['current_day'] and not c_run(conn,trip_id,s['id'])]
    if slots:
        c_start_slot(conn,trip_id,slots[0])


def c_fingerprint(conn,trip_id):
    return hashlib.sha256(json.dumps([(s['id'],s['activity_id'],s['day_number'],s['order_index']) for s in c_schedule(conn,trip_id)]).encode()).hexdigest()


def c_adjustment_applied(conn,trip_id,preview):
    schedule=[dict(r) for r in conn.execute('''SELECT ia.* FROM itinerary_activities ia
        JOIN itineraries i ON i.id=ia.itinerary_id WHERE i.trip_id=? AND ia.status!='rejected' ''',(trip_id,))]
    if preview['operation']=='remove':
        target=conn.execute('SELECT status FROM itinerary_activities WHERE id=?',(preview['target_activity_id'],)).fetchone()
        return target is None or target['status']=='rejected'
    return any(s['id']==preview['target_activity_id'] and s['activity_id']==preview['replacement_activity_id'] for s in schedule)


def c_log_adjustment(conn,trip_id,preview):
    before = preview.get('before_activity') or {}
    after = conn.execute('SELECT * FROM itinerary_activities WHERE id=?',(preview['target_activity_id'],)).fetchone()
    after = dict(after) if after and after['status']!='rejected' else None
    conn.execute('''INSERT OR IGNORE INTO trip_edit_history(id,trip_id,user_id,before_json,after_json)
        VALUES(?,?,?,?,?)''',(preview['token'],trip_id,preview['user_id'],
        json.dumps({'operation':preview['operation'],'occurrence_id':preview['target_activity_id'],'activity':before}),
        json.dumps({'activity':after,'cost_delta_inr':preview.get('cost_delta_inr',0),
                    'duration_delta_minutes':preview.get('duration_delta_minutes',0)})))


def c_finish_adjustment(conn,trip_id,token):
    conn.execute('''UPDATE trip_runtime SET operation_in_flight=0,operation_started_at=NULL,pending_decision_json=NULL,preview_json=NULL,
        last_confirmation_token=?,version=version+1 WHERE trip_id=?''',(token,trip_id))
    c_advance(conn,trip_id)


def c_snapshot(conn,trip):
    tid = trip['id']
    runtime = c_runtime(conn,tid)
    schedule = c_schedule(conn,tid)
    runs = [dict(r) for r in conn.execute('SELECT * FROM activity_runs WHERE trip_id=? ORDER BY day_number,started_at,id',(tid,))]
    by_slot = {r['itinerary_activity_id']:r for r in runs}
    today = [s for s in schedule if s['day_number']==runtime['current_day']]
    for slot in schedule:
        slot['catalogue_activity_id'] = slot['activity_id']
        slot['activity_id'] = slot['id']
        slot['applicable_rating_keys'] = c_applicable(slot)
        slot['run'] = by_slot.get(slot['id'])
    current = next((s for s in schedule if s['id']==runtime['current_activity_id']),None)
    pending = c_pending_review(conn,tid)
    review = next((s for s in schedule if pending and s['id']==pending['itinerary_activity_id']),None)
    feedback = conn.execute('SELECT * FROM post_trip_feedback WHERE trip_id=?',(tid,)).fetchone()
    feedback = dict(feedback) if feedback else None
    if feedback is None and runtime['post_feedback_draft_json']:
        feedback = json.loads(runtime['post_feedback_draft_json'])
    for row in runs:
        row['ratings'] = json.loads(row['ratings_json'] or '{}')
    if feedback:
        feedback['ratings'] = json.loads(feedback['ratings_json'])
        feedback['per_place_ratings'] = json.loads(feedback['per_place_ratings_json'])
    outcomes_today = [r for r in runs if r['day_number']==runtime['current_day'] and r.get('ended_at')]
    day_counts = {'completed':0,'early_ended':0,'skipped':0,'not_done':0}
    for run in outcomes_today:
        outcome = run.get('outcome') or 'not_done'
        day_counts[outcome] = day_counts.get(outcome,0)+1
    days_finished = max(0, runtime['current_day'] - 1 + int(bool(runtime['day_ended'])))
    if runtime['status']=='completed': phase='completed'
    elif runtime['day_ended']: phase='day_summary'
    elif review: phase='activity_review'
    elif runtime['pending_decision_json']: phase='itinerary_decision'
    elif current: phase='activity'
    else: phase='awaiting_day_end' if runtime['status']=='live' else runtime['status']
    last_today = bool(current and today and current['id']==today[-1]['id'])
    label = ('End trip' if runtime['current_day']==trip['duration_days'] else 'End day') if last_today else 'End activity'
    feedback_pending = runtime['status']=='completed' and not (feedback and feedback['submitted_at'])
    archived = runtime['status']=='completed' and bool(feedback and feedback['submitted_at'])
    status_now = runtime['status']
    permitted = (['edit','generate','finalize'] if status_now=='draft' else
                 ['start'] if status_now=='finalized' else
                 ['start_activity','end_activity','review_activity','adjust_remaining','end_day','start_next_day','end_trip'] if status_now=='live' else
                 ['submit_feedback'] if feedback_pending else [])
    return {'trip_id':tid,'status':runtime['status'],'runtime':runtime,'phase':phase,
        'current_activity':current,'pending_review':review,'today':today,'schedule':schedule,'runs':runs,
        'total_days':trip['duration_days'],'end_activity_label':label,
        'day_summary':{'current_day':runtime['current_day'],'days_finished':days_finished,
            'total_trip_days':trip['duration_days'],'outcomes_today':day_counts,
            'completed_today':[r for r in outcomes_today if r.get('outcome')=='completed'],
            'ended_early_today':[r for r in outcomes_today if r.get('outcome')=='early_ended'],
            'skipped_today':[r for r in outcomes_today if r.get('outcome') in ('skipped','not_done')]},
        'tab_access':{'pre_trip':{'available':status_now in ('draft','finalized'),'read_only':status_now!='draft'},
            'live':{'available':status_now=='live','read_only':status_now!='live'},
            'post_trip':{'available':status_now=='completed','read_only':archived}},
        'permitted_actions':permitted,'active':status_now!='completed','archived':archived,
        'pending_decision':json.loads(runtime['pending_decision_json']) if runtime['pending_decision_json'] else None,
        'preview':json.loads(runtime['preview_json']) if runtime['preview_json'] else None,
        'post_feedback':feedback,'feedback_required':feedback_pending,'feedback_pending':feedback_pending,
        'closed_out':archived, 'rating_keys':sorted(C_RATING_KEYS)}


@runtime_router.get('/{trip_id}/runtime')
def c_get_runtime(trip_id: str,request: Request):
    with c_transaction(trip_id,c_actor(request)) as (conn,trip):
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/finalize')
def c_finalize(trip_id: str,request: Request,payload: CActor = Body(default=CActor())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        runtime = c_runtime(conn,trip_id)
        if runtime['status']!='draft': c_error(409,'Only a draft itinerary can be finalized.','NOT_DRAFT')
        if not c_schedule(conn,trip_id): c_error(409,'Add at least one activity before finalizing.','EMPTY_ITINERARY')
        conn.execute("UPDATE trip_runtime SET status='finalized',version=version+1 WHERE trip_id=?",(trip_id,))
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/unfinalize')
def c_unfinalize(trip_id: str,request: Request,payload: CActor = Body(default=CActor())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        if c_runtime(conn,trip_id)['status']!='finalized': c_error(409,'Only a finalized trip that has not started can be reopened.','NOT_FINALIZED')
        conn.execute("UPDATE trip_runtime SET status='draft',version=version+1 WHERE trip_id=?",(trip_id,))
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/start')
def c_start(trip_id: str,request: Request,payload: CActor = Body(default=CActor())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        if c_runtime(conn,trip_id)['status']!='finalized': c_error(409,'Finalize the itinerary before starting; a trip can start only once.','NOT_FINALIZED')
        if not c_schedule(conn,trip_id): c_error(409,'The itinerary has no activities. Reopen it and add activities.','EMPTY_ITINERARY')
        conn.execute("UPDATE trip_runtime SET status='live',started_at=?,current_day=1,day_ended=0,version=version+1 WHERE trip_id=?",(c_now(),trip_id))
        c_advance(conn,trip_id)
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/activities/{activity_id}/start')
def c_activity_start(trip_id: str,activity_id: str,request: Request,payload: CActor = Body(default=CActor())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        slot = c_slot(conn,trip_id,activity_id)
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        if c_run(conn,trip_id,slot['id']): c_error(409,'This activity has already been started or marked not done.','ALREADY_STARTED')
        if runtime['current_activity_id'] or c_pending_review(conn,trip_id) or runtime['pending_decision_json'] or runtime['day_ended']:
            c_error(409,'Finish the current activity, review or day transition first.','OUT_OF_ORDER')
        upcoming = [s for s in c_schedule(conn,trip_id) if s['day_number']==runtime['current_day'] and not c_run(conn,trip_id,s['id'])]
        if not upcoming or upcoming[0]['id']!=slot['id']: c_error(409,'Start activities in order on the current day.','OUT_OF_ORDER')
        c_start_slot(conn,trip_id,slot)
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/activities/{activity_id}/end')
def c_activity_end(trip_id: str,activity_id: str,request: Request,payload: CEndActivity = Body(default=CEndActivity())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        slot = c_slot(conn,trip_id,activity_id)
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        run = c_run(conn,trip_id,slot['id'])
        if not run or not run['started_at']: c_error(409,'This activity has not started.','NOT_STARTED')
        if run['ended_at'] or runtime['current_activity_id']!=slot['id']: c_error(409,'This activity has already ended or is not current.','NOT_CURRENT')
        conn.execute('UPDATE activity_runs SET ended_at=?,outcome=? WHERE id=?',(c_now(),payload.outcome,run['id']))
        conn.execute('UPDATE trip_runtime SET current_activity_id=NULL,version=version+1 WHERE trip_id=?',(trip_id,))
        return c_snapshot(conn,trip)


class CAtomicConnection:
    """Keep existing policy persistence helpers inside the review transaction."""
    def __init__(self,conn): self.conn=conn
    def __getattr__(self,name): return getattr(self.conn,name)
    def commit(self): pass


def c_learn_review(conn,trip,slot,run,ratings):
    if not ratings: return
    atomic = CAtomicConnection(conn)
    context = json.loads(run['context_json']) if run['context_json'] else _preserve_or_get_activity_context(
        atomic,slot['itinerary_id'],slot['activity_id'],trip['user_id'],trip,slot)
    policy = load_user_policy(conn,trip['user_id'])
    arm = slot['category'] if slot['category'] in CANONICAL_ARMS else 'culture_history'
    reward = (sum(ratings.values())/len(ratings)-3)/2
    policy.update(arm,np.array(context,dtype=float),reward)
    save_user_policy(atomic,policy)
    conn.execute('UPDATE activity_runs SET context_json=?,learning_applied=1 WHERE id=?',(json.dumps(context),run['id']))


@runtime_router.post('/{trip_id}/activities/{activity_id}/review')
def c_activity_review(trip_id: str,activity_id: str,request: Request,payload: CReview):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        slot = c_slot(conn,trip_id,activity_id)
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        run = c_run(conn,trip_id,slot['id'])
        pending = c_pending_review(conn,trip_id)
        if not run or not run['ended_at']: c_error(409,'End the activity before reviewing it.','NOT_ENDED')
        if run['action']: c_error(409,'This activity review has already been saved.','ALREADY_REVIEWED')
        if not pending or pending['id']!=run['id']: c_error(409,'Review the most recently ended activity first.','OUT_OF_ORDER')
        applicable = set(c_applicable(slot))
        if set(payload.ratings)-applicable: c_error(422,'These rating parameters do not apply to this activity.','INVALID_RATINGS','ratings')
        if run['outcome'] in ('completed','early_ended') and set(payload.ratings)!=applicable:
            c_error(422,'Rate every applicable activity parameter.','MISSING_RATINGS','ratings')
        conn.execute('UPDATE activity_runs SET ratings_json=?,notes=?,action=? WHERE id=?',
            (json.dumps(payload.ratings),payload.notes,payload.action,run['id']))
        c_learn_review(conn,trip,slot,run,payload.ratings)
        if payload.action=='keep':
            c_advance(conn,trip_id)
        else:
            decision = {'action':payload.action,'run_id':run['id']}
            conn.execute('UPDATE trip_runtime SET pending_decision_json=?,version=version+1 WHERE trip_id=?',(json.dumps(decision),trip_id))
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/continue')
def c_continue(trip_id: str,request: Request,payload: CActor = Body(default=CActor())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        if not runtime['pending_decision_json']: c_error(409,'There is no pending itinerary decision.','NO_DECISION')
        conn.execute('UPDATE trip_runtime SET pending_decision_json=NULL,preview_json=NULL,version=version+1 WHERE trip_id=?',(trip_id,))
        c_advance(conn,trip_id)
        return c_snapshot(conn,trip)


def c_check_day(trip,day):
    if day<1 or day>trip['duration_days']: c_error(404,'Day not found in this trip.','DAY_NOT_FOUND','day')


@runtime_router.post('/{trip_id}/days/{day}/end')
def c_end_day(trip_id: str,day: int,request: Request,payload: CEndDay = Body(default=CEndDay())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        c_check_day(trip,day)
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        if day!=runtime['current_day'] or runtime['day_ended']: c_error(409,'End only the current open day.','OUT_OF_ORDER')
        if c_pending_review(conn,trip_id) or runtime['pending_decision_json']:
            c_error(409,'Save the pending activity review and itinerary decision first.','REVIEW_REQUIRED')
        slots = [s for s in c_schedule(conn,trip_id) if s['day_number']==day]
        unfinished = [s for s in slots if not c_run(conn,trip_id,s['id']) or not c_run(conn,trip_id,s['id'])['ended_at']]
        valid_ids = {s['id'] for s in unfinished}
        if set(payload.dispositions)-valid_ids: c_error(404,'A marked activity is not unfinished on this day.','ACTIVITY_NOT_FOUND','dispositions')
        if valid_ids!=set(payload.dispositions): c_error(409,'Unfinished activities remain. Explicitly mark each skipped or not done.','UNFINISHED_ACTIVITIES','dispositions')
        for slot in unfinished:
            run = c_run(conn,trip_id,slot['id'])
            if run:
                conn.execute("UPDATE activity_runs SET ended_at=?,outcome=?,action='keep',ratings_json='{}' WHERE id=?",(c_now(),payload.dispositions[slot['id']],run['id']))
            else:
                conn.execute('''INSERT INTO activity_runs(id,trip_id,activity_id,itinerary_activity_id,day_number,ended_at,ratings_json,action,outcome)
                    VALUES(?,?,?,?,?,?,'{}','keep',?)''',(str(uuid.uuid4()),trip_id,slot['activity_id'],slot['id'],day,c_now(),payload.dispositions[slot['id']]))
        conn.execute('UPDATE trip_runtime SET day_ended=1,current_activity_id=NULL,version=version+1 WHERE trip_id=?',(trip_id,))
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/days/{day}/start')
def c_start_day(trip_id: str,day: int,request: Request,payload: CActor = Body(default=CActor())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        c_check_day(trip,day)
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        if not runtime['day_ended'] or day!=runtime['current_day']+1:
            c_error(409,'Finish the current day, then start the immediately following day.','OUT_OF_ORDER')
        conn.execute('UPDATE trip_runtime SET current_day=?,day_ended=0,version=version+1 WHERE trip_id=?',(day,trip_id))
        c_advance(conn,trip_id)
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/end')
def c_end_trip(trip_id: str,request: Request,payload: CActor = Body(default=CActor())):
    with c_transaction(trip_id,c_actor(request,payload)) as (conn,trip):
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        if runtime['current_day']!=trip['duration_days'] or not runtime['day_ended']:
            c_error(409,'Finish and end every trip day before ending the trip.','UNFINISHED_TRIP')
        if runtime['pending_decision_json'] or c_pending_review(conn,trip_id): c_error(409,'Save the pending review first.','REVIEW_REQUIRED')
        conn.execute("UPDATE trip_runtime SET status='completed',ended_at=?,version=version+1 WHERE trip_id=?",(c_now(),trip_id))
        conn.execute('''INSERT INTO live_trip_state(trip_id,user_id,is_started,is_completed,current_day,completed_at)
            VALUES(?,?,1,1,?,?) ON CONFLICT(trip_id) DO UPDATE SET is_completed=1,completed_at=excluded.completed_at''',
            (trip_id,trip['user_id'],trip['duration_days'],c_now()))
        return c_snapshot(conn,trip)


async def c_call_existing(request,method,path,payload=None):
    """Cross-owner itinerary interaction is exclusively through existing APIs."""
    token = C_MUTATION_CAPABILITY.set(request.path_params.get('trip_id'))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=request.app),base_url='http://internal') as client:
            response = await client.request(method,path,json=payload,timeout=20,
                headers={'Authorization':request.headers.get('Authorization','')})
        if response.status_code>=400:
            c_error(503,'The existing recommendation/feedback service could not complete the request. Your trip state is unchanged; please retry.',
                    'DOWNSTREAM_UNAVAILABLE')
        return response.json()
    except HTTPException:
        raise
    except Exception:
        c_error(503,'The recommendation service is unavailable. Your entries have been kept. Please retry.','DOWNSTREAM_UNAVAILABLE')
    finally:
        C_MUTATION_CAPABILITY.reset(token)


def c_upcoming(conn,trip_id,slot):
    runtime = c_runtime(conn,trip_id)
    c_require_live(runtime)
    if not runtime['pending_decision_json']: c_error(409,'Choose enhance or change in an activity review first.','NO_DECISION')
    if slot['day_number']<runtime['current_day'] or c_run(conn,trip_id,slot['id']):
        c_error(409,'Only upcoming activities can be changed.','NOT_UPCOMING')


@runtime_router.get('/{trip_id}/suggestions')
async def c_suggestions(trip_id: str,request: Request):
    actor = c_actor(request)
    with c_transaction(trip_id,actor) as (conn,trip):
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        if not runtime['pending_decision_json']: c_error(409,'Choose enhance or change in an activity review first.','NO_DECISION')
        upcoming = [s for s in c_schedule(conn,trip_id) if s['day_number']>=runtime['current_day'] and not c_run(conn,trip_id,s['id'])]
        if not upcoming: return {'targets':[],'alternatives':[],'message':'No upcoming activities remain. You can leave the itinerary as it is.'}
        requested=request.query_params.get('activity_id')
        target=c_slot(conn,trip_id,requested) if requested else upcoming[0]
        c_upcoming(conn,trip_id,target)
    data = await c_call_existing(request,'GET',f"/api/live/{trip_id}/replan?user_id={actor}&activity_id={target['activity_id']}")
    return {'targets':[{'activity_id':s['id'],'title':s['title'],'day':s['day_number']} for s in upcoming],
            'target_activity_id':target['id'],'alternatives':data.get('alternatives',[])}


@runtime_router.post('/{trip_id}/adjustments/preview')
async def c_preview(trip_id: str,request: Request,payload: CPreview):
    actor = c_actor(request,payload)
    with c_transaction(trip_id,actor) as (conn,trip):
        slot = c_slot(conn,trip_id,payload.target_activity_id)
        c_upcoming(conn,trip_id,slot)
        if payload.operation=='remove' and json.loads(c_runtime(conn,trip_id)['pending_decision_json'])['action']!='change':
            c_error(422,'Choose change in the activity review to remove upcoming activities.','INVALID_OPERATION','operation')
        fingerprint = c_fingerprint(conn,trip_id)
        affected = [slot]
        for s in affected: c_upcoming(conn,trip_id,s)
        if payload.operation=='swap':
            if not conn.execute('SELECT id FROM destination_activities WHERE id=?',(payload.replacement_activity_id,)).fetchone():
                c_error(404,'Replacement activity not found.','ACTIVITY_NOT_FOUND','replacement_activity_id')
    if payload.operation=='swap':
        data = await c_call_existing(request,'GET',f"/api/live/{trip_id}/replan?user_id={actor}&activity_id={slot['activity_id']}")
        alternative = next((a for a in data.get('alternatives',[]) if a['id']==payload.replacement_activity_id),None)
        if not alternative: c_error(422,'Choose one of the recommended alternatives for this activity.','INVALID_REPLACEMENT','replacement_activity_id')
        title = alternative['name']
    else:
        title = f"Remove {slot['title']} ({len(affected)} upcoming occurrence(s))"
    preview = {'token':uuid.uuid4().hex,'fingerprint':fingerprint,'operation':payload.operation,
        'target_activity_id':slot['id'],'catalogue_activity_id':slot['activity_id'],
        'replacement_activity_id':payload.replacement_activity_id,'title':title,'affected_count':len(affected),
        'before_activity':slot,'user_id':actor}
    if payload.operation=='swap':
        preview['cost_delta_inr']=int(round(float(alternative.get('cost_estimate') or 0)-float(slot.get('cost_estimate') or 0)))
        preview['duration_delta_minutes']=int(alternative.get('duration_minutes') or 0)-int(slot.get('duration_minutes') or 0)
    else:
        preview['cost_delta_inr']=-int(round(float(slot.get('cost_estimate') or 0)))
        preview['duration_delta_minutes']=-int(slot.get('duration_minutes') or 0)
    with c_transaction(trip_id,actor) as (conn,trip):
        c_upcoming(conn,trip_id,c_slot(conn,trip_id,slot['id']))
        if c_fingerprint(conn,trip_id)!=fingerprint: c_error(409,'The itinerary changed. Request a fresh preview.','STALE_PREVIEW')
        conn.execute('UPDATE trip_runtime SET preview_json=? WHERE trip_id=?',(json.dumps(preview),trip_id))
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/adjustments/confirm')
async def c_confirm(trip_id: str,request: Request,payload: CConfirm):
    actor = c_actor(request,payload)
    with c_transaction(trip_id,actor) as (conn,trip):
        runtime = c_runtime(conn,trip_id)
        c_require_live(runtime)
        if runtime['last_confirmation_token']==payload.token:
            return c_snapshot(conn,trip)
        preview = json.loads(runtime['preview_json']) if runtime['preview_json'] else None
        if not preview or preview['token']!=payload.token: c_error(409,'Request a preview before confirming this change.','NO_PREVIEW')
        slot = c_slot(conn,trip_id,preview['target_activity_id'])
        c_upcoming(conn,trip_id,slot)
        if c_fingerprint(conn,trip_id)!=preview['fingerprint']: c_error(409,'The itinerary changed. Request a fresh preview.','STALE_PREVIEW')
        preview['confirmed']=True
        conn.execute('UPDATE trip_runtime SET operation_in_flight=1,operation_started_at=?,preview_json=? WHERE trip_id=?',
                     (c_now(),json.dumps(preview),trip_id))
    try:
        if preview['operation']=='swap':
            await c_call_existing(request,'POST',f'/api/live/{trip_id}/replan',{
                'user_id':actor,'activity_id':preview['catalogue_activity_id'],
                'itinerary_activity_id':preview['target_activity_id'],'replacement_activity_id':preview['replacement_activity_id'],
                'reason':'Confirmed activity review improvement','is_trip_specific':True})
        else:
            await c_call_existing(request,'DELETE',f"/api/trip-actions/{trip_id}/activity/{preview['target_activity_id']}?user_id={actor}")
    except Exception as exc:
        with c_transaction(trip_id,actor) as (conn,trip):
            # The endpoint may have committed before its response was lost.
            # Accept that exact confirmed result instead of applying it twice.
            if c_adjustment_applied(conn,trip_id,preview):
                c_log_adjustment(conn,trip_id,preview)
                c_finish_adjustment(conn,trip_id,payload.token)
                return c_snapshot(conn,trip)
            conn.execute('UPDATE trip_runtime SET operation_in_flight=0,operation_started_at=NULL WHERE trip_id=?',(trip_id,))
        if isinstance(exc,HTTPException): raise
        c_error(503,'The itinerary update failed. Your preview has been kept; retry or leave the itinerary as it is.','DOWNSTREAM_UNAVAILABLE')
    with c_transaction(trip_id,actor) as (conn,trip):
        c_log_adjustment(conn,trip_id,preview)
        c_finish_adjustment(conn,trip_id,payload.token)
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/adjustments/undo')
async def c_undo_adjustment(trip_id: str,request: Request,payload: CActor = Body(default=CActor())):
    actor=c_actor(request,payload)
    with c_transaction(trip_id,actor) as (conn,trip):
        runtime=c_runtime(conn,trip_id)
        if runtime['status'] not in ('draft','live'):
            c_error(409,'Only draft or live trips can undo a recent itinerary change.','ILLEGAL_STATE')
        if runtime['status']=='live':
            c_require_live(runtime)
            if runtime['current_activity_id'] or c_pending_review(conn,trip_id):
                c_error(409,'Finish the current activity review before undoing an itinerary change.','ACTIVITY_IN_PROGRESS')
        row=conn.execute('''SELECT * FROM trip_edit_history WHERE trip_id=? AND user_id=? AND undone_at IS NULL
            ORDER BY created_at DESC,id DESC LIMIT 1''',(trip_id,actor)).fetchone()
        if not row:
            c_error(409,'There is no confirmed itinerary change to undo.','NOTHING_TO_UNDO')
        history=dict(row)
        before=json.loads(history['before_json'])
        original=before.get('activity') or {}
        occurrence=before.get('occurrence_id')
        if before.get('operation')=='swap' and original.get('activity_id'):
            action={'kind':'swap','occurrence_id':occurrence,'replacement_activity_id':original['activity_id']}
        elif before.get('operation')=='remove':
            action={'kind':'restore','occurrence_id':occurrence}
        else:
            c_error(409,'This itinerary change cannot be undone.','UNDO_UNAVAILABLE')
    try:
        if action['kind']=='swap':
            await c_call_existing(request,'POST',f"/api/trip-actions/{trip_id}/activity/{action['occurrence_id']}/swap",{
                'user_id':actor,'occurrence_id':action['occurrence_id'],
                'replacement_activity_id':action['replacement_activity_id'],'is_trip_specific':True})
        else:
            await c_call_existing(request,'POST',f"/api/trip-actions/{trip_id}/activity/{action['occurrence_id']}/restore?user_id={actor}")
    except Exception:
        c_error(503,'The change could not be undone. The current itinerary has been kept.','UNDO_FAILED')
    with c_transaction(trip_id,actor) as (conn,trip):
        conn.execute('UPDATE trip_edit_history SET undone_at=? WHERE id=? AND undone_at IS NULL',(c_now(),history['id']))
        return c_snapshot(conn,trip)


@runtime_router.post('/{trip_id}/post-feedback')
async def c_post_feedback(trip_id: str,request: Request,payload: CPostFeedback):
    actor = c_actor(request,payload)
    with c_transaction(trip_id,actor) as (conn,trip):
        runtime = c_runtime(conn,trip_id)
        if runtime['status']!='completed': c_error(409,'End the trip before filling out post-trip feedback.','TRIP_NOT_COMPLETED')
        existing = conn.execute('SELECT * FROM post_trip_feedback WHERE trip_id=?',(trip_id,)).fetchone()
        if existing and existing['submitted_at']: return c_snapshot(conn,trip)
        if runtime['operation_in_flight']: c_error(409,'Feedback submission is already in progress.','SUBMISSION_IN_PROGRESS')
        already_delivered = bool(conn.execute('SELECT id FROM live_postrip WHERE trip_id=?',(trip_id,)).fetchone())
        if already_delivered and not (existing and existing['delivery_started_at']):
            c_error(409,'Feedback was already submitted through the previous trip interface. A second learning submission is not allowed.','ALREADY_SUBMITTED')
        places=[]
        for item in payload.per_place_ratings:
            slot = c_slot(conn,trip_id,item.activity_id)
            if set(item.ratings)-set(c_applicable(slot)): c_error(422,'A per-place rating parameter does not apply to that activity.','INVALID_RATINGS','per_place_ratings')
            places.append({'activity_id':slot['id'],'catalogue_activity_id':slot['activity_id'],'ratings':item.ratings})
        try: saved_prefs=json.loads(trip.get('trip_preferences_json') or '{}')
        except (TypeError,ValueError): saved_prefs={}
        from app.core.party import trip_type as canonical_trip_type
        resolved_trip_type=payload.trip_type or saved_prefs.get('trip_type') or canonical_trip_type(dict(trip),saved_prefs.get('party'))
        draft = dict(trip_id=trip_id,user_id=actor,ratings_json=json.dumps(payload.ratings),trip_type=resolved_trip_type,
                     would_revisit=payload.would_revisit,liked=payload.liked or '',disliked=payload.disliked or '',
                     notes=payload.notes,per_place_ratings_json=json.dumps(places),submitted_at=None,
                     delivery_started_at=None if payload.draft else c_now())
        conn.execute('UPDATE trip_runtime SET post_feedback_draft_json=? WHERE trip_id=?',(json.dumps(draft),trip_id))
        if payload.draft: return c_snapshot(conn,trip)
        conn.execute('UPDATE trip_runtime SET operation_in_flight=1,operation_started_at=? WHERE trip_id=?',(c_now(),trip_id))
    try:
        if not already_delivered:
            # Existing endpoint supplies core feedback used by ranking and applies
            # optional per-place evaluations to the same LinUCB learner.
            legacy_places = {}
            for place in places:
                scores = place['ratings']
                legacy_places[place['catalogue_activity_id']] = {'activity_id':place['catalogue_activity_id'],
                    'rating':round(sum(scores.values())/len(scores)),'comments':payload.notes}
            await c_call_existing(request,'POST',f'/api/live/{trip_id}/postrip',{
                'user_id':actor,'overall_satisfaction':payload.ratings['overall'],
                'enjoyed_most':payload.liked,'disliked':payload.disliked,'comments':payload.notes,
                'activity_ratings':list(legacy_places.values())})
    except Exception as exc:
        with get_connection() as conn:
            conn.execute('UPDATE trip_runtime SET operation_in_flight=0,operation_started_at=NULL WHERE trip_id=?',(trip_id,))
        if isinstance(exc,HTTPException): raise
        c_error(503,'Feedback could not be submitted. Your saved draft has been kept; please retry.','DOWNSTREAM_UNAVAILABLE')
    with c_transaction(trip_id,actor) as (conn,trip):
        c_publish_feedback(conn,draft,c_now())
        conn.execute('UPDATE trip_runtime SET operation_in_flight=0,operation_started_at=NULL,version=version+1 WHERE trip_id=?',(trip_id,))
        return c_snapshot(conn,trip)


class CRuntimeGuard(BaseHTTPMiddleware):
    """Lock existing editing entry points without changing B's implementation."""
    async def dispatch(self,request,call_next):
        if request.method not in ('POST','PUT','PATCH','DELETE'):
            return await call_next(request)
        path = request.url.path
        trip_id = None
        category = None
        patterns = [
            (r'^/api/trip-actions/([^/]+)/(.+)$','edit'),
            (r'^/api/itinerary/generate/([^/]+)$','edit'),
            (r'^/api/itinerary/timed/generate/([^/]+)$','edit'),
            (r'^/api/plan/generate/([^/]+)$','edit'),
            (r'^/api/plan/([^/]+)(?:/.*)?$','edit'),
            (r'^/api/stay/([^/]+)/(?:select|replan|hotel-first-preview)$','edit'),
            (r'^/api/trips/([^/]+)$','edit'),
            (r'^/api/live/([^/]+)/(?:activity/[^/]+/status|complete|postrip|replan|simulate|alerts/.*)$','live'),
        ]
        for pattern,kind in patterns:
            match=re.match(pattern,path)
            if match:
                trip_id,category=match[1],kind
                break
        body = None
        if path.startswith('/api/itinerary/feedback/') or path=='/api/itinerary/regenerate':
            try:
                body=await request.json()
                with get_connection() as conn:
                    row=conn.execute('SELECT trip_id FROM itineraries WHERE id=?',(body.get('itinerary_id'),)).fetchone()
                if row: trip_id,category=row[0],'edit'
            except (ValueError,AttributeError,sqlite3.Error):
                return await call_next(request)
        if not trip_id:
            return await call_next(request)
        try:
            with get_connection() as conn:
                row=conn.execute('SELECT * FROM trip_runtime WHERE trip_id=?',(trip_id,)).fetchone()
                runtime=dict(row) if row else None
            if not runtime: return await call_next(request)
            if C_MUTATION_CAPABILITY.get()==trip_id: return await call_next(request)
            # Old finalize/start controls participate once a trip is enrolled.
            if path==f'/api/trip-actions/{trip_id}/finalize':
                return JSONResponse(c_finalize(trip_id,request,CActor()))
            if path==f'/api/trip-actions/{trip_id}/start':
                return JSONResponse(c_start(trip_id,request,CActor()))
            if category=='edit' and runtime['status']!='draft':
                c_error(409,'The itinerary is locked. Reopen a finalized trip before editing, or use a confirmed live-trip adjustment.','ITINERARY_LOCKED')
            if category=='live':
                if runtime['status']!='live': c_error(409,'This action requires a live trip.','NOT_LIVE')
                if path.endswith('/simulate'):
                    try:
                        body=await request.json()
                        payload=CDisruption.model_validate(body)
                    except (ValueError,ValidationError):
                        c_error(422,'Choose a valid disruption, severity and integer day number.','INVALID_INPUT','condition_type')
                    with get_connection() as conn:
                        trip=conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone()
                        if trip['user_id']!=c_actor(request,payload): c_error(403,'This trip belongs to another user.','NOT_OWNER')
                        c_check_day(dict(trip),payload.day_number)
                        if payload.day_number!=runtime['current_day']: c_error(409,'Simulate disruptions for the current day only.','OUT_OF_ORDER')
                        if payload.target_activity_id:
                            c_slot(conn,trip_id,payload.target_activity_id)
                    return await call_next(request)
                if '/alerts/' in path:
                    return await call_next(request)
                c_error(409,'Use the current activity review and runtime controls for this trip.','USE_RUNTIME_FLOW')
        except HTTPException as exc:
            return c_error_response(exc)
        except sqlite3.OperationalError as exc:
            if 'no such table: trip_runtime' in str(exc): return await call_next(request)
            return JSONResponse({'detail':'Trip storage is temporarily unavailable. Please retry.','code':'DATABASE_UNAVAILABLE','field':None},status_code=503)
        return await call_next(request)


def include_c_router(app):
    """C-owned router registration, error boundary and cross-route editing guard."""
    app.include_router(runtime_router)
    app.add_middleware(CRuntimeGuard)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="upcoming, in_progress, completed, skipped, or delayed")
    notes: Optional[str] = None
    user_id: Optional[str] = None


class SimulateConditionRequest(BaseModel):
    condition_type: str = Field(..., description="heavy_rain, extreme_heat, closure, traffic_delay, strike, fatigue, unexpected_crowding")
    day_number: int = Field(1, ge=1)
    severity: str = "moderate"
    description: Optional[str] = None
    target_activity_id: Optional[str] = None
    user_id: Optional[str] = None


class ReplanExecuteRequest(BaseModel):
    activity_id: str
    itinerary_activity_id: Optional[str] = None
    replacement_activity_id: str
    reason: str = "Condition disruption"
    is_trip_specific: bool = True
    user_id: Optional[str] = None


class CompleteTripRequest(BaseModel):
    user_id: Optional[str] = None


class ActivityRatingItem(BaseModel):
    activity_id: str
    rating: int = Field(..., ge=1, le=5)
    enjoyed: Optional[bool] = None
    remember_preference: bool = True
    comments: Optional[str] = None


class PostTripFeedbackRequest(BaseModel):
    user_id: Optional[str] = None
    overall_satisfaction: float = Field(..., ge=1.0, le=5.0)
    pace_rating: Optional[str] = "just_right"
    budget_accuracy: Optional[str] = "accurate"
    itinerary_realistic: Optional[str] = "realistic"
    enjoyed_most: Optional[str] = None
    disliked: Optional[str] = None
    comments: Optional[str] = None
    activity_ratings: List[ActivityRatingItem] = []


def rating_to_reward(rating: int) -> float:
    """
    Standardizes post-trip 1-5 star ratings to LinUCB scalar rewards:
    5 -> +1.0 (Very satisfied)
    4 -> +0.5 (Satisfied)
    3 ->  0.0 (Neutral, no weight update)
    2 -> -0.5 (Dissatisfied)
    1 -> -1.0 (Very dissatisfied)
    """
    if rating >= 5:
        return 1.0
    elif rating == 4:
        return 0.5
    elif rating == 3:
        return 0.0
    elif rating == 2:
        return -0.5
    else:
        return -1.0


# ---------------------------------------------------------------------------
# Database Schema Initialization
# ---------------------------------------------------------------------------

def init_tables(conn: sqlite3.Connection):
    """Initializes all live_* tables owned by Person B."""
    cursor = conn.cursor()

    # 1. Trip execution state (started/completed flags)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_trip_state (
            trip_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            is_started INTEGER DEFAULT 0,
            is_completed INTEGER DEFAULT 0,
            current_day INTEGER DEFAULT 1,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    # 2. Activity execution status (upcoming, in_progress, completed, skipped, delayed)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_activity_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL,
            activity_id TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trip_id, activity_id)
        )
    """)

    # 3. Simulated environmental/travel conditions (heavy_rain, heat, closure, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL,
            day_number INTEGER NOT NULL,
            condition_type TEXT NOT NULL,
            severity TEXT DEFAULT 'moderate',
            description TEXT,
            source TEXT DEFAULT 'simulated',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4. Proactive contextual alerts generated from conditions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL,
            day_number INTEGER NOT NULL,
            activity_id TEXT NOT NULL,
            condition_id INTEGER,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            suggested_action TEXT,
            is_dismissed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (condition_id) REFERENCES live_conditions(id)
        )
    """)

    # 5. Post-trip overall feedback summary
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_postrip (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            overall_satisfaction REAL NOT NULL,
            pace_rating TEXT,
            budget_accuracy TEXT,
            itinerary_realistic TEXT,
            enjoyed_most TEXT,
            disliked TEXT,
            comments TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 6. Post-trip per-activity evaluations (with duplicate protection and LinUCB rewards)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_activity_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL,
            activity_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            enjoyed INTEGER NOT NULL,
            remember_preference INTEGER DEFAULT 1,
            reward_assigned REAL NOT NULL,
            arm_id TEXT NOT NULL,
            context_vector_json TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trip_id, activity_id)
        )
    """)

    # 7. Exact historical 24-dim context vector preservation per activity recommendation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_activity_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            itinerary_id TEXT NOT NULL,
            activity_id TEXT NOT NULL,
            context_vector_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(itinerary_id, activity_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_act_status_trip ON live_activity_status(trip_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_conditions_trip ON live_conditions(trip_id, day_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_alerts_trip ON live_alerts(trip_id, day_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_act_feedback_trip ON live_activity_feedback(trip_id)")
    conn.commit()
    from app.db_migrations_c import migrate_c
    migrate_c(conn)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _verify_trip_ownership(trip_id: str, user_id: Optional[str]) -> Dict[str, Any]:
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if user_id and trip["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to trip")
    return trip


def _preserve_or_get_activity_context(
    conn: sqlite3.Connection,
    itinerary_id: str,
    activity_id: str,
    user_id: str,
    trip: Dict[str, Any],
    activity_row: Dict[str, Any]
) -> List[float]:
    """Retrieves or snapshots the exact 24-dimensional context vector for historical consistency."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT context_vector_json FROM live_activity_contexts
        WHERE itinerary_id = ? AND activity_id = ?
    """, (itinerary_id, activity_id))
    row = cursor.fetchone()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            pass

    # Look in rl_feedback_log if previously logged
    cursor.execute("""
        SELECT context_vector_json FROM rl_feedback_log
        WHERE itinerary_id = ? AND activity_id = ?
        ORDER BY created_at DESC LIMIT 1
    """, (itinerary_id, activity_id))
    fb_row = cursor.fetchone()
    if fb_row and fb_row[0]:
        try:
            vec = json.loads(fb_row[0])
            cursor.execute("""
                INSERT OR IGNORE INTO live_activity_contexts (itinerary_id, activity_id, context_vector_json)
                VALUES (?, ?, ?)
            """, (itinerary_id, activity_id, fb_row[0]))
            conn.commit()
            return vec
        except Exception:
            pass

    # Otherwise compute with profile and trip context at schedule time and persist
    user_ctx = get_user_context(user_id)
    profile = {}
    if user_ctx.get("basic"):
        profile.update(user_ctx["basic"])
    if user_ctx.get("detailed"):
        profile.update(user_ctx["detailed"])

    day_num = activity_row.get("day_number", 1)
    tot_days = trip.get("duration_days", 5)
    time_slot = activity_row.get("time_slot", "afternoon")

    vec_arr = extract_context_vector(
        user_profile=profile,
        trip_config={"duration_days": tot_days, "total_budget": trip.get("total_budget", 1000.0)},
        day_number=day_num,
        total_days=tot_days,
        time_slot=time_slot,
        activity=activity_row
    )
    vec_list = vec_arr.tolist()
    cursor.execute("""
        INSERT OR IGNORE INTO live_activity_contexts (itinerary_id, activity_id, context_vector_json)
        VALUES (?, ?, ?)
    """, (itinerary_id, activity_id, json.dumps(vec_list)))
    conn.commit()
    return vec_list


# ---------------------------------------------------------------------------
# Module Verification Endpoints
# ---------------------------------------------------------------------------

@router.get("/module-info")
def module_info():
    """Returns module metadata and status for health checking."""
    return {
        "module": MODULE["id"],
        "title": MODULE["title"],
        "owner": MODULE["owner"],
        "status": "active"
    }


@router.get("/{trip_id}/state")
def get_trip_state(trip_id: str, user_id: Optional[str] = Query(None)):
    """Retrieves live execution state of a trip."""
    trip = _verify_trip_ownership(trip_id, user_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM live_trip_state WHERE trip_id = ?", (trip_id,))
        row = cursor.fetchone()
        if not row:
            return {
                "trip_id": trip_id,
                "user_id": trip["user_id"],
                "is_started": 0,
                "is_completed": 0,
                "current_day": 1,
                "started_at": None,
                "completed_at": None
            }
        return dict(row)


# ---------------------------------------------------------------------------
# Today's Itinerary & Status Endpoints
# ---------------------------------------------------------------------------

@router.get("/{trip_id}/today")
def get_today_itinerary(
    trip_id: str,
    date: Optional[str] = Query(None),
    day: Optional[int] = Query(None),
    user_id: Optional[str] = Query(None)
):
    """
    Retrieves the current day's scheduled activities from the pre-trip itinerary,
    enriched with live status, live simulated conditions, and active alerts.
    """
    trip = _verify_trip_ownership(trip_id, user_id)
    itin = get_itinerary(trip_id)
    if not itin:
        raise HTTPException(status_code=404, detail="No pre-trip itinerary generated for this trip")

    total_days = trip.get("duration_days", 1)
    target_day = day
    if target_day is None and date:
        try:
            start_dt = datetime.strptime(trip["start_date"], "%Y-%m-%d")
            query_dt = datetime.strptime(date, "%Y-%m-%d")
            diff = (query_dt - start_dt).days + 1
            if 1 <= diff <= total_days:
                target_day = diff
            else:
                target_day = 1
        except Exception:
            target_day = 1
    if target_day is None:
        from app.services.trip_weather import today_india
        target_day = (today_india()-datetime.strptime(trip['start_date'],'%Y-%m-%d').date()).days+1
    target_day = max(1, min(total_days, target_day))

    try:
        start_dt = datetime.strptime(trip["start_date"], "%Y-%m-%d")
        day_date = (start_dt + timedelta(days=target_day - 1)).strftime("%Y-%m-%d")
    except Exception:
        day_date = trip.get("start_date", "")

    with get_connection() as conn:
        cursor = conn.cursor()

        # Load live activity statuses
        cursor.execute("SELECT activity_id, status, notes, updated_at FROM live_activity_status WHERE trip_id = ?", (trip_id,))
        statuses = {r[0]: {"status": r[1], "notes": r[2], "updated_at": r[3]} for r in cursor.fetchall()}

        # Load live alerts
        cursor.execute("""
            SELECT id, activity_id, severity, title, message, suggested_action, is_dismissed, created_at
            FROM live_alerts
            WHERE trip_id = ? AND day_number = ? AND is_dismissed = 0
        """, (trip_id, target_day))
        alerts_map: Dict[str, List[Dict[str, Any]]] = {}
        for r in cursor.fetchall():
            alert_dict = {
                "id": r[0],
                "activity_id": r[1],
                "severity": r[2],
                "title": r[3],
                "message": r[4],
                "suggested_action": r[5],
                "is_dismissed": bool(r[6]),
                "created_at": str(r[7])
            }
            alerts_map.setdefault(r[1], []).append(alert_dict)

        # Load simulated conditions active for this day
        cursor.execute("""
            SELECT id, condition_type, severity, description, source, created_at
            FROM live_conditions
            WHERE trip_id = ? AND day_number = ?
            ORDER BY created_at DESC
        """, (trip_id, target_day))
        conditions = [{
            "id": r[0],
            "condition_type": r[1],
            "severity": r[2],
            "description": r[3],
            "source": r[4],
            "created_at": str(r[5])
        } for r in cursor.fetchall()]

        # Filter activities for targeted day
        raw_activities = itin.get("activities", [])
        day_activities = []
        for act in raw_activities:
            if act.get("day_number") == target_day:
                act_id = act.get("activity_id") or act.get("id")
                _preserve_or_get_activity_context(conn, itin["id"], act_id, trip["user_id"], trip, act)

                live_st = statuses.get(act_id, {})
                act_status = live_st.get("status", "upcoming")
                act_notes = live_st.get("notes")

                day_activities.append({
                    "id": act.get("id"),
                    "activity_id": act_id,
                    "day_number": target_day,
                    "time_slot": act.get("time_slot"),
                    "title": act.get("title"),
                    "category": act.get("category"),
                    "description": act.get("description"),
                    "location_name": act.get("location_name") or act.get("title"),
                    "neighborhood": act.get("neighborhood"),
                    "latitude": act.get("latitude"),
                    "longitude": act.get("longitude"),
                    "duration_minutes": act.get("duration_minutes", 90),
                    "cost_estimate": act.get("cost_estimate", 0.0),
                    "transit_suggestion": act.get("transit_suggestion"),
                    "transit_duration_minutes": act.get("transit_duration_minutes", 15),
                    "why_it_suits": act.get("why_it_suits"),
                    "status": act_status,
                    "notes": act_notes,
                    "alerts": alerts_map.get(act_id, [])
                })

    from app.core.cost_model import estimate_cost
    cost = estimate_cost(trip, raw_activities)
    from app.services.trip_weather import weather_for_trip
    weather = weather_for_trip(trip)
    budget_alerts = [] if cost['budget_difference'] >= 0 else [{'type':'budget','message':cost['budget_message']}]
    return {
        "cost_estimate": cost,
        "budget_alerts": budget_alerts,
        "weather": weather,
        "trip_id": trip_id,
        "destination_name": trip.get("destination_name"),
        "day_number": target_day,
        "date": day_date,
        "total_days": total_days,
        "activities_count": len(day_activities),
        "activities": day_activities,
        "conditions": conditions,
        "is_simulated_environment": True
    }


@router.post("/{trip_id}/activity/{activity_id}/status")
def update_activity_status(trip_id: str, activity_id: str, req: StatusUpdateRequest):
    """Updates the live status of an activity during a trip (upcoming, in_progress, completed, skipped, delayed)."""
    _verify_trip_ownership(trip_id, req.user_id)

    if req.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{req.status}'. Must be one of: {sorted(list(VALID_STATUSES))}"
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO live_activity_status (trip_id, activity_id, status, notes, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(trip_id, activity_id) DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
        """, (trip_id, activity_id, req.status, req.notes))
        conn.commit()

    return {
        "status": "success",
        "trip_id": trip_id,
        "activity_id": activity_id,
        "new_status": req.status,
        "notes": req.notes
    }


# ---------------------------------------------------------------------------
# Simulated Conditions & Alert Generation Engine
# ---------------------------------------------------------------------------

def _evaluate_alerts_for_condition(
    conn: sqlite3.Connection,
    trip_id: str,
    day_number: int,
    condition_id: int,
    condition_type: str,
    severity: str,
    target_activity_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Generates targeted, non-duplicate alerts respecting daily budget limits and user profile."""
    itin = get_itinerary(trip_id)
    if not itin:
        return []

    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM live_alerts
        WHERE trip_id = ? AND day_number = ? AND is_dismissed = 0
    """, (trip_id, day_number))
    current_alerts_count = cursor.fetchone()[0]

    activities = [a for a in itin.get("activities", []) if a.get("day_number") == day_number]
    if target_activity_id:
        activities = [a for a in activities if (a.get("activity_id") == target_activity_id or a.get("id") == target_activity_id)]

    created_alerts = []

    for act in activities:
        if current_alerts_count >= MAX_ALERTS_PER_DAY:
            break

        act_id = act.get("activity_id") or act.get("id")
        act_title = act.get("title", "Scheduled Activity")
        category = act.get("category", "")
        tags = str(act.get("tags", "")).lower()

        alert_data = None

        if condition_type == "heavy_rain":
            if category in {"nature_outdoors", "scenic", "adventure"} or "outdoor" in tags:
                alert_data = {
                    "severity": "warning",
                    "title": f"Rain Alert: {act_title}",
                    "message": f"Heavy rain simulated during {act_title}. Outdoor exploration may be disrupted.",
                    "suggested_action": "Request an indoor alternative (museum, temple hall, or culinary spot)."
                }
        elif condition_type == "extreme_heat":
            if act.get("time_slot") in {"afternoon", "meal"} or category in {"nature_outdoors", "adventure"}:
                alert_data = {
                    "severity": "advisory",
                    "title": f"Heat Advisory: {act_title}",
                    "message": f"Extreme heat simulated during {act_title}. Hydration and sun protection recommended.",
                    "suggested_action": "Shift activity to morning or choose air-conditioned indoor alternatives."
                }
        elif condition_type == "closure":
            alert_data = {
                "severity": "critical",
                "title": f"Closure Disruption: {act_title}",
                "message": f"{act_title} is reported temporarily unavailable due to simulated facility closure.",
                "suggested_action": "Replan now to replace this attraction with a nearby open venue."
            }
        elif condition_type in {"traffic_delay", "strike"}:
            if act.get("time_slot") in {"afternoon", "evening"}:
                alert_data = {
                    "severity": "warning",
                    "title": f"Transit Delay: {act_title}",
                    "message": f"Severe transit congestion simulated en route to {act_title}.",
                    "suggested_action": "Depart earlier or select an alternative attraction within walking distance."
                }
        elif condition_type == "fatigue":
            alert_data = {
                "severity": "advisory",
                "title": f"Pacing Advisory: {act_title}",
                "message": f"Traveller fatigue reported before {act_title}.",
                "suggested_action": "Switch to a relaxed, low-intensity activity or take a rest break."
            }
        elif condition_type == "unexpected_crowding":
            alert_data = {
                "severity": "warning",
                "title": f"Crowd Warning: {act_title}",
                "message": f"Exceptional crowding simulated at {act_title}. Extended wait times expected.",
                "suggested_action": "Visit during off-peak hours or substitute with a less crowded local alternative."
            }

        if alert_data:
            cursor.execute("""
                SELECT id FROM live_alerts
                WHERE trip_id = ? AND day_number = ? AND activity_id = ? AND title = ? AND is_dismissed = 0
            """, (trip_id, day_number, act_id, alert_data["title"]))
            if cursor.fetchone():
                continue

            cursor.execute("""
                INSERT INTO live_alerts (
                    trip_id, day_number, activity_id, condition_id,
                    severity, title, message, suggested_action, is_dismissed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                trip_id,
                day_number,
                act_id,
                condition_id,
                alert_data["severity"],
                alert_data["title"],
                alert_data["message"],
                alert_data["suggested_action"]
            ))
            new_alert_id = cursor.lastrowid
            created_alerts.append({
                "id": new_alert_id,
                "activity_id": act_id,
                "severity": alert_data["severity"],
                "title": alert_data["title"],
                "message": alert_data["message"],
                "suggested_action": alert_data["suggested_action"]
            })
            current_alerts_count += 1

    conn.commit()
    return created_alerts


@router.post("/{trip_id}/simulate")
def simulate_condition(trip_id: str, req: SimulateConditionRequest):
    """
    Triggers a simulated environmental, weather, or travel condition.
    Explicitly tags the condition source as 'simulated' and generates proactive alerts.
    """
    _verify_trip_ownership(trip_id, req.user_id)

    if req.condition_type not in VALID_CONDITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid condition '{req.condition_type}'. Must be one of: {sorted(list(VALID_CONDITIONS))}"
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        desc = req.description or f"Simulated condition: {req.condition_type.replace('_', ' ')}"
        cursor.execute("""
            INSERT INTO live_conditions (trip_id, day_number, condition_type, severity, description, source)
            VALUES (?, ?, ?, ?, ?, 'simulated')
        """, (trip_id, req.day_number, req.condition_type, req.severity, desc))
        cond_id = cursor.lastrowid
        conn.commit()

        # Run alert generation engine
        alerts = _evaluate_alerts_for_condition(
            conn=conn,
            trip_id=trip_id,
            day_number=req.day_number,
            condition_id=cond_id,
            condition_type=req.condition_type,
            severity=req.severity,
            target_activity_id=req.target_activity_id
        )

    return {
        "status": "success",
        "trip_id": trip_id,
        "day_number": req.day_number,
        "condition_id": cond_id,
        "condition_type": req.condition_type,
        "severity": req.severity,
        "source": "simulated",
        "alerts_generated": alerts,
        "message": f"Successfully simulated {req.condition_type} for day {req.day_number}. Source is explicitly labelled 'simulated'."
    }


@router.get("/{trip_id}/alerts")
def get_alerts(trip_id: str, day: Optional[int] = Query(None), user_id: Optional[str] = Query(None)):
    """Retrieves all active alerts for a trip, optionally filtered by day."""
    _verify_trip_ownership(trip_id, user_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        if day is not None:
            cursor.execute("""
                SELECT id, day_number, activity_id, condition_id, severity, title, message, suggested_action, is_dismissed, created_at
                FROM live_alerts
                WHERE trip_id = ? AND day_number = ? AND is_dismissed = 0
                ORDER BY created_at DESC
            """, (trip_id, day))
        else:
            cursor.execute("""
                SELECT id, day_number, activity_id, condition_id, severity, title, message, suggested_action, is_dismissed, created_at
                FROM live_alerts
                WHERE trip_id = ? AND is_dismissed = 0
                ORDER BY day_number ASC, created_at DESC
            """, (trip_id,))

        alerts = [{
            "id": r[0],
            "day_number": r[1],
            "activity_id": r[2],
            "condition_id": r[3],
            "severity": r[4],
            "title": r[5],
            "message": r[6],
            "suggested_action": r[7],
            "is_dismissed": bool(r[8]),
            "created_at": str(r[9])
        } for r in cursor.fetchall()]

    return {"trip_id": trip_id, "alerts": alerts}


@router.post("/{trip_id}/alerts/{alert_id}/dismiss")
def dismiss_alert(trip_id: str, alert_id: int, user_id: Optional[str] = Query(None)):
    """Dismisses an active alert."""
    _verify_trip_ownership(trip_id, user_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE live_alerts SET is_dismissed = 1 WHERE id = ? AND trip_id = ?", (alert_id, trip_id))
        conn.commit()

    return {"status": "success", "alert_id": alert_id, "dismissed": True}


# ---------------------------------------------------------------------------
# Targeted Replanning Endpoints
# ---------------------------------------------------------------------------

@router.get("/{trip_id}/replan")
def get_replan_alternatives(
    trip_id: str,
    activity_id: str,
    condition: Optional[str] = Query(None),
    reason: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None)
):
    """
    Finds targeted replacement activities for an affected attraction using
    the existing get_slot_alternatives functionality, with environmental condition filtering.
    """
    trip = _verify_trip_ownership(trip_id, user_id)
    itin = get_itinerary(trip_id)
    if not itin:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    with get_connection() as conn:
        candidates = get_slot_alternatives(conn, trip["user_id"], itin["id"], activity_id)

        filtered = []
        for c in candidates:
            if condition == "heavy_rain":
                if c.get("category") == "nature_outdoors":
                    continue
            elif condition == "fatigue":
                if c.get("physical_intensity") == "high":
                    continue

            why = f"Recommended replacement for {condition or 'disruption'}"
            if c.get("neighborhood"):
                why += f" located in {c['neighborhood']}"
            c_dict = dict(c)
            c_dict["replan_suitability_reason"] = why
            filtered.append(c_dict)

        if not filtered and candidates:
            filtered = [dict(c) for c in candidates]

    return {
        "trip_id": trip_id,
        "affected_activity_id": activity_id,
        "condition_filtered_by": condition,
        "alternatives_count": len(filtered),
        "alternatives": filtered
    }


@router.post("/{trip_id}/replan")
def execute_replan(trip_id: str, req: ReplanExecuteRequest):
    """
    Executes targeted activity replanning:
    1. Replaces ONLY the specified affected activity row in itinerary_activities.
    2. Preserves all other activities and time slots untouched.
    3. Calls process_activity_feedback with action_type='modify' and is_trip_specific=True.
    4. Snapshots the historical context vector for the new activity.
    """
    trip = _verify_trip_ownership(trip_id, req.user_id)
    itin = get_itinerary(trip_id)
    if not itin:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, day_number, time_slot, order_index, cost_estimate
            FROM itinerary_activities
            WHERE itinerary_id = ? AND activity_id = ? AND (? IS NULL OR id = ?)
        """, (itin["id"], req.activity_id, req.itinerary_activity_id, req.itinerary_activity_id))
        target_row = cursor.fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail="Activity to replace not found in itinerary")

        row_id, day_num, slot, order_idx, old_cost = target_row

        cursor.execute("SELECT * FROM destination_activities WHERE id = ?", (req.replacement_activity_id,))
        rep_row = cursor.fetchone()
        if not rep_row:
            raise HTTPException(status_code=404, detail="Replacement activity not found in destination catalog")

        rep_act = dict(rep_row)
        from app.core.cost_model import activity_fee_inr
        new_cost = activity_fee_inr(rep_act)

        # Runtime reviews have already supplied feedback. Avoid changing the
        # status of other occurrences of the same place through the legacy
        # catalogue-ID feedback helper; keep legacy behaviour for old callers.
        if req.itinerary_activity_id is None:
            process_activity_feedback(
                conn=conn,
                user_id=trip["user_id"],
                trip_id=trip_id,
                itinerary_id=itin["id"],
                activity_id=req.activity_id,
                action_type="modify",
                rejection_reason=req.reason,
                is_trip_specific=req.is_trip_specific
            )

        # 2. Update ONLY the target activity row
        cursor.execute("""
            UPDATE itinerary_activities
            SET activity_id = ?,
                title = ?,
                category = ?,
                description = ?,
                location_name = ?,
                neighborhood = ?,
                latitude = ?,
                longitude = ?,
                duration_minutes = ?,
                cost_estimate = ?,
                why_it_suits = ?,
                status = 'modified',
                rejection_reason = NULL
            WHERE id = ?
        """, (
            rep_act["id"],
            rep_act["name"],
            rep_act["category"],
            rep_act.get("description", ""),
            rep_act["name"],
            rep_act["neighborhood"],
            rep_act.get("latitude"),
            rep_act.get("longitude"),
            rep_act.get("duration_minutes", 90),
            new_cost,
            f"Replanned during trip due to: {req.reason}",
            row_id
        ))

        # 3. Update live activity status
        cursor.execute("""
            INSERT INTO live_activity_status (trip_id, activity_id, status, notes, updated_at)
            VALUES (?, ?, 'upcoming', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(trip_id, activity_id) DO UPDATE SET
                status = 'upcoming',
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
        """, (trip_id, rep_act["id"], f"Replanned replacement for {req.activity_id}"))

        cursor.execute("""
            UPDATE live_alerts
            SET is_dismissed = 1
            WHERE trip_id = ? AND activity_id = ?
        """, (trip_id, req.activity_id))

        conn.commit()

        from app.itinerary_generator import get_itinerary_details
        get_itinerary_details(conn,trip['user_id'],trip_id)
        # 4. Snapshot historical 24-dim context vector for new activity
        _preserve_or_get_activity_context(conn, itin["id"], rep_act["id"], trip["user_id"], trip, {
            "day_number": day_num,
            "time_slot": slot,
            "category": rep_act["category"],
            "cost_estimate": new_cost,
            "tags": [rep_act["category"]]
        })

    return get_today_itinerary(trip_id=trip_id, day=day_num, user_id=trip["user_id"])


# ---------------------------------------------------------------------------
# Post-Trip Feedback & Genuine LinUCB Learning Endpoints
# ---------------------------------------------------------------------------

@router.post("/{trip_id}/complete")
def complete_trip(trip_id: str, req: CompleteTripRequest):
    """Marks a trip as completed. Only completed trips become eligible for post-trip evaluation."""
    trip = _verify_trip_ownership(trip_id, req.user_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO live_trip_state (trip_id, user_id, is_started, is_completed, current_day, completed_at)
            VALUES (?, ?, 1, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(trip_id) DO UPDATE SET
                is_completed = 1,
                completed_at = COALESCE(live_trip_state.completed_at, CURRENT_TIMESTAMP)
        """, (trip_id, trip["user_id"], trip.get("duration_days", 1)))
        conn.commit()

        conn.execute("UPDATE trips SET status='completed' WHERE id=?",(trip_id,))
        conn.execute("UPDATE itineraries SET status='completed' WHERE trip_id=?",(trip_id,))
        conn.commit()
        cursor.execute("SELECT * FROM live_trip_state WHERE trip_id = ?", (trip_id,))
        row = cursor.fetchone()
        return {
            "status": "success",
            "message": f"Trip to {trip['destination_name']} successfully marked as completed.",
            "trip_id": trip_id,
            "is_completed": 1,
            "completed_at": str(dict(row).get("completed_at"))
        }


@router.post("/{trip_id}/postrip")
def submit_post_trip_feedback(trip_id: str, req: PostTripFeedbackRequest):
    """
    Submits structured post-trip feedback for a completed trip.
    Genuinely updates the user's LinUCB recommendation policy using the original
    24-dimensional context vector for each evaluated activity.
    Enforces duplicate feedback protection and user isolation.
    """
    trip = _verify_trip_ownership(trip_id, req.user_id)
    itin = get_itinerary(trip_id)
    if not itin:
        raise HTTPException(status_code=404, detail="Itinerary not found for this trip")

    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Incomplete trip protection
        cursor.execute("SELECT is_completed FROM live_trip_state WHERE trip_id = ?", (trip_id,))
        state_row = cursor.fetchone()
        if not state_row or state_row[0] != 1:
            raise HTTPException(
                status_code=400,
                detail="Trip is not completed yet. Only completed trips can receive post-trip evaluation."
            )

        # 2. Duplicate submission protection for trip
        cursor.execute("SELECT id FROM live_postrip WHERE trip_id = ?", (trip_id,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=409,
                detail="Post-trip feedback has already been submitted for this trip."
            )

        # 3. Insert overall post-trip review inside transaction
        try:
            cursor.execute("""
                INSERT INTO live_postrip (
                    trip_id, user_id, overall_satisfaction, pace_rating, budget_accuracy,
                    itinerary_realistic, enjoyed_most, disliked, comments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trip_id,
                trip["user_id"],
                req.overall_satisfaction,
                req.pace_rating,
                req.budget_accuracy,
                req.itinerary_realistic,
                req.enjoyed_most,
                req.disliked,
                req.comments
            ))
            postrip_id = cursor.lastrowid

            # 4. Process per-activity feedback with LinUCB online policy updates
            policy = load_user_policy(conn, trip["user_id"])
            updates_applied = 0
            evaluated_activities = []

            for item in req.activity_ratings:
                if not (1 <= item.rating <= 5):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid rating {item.rating} for activity {item.activity_id}. Ratings must be between 1 and 5."
                    )

                # Prevent duplicate activity feedback
                cursor.execute("""
                    SELECT id FROM live_activity_feedback
                    WHERE trip_id = ? AND activity_id = ?
                """, (trip_id, item.activity_id))
                if cursor.fetchone():
                    continue  # Skip duplicate activity

                reward = rating_to_reward(item.rating)
                enjoyed = item.enjoyed if item.enjoyed is not None else (item.rating >= 4)

                # Locate category and itinerary details
                cursor.execute("""
                    SELECT ia.category, ia.itinerary_id, ia.day_number, ia.time_slot, ia.cost_estimate
                    FROM itinerary_activities ia
                    WHERE ia.itinerary_id = ? AND ia.activity_id = ?
                """, (itin["id"], item.activity_id))
                act_row = cursor.fetchone()

                if act_row:
                    category = act_row[0]
                    act_day = act_row[2]
                    act_slot = act_row[3]
                    act_cost = act_row[4]
                else:
                    cursor.execute("SELECT category, estimated_cost FROM destination_activities WHERE id = ?", (item.activity_id,))
                    dest_row = cursor.fetchone()
                    category = dest_row[0] if dest_row else "culture_history"
                    act_day = 1
                    act_slot = "afternoon"
                    act_cost = dest_row[1] if dest_row else 0.0

                arm_id = category if category in CANONICAL_ARMS else "culture_history"

                # Retrieve exact historical 24-dimensional context vector
                orig_context = _preserve_or_get_activity_context(
                    conn=conn,
                    itinerary_id=itin["id"],
                    activity_id=item.activity_id,
                    user_id=trip["user_id"],
                    trip=trip,
                    activity_row={
                        "category": category,
                        "day_number": act_day,
                        "time_slot": act_slot,
                        "cost_estimate": act_cost,
                        "tags": [category]
                    }
                )

                # Update user's LinUCB policy if remember_preference is enabled and reward != 0.0
                policy_updated = False
                if item.remember_preference and reward != 0.0:
                    context_arr = np.array(orig_context, dtype=float)
                    policy.update(arm_id, context_arr, reward)
                    policy_updated = True
                    updates_applied += 1

                # Log to live_activity_feedback
                cursor.execute("""
                    INSERT INTO live_activity_feedback (
                        trip_id, activity_id, rating, enjoyed, remember_preference,
                        reward_assigned, arm_id, context_vector_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trip_id,
                    item.activity_id,
                    item.rating,
                    1 if enjoyed else 0,
                    1 if item.remember_preference else 0,
                    reward,
                    arm_id,
                    json.dumps(orig_context)
                ))

                evaluated_activities.append({
                    "activity_id": item.activity_id,
                    "rating": item.rating,
                    "reward_assigned": reward,
                    "arm_id": arm_id,
                    "remember_preference": item.remember_preference,
                    "policy_updated": policy_updated
                })

            # Save persistent policy update to SQLite
            if updates_applied > 0:
                save_user_policy(conn, policy)

            conn.commit()

            # Contract integration: save to core_trip_feedback so Person C ranking queries it
            try:
                from app.core.stores import save_trip_feedback
                save_trip_feedback(
                    trip_id=trip_id,
                    user_id=trip["user_id"],
                    feedback={
                        "overall_satisfaction": req.overall_satisfaction,
                        "pace_rating": req.pace_rating,
                        "budget_accuracy": req.budget_accuracy,
                        "itinerary_realistic": req.itinerary_realistic,
                        "enjoyed_most": req.enjoyed_most,
                        "disliked": req.disliked,
                        "comments": req.comments,
                        "activities": evaluated_activities,
                    }
                )
            except Exception:
                pass
        except Exception:
            conn.rollback()
            raise

    return {
        "status": "success",
        "trip_id": trip_id,
        "postrip_id": postrip_id,
        "overall_satisfaction": req.overall_satisfaction,
        "activities_evaluated": len(evaluated_activities),
        "policy_updates_applied": updates_applied,
        "evaluated_details": evaluated_activities,
        "message": f"Successfully processed post-trip feedback. Applied {updates_applied} LinUCB policy updates using original 24-dim context vectors."
    }


@router.get("/{trip_id}/postrip")
def get_post_trip_feedback(trip_id: str, user_id: Optional[str] = Query(None)):
    """Retrieves submitted post-trip feedback and activity evaluations for a trip."""
    trip = _verify_trip_ownership(trip_id, user_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM live_postrip WHERE trip_id = ?", (trip_id,))
        review_row = cursor.fetchone()
        if not review_row:
            return {"trip_id": trip_id, "has_feedback": False, "feedback": None}

        review_dict = dict(review_row)
        cursor.execute("""
            SELECT laf.activity_id, laf.rating, laf.enjoyed, laf.remember_preference,
                   laf.reward_assigned, laf.arm_id, laf.submitted_at,
                   COALESCE(da.name, ia.title, laf.activity_id) as activity_title
            FROM live_activity_feedback laf
            LEFT JOIN destination_activities da ON laf.activity_id = da.id
            LEFT JOIN itinerary_activities ia ON laf.activity_id = ia.activity_id
            WHERE laf.trip_id = ?
        """, (trip_id,))
        activities = [dict(r) for r in cursor.fetchall()]

    return {
        "trip_id": trip_id,
        "has_feedback": True,
        "review": review_dict,
        "activity_evaluations": activities
    }


@router.get("/{user_id}/learning-summary")
def get_learning_summary(user_id: str, caller_user_id: Optional[str] = Query(None)):
    """
    Provides empirical post-trip learning insights:
    - Arm-by-arm LinUCB pull counts, total rewards, and weight vector norms.
    - Most and least enjoyed activity categories.
    - Transparent viva explanation of how feedback shifts future recommendation rankings.
    """
    if caller_user_id and caller_user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to learning summary")
    with get_connection() as conn:
        cursor = conn.cursor()

        # Load user policy
        policy = load_user_policy(conn, user_id)

        # Load all post-trip activity evaluations for this user's trips
        cursor.execute("""
            SELECT laf.arm_id, laf.rating, laf.reward_assigned, laf.enjoyed, laf.submitted_at
            FROM live_activity_feedback laf
            JOIN trips t ON laf.trip_id = t.id
            WHERE t.user_id = ?
            ORDER BY laf.submitted_at DESC
        """, (user_id,))
        feedback_rows = cursor.fetchall()
        # C: include exact per-occurrence shared-parameter reviews in the
        # existing learning summary without requiring any history-table writes.
        c_rows = cursor.execute("""SELECT ar.ratings_json,ar.ended_at,da.category FROM activity_runs ar
            JOIN trips t ON t.id=ar.trip_id LEFT JOIN destination_activities da ON da.id=ar.activity_id
            WHERE t.user_id=? AND ar.learning_applied=1""",(user_id,)).fetchall()
        for review in c_rows:
            scores=json.loads(review['ratings_json'] or '{}')
            if scores:
                mean=sum(scores.values())/len(scores)
                feedback_rows.append((review['category'] or 'culture_history',mean,(mean-3)/2,mean>=4,review['ended_at']))


        arm_stats: Dict[str, Dict[str, Any]] = {}
        for arm in CANONICAL_ARMS:
            arm_data = policy.arms.get(arm, {})
            weights = policy.get_arm_weights(arm)
            arm_stats[arm] = {
                "arm_id": arm,
                "pull_count": arm_data.get("pull_count", 0),
                "total_reward": round(arm_data.get("total_reward", 0.0), 2),
                "weight_norm": round(float(np.linalg.norm(weights)), 4),
                "feedback_count": 0,
                "avg_rating": None
            }

        arm_ratings: Dict[str, List[int]] = {}
        for r in feedback_rows:
            arm = r[0]
            rating = r[1]
            if arm in arm_stats:
                arm_stats[arm]["feedback_count"] += 1
                arm_ratings.setdefault(arm, []).append(rating)

        for arm, ratings in arm_ratings.items():
            if ratings:
                arm_stats[arm]["avg_rating"] = round(sum(ratings) / len(ratings), 2)

        # Identify most and least enjoyed categories
        rated_arms = [a for a in arm_stats.values() if a["avg_rating"] is not None]
        rated_arms.sort(key=lambda item: item["avg_rating"], reverse=True)

        most_enjoyed = rated_arms[0]["arm_id"] if rated_arms else None
        least_enjoyed = rated_arms[-1]["arm_id"] if rated_arms and len(rated_arms) > 1 else None

        # Academic transparency note
        explanation = (
            f"LinUCB policy updated across {len(feedback_rows)} post-trip activity evaluations. "
            f"Positive rewards (+0.5 to +1.0) increase theta weights for favored categories ({most_enjoyed or 'none'}), "
            f"raising future UCB exploitation terms. Dissatisfied activities apply negative updates (-0.5 to -1.0). "
            f"Note: Single-trip feedback initiates directional adaptation; full preference convergence requires repeated interactions."
        )

        return {
            "user_id": user_id,
            "total_evaluations_processed": len(feedback_rows),
            "most_enjoyed_category": most_enjoyed,
            "least_enjoyed_category": least_enjoyed,
            "arms_summary": list(arm_stats.values()),
            "explanation": explanation
        }



# ============================================================================
# Weather Alerts and Sunrise/Sunset Integration (Task B9)
# ============================================================================

@router.get("/{trip_id}/weather-alerts")
def get_live_weather_alerts(trip_id: str):
    """GET /api/live/{trip_id}/weather-alerts
    Retrieves live sunrise/sunset and daily weather alert variables via Open-Meteo.
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    from app.providers.geo import resolve_trip_location
    loc_info = resolve_trip_location(
        destination_id=trip.get("destination_id"),
        destination_name=trip.get("destination_name"),
        lat=trip.get("destination_lat"),
        lon=trip.get("destination_lon"),
        resolved_location=trip.get("resolved_location"),
    )
    lat = loc_info.get("lat")
    lon = loc_info.get("lon")
    if lat is None or lon is None:
        return {
            "trip_id": trip_id,
            "destination_name": trip.get("destination_name"),
            "available": False,
            "message": "Weather information unavailable",
            "forecast": None,
            "provenance": {"source": "unavailable", "is_live": False, "is_estimate": False},
        }

    from app.services.trip_weather import weather_for_trip
    forecast = weather_for_trip(trip)
    daily_list = forecast.get("daily_forecast") or []
    first_day = daily_list[0] if daily_list else {}
    sunrise = first_day.get("sunrise")
    sunset = first_day.get("sunset")

    return {
        "trip_id": trip_id,
        "destination_name": trip.get("destination_name"),
        "resolved_location": loc_info.get("resolved_location") or trip.get("destination_name"),
        "coordinates": {"lat": lat, "lon": lon},
        "sunrise": sunrise,
        "sunset": sunset,
        "golden_hour_morning": None,
        "golden_hour_evening": None,
        "forecast": forecast,
        "provenance": forecast.get("provenance", {
            "source": "open-meteo",
            "is_live": False,
            "is_estimate": True,
            "attribution": "Weather data by Open-Meteo.com"
        })
    }
