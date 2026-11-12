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
        target_day = 1
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

    return {
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
            WHERE itinerary_id = ? AND activity_id = ?
        """, (itin["id"], req.activity_id))
        target_row = cursor.fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail="Activity to replace not found in itinerary")

        row_id, day_num, slot, order_idx, old_cost = target_row

        cursor.execute("SELECT * FROM destination_activities WHERE id = ?", (req.replacement_activity_id,))
        rep_row = cursor.fetchone()
        if not rep_row:
            raise HTTPException(status_code=404, detail="Replacement activity not found in destination catalog")

        rep_act = dict(rep_row)
        new_cost = float(rep_act.get("cost_amount") or rep_act.get("estimated_cost", 0.0))

        # 1. Feedback for old activity (marked modified, trip-specific to preserve permanent policy)
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

        # Update total cost
        cursor.execute("""
            UPDATE itineraries
            SET total_estimated_cost = (
                SELECT COALESCE(SUM(cost_estimate), 0.0) FROM itinerary_activities WHERE itinerary_id = ?
            ), updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (itin["id"], itin["id"]))

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

    from app.providers.weather import get_weather_forecast
    forecast = get_weather_forecast(lat, lon, days=7)
    daily_list = forecast.get("daily_forecast") or []
    first_day = daily_list[0] if daily_list else {}
    sunrise = first_day.get("sunrise", "06:18 AM")
    sunset = first_day.get("sunset", "18:25 PM")

    return {
        "trip_id": trip_id,
        "destination_name": trip.get("destination_name"),
        "resolved_location": loc_info.get("resolved_location") or trip.get("destination_name"),
        "coordinates": {"lat": lat, "lon": lon},
        "sunrise": sunrise,
        "sunset": sunset,
        "golden_hour_morning": "06:18 - 07:15 AM",
        "golden_hour_evening": "17:30 - 18:25 PM",
        "forecast": forecast,
        "provenance": forecast.get("provenance", {
            "source": "open-meteo",
            "is_live": False,
            "is_estimate": True,
            "attribution": "Weather data by Open-Meteo.com"
        })
    }
