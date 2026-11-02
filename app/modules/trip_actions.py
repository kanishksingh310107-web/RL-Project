# Pre-Trip Itinerary Actions & Timeline Engine
# Owner: Person C (Integrator)
# Manages timed day-by-day itinerary views, activity swapping, removal,
# trip finalization, and the 'Start Trip' activation lifecycle.

import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query, status

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


class RemoveRequest(BaseModel):
    user_id: str
    reason: Optional[str] = "not_interested"


@router.get("/{trip_id}/timed-view")
def get_timed_itinerary_view(trip_id: str):
    """
    Returns an enriched day-by-day timeline view including:
    - Sightseeing activities
    - Transit / travel buffers between locations
    - Structured meal times (Lunch / Dinner)
    - Rest and relaxation breaks
    """
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

        return {
            "trip": trip,
            "itinerary": itinerary,
            "trip_status": trip_status,
            "has_itinerary": True,
            "days": days_output
        }


@router.post("/{trip_id}/finalize")
def finalize_trip_itinerary(trip_id: str, user_id: str = Query(...)):
    """
    Finalizes the itinerary, locking edits and transitioning trip status to 'finalized'.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        trip_row = cursor.execute("SELECT * FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id)).fetchone()
        if not trip_row:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        now_iso = datetime.datetime.utcnow().isoformat()
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
def start_trip(trip_id: str, user_id: str = Query(...)):
    """
    Activates the trip! Transitions trip status to 'active_trip'.
    Prepares the system for future live-trip features (today's schedule, real-time alerts).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        trip_row = cursor.execute("SELECT * FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id)).fetchone()
        if not trip_row:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        now_iso = datetime.datetime.utcnow().isoformat()
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
    payload: SwapRequest
):
    """
    Swaps an existing itinerary activity with an alternative suggested activity.
    Updates the LinUCB bandit (-0.4 for old activity, +1.0 for new replacement).
    """
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
        cursor.execute("""
            UPDATE itinerary_activities
            SET activity_id = ?, title = ?, category = ?, description = ?,
                location_name = ?, neighborhood = ?, latitude = ?, longitude = ?,
                duration_minutes = ?, cost_estimate = ?, status = 'accepted'
            WHERE itinerary_id = ? AND activity_id = ?
        """, (
            rep_data["id"], rep_data["name"], rep_data["category"], rep_data["description"],
            rep_data["name"], rep_data["neighborhood"], rep_data["latitude"], rep_data["longitude"],
            rep_data["duration_minutes"], rep_data["cost_amount"],
            itinerary_id, activity_id
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
                is_implicit=False
            )
        except Exception:
            pass

        return {
            "status": "swapped",
            "message": f"Successfully replaced with '{rep_data['name']}'.",
            "new_activity": rep_data
        }


@router.delete("/{trip_id}/activity/{activity_id}")
def remove_itinerary_activity(
    trip_id: str,
    activity_id: str,
    user_id: str = Query(...)
):
    """
    Removes an activity from the itinerary and informs the bandit policy.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        itin = cursor.execute("SELECT id FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not itin:
            raise HTTPException(status_code=404, detail="Itinerary not found")
        itinerary_id = itin[0]

        cursor.execute(
            "DELETE FROM itinerary_activities WHERE itinerary_id = ? AND activity_id = ?",
            (itinerary_id, activity_id)
        )
        conn.commit()

        # Update policy with reject signal
        try:
            process_activity_feedback(
                conn=conn,
                user_id=user_id,
                trip_id=trip_id,
                itinerary_id=itinerary_id,
                activity_id=activity_id,
                action_type="reject",
                rejection_reason="removed_by_user",
                is_trip_specific=True,
                is_implicit=False
            )
        except Exception:
            pass

        return {
            "status": "removed",
            "message": "Activity removed from your itinerary."
        }
