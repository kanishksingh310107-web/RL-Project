"""Suggestion Engine powered by Contextual LinUCB.
Provides 3 alternative activity recommendations when a user modifies or replaces
an activity in their timed itinerary.
"""
import json
import numpy as np
from typing import Dict, Any, List, Optional, Tuple

from app.database import get_connection
from app.rl_planner import (
    load_user_policy,
    extract_context_vector,
    is_activity_safe_and_valid,
    CANONICAL_ARMS
)


def _load_user_profile(conn, user_id: str) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT interests, pace, crowd_tolerance, budget_tier
        FROM traveller_profiles WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    prof = dict(row) if row else {}
    if "interests" in prof and isinstance(prof["interests"], str):
        try:
            prof["interests"] = json.loads(prof["interests"])
        except Exception:
            prof["interests"] = []

    cursor.execute("""
        SELECT avoidances, walking_tolerance, dietary
        FROM detailed_profiles WHERE user_id = ?
    """, (user_id,))
    det = cursor.fetchone()
    if det:
        d_dict = dict(det)
        try:
            prof["avoidances"] = json.loads(d_dict["avoidances"]) if d_dict.get("avoidances") else []
        except Exception:
            prof["avoidances"] = []
        prof["walking_tolerance"] = d_dict.get("walking_tolerance", "medium")
        try:
            prof["dietary"] = json.loads(d_dict["dietary"]) if d_dict.get("dietary") else []
        except Exception:
            prof["dietary"] = []
    return prof


def _load_trip(conn, trip_id: str) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
    row = cursor.fetchone()
    return dict(row) if row else {}


def _get_candidate_activities(conn, destination_id: str) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (destination_id,))
    rows = cursor.fetchall()
    if rows:
        return [dict(r) for r in rows]

    from app.activity_data import CURATED_ACTIVITIES
    return [dict(a) for a in CURATED_ACTIVITIES if a.get("destination_id") == destination_id]


def get_linucb_alternatives(
    conn,
    user_id: str,
    trip_id: str,
    activity_id: str,
    day_number: int = 1,
    slot_time: str = "afternoon",
    limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Queries Contextual LinUCB to suggest 3 alternative activities matching
    the user's profile interests and slot time (e.g. replacing an adventure trek
    with a peaceful temple or cafe).
    """
    trip = _load_trip(conn, trip_id)
    if not trip:
        raise ValueError(f"Trip {trip_id} not found")

    dest_id = trip.get("destination_id", "manali_spiti_india")
    total_days = trip.get("duration_days", 1)
    total_budget = trip.get("total_budget", 1000.0)

    user_profile = _load_user_profile(conn, user_id)
    policy = load_user_policy(conn, user_id)

    # Determine exclusions: the activity being replaced + activities already scheduled today
    cursor = conn.cursor()
    exclusions = {activity_id}

    # Also check if activity_id corresponds to a slot in timed_itinerary_slots
    cursor.execute("""
        SELECT activity_id FROM timed_itinerary_slots
        WHERE trip_id = ? AND day_number = ? AND activity_id IS NOT NULL
    """, (trip_id, day_number))
    for r in cursor.fetchall():
        if r[0]:
            exclusions.add(r[0])

    # Check itinerary_activities as well
    cursor.execute("""
        SELECT ia.activity_id FROM itinerary_activities ia
        JOIN itineraries i ON ia.itinerary_id = i.id
        WHERE i.trip_id = ? AND ia.day_number = ?
    """, (trip_id, day_number))
    for r in cursor.fetchall():
        if r[0]:
            exclusions.add(r[0])

    candidates = _get_candidate_activities(conn, dest_id)

    scored_candidates = []
    for cand in candidates:
        cand_id = cand.get("id")
        if cand_id in exclusions and cand_id != activity_id:
            continue
        if cand_id == activity_id:
            continue

        is_safe, _ = is_activity_safe_and_valid(cand, user_profile, exclusions)
        if not is_safe:
            continue

        arm_id = cand.get("category", "culture_history")
        if arm_id not in CANONICAL_ARMS:
            arm_id = "culture_history"

        context = extract_context_vector(
            user_profile=user_profile,
            trip_config={"duration_days": total_days, "total_budget": total_budget},
            day_number=day_number,
            total_days=total_days,
            time_slot=slot_time,
            activity=cand
        )

        total_score, exploitation, exploration = policy.predict_score(arm_id, context)

        cat_title = arm_id.replace("_", " ").title()
        reason = f"LinUCB Selected: Aligns with your preference for {cat_title} during {slot_time} (Score: {total_score:.2f})"

        scored_candidates.append({
            "id": cand_id,
            "activity_id": cand_id,
            "title": cand.get("name", cand.get("title", "Alternative Activity")),
            "name": cand.get("name", cand.get("title", "Alternative Activity")),
            "category": arm_id,
            "neighborhood": cand.get("neighborhood", "Local Area"),
            "location": cand.get("neighborhood", "Local Area"),
            "duration_minutes": cand.get("duration_minutes", 90),
            "estimated_cost": float(cand.get("cost_amount") or cand.get("estimated_cost", 10.0)),
            "cost_amount": float(cand.get("cost_amount") or cand.get("estimated_cost", 10.0)),
            "description": cand.get("description", ""),
            "score": round(float(total_score), 4),
            "exploitation": round(float(exploitation), 4),
            "exploration_bonus": round(float(exploration), 4),
            "reason": reason
        })

    # Sort descending by LinUCB total score
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)

    # If fewer than limit, relax exclusions to include other destination activities
    if len(scored_candidates) < limit:
        for cand in candidates:
            cand_id = cand.get("id")
            if cand_id == activity_id:
                continue
            if any(s["id"] == cand_id for s in scored_candidates):
                continue
            arm_id = cand.get("category", "culture_history")
            scored_candidates.append({
                "id": cand_id,
                "activity_id": cand_id,
                "title": cand.get("name", cand.get("title", "Alternative Activity")),
                "name": cand.get("name", cand.get("title", "Alternative Activity")),
                "category": arm_id,
                "neighborhood": cand.get("neighborhood", "Local Area"),
                "location": cand.get("neighborhood", "Local Area"),
                "duration_minutes": cand.get("duration_minutes", 90),
                "estimated_cost": float(cand.get("cost_amount") or cand.get("estimated_cost", 10.0)),
                "cost_amount": float(cand.get("cost_amount") or cand.get("estimated_cost", 10.0)),
                "description": cand.get("description", ""),
                "score": 0.5,
                "exploitation": 0.5,
                "exploration_bonus": 0.0,
                "reason": f"Alternative option: {arm_id.replace('_', ' ').title()}"
            })

    return scored_candidates[:limit]
