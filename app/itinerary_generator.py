# Adaptive Itinerary Generator and Day-by-Day Scheduler
# Uses Contextual LinUCB policy, geographical neighborhood clustering,
# pacing controls, and constraint satisfaction to construct realistic daily plans.

import json
import uuid
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.core.cost_model import activity_fee_inr
from app.core.assumptions import FALLBACK_CATEGORY_PRICE_INR

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
    """Retrieve base, detailed, and deep-personalisation inputs for planning."""
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

    # The itinerary used to stop at Level 2, so completed deep answers never
    # reached its candidate filters or LinUCB context. Merge saved answers and
    # normalize the high-impact constraints consumed by the planner.
    cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
    precision_row = cursor.fetchone()
    precision_answers = {}
    if precision_row and precision_row["answers_json"]:
        try:
            precision_answers = json.loads(precision_row["answers_json"])
        except (TypeError, ValueError):
            precision_answers = {}
    profile["precision_answers"] = precision_answers
    profile.update(precision_answers)

    avoidances = precision_answers.get("d22_avoidances") or profile.get("avoidances") or []
    if isinstance(avoidances, str):
        avoidances = [avoidances]
    profile["avoidances"] = avoidances

    allergens = precision_answers.get("d11_food_allergens") or []
    if isinstance(allergens, str):
        allergens = [allergens]
    if allergens and "no_allergies" not in allergens:
        profile["allergies"] = allergens
        existing_diet = profile.get("dietary") or []
        if isinstance(existing_diet, str):
            existing_diet = [existing_diet]
        profile["dietary"] = list(dict.fromkeys(existing_diet + allergens))

    walking = precision_answers.get("d19_daily_walking_km")
    if walking in ("under_2km", "2_5km"):
        profile["walking_tolerance"] = "minimal" if walking == "under_2km" else "low"

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

    cursor.execute('UPDATE itineraries SET total_days=? WHERE id=?',(trip['duration_days'],itinerary_id))
    # 3. Load user profile, LinUCB policy, and candidates
    user_profile = _load_user_profile(conn, user_id)
    from app.core.party import normalize_party
    party = normalize_party(trip)
    user_profile['has_children'] = bool(party['children'])
    user_profile['has_elderly'] = bool(party['seniors'])
    if party['seniors']:
        user_profile['walking_tolerance'] = 'low'
    policy = load_user_policy(conn, user_id)
    trip_exclusions = _get_trip_exclusions(conn, trip_id)

    cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (trip["destination_id"],))
    candidate_rows = cursor.fetchall()
    all_candidates = [dict(r) for r in candidate_rows]

    if not all_candidates:
        from app.providers.geo import resolve_trip_location, haversine_distance_km
        from app.activity_data import CURATED_ACTIVITIES
        centre = resolve_trip_location(destination_id=trip['destination_id'],destination_name=trip['destination_name'],
            lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
        curated_ids = {a['id'] for a in CURATED_ACTIVITIES}
        if centre.get('lat') is not None:
            all_candidates = [dict(r) for r in cursor.execute('SELECT * FROM destination_activities') if r['id'] in curated_ids
                and r['latitude'] is not None and r['longitude'] is not None
                and haversine_distance_km(centre['lat'],centre['lon'],r['latitude'],r['longitude']) <= 40]

    # Test runs are intentionally offline; use the curated fallback below instead
    # of waiting on live providers.
    from app.database import DB_PATH
    offline_test = DB_PATH.name == "test.db"

    # Integrate Live Places (Overpass API) and Places API dynamically if DB has few or no activities
    if not all_candidates and not offline_test:
        try:
            from app.services.live_api_service import get_live_places_around, search_geocoding
            dest_name = trip.get("destination_name", "")
            geo_res = search_geocoding(dest_name)
            places_list = []
            source_tag = "OpenStreetMap Overpass (source: api)"
            if geo_res.get("results"):
                top_geo = geo_res["results"][0]
                lat = top_geo.get("latitude", 0.0)
                lon = top_geo.get("longitude", 0.0)
                live_p = get_live_places_around(lat, lon, city=dest_name, radius=6000)
                if live_p and live_p.get("places"):
                    places_list = live_p["places"]
                    src = live_p.get("source", "api")
                    source_tag = f"OpenStreetMap Overpass (source: {src})"

            if places_list:
                for p in places_list:
                    p_id = p.get("place_id") or f"{trip['destination_id']}_{p['name'].lower().replace(' ', '_')[:25]}"
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
                    cost = FALLBACK_CATEGORY_PRICE_INR.get(can_cat,FALLBACK_CATEGORY_PRICE_INR["other"])
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
                        p.get("neighborhood") or f"Central {dest_name}",
                        p.get("lat") or 0.0,
                        p.get("lon") or 0.0,
                        dur_mins,
                        "budget",
                        cost,
                        "moderate",
                        "moderate",
                        "09:00",
                        "18:00",
                        json.dumps([can_cat, "live_overpass"]),
                        json.dumps([]),
                        f"Visit {p['name']}, a verified spot in {dest_name}.",
                        None,
                        source_tag
                    ))
                conn.commit()
                cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (trip["destination_id"],))
                all_candidates = [dict(r) for r in cursor.fetchall()]
        except Exception:
            pass

    # Fallback to local places_service if still < 8
    if not all_candidates and not offline_test:
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
                    cost = FALLBACK_CATEGORY_PRICE_INR.get(can_cat,FALLBACK_CATEGORY_PRICE_INR["other"])
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
        # Resolve catalogue aliases by actual destination centre, never text alone.
        from app.providers.geo import resolve_trip_location, haversine_distance_km
        loc = resolve_trip_location(destination_id=trip['destination_id'], destination_name=trip['destination_name'],
            lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
        if loc.get('lat') is not None:
            all_candidates = [dict(r) for r in cursor.execute('SELECT * FROM destination_activities')
                if r['latitude'] is not None and r['longitude'] is not None and
                haversine_distance_km(loc['lat'],loc['lon'],r['latitude'],r['longitude']) <= 30]
    if not all_candidates:
        # Fallback dummy candidate if no specific activities in DB for unseeded destinations
        all_candidates = [{
            "id": f"{trip['destination_id']}_city_walk",
            "destination_id": trip["destination_id"],
            "name": f"Historic Walking Exploration of {trip['destination_name']}",
            "category": "culture_history",
            "neighborhood": "Central Old Town",
            "latitude": trip.get("destination_lat"),
            "longitude": trip.get("destination_lon"),
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

    from app.providers.geo import resolve_trip_location, haversine_distance_km
    location = resolve_trip_location(destination_id=trip['destination_id'],destination_name=trip['destination_name'],
        lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
    if location.get('lat') is not None:
        # Multi-city catalogue destinations are planned around the chosen centre.
        # Long-distance excursions require a separate destination/trip.
        all_candidates = [c for c in all_candidates if c.get('latitude') is not None and c.get('longitude') is not None
            and haversine_distance_km(location['lat'],location['lon'],c['latitude'],c['longitude']) <= 40]
    from app.activity_data import CURATED_ACTIVITIES
    for candidate in all_candidates:
        if (candidate.get('neighborhood') or '').startswith('Central '):
            nearest = min(CURATED_ACTIVITIES,key=lambda a:haversine_distance_km(candidate['latitude'],candidate['longitude'],a['latitude'],a['longitude']))
            distance = haversine_distance_km(candidate['latitude'],candidate['longitude'],nearest['latitude'],nearest['longitude'])
            candidate['neighborhood'] = nearest['neighborhood'] if distance <= 5 else 'Near ' + candidate['name']
    prefs = trip.get('trip_preferences_json') or '{}'
    prefs = json.loads(prefs) if isinstance(prefs,str) else prefs
    anchor = prefs.get('stay_anchor')
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
        day_neighborhood = neighborhoods[(day_idx - 1) % len(neighborhoods)] if neighborhoods else "No nearby activities"

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

            # Enforce a real-distance cluster before policy scoring (12 km
            # maximum between every pair of stops); meals may use another area.
            if day_activities:
                valid_candidates = [c for c in valid_candidates if all(
                    c.get('latitude') is not None and a.get('latitude') is not None and
                    haversine_distance_km(c['latitude'],c['longitude'],a['latitude'],a['longitude']) <= 12
                    for a in day_activities)]
            if not valid_candidates:
                continue
            if party['children']:
                valid_candidates = [c for c in valid_candidates if not any(t in str(c.get('tags','')).lower() for t in ('nightclub','nightlife','bar_crawl','alcohol'))]
            if party['seniors']:
                valid_candidates = [c for c in valid_candidates if c.get('physical_intensity') not in ('high','strenuous')]
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

                if anchor and not preceding_act and c.get('latitude') is not None:
                    score -= haversine_distance_km(anchor['lat'],anchor['lon'],c['latitude'],c['longitude']) * .1
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
                if anchor:
                    distance = haversine_distance_km(anchor['lat'],anchor['lon'],chosen_act['latitude'],chosen_act['longitude'])
                    transit_mins = max(5,round(distance*1.35/25*60+5))
                    transit_text = f"From {anchor['name']} to {chosen_act['neighborhood']} ({distance:.1f} km straight-line estimate)"
                else:
                    transit_text = f"Depart from lodging to {chosen_act['neighborhood']}"
                    transit_mins = 15

            # Tailored explanation with explicit "Because you said..." attribution
            because_reasons = []
            if chosen_act["category"] == "food_dining":
                diet_list = user_profile.get("dietary") or []
                clean_diet = [d for d in diet_list if d != "none"]
                if clean_diet:
                    because_reasons.append(f"prefer {', '.join(clean_diet)} dining (Q20)")
                else:
                    because_reasons.append("enjoy authentic local food (Q21)")
            elif any(t in chosen_act["category"] for t in ["culture", "history"]):
                because_reasons.append("enjoy cultural and historical sites (Q14)")
            elif any(t in chosen_act["category"] for t in ["nature", "outdoor", "adventure"]):
                because_reasons.append("enjoy nature and outdoor exploration (Q5, Q14)")
            elif any(t in chosen_act["category"] for t in ["relaxation", "wellness"]):
                because_reasons.append("prefer peaceful, relaxing experiences (Q5)")
            else:
                because_reasons.append(f"enjoy {chosen_act['category'].replace('_', ' ')} (Q14)")

            walking_val = user_profile.get("walking_tolerance")
            if walking_val:
                because_reasons.append(f"have a {str(walking_val).replace('_', ' ')} walking limit (Q74)")

            because_you_said = f"Because you said you {' and '.join(because_reasons[:2])}."
            why_text = f"{because_you_said} Paced comfortably for your schedule."
            if bonus_val > 0.35:
                why_text += " (LinUCB exploration candidate)"

            act_record_id = str(uuid.uuid4())
            cost_val = activity_fee_inr(chosen_act)
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
                "because_you_said": because_you_said,
                "status": "proposed",
                "photo_url": chosen_act.get("photo_url"),
                "data_source": chosen_act.get("data_source", "curated")
            })

            preceding_act = chosen_act
            order_idx += 1

        actual_areas = list(dict.fromkeys(a['neighborhood'] for a in day_activities if a.get('neighborhood')))
        day_neighborhood = ' & '.join(actual_areas) or 'Free time near your stay'
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

    from app.providers.geo import resolve_trip_location
    loc_info = resolve_trip_location(
        destination_id=trip.get("destination_id"),
        destination_name=trip.get("destination_name"),
        lat=trip.get("destination_lat"),
        lon=trip.get("destination_lon"),
        resolved_location=trip.get("resolved_location"),
        allow_live_geocode=False,
    )

    from app.core.cost_model import apply_itinerary_cost
    return apply_itinerary_cost(conn, {
        "id": itinerary_id,
        "trip_id": trip_id,
        "user_id": user_id,
        "title": f"Personalised Itinerary: {trip['destination_name']}",
        "destination_id": trip.get("destination_id"),
        "destination_name": trip["destination_name"],
        "destination_lat": loc_info.get("lat"),
        "destination_lon": loc_info.get("lon"),
        "resolved_location": loc_info.get("resolved_location") or trip["destination_name"],
        "start_date": trip.get("start_date"),
        "end_date": trip.get("end_date"),
        "total_days": trip["duration_days"],
        "status": "active",
        "total_estimated_cost": total_itinerary_cost,
        "summary_notes": f"Generated via LinUCB for {trip['travellers_count']} traveller(s). Activities stay within 40 km of the selected destination centre; separate cities require separate trips.",
        "days": day_models,
        "created_at": str(datetime.now()),
        "updated_at": str(datetime.now())
    })

def get_itinerary_details(conn, user_id: str, trip_id: str) -> Optional[Dict[str, Any]]:
    """Fetches full structured itinerary with all activities."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.id, i.trip_id, i.user_id, i.title, i.total_days, i.status,
               i.total_estimated_cost, i.summary_notes, i.created_at, i.updated_at,
               t.destination_name, t.start_date, t.end_date,
               t.destination_id, t.destination_lat, t.destination_lon, t.resolved_location
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

    from app.providers.geo import resolve_trip_location
    loc_info = resolve_trip_location(
        destination_id=row[13],
        destination_name=row[10],
        lat=row[14],
        lon=row[15],
        resolved_location=row[16],
        allow_live_geocode=False,
    )

    for day in days_dict.values():
        areas = list(dict.fromkeys(a['neighborhood'] for a in day['activities'] if a.get('neighborhood')))
        day['neighborhood'] = ' & '.join(areas) or 'Free time near your stay'
        day['theme'] = 'Exploring ' + day['neighborhood'] if areas else 'Free time near your stay'
    from app.core.cost_model import apply_itinerary_cost
    return apply_itinerary_cost(conn, {
        "id": itin_id,
        "trip_id": row[1],
        "user_id": row[2],
        "title": row[3],
        "destination_id": row[13],
        "destination_name": row[10],
        "destination_lat": loc_info.get("lat"),
        "destination_lon": loc_info.get("lon"),
        "resolved_location": loc_info.get("resolved_location") or row[10],
        "start_date": row[11],
        "end_date": row[12],
        "total_days": total_days,
        "status": row[5],
        "total_estimated_cost": row[6],
        "summary_notes": row[7],
        "days": list(days_dict.values()),
        "created_at": str(row[8]),
        "updated_at": str(row[9])
    })

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

    from app.providers.geo import resolve_trip_location, haversine_distance_km
    trip = dict(cursor.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone())
    location = resolve_trip_location(destination_id=dest_id,destination_name=trip['destination_name'],
        lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
    all_candidates = [dict(r) for r in cursor.execute('SELECT * FROM destination_activities') if r['latitude'] is not None
        and r['longitude'] is not None and location.get('lat') is not None
        and haversine_distance_km(location['lat'],location['lon'],r['latitude'],r['longitude'])<=40]

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
