# Pre-Trip Itinerary Actions & Timeline Engine
# Owner: Person C (Integrator)
# Manages timed day-by-day itinerary views, activity swapping, removal,
# trip finalization, and the 'Start Trip' activation lifecycle.

import datetime
import uuid
import re
import hashlib
from typing import Dict, Any, List, Optional
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from fastapi import APIRouter, HTTPException, Query, status, Request

from app.database import get_connection
from app.modules.common import _decode
from app.rl_planner import process_activity_feedback
from app.itinerary_generator import get_slot_alternatives

MODULE = {
    "id": "itinerary_editor",
    "title": "Trip Itinerary",
    "icon": "fa-calendar-check",
    "owner": "C"
}

router = APIRouter(prefix="/api/trip-actions", tags=["trip-actions"])


class CustomActivityCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    category: Literal['culture_history','nature_outdoors','food_dining','adventure','relaxation','shopping_local','scenic','appointment'] = 'appointment'
    day_number: int = Field(ge=1, le=90, strict=True)
    duration_minutes: int = Field(ge=15, le=720, strict=True)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location_name: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    cost_estimate_inr: int = Field(0, ge=0, le=1_000_000_000, strict=True)
    is_pinned: bool = False
    is_fixed_booking: bool = False
    booking_label: Optional[str] = Field(None, max_length=120)

    @field_validator('title','location_name','booking_label',mode='before')
    @classmethod
    def clean_custom_text(cls,value,info):
        if value is None and info.field_name!='title': return value
        if not isinstance(value,str): raise ValueError('Enter text for '+info.field_name.replace('_',' ')+'.')
        cleaned=re.sub(r'<[^>]*>','',value).strip()
        if not cleaned: raise ValueError(info.field_name.replace('_',' ').title()+' cannot be empty.')
        return cleaned

    @field_validator('start_time','end_time')
    @classmethod
    def valid_booking_time(cls,value):
        if value is None: return value
        try:
            if len(value)!=5 or datetime.datetime.strptime(value,'%H:%M').strftime('%H:%M')!=value: raise ValueError
        except (TypeError,ValueError) as exc:
            raise ValueError('Use 24-hour HH:MM booking times.') from exc
        return value

    @model_validator(mode='after')
    def valid_booking(self):
        if self.is_fixed_booking:
            if not self.start_time or not self.end_time:
                raise ValueError('Fixed bookings need start and end times.')
            start=datetime.datetime.strptime(self.start_time,'%H:%M')
            end=datetime.datetime.strptime(self.end_time,'%H:%M')
            if end<=start: raise ValueError('Booking end must be after its start on the same day.')
            self.duration_minutes=int((end-start).total_seconds()//60)
        elif bool(self.start_time)!=bool(self.end_time):
            raise ValueError('Provide both booking times or neither.')
        return self


def _refresh_custom_schedule(conn, trip_id):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trip_schedule_prefs'").fetchone() and conn.execute('SELECT 1 FROM trip_schedule_prefs WHERE trip_id=?',(trip_id,)).fetchone():
        from app.services.timed_itinerary import regenerate_timed_itinerary_for_trip
        regenerate_timed_itinerary_for_trip(conn,trip_id)


def _require_trip_owner(request,trip_id,user_id=None):
    authorization=request.headers.get('authorization','')
    token_hash=hashlib.sha256(authorization[7:].strip().encode()).hexdigest() if authorization.startswith('Bearer ') else ''
    with get_connection() as conn:
        session=conn.execute('SELECT user_id FROM auth_sessions WHERE token_hash=? AND expires_at>?',
            (token_hash,datetime.datetime.now(datetime.timezone.utc).isoformat())).fetchone()
        trip=conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone()
        if not trip: raise HTTPException(404,detail={'detail':'Trip not found.','code':'TRIP_NOT_FOUND'})
        if not session or session['user_id']!=trip['user_id'] or (user_id and user_id!=session['user_id']):
            raise HTTPException(403,detail={'detail':'This trip belongs to another user.','code':'NOT_OWNER'})
        return dict(trip),session['user_id']


@router.post('/{trip_id}/activities')
def add_custom_activity(trip_id: str,payload: CustomActivityCreate,request: Request):
    authorization=request.headers.get('authorization','')
    if not authorization.startswith('Bearer '):
        raise HTTPException(403,detail={'detail':'Sign in to edit this trip.','code':'AUTH_REQUIRED'})
    token_hash=hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
    with get_connection() as conn:
        session=conn.execute('SELECT user_id FROM auth_sessions WHERE token_hash=? AND expires_at>?',
            (token_hash,datetime.datetime.now(datetime.timezone.utc).isoformat())).fetchone()
        trip=conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone()
        if not trip: raise HTTPException(404,detail={'detail':'Trip not found.','code':'TRIP_NOT_FOUND'})
        if not session or session['user_id']!=payload.user_id or trip['user_id']!=payload.user_id:
            raise HTTPException(403,detail={'detail':'This trip belongs to another user.','code':'NOT_OWNER'})
        runtime=conn.execute('SELECT status FROM trip_runtime WHERE trip_id=?',(trip_id,)).fetchone()
        if runtime and runtime['status']!='draft':
            raise HTTPException(409,detail={'detail':'Only draft itineraries can be edited.','code':'ITINERARY_LOCKED'})
        if payload.day_number>trip['duration_days']:
            raise HTTPException(422,detail={'detail':'Activity day must fall within the trip dates.','code':'INVALID_DAY','field':'day_number'})
        itinerary=conn.execute('SELECT * FROM itineraries WHERE trip_id=? AND user_id=?',(trip_id,payload.user_id)).fetchone()
        if not itinerary: raise HTTPException(404,detail={'detail':'Generate the itinerary before adding activities.','code':'ITINERARY_NOT_FOUND'})
        occurrence_id=str(uuid.uuid4())
        custom_id='custom_'+occurrence_id
        order=conn.execute('SELECT COALESCE(MAX(order_index),-1)+1 FROM itinerary_activities WHERE itinerary_id=? AND day_number=?',
                           (itinerary['id'],payload.day_number)).fetchone()[0]
        start_hour=int(payload.start_time[:2]) if payload.start_time else 9
        slot='morning' if start_hour<12 else 'afternoon' if start_hour<18 else 'evening'
        conn.execute('''INSERT INTO itinerary_activities(id,itinerary_id,day_number,time_slot,activity_id,title,category,
            description,location_name,neighborhood,latitude,longitude,duration_minutes,cost_estimate,status,order_index,
            is_pinned,is_fixed_booking,booking_start_time,booking_end_time,booking_label)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (occurrence_id,itinerary['id'],payload.day_number,slot,custom_id,payload.title,payload.category,
             payload.booking_label or ('Custom appointment' if payload.category=='appointment' else 'Traveler-added activity'),
             payload.location_name,payload.location_name,payload.latitude,payload.longitude,payload.duration_minutes,
             payload.cost_estimate_inr,'proposed',order,int(payload.is_pinned or payload.is_fixed_booking),int(payload.is_fixed_booking),
             payload.start_time if payload.is_fixed_booking else None,payload.end_time if payload.is_fixed_booking else None,
             payload.booking_label))
        conn.commit()
        _refresh_custom_schedule(conn,trip_id)
        return {'status':'created','occurrence_id':occurrence_id,'activity_id':custom_id,
                'day_number':payload.day_number,'is_pinned':bool(payload.is_pinned or payload.is_fixed_booking),
                'is_fixed_booking':payload.is_fixed_booking}


def init_tables(conn):
    """Ensure trips table has status and lifecycle timestamp columns."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(trips)")
    cols = [r[1] for r in cursor.fetchall()]

    if "status" not in cols:
        cursor.execute("ALTER TABLE trips ADD COLUMN status TEXT DEFAULT 'planning'")
    if "finalized_at" not in cols:
        cursor.execute("ALTER TABLE trips ADD COLUMN finalized_at TIMESTAMP")
    if "started_at" not in cols:
        cursor.execute("ALTER TABLE trips ADD COLUMN started_at TIMESTAMP")
    conn.commit()


class SwapRequest(BaseModel):
    user_id: str
    replacement_activity_id: str
    is_trip_specific: bool = True
    occurrence_id: Optional[str] = None


class RemoveRequest(BaseModel):
    user_id: str
    reason: Optional[str] = "not_interested"


@router.get("/{trip_id}/timed-view")
def get_timed_itinerary_view(trip_id: str,request: Request):
    """
    Returns an enriched day-by-day timeline view including:
    - Sightseeing activities
    - Transit / travel buffers between locations
    - Structured meal times (Lunch / Dinner)
    - Rest and relaxation breaks
    """
    _require_trip_owner(request,trip_id)
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Fetch Trip details
        trip_row = cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if not trip_row:
            raise HTTPException(status_code=404, detail="Trip not found")
        trip = _decode(trip_row)
        trip_status = trip.get("status") or "planning"

        # 2. Fetch Itinerary
        itin_row = cursor.execute("SELECT * FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not itin_row:
            return {
                "trip": trip,
                "has_itinerary": False,
                "days": [],
                "message": "Itinerary has not been generated yet for this trip."
            }
        itinerary = _decode(itin_row)

        # 3. Fetch all itinerary activities ordered by day and index
        act_rows = cursor.execute(
            "SELECT * FROM itinerary_activities WHERE itinerary_id = ? ORDER BY day_number, order_index",
            (itinerary["id"],)
        ).fetchall()
        activities = [_decode(a) for a in act_rows]

        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trip_schedule_prefs'").fetchone() and conn.execute('SELECT 1 FROM trip_schedule_prefs WHERE trip_id=?',(trip_id,)).fetchone():
            from app.services.timed_itinerary import regenerate_timed_itinerary_for_trip, init_timed_tables
            from app.itinerary_generator import get_itinerary_details
            shared = get_itinerary_details(conn,trip['user_id'],trip_id)
            init_timed_tables(conn)
            stored=conn.execute('SELECT id FROM timed_itineraries WHERE trip_id=?',(trip_id,)).fetchone()
            if not stored:
                schedule=regenerate_timed_itinerary_for_trip(conn,trip_id,trip['user_id'])
            else:
                rows=[dict(r) for r in conn.execute('SELECT * FROM timed_itinerary_slots WHERE trip_id=? ORDER BY day_number,order_index,id',(trip_id,))]
                grouped={day:[] for day in range(1,trip.get('duration_days',1)+1)}
                for slot in rows:
                    if slot.get('provenance_json'):
                        try: slot['provenance']=__import__('json').loads(slot.pop('provenance_json'))
                        except (TypeError,ValueError): pass
                    grouped.setdefault(slot['day_number'],[]).append(slot)
                schedule={'days':[{'day_number':day,'slots':slots,'note':None,
                    'arrival_marker':trip.get('hotel_arrival_time') if day==1 else None,
                    'departure_marker':trip.get('hotel_departure_time') if day==trip.get('duration_days') else None,
                    'total_cost':sum(float(s.get('estimated_cost') or 0) for s in slots)}
                    for day,slots in sorted(grouped.items())]}
            days_output = []
            for day in schedule['days']:
                timeline = []
                for slot in day['slots']:
                    original = next((a for a in activities if a['day_number']==day['day_number'] and a['activity_id']==slot['activity_id']),{})
                    timeline.append(dict(original, type=slot['slot_type'], id=original.get('id'),
                        activity_id=slot['activity_id'], title=slot['title'], description=slot['description'],
                        time_range=slot['start_time']+' – '+slot['end_time'], duration_minutes=slot['duration_mins'],
                        cost_estimate=slot['estimated_cost'], can_edit=slot['slot_type'] in ('activity','shopping'),
                        slot_type_label=slot['slot_type'].replace('_',' ').title(), badge_color='blue'))
                days_output.append(dict(day_number=day['day_number'], timeline=timeline, note=day['note'],
                    arrival_marker=day['arrival_marker'],departure_marker=day['departure_marker'],
                    total_cost=shared['days'][day['day_number']-1]['total_cost'],formatted_date=f"Day {day['day_number']}"))
            return dict(trip=trip,itinerary=itinerary,trip_status=trip_status,has_itinerary=True,days=days_output,cost_estimate=shared['cost_estimate'])

        # Group activities by day
        days_map: Dict[int, List[Dict[str, Any]]] = {}
        total_days = trip.get("duration_days", 1)
        for d in range(1, total_days + 1):
            days_map[d] = []

        for act in activities:
            day_num = act.get("day_number", 1)
            if day_num not in days_map:
                days_map[day_num] = []
            days_map[day_num].append(act)

        # Build realistic timed schedule per day with Transit, Meals, and Rest
        days_output = []
        start_date_str = trip.get("start_date")

        for day_num, day_acts in sorted(days_map.items()):
            # Calculate calendar date for this day
            cal_date_str = ""
            if start_date_str:
                try:
                    dt = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    cal_date_str = (dt + datetime.timedelta(days=day_num - 1)).strftime("%A, %d %b %Y")
                except ValueError:
                    cal_date_str = f"Day {day_num}"

            timeline_blocks = []

            # Block 1: Morning Activity (09:30 AM - 11:30 AM)
            morning_act = next((a for a in day_acts if a.get("time_slot") == "morning"), None)
            if not morning_act and day_acts:
                morning_act = day_acts[0]

            if morning_act:
                timeline_blocks.append({
                    "type": "activity",
                    "slot_type_label": "Sightseeing",
                    "badge_color": "blue",
                    "id": morning_act["id"],
                    "activity_id": morning_act["activity_id"],
                    "title": morning_act["title"],
                    "category": morning_act["category"],
                    "description": morning_act.get("description", ""),
                    "location_name": morning_act.get("location_name", ""),
                    "neighborhood": morning_act.get("neighborhood", ""),
                    "time_range": "09:30 AM – 11:30 AM",
                    "duration_minutes": morning_act.get("duration_minutes", 120),
                    "cost_estimate": morning_act.get("cost_estimate", 0.0),
                    "can_edit": True
                })

                # Transit Buffer after morning activity
                transit_desc = morning_act.get("transit_suggestion") or "Local auto / taxi transfer"
                transit_mins = morning_act.get("transit_duration_minutes") or 30
                timeline_blocks.append({
                    "type": "transit",
                    "slot_type_label": "Travel & Transit",
                    "badge_color": "slate",
                    "title": f"Transfer ({transit_mins} mins)",
                    "description": f"{transit_desc} to next destination.",
                    "time_range": "11:30 AM – 12:15 PM",
                    "duration_minutes": transit_mins,
                    "cost_estimate": 5.0,
                    "can_edit": False
                })

            # Block 2: Eating Time / Lunch (12:15 PM - 01:45 PM)
            timeline_blocks.append({
                "type": "meal",
                "slot_type_label": "Dining & Eating",
                "badge_color": "amber",
                "title": f"Local Lunch & Cuisine Tasting ({trip.get('destination_name', 'Local')} specialties)",
                "description": "Midday dining break to savor authentic regional dishes and refresh.",
                "time_range": "12:15 PM – 01:45 PM",
                "duration_minutes": 90,
                "cost_estimate": 15.0,
                "can_edit": False
            })

            # Block 3: Afternoon Activity (02:00 PM - 04:30 PM)
            afternoon_act = next((a for a in day_acts if a.get("time_slot") == "afternoon"), None)
            if not afternoon_act and len(day_acts) > 1:
                afternoon_act = day_acts[1]

            if afternoon_act:
                timeline_blocks.append({
                    "type": "activity",
                    "slot_type_label": "Afternoon Exploration",
                    "badge_color": "blue",
                    "id": afternoon_act["id"],
                    "activity_id": afternoon_act["activity_id"],
                    "title": afternoon_act["title"],
                    "category": afternoon_act["category"],
                    "description": afternoon_act.get("description", ""),
                    "location_name": afternoon_act.get("location_name", ""),
                    "neighborhood": afternoon_act.get("neighborhood", ""),
                    "time_range": "02:00 PM – 04:30 PM",
                    "duration_minutes": afternoon_act.get("duration_minutes", 150),
                    "cost_estimate": afternoon_act.get("cost_estimate", 0.0),
                    "can_edit": True
                })

            # Block 4: Rest & Relaxation Time (04:30 PM - 06:00 PM)
            timeline_blocks.append({
                "type": "rest",
                "slot_type_label": "Rest & Leisure",
                "badge_color": "emerald",
                "title": "Rest & Hotel Tea Break",
                "description": "Unscheduled downtime for relaxation, foot soak, or quiet tea time before the evening.",
                "time_range": "04:30 PM – 06:00 PM",
                "duration_minutes": 90,
                "cost_estimate": 0.0,
                "can_edit": False
            })

            # Block 5: Evening Activity / Dinner (06:30 PM - 09:00 PM)
            evening_act = next((a for a in day_acts if a.get("time_slot") == "evening"), None)
            if not evening_act and len(day_acts) > 2:
                evening_act = day_acts[2]

            if evening_act:
                timeline_blocks.append({
                    "type": "activity",
                    "slot_type_label": "Evening Activity",
                    "badge_color": "indigo",
                    "id": evening_act["id"],
                    "activity_id": evening_act["activity_id"],
                    "title": evening_act["title"],
                    "category": evening_act["category"],
                    "description": evening_act.get("description", ""),
                    "location_name": evening_act.get("location_name", ""),
                    "neighborhood": evening_act.get("neighborhood", ""),
                    "time_range": "06:30 PM – 08:30 PM",
                    "duration_minutes": evening_act.get("duration_minutes", 120),
                    "cost_estimate": evening_act.get("cost_estimate", 0.0),
                    "can_edit": True
                })

            days_output.append({
                "day_number": day_num,
                "formatted_date": cal_date_str,
                "timeline": timeline_blocks
            })

        from app.core.cost_model import estimate_cost
        cost = estimate_cost(trip,activities)
        from app.itinerary_generator import get_itinerary_details
        shared = get_itinerary_details(conn,trip['user_id'],trip_id)
        for day in days_output:
            daily = next((d for d in shared['days'] if d['day_number']==day['day_number']),None)
            day['total_cost'] = daily['total_cost'] if daily else 0
            for block in day['timeline']:
                if block['type']=='transit':
                    block['cost_estimate'] = round(cost['cost_breakdown']['local_transit']['per_party']/cost['days'],2)
                if block['type']=='meal':
                    block['cost_estimate'] = round(cost['cost_breakdown']['food']['per_party']/cost['days'],2)
        return {"trip": trip, "itinerary": itinerary,"cost_estimate":cost,
            "trip_status": trip_status, "has_itinerary": True,"days": days_output}


@router.post("/{trip_id}/finalize")
def finalize_trip_itinerary(trip_id: str, request: Request, user_id: str = Query(...)):
    """
    Finalizes the itinerary, locking edits and transitioning trip status to 'finalized'.
    """
    _require_trip_owner(request,trip_id,user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        trip_row = cursor.execute("SELECT * FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id)).fetchone()
        if not trip_row:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute("UPDATE trips SET status = 'finalized', finalized_at = ? WHERE id = ?", (now_iso, trip_id))
        cursor.execute("UPDATE itineraries SET status = 'finalized', updated_at = ? WHERE trip_id = ?", (now_iso, trip_id))
        conn.commit()

        return {
            "trip_id": trip_id,
            "status": "finalized",
            "finalized_at": now_iso,
            "message": "Itinerary has been finalized! You can now start the trip when ready."
        }


@router.post("/{trip_id}/start")
def start_trip(trip_id: str, request: Request, user_id: str = Query(...)):
    """
    Activates the trip! Transitions trip status to 'active_trip'.
    Prepares the system for future live-trip features (today's schedule, real-time alerts).
    """
    _require_trip_owner(request,trip_id,user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        trip_row = cursor.execute("SELECT * FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id)).fetchone()
        if not trip_row:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute("UPDATE trips SET status = 'active_trip', started_at = ? WHERE id = ?", (now_iso, trip_id))
        cursor.execute("UPDATE itineraries SET status = 'active_trip', updated_at = ? WHERE trip_id = ?", (now_iso, trip_id))
        conn.commit()

        return {
            "trip_id": trip_id,
            "status": "active_trip",
            "started_at": now_iso,
            "message": "🚀 Trip started! Real-time location tracking and proactive assistance are now active."
        }


@router.post("/{trip_id}/activity/{activity_id}/swap")
def swap_itinerary_activity(
    trip_id: str,
    activity_id: str,
    payload: SwapRequest,
    request: Request
):
    """
    Swaps an existing itinerary activity with an alternative suggested activity.
    Updates the LinUCB bandit (-0.4 for old activity, +1.0 for new replacement).
    """
    _require_trip_owner(request,trip_id,payload.user_id)
    with get_connection() as conn:
        cursor = conn.cursor()

        # Find itinerary for this trip
        itin = cursor.execute("SELECT id FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not itin:
            raise HTTPException(status_code=404, detail="Itinerary not found for this trip")
        itinerary_id = itin[0]

        # Fetch replacement activity details from catalogue
        cursor.execute("SELECT * FROM destination_activities WHERE id = ?", (payload.replacement_activity_id,))
        rep_row = cursor.fetchone()
        if not rep_row:
            raise HTTPException(status_code=404, detail=f"Replacement activity '{payload.replacement_activity_id}' not found")
        rep_data = dict(rep_row)

        # Update the slot in itinerary_activities
        occurrence_id=payload.occurrence_id or activity_id
        target=cursor.execute("SELECT id,activity_id FROM itinerary_activities WHERE itinerary_id=? AND (id=? OR activity_id=?) ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END",
                              (itinerary_id,occurrence_id,activity_id,occurrence_id)).fetchall()
        if not target:
            raise HTTPException(status_code=404,detail='Activity occurrence not found')
        if len(target)>1 and target[0]['id']!=occurrence_id:
            raise HTTPException(status_code=409,detail={'detail':'This place occurs more than once. Use an itinerary occurrence ID.','code':'AMBIGUOUS_OCCURRENCE','field':'occurrence_id'})
        occurrence_id=target[0]['id']
        old_activity_id=target[0]['activity_id']
        cursor.execute("""
            UPDATE itinerary_activities
            SET activity_id = ?, title = ?, category = ?, description = ?,
                location_name = ?, neighborhood = ?, latitude = ?, longitude = ?,
                duration_minutes = ?, cost_estimate = ?, status = 'accepted'
            WHERE itinerary_id = ? AND id = ?
        """, (
            rep_data["id"], rep_data["name"], rep_data["category"], rep_data["description"],
            rep_data["name"], rep_data["neighborhood"], rep_data["latitude"], rep_data["longitude"],
            rep_data["duration_minutes"], __import__("app.core.cost_model",fromlist=["activity_fee_inr"]).activity_fee_inr(rep_data),
            itinerary_id, occurrence_id
        ))
        conn.commit()

        # Update LinUCB parameters
        try:
            process_activity_feedback(
                conn=conn,
                user_id=payload.user_id,
                trip_id=trip_id,
                itinerary_id=itinerary_id,
                activity_id=rep_data["id"],
                action_type="modify",
                is_trip_specific=payload.is_trip_specific,
                is_implicit=False,
                occurrence_id=occurrence_id
            )
        except Exception:
            pass

        _refresh_custom_schedule(conn,trip_id)
        return {
            "status": "swapped",
            "message": f"Successfully replaced with '{rep_data['name']}'.",
            "new_activity": rep_data
        }


@router.delete("/{trip_id}/activity/{activity_id}")
def remove_itinerary_activity(
    trip_id: str,
    activity_id: str,
    request: Request,
    user_id: str = Query(...)
):
    """
    Removes an activity from the itinerary and informs the bandit policy.
    """
    _require_trip_owner(request,trip_id,user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        itin = cursor.execute("SELECT id FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not itin:
            raise HTTPException(status_code=404, detail="Itinerary not found")
        itinerary_id = itin[0]

        matches=cursor.execute('SELECT id,activity_id FROM itinerary_activities WHERE itinerary_id=? AND (id=? OR activity_id=?) ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END',
                               (itinerary_id,activity_id,activity_id,activity_id)).fetchall()
        if not matches:
            raise HTTPException(status_code=404,detail='Activity occurrence not found')
        if len(matches)>1 and matches[0]['id']!=activity_id:
            raise HTTPException(status_code=409,detail={'detail':'This place occurs more than once. Use an itinerary occurrence ID.','code':'AMBIGUOUS_OCCURRENCE','field':'activity_id'})
        occurrence_id=matches[0]['id']
        catalogue_id=matches[0]['activity_id']

        # Update policy with reject signal
        try:
            process_activity_feedback(
                conn=conn,
                user_id=user_id,
                trip_id=trip_id,
                itinerary_id=itinerary_id,
                activity_id=catalogue_id,
                action_type="reject",
                rejection_reason="removed_by_user",
                is_trip_specific=True,
                is_implicit=False,
                occurrence_id=occurrence_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=409,detail={'detail':str(exc),'code':'OCCURRENCE_CONFLICT'})

        _refresh_custom_schedule(conn,trip_id)
        return {
            "status": "removed",
            "message": "Activity removed from your itinerary."
        }


@router.post("/{trip_id}/activity/{activity_id}/restore")
def restore_rejected_occurrence(trip_id: str, activity_id: str, request: Request, user_id: str = Query(...)):
    """Restore one rejected occurrence by its stable itinerary row ID."""
    _require_trip_owner(request,trip_id,user_id)
    with get_connection() as conn:
        itinerary = conn.execute('SELECT id FROM itineraries WHERE trip_id=? AND user_id=?',(trip_id,user_id)).fetchone()
        if not itinerary:
            raise HTTPException(404,detail='Itinerary not found or unauthorized')
        row = conn.execute("SELECT id FROM itinerary_activities WHERE itinerary_id=? AND id=? AND status='rejected'",
                           (itinerary['id'],activity_id)).fetchone()
        if not row:
            raise HTTPException(404,detail='Rejected itinerary occurrence not found')
        conn.execute("UPDATE itinerary_activities SET status='proposed',rejection_reason=NULL WHERE id=?",(row['id'],))
        conn.commit()
        _refresh_custom_schedule(conn,trip_id)
    return {'status':'restored','occurrence_id':row['id']}

# ---------------------------------------------------------------------------
# Rescheduling and Day-Switching Models & Endpoints
# ---------------------------------------------------------------------------

class RescheduleRequest(BaseModel):
    user_id: str
    occurrence_id: Optional[str] = Field(None,min_length=1,max_length=100)
    direction: Literal['earlier','later'] = 'later'
    target_day: Optional[int] = Field(None,ge=1,le=90,strict=True)


class SwitchDaysRequest(BaseModel):
    user_id: str
    activity_id_a: str
    activity_id_b: str


def _resolve_occurrence(conn,itinerary_id,identifier):
    select='SELECT id,day_number,time_slot,order_index,title FROM itinerary_activities WHERE itinerary_id=?'
    exact=conn.execute(select+' AND id=?',(itinerary_id,identifier)).fetchone()
    if exact: return exact
    matches=conn.execute(select+' AND activity_id=? ORDER BY day_number,order_index,id',
                         (itinerary_id,identifier)).fetchall()
    if not matches: raise HTTPException(404,detail='Activity occurrence not found')
    if len(matches)>1:
        raise HTTPException(409,detail={'detail':'This place occurs more than once. Use an itinerary occurrence ID.','code':'AMBIGUOUS_OCCURRENCE','field':'occurrence_id'})
    return matches[0]


@router.post("/{trip_id}/activity/{activity_id}/reschedule")
def reschedule_itinerary_activity(
    trip_id: str,
    activity_id: str,
    payload: RescheduleRequest,
    request: Request
):
    """
    Reschedules an existing activity:
    - Moves it earlier or later within the day by swapping order/time with the adjacent activity.
    - Or moves it to another specified day.
    """
    _require_trip_owner(request,trip_id,payload.user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        itin = cursor.execute("SELECT id FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not itin:
            raise HTTPException(status_code=404, detail="Itinerary not found")
        itinerary_id = itin[0]

        target = _resolve_occurrence(conn,itinerary_id,payload.occurrence_id or activity_id)

        t_id, t_day, t_slot, t_order, t_title = target

        if payload.target_day and payload.target_day != t_day:
            # Move to another day: append as highest order on target day
            cursor.execute("""
                SELECT COALESCE(MAX(order_index), 0) + 1 FROM itinerary_activities
                WHERE itinerary_id = ? AND day_number = ?
            """, (itinerary_id, payload.target_day))
            new_order = cursor.fetchone()[0]
            cursor.execute("""
                UPDATE itinerary_activities
                SET day_number = ?, order_index = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (payload.target_day, new_order, t_id))
            conn.commit()
            _refresh_custom_schedule(conn,trip_id)
            return {
                "status": "rescheduled",
                "message": f"Moved '{t_title}' to Day {payload.target_day}.",
                "activity_id": activity_id,
                "new_day": payload.target_day
            }

        # Swap order with adjacent activity within the same day
        if payload.direction == "earlier":
            cursor.execute("""
                SELECT id, time_slot, order_index, title FROM itinerary_activities
                WHERE itinerary_id = ? AND day_number = ? AND order_index < ?
                ORDER BY order_index DESC LIMIT 1
            """, (itinerary_id, t_day, t_order))
        else: # later
            cursor.execute("""
                SELECT id, time_slot, order_index, title FROM itinerary_activities
                WHERE itinerary_id = ? AND day_number = ? AND order_index > ?
                ORDER BY order_index ASC LIMIT 1
            """, (itinerary_id, t_day, t_order))

        adjacent = cursor.fetchone()
        if not adjacent:
            direction_label = "earlier" if payload.direction == "earlier" else "later"
            return {
                "status": "unchanged",
                "message": f"'{t_title}' is already the {direction_label} activity on Day {t_day}. You can move it to another day or replace it.",
                "activity_id": activity_id
            }

        adj_id, adj_slot, adj_order, adj_title = adjacent

        # Swap time slots and order indices
        cursor.execute("""
            UPDATE itinerary_activities
            SET time_slot = ?, order_index = ?
            WHERE id = ?
        """, (adj_slot, adj_order, t_id))

        cursor.execute("""
            UPDATE itinerary_activities
            SET time_slot = ?, order_index = ?
            WHERE id = ?
        """, (t_slot, t_order, adj_id))

        conn.commit()
        _refresh_custom_schedule(conn,trip_id)
        return {
            "status": "rescheduled",
            "message": f"Rescheduled '{t_title}' with '{adj_title}' on Day {t_day}.",
            "activity_id": activity_id,
            "direction": payload.direction
        }


@router.post("/{trip_id}/switch-days")
def switch_activities_between_days(
    trip_id: str,
    payload: SwitchDaysRequest,
    request: Request
):
    """
    Swaps two activities between different days without duplicate entries or scheduling conflicts.
    """
    _require_trip_owner(request,trip_id,payload.user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        itin = cursor.execute("SELECT id FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not itin:
            raise HTTPException(status_code=404, detail="Itinerary not found")
        itinerary_id = itin[0]

        act_a = _resolve_occurrence(conn,itinerary_id,payload.activity_id_a)
        act_b = _resolve_occurrence(conn,itinerary_id,payload.activity_id_b)

        id_a, day_a, slot_a, order_a, title_a = act_a
        id_b, day_b, slot_b, order_b, title_b = act_b
        if day_a==day_b:
            raise HTTPException(status_code=422,detail={'detail':'Choose activities from two different days.','code':'SAME_DAY','field':'activity_id_b'})
        next_a=conn.execute('SELECT COALESCE(MAX(order_index),-1)+1 FROM itinerary_activities WHERE itinerary_id=? AND day_number=? AND id!=?',
                             (itinerary_id,day_b,id_b)).fetchone()[0]
        next_b=conn.execute('SELECT COALESCE(MAX(order_index),-1)+1 FROM itinerary_activities WHERE itinerary_id=? AND day_number=? AND id!=?',
                             (itinerary_id,day_a,id_a)).fetchone()[0]

        # Atomically swap day, slot, and order
        cursor.execute("""
            UPDATE itinerary_activities
            SET day_number = ?, time_slot = ?, order_index = ?
            WHERE id = ?
        """, (day_b, slot_a, next_a, id_a))

        cursor.execute("""
            UPDATE itinerary_activities
            SET day_number = ?, time_slot = ?, order_index = ?
            WHERE id = ?
        """, (day_a, slot_b, next_b, id_b))

        conn.commit()
        _refresh_custom_schedule(conn,trip_id)

        return {
            "status": "switched",
            "message": f"Successfully switched '{title_a}' (Day {day_a}) with '{title_b}' (Day {day_b}).",
            "activity_a": {"id": payload.activity_id_a, "new_day": day_b},
            "activity_b": {"id": payload.activity_id_b, "new_day": day_a}
        }


@router.get("/{trip_id}/activity/{activity_id}/alternatives")
def get_activity_alternatives_detailed(
    trip_id: str,
    activity_id: str,
    user_id: Optional[str] = Query(None)
):
    """
    Retrieves alternative recommendations, distinguishing between:
    - Truly fresh alternatives (not anywhere in this trip).
    - Already scheduled activities in other days (available to switch between days).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        itin = cursor.execute("SELECT id FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not itin:
            raise HTTPException(status_code=404, detail="Itinerary not found")
        itinerary_id = itin[0]

        target_user = user_id
        if not target_user:
            t_row = cursor.execute("SELECT user_id FROM trips WHERE id = ?", (trip_id,)).fetchone()
            target_user = t_row[0] if t_row else ""

        alts = get_slot_alternatives(conn, target_user, itinerary_id, activity_id)

        fresh = [a for a in alts if not a.get("is_already_scheduled")]
        scheduled_elsewhere = [a for a in alts if a.get("is_already_scheduled")]

        no_fresh_msg = None
        if not fresh:
            no_fresh_msg = "All curated highlights for this destination are currently in your itinerary. You can switch activities with another day or reschedule."

        return {
            "trip_id": trip_id,
            "activity_id": activity_id,
            "fresh_alternatives": fresh,
            "switch_day_options": scheduled_elsewhere,
            "all_options": alts,
            "notice": no_fresh_msg
        }

