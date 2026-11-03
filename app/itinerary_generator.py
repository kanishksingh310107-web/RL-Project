# Adaptive Itinerary Generator and Day-by-Day Scheduler
# Uses Contextual LinUCB policy, geographical neighborhood clustering,
# pacing controls, and constraint satisfaction to construct realistic daily plans.

import json
import uuid
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.rl_planner import (
    LinUCBPolicy, load_user_policy, extract_context_vector,
    is_activity_safe_and_valid, CANONICAL_ARMS
)

def _get_trip_exclusions(conn, trip_id: str) -> set:
    """Retrieve activities already rejected in this specific trip."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT activity_id FROM rl_feedback_log
        WHERE trip_id = ? AND action_type = 'reject'
    """, (trip_id,))
    return set(row[0] for row in cursor.fetchall())

def _load_user_profile(conn, user_id: str) -> Dict[str, Any]:
    """Retrieve unified traveller profile data."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM traveller_profiles WHERE user_id = ?", (user_id,))
    base_row = cursor.fetchone()
    profile = dict(base_row) if base_row else {}

    if "interests" in profile and isinstance(profile["interests"], str):
        try:
            profile["interests"] = json.loads(profile["interests"])
        except Exception:
            profile["interests"] = []

    cursor.execute("SELECT * FROM detailed_profiles WHERE user_id = ?", (user_id,))
    det_row = cursor.fetchone()
    if det_row:
        det_dict = dict(det_row)
        for field in ["avoidances", "accessibility", "dietary"]:
            if field in det_dict and isinstance(det_dict[field], str):
                try:
                    profile[field] = json.loads(det_dict[field])
                except Exception:
                    profile[field] = []
        profile["walking_tolerance"] = det_dict.get("walking_tolerance", "medium")
        profile["schedule_density"] = det_dict.get("schedule_density", "balanced_2_3")
        profile["stay_style"] = det_dict.get("stay_style", "boutique")
        profile["transit_pref"] = det_dict.get("transit_pref", "public_transit")

    return profile

def generate_itinerary(conn, user_id: str, trip_id: str) -> Dict[str, Any]:
    """Generates a complete day-by-day itinerary tailored by LinUCB."""
    cursor = conn.cursor()

    # 1. Verify trip existence and ownership
    cursor.execute("SELECT * FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id))
    trip_row = cursor.fetchone()
    if not trip_row:
        raise ValueError("Trip not found or unauthorized access")
    trip = dict(trip_row)

    # 2. Check if itinerary already exists for this trip
    cursor.execute("SELECT id FROM itineraries WHERE trip_id = ?", (trip_id,))
    existing_itin = cursor.fetchone()
    if existing_itin:
        itinerary_id = existing_itin[0]
        # Clear existing activities to regenerate clean plan
        cursor.execute("DELETE FROM itinerary_activities WHERE itinerary_id = ?", (itinerary_id,))
    else:
        itinerary_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO itineraries (id, trip_id, user_id, title, total_days, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (
            itinerary_id,
            trip_id,
            user_id,
            f"Personalised Itinerary: {trip['destination_name']}",
            trip["duration_days"]
        ))

    # 3. Load user profile, LinUCB policy, and candidates
    user_profile = _load_user_profile(conn, user_id)
    policy = load_user_policy(conn, user_id)
    trip_exclusions = _get_trip_exclusions(conn, trip_id)

    cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (trip["destination_id"],))
    candidate_rows = cursor.fetchall()
    all_candidates = [dict(r) for r in candidate_rows]

    # Integrate Places API dynamically if database has few or no activities for this destination
    if len(all_candidates) < 8:
        try:
            from app.services.places_service import get_places_for_destination
            places_res = get_places_for_destination(trip["destination_id"])
            if places_res and places_res.get("places"):
                for p in places_res["places"]:
                    p_id = p.get("place_id") or f"{trip['destination_id']}_{p['name'].lower().replace(' ', '_')[:20]}"
                    cat_raw = p.get("category", "culture")
                    cat_map = {
                        "culture": "culture_history",
                        "nature": "nature_outdoors",
                        "food": "food_dining",
                        "adventure": "nature_outdoors",
                        "rest": "relaxation_wellness"
                    }
                    can_cat = cat_map.get(cat_raw, "culture_history")
                    dur_mins = int((p.get("typical_duration_hours") or 1.5) * 60)
                    cost = 250.0 if can_cat == "culture_history" else (450.0 if can_cat == "food_dining" else 150.0)
                    cursor.execute("""
                        INSERT OR IGNORE INTO destination_activities (
                            id, destination_id, name, category, neighborhood,
                            latitude, longitude, duration_minutes, cost_tier,
                            cost_amount, physical_intensity, crowd_level,
                            opening_time, closing_time, tags, avoidance_triggers,
                            description, photo_url, data_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        p_id,
                        trip["destination_id"],
                        p["name"],
                        can_cat,
                        f"Central {trip.get('destination_name', 'Area')}",
                        p.get("lat") or 0.0,
                        p.get("lon") or 0.0,
                        dur_mins,
                        "budget",
                        cost,
                        "moderate",
                        "moderate",
                        "09:00",
                        "18:00",
                        json.dumps([can_cat, "places_service"]),
                        json.dumps([]),
                        f"Explore {p['name']}, a verified highlight in {trip.get('destination_name', 'destination')}.",
                        None,
                        places_res.get("source", "places_service")
                    ))
                conn.commit()
                cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (trip["destination_id"],))
                all_candidates = [dict(r) for r in cursor.fetchall()]
        except Exception:
            pass

    if not all_candidates:
        # Fallback dummy candidate if no specific activities in DB for unseeded destinations
        all_candidates = [{
            "id": f"{trip['destination_id']}_city_walk",
            "destination_id": trip["destination_id"],
            "name": f"Historic Walking Exploration of {trip['destination_name']}",
            "category": "culture_history",
            "neighborhood": "Central Old Town",
            "latitude": 35.0,
            "longitude": 135.0,
            "duration_minutes": 120,
            "cost_tier": "free",
            "cost_amount": 0.0,
            "physical_intensity": "low",
            "crowd_level": "moderate",
            "opening_time": "09:00",
            "closing_time": "18:00",
            "tags": json.dumps(["culture_history", "scenic"]),
            "avoidance_triggers": json.dumps([]),
            "description": f"Explore historic neighborhoods and architecture of {trip['destination_name']}.",
            "photo_url": None,
            "data_source": "estimated"
        }]

    # 4. Group candidates by neighborhood to enable realistic geographical clustering
    neighborhoods = sorted(list(set(c["neighborhood"] for c in all_candidates)))

    # Schedule parameters based on pace
    pace = trip.get("travel_pace", "balanced")
    if pace == "relaxed":
        slots = ["morning", "meal", "afternoon"]
    elif pace == "packed":
        slots = ["morning", "morning_extra", "meal", "afternoon", "evening"]
    else: # balanced
        slots = ["morning", "meal", "afternoon", "evening"]

    used_activity_ids = set(trip_exclusions)
    total_itinerary_cost = 0.0
    start_dt = datetime.strptime(trip["start_date"], "%Y-%m-%d")

    day_models = []

    for day_idx in range(1, trip["duration_days"] + 1):
        day_date = (start_dt + timedelta(days=day_idx - 1)).strftime("%Y-%m-%d")
        day_neighborhood = neighborhoods[(day_idx - 1) % len(neighborhoods)]

        day_activities = []
        used_activity_ids_today = set()
        preceding_act = None
        order_idx = 0

        for slot in slots:
            slot_name = "morning" if "morning" in slot else slot
            is_meal = (slot == "meal")

            # Prefer activities not yet scheduled anywhere in the trip; fall back to not used today
            unused_in_trip = [c for c in all_candidates if c["id"] not in used_activity_ids and c["id"] not in trip_exclusions]
            unused_today = [c for c in all_candidates if c["id"] not in used_activity_ids_today and c["id"] not in trip_exclusions]
            candidates_pool = unused_in_trip if unused_in_trip else unused_today

            # Filter candidates for this slot
            valid_candidates = []
            for c in candidates_pool:
                is_safe, _ = is_activity_safe_and_valid(c, user_profile, trip_exclusions)
                if not is_safe:
                    continue

                if is_meal:
                    if c["category"] == "food_dining":
                        valid_candidates.append(c)
                else:
                    if c["category"] != "food_dining":
                        valid_candidates.append(c)

            # If no candidate found in category, relax category constraint from pool
            if not valid_candidates:
                for c in candidates_pool:
                    is_safe, _ = is_activity_safe_and_valid(c, user_profile, trip_exclusions)
                    if is_safe:
                        valid_candidates.append(c)

            if not valid_candidates:
                continue

            # LinUCB Scoring
            scored_candidates = []
            for c in valid_candidates:
                arm_id = c["category"] if c["category"] in CANONICAL_ARMS else "culture_history"
                context_x = extract_context_vector(
                    user_profile=user_profile,
                    trip_config=trip,
                    day_number=day_idx,
                    total_days=trip["duration_days"],
                    time_slot=slot_name,
                    activity=c,
                    preceding_activity=preceding_act
                )
                score, exploitation, exploration = policy.predict_score(arm_id, context_x)

                # Small neighborhood clustering bonus
                if c["neighborhood"] == day_neighborhood:
                    score += 0.25

                scored_candidates.append((score, c, exploitation, exploration))

            scored_candidates.sort(key=lambda item: item[0], reverse=True)
            chosen_score, chosen_act, exp_val, bonus_val = scored_candidates[0]

            used_activity_ids.add(chosen_act["id"])
            used_activity_ids_today.add(chosen_act["id"])

            # Transit suggestion
            if preceding_act:
                if preceding_act.get("neighborhood") == chosen_act.get("neighborhood"):
                    transit_text = f"5-10 min stroll within {chosen_act['neighborhood']}"
                    transit_mins = 8
                else:
                    transit_text = f"15-20 min transit from {preceding_act['neighborhood']} to {chosen_act['neighborhood']}"
                    transit_mins = 18
            else:
                transit_text = f"Depart from lodging to {chosen_act['neighborhood']}"
                transit_mins = 15

            # Tailored explanation
            why_text = f"Chosen for your interest in {chosen_act['category'].replace('_', ' ')} with convenient pacing."
            if bonus_val > 0.35:
                why_text += " (Exploration candidate to discover new local preferences)"

            act_record_id = str(uuid.uuid4())
            cost_val = float(chosen_act.get("cost_amount", 0.0))
            total_itinerary_cost += cost_val

            cursor.execute("""
                INSERT INTO itinerary_activities (
                    id, itinerary_id, day_number, time_slot, activity_id,
                    title, category, description, location_name, neighborhood,
                    latitude, longitude, duration_minutes, cost_estimate,
                    transit_suggestion, transit_duration_minutes, why_it_suits,
                    status, order_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)
            """, (
                act_record_id,
                itinerary_id,
                day_idx,
                slot_name,
                chosen_act["id"],
                chosen_act["name"],
                chosen_act["category"],
                chosen_act["description"],
                chosen_act["name"],
                chosen_act["neighborhood"],
                chosen_act.get("latitude"),
                chosen_act.get("longitude"),
                chosen_act.get("duration_minutes", 90),
                cost_val,
                transit_text,
                transit_mins,
                why_text,
                order_idx
            ))

            day_activities.append({
                "id": act_record_id,
                "itinerary_id": itinerary_id,
                "day_number": day_idx,
                "time_slot": slot_name,
                "activity_id": chosen_act["id"],
                "title": chosen_act["name"],
                "category": chosen_act["category"],
                "description": chosen_act["description"],
                "location_name": chosen_act["name"],
                "neighborhood": chosen_act["neighborhood"],
                "latitude": chosen_act.get("latitude"),
                "longitude": chosen_act.get("longitude"),
                "duration_minutes": chosen_act.get("duration_minutes", 90),
                "cost_estimate": cost_val,
                "transit_suggestion": transit_text,
                "transit_duration_minutes": transit_mins,
                "why_it_suits": why_text,
                "status": "proposed",
                "photo_url": chosen_act.get("photo_url"),
                "data_source": chosen_act.get("data_source", "curated")
            })

            preceding_act = chosen_act
            order_idx += 1

        day_models.append({
            "day_number": day_idx,
            "date": day_date,
            "theme": f"Exploring {day_neighborhood}",
            "neighborhood": day_neighborhood,
            "activities": day_activities,
            "total_cost": sum(a["cost_estimate"] for a in day_activities),
            "total_duration_minutes": sum(a["duration_minutes"] for a in day_activities)
        })

    # Update total cost in itinerary
    cursor.execute("""
        UPDATE itineraries
        SET total_estimated_cost = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (total_itinerary_cost, itinerary_id))
    conn.commit()

    return {
        "id": itinerary_id,
        "trip_id": trip_id,
        "user_id": user_id,
        "title": f"Personalised Itinerary: {trip['destination_name']}",
        "destination_name": trip["destination_name"],
        "total_days": trip["duration_days"],
        "status": "active",
        "total_estimated_cost": total_itinerary_cost,
        "summary_notes": f"Generated via LinUCB Contextual Bandit policy for {trip['travellers_count']} traveler(s) at {trip['travel_pace']} pace.",
        "days": day_models,
        "created_at": str(datetime.now()),
        "updated_at": str(datetime.now())
    }

def get_itinerary_details(conn, user_id: str, trip_id: str) -> Optional[Dict[str, Any]]:
    """Fetches full structured itinerary with all activities."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.id, i.trip_id, i.user_id, i.title, i.total_days, i.status,
               i.total_estimated_cost, i.summary_notes, i.created_at, i.updated_at,
               t.destination_name, t.start_date
        FROM itineraries i
        JOIN trips t ON i.trip_id = t.id
        WHERE i.trip_id = ? AND i.user_id = ?
    """, (trip_id, user_id))
    row = cursor.fetchone()
    if not row:
        return None

    itin_id = row[0]
    total_days = row[4]
    start_dt = datetime.strptime(row[11], "%Y-%m-%d")

    cursor.execute("""
        SELECT ia.id, ia.itinerary_id, ia.day_number, ia.time_slot, ia.activity_id,
               ia.title, ia.category, ia.description, ia.location_name, ia.neighborhood,
               ia.latitude, ia.longitude, ia.duration_minutes, ia.cost_estimate,
               ia.transit_suggestion, ia.transit_duration_minutes, ia.why_it_suits,
               ia.status, ia.rejection_reason, ia.order_index, da.photo_url, da.data_source
        FROM itinerary_activities ia
        LEFT JOIN destination_activities da ON ia.activity_id = da.id
        WHERE ia.itinerary_id = ?
        ORDER BY ia.day_number ASC, ia.order_index ASC
    """, (itin_id,))
    act_rows = cursor.fetchall()

    days_dict = {}
    for d in range(1, total_days + 1):
        day_date = (start_dt + timedelta(days=d - 1)).strftime("%Y-%m-%d")
        days_dict[d] = {
            "day_number": d,
            "date": day_date,
            "theme": f"Day {d} Exploration",
            "neighborhood": "Local Area",
            "activities": [],
            "total_cost": 0.0,
            "total_duration_minutes": 0
        }

    for a in act_rows:
        day_n = a[2]
        act_dict = {
            "id": a[0],
            "itinerary_id": a[1],
            "day_number": day_n,
            "time_slot": a[3],
            "activity_id": a[4],
            "title": a[5],
            "category": a[6],
            "description": a[7],
            "location_name": a[8],
            "neighborhood": a[9],
            "latitude": a[10],
            "longitude": a[11],
            "duration_minutes": a[12],
            "cost_estimate": a[13],
            "transit_suggestion": a[14],
            "transit_duration_minutes": a[15],
            "why_it_suits": a[16],
            "status": a[17],
            "rejection_reason": a[18],
            "order_index": a[19],
            "photo_url": a[20],
            "data_source": a[21] or "curated"
        }
        if day_n in days_dict:
            days_dict[day_n]["activities"].append(act_dict)
            days_dict[day_n]["total_cost"] += a[13]
            days_dict[day_n]["total_duration_minutes"] += a[12]
            if a[9]:
                days_dict[day_n]["neighborhood"] = a[9]
                days_dict[day_n]["theme"] = f"Exploring {a[9]}"

    return {
        "id": itin_id,
        "trip_id": row[1],
        "user_id": row[2],
        "title": row[3],
        "destination_name": row[10],
        "total_days": total_days,
        "status": row[5],
        "total_estimated_cost": row[6],
        "summary_notes": row[7],
        "days": list(days_dict.values()),
        "created_at": str(row[8]),
        "updated_at": str(row[9])
    }

def get_slot_alternatives(conn, user_id: str, itinerary_id: str, activity_id: str) -> List[Dict[str, Any]]:
    """Finds top 3 candidate replacements for an activity when user requests MODIFY."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ia.day_number, ia.time_slot, ia.category, ia.neighborhood,
               t.destination_id, i.trip_id
        FROM itinerary_activities ia
        JOIN itineraries i ON ia.itinerary_id = i.id
        JOIN trips t ON i.trip_id = t.id
        WHERE ia.itinerary_id = ? AND ia.activity_id = ?
    """, (itinerary_id, activity_id))
    row = cursor.fetchone()
    if not row:
        return []

    day_num, slot, category, neighborhood, dest_id, trip_id = row

    user_profile = _load_user_profile(conn, user_id)
    policy = load_user_policy(conn, user_id)
    trip_exclusions = _get_trip_exclusions(conn, trip_id)
    trip_exclusions.add(activity_id)

    # Exclude activities already scheduled on this same day and the activity itself
    # Map all scheduled activities in this itinerary across all days
    cursor.execute("""
        SELECT day_number, time_slot, activity_id, title FROM itinerary_activities
        WHERE itinerary_id = ?
    """, (itinerary_id,))
    all_scheduled = cursor.fetchall()
    scheduled_map = {r[2]: {"day_number": r[0], "time_slot": r[1], "title": r[3]} for r in all_scheduled}

    cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (dest_id,))
    all_candidates = [dict(r) for r in cursor.fetchall()]

    # If few candidates in DB, populate from Places API
    if len(all_candidates) < 6:
        try:
            from app.services.places_service import get_places_for_destination
            places_res = get_places_for_destination(dest_id)
            if places_res and places_res.get("places"):
                for p in places_res["places"]:
                    p_id = p.get("place_id") or f"{dest_id}_{p['name'].lower().replace(' ', '_')[:20]}"
                    cat_map = {"culture": "culture_history", "nature": "nature_outdoors", "food": "food_dining"}
                    can_cat = cat_map.get(p.get("category", "culture"), "culture_history")
                    cursor.execute("""
                        INSERT OR IGNORE INTO destination_activities (
                            id, destination_id, name, category, neighborhood,
                            latitude, longitude, duration_minutes, cost_tier,
                            cost_amount, physical_intensity, crowd_level,
                            opening_time, closing_time, tags, avoidance_triggers,
                            description, photo_url, data_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        p_id, dest_id, p["name"], can_cat, "Local Area",
                        p.get("lat") or 0.0, p.get("lon") or 0.0, 90, "budget", 250.0,
                        "moderate", "moderate", "09:00", "18:00", "[]", "[]",
                        f"Visit {p['name']}.", None, places_res.get("source", "places_service")
                    ))
                conn.commit()
                cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (dest_id,))
                all_candidates = [dict(r) for r in cursor.fetchall()]
        except Exception:
            pass

    fresh_candidates = []
    switch_candidates = []

    for c in all_candidates:
        if c["id"] == activity_id:
            continue

        is_safe, _ = is_activity_safe_and_valid(c, user_profile, trip_exclusions)
        if not is_safe:
            continue

        arm_id = c["category"] if c["category"] in CANONICAL_ARMS else "culture_history"
        context_x = extract_context_vector(
            user_profile=user_profile,
            trip_config={"duration_days": 5},
            day_number=day_num,
            total_days=5,
            time_slot=slot,
            activity=c
        )
        score, _, _ = policy.predict_score(arm_id, context_x)
        if c.get("neighborhood") == neighborhood:
            score += 0.2

        c_copy = dict(c)
        if c["id"] in scheduled_map:
            # Already in another day of this itinerary
            c_copy["is_already_scheduled"] = True
            c_copy["scheduled_day"] = scheduled_map[c["id"]]["day_number"]
            c_copy["scheduled_time"] = scheduled_map[c["id"]]["time_slot"]
            c_copy["alternative_type"] = "switch_day"
            c_copy["reason"] = f"Already in your itinerary on Day {c_copy['scheduled_day']} ({c_copy['scheduled_time']}). You can switch activities with that day."
            switch_candidates.append((score, c_copy))
        else:
            # Truly fresh alternative
            c_copy["is_already_scheduled"] = False
            c_copy["alternative_type"] = "new_replacement"
            c_copy["reason"] = "Personalized alternative matching your profile and destination."
            fresh_candidates.append((score, c_copy))

    fresh_candidates.sort(key=lambda item: item[0], reverse=True)
    switch_candidates.sort(key=lambda item: item[0], reverse=True)

    # Return top 3 fresh candidates, or if none, transparently return switch candidates
    if fresh_candidates:
        result = [item[1] for item in fresh_candidates[:3]]
    else:
        result = [item[1] for item in switch_candidates[:3]]

    return result
