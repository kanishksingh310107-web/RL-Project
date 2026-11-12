"""Planning Personalization & Hard Filters (Person A).

Filters candidate places using traveler profile constraints:
- Hard filters: avoidances, accessibility, health factors, physical demand,
  walking tolerance, dietary/allergies, opening hours & opening days.
- Distinguishes verified safety from unverified live places.
  Rule: Never mark live venues as 'safe'; mark 'cannot verify, check with venue'.
"""
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from app.core.schemas import Place


def filter_candidate_places(
    places: List[Place],
    profile: Dict[str, Any],
    trip_date: Optional[str] = None,
) -> Tuple[List[Place], List[str], Dict[str, List[str]]]:
    """Filters candidate places against profile constraints.
    
    Returns:
        (valid_places, warning_messages, personalization_metadata)
    """
    valid: List[Place] = []
    warnings: List[str] = []
    used_constraints: List[str] = []
    unavailable_constraints: List[str] = []

    # Extract constraints from unified profile
    avoidances = set(profile.get("avoidances") or [])
    accessibility_needs = profile.get("accessibility") or []
    if isinstance(accessibility_needs, str):
        accessibility_needs = [accessibility_needs]
    accessibility_needs = set(accessibility_needs)

    health_factors = set(profile.get("health_factors") or [])
    walking_tolerance = profile.get("walking_tolerance")
    physical_demand = profile.get("physical_demand") or "moderate"
    dietary_prefs = set(profile.get("dietary") or [])

    has_children = bool(profile.get("has_children") or profile.get("companions") in ("family", "family_with_children"))
    has_elderly = bool(profile.get("has_elderly") or profile.get("companions") in ("family_with_elders", "family_multi_gen"))

    if avoidances:
        used_constraints.append("avoidances")
    if accessibility_needs:
        used_constraints.append("accessibility")
    if health_factors:
        used_constraints.append("health_factors")
    if walking_tolerance:
        used_constraints.append("walking_tolerance")
    if dietary_prefs:
        used_constraints.append("dietary")
    if has_children:
        used_constraints.append("children_safety")
    if has_elderly:
        used_constraints.append("elderly_safety")

    # Map day of week if trip_date is provided
    target_day_name: Optional[str] = None
    if trip_date:
        try:
            dt = datetime.strptime(trip_date, "%Y-%m-%d")
            target_day_name = dt.strftime("%A").lower()  # 'monday', 'tuesday', etc.
            used_constraints.append("opening_days")
        except ValueError:
            target_day_name = None

    for p in places:
        if isinstance(p, dict):
            cat = (p.get("category") or p.get("arm") or "").lower()
            name_lower = (p.get("name") or p.get("title") or "").lower()
            opening_days = p.get("opening_days")
            opening_hours = p.get("opening_hours")
            p_prov = p.get("provenance") or {}
            is_live = p_prov.get("is_live", False) if isinstance(p_prov, dict) else getattr(p_prov, "is_live", False)
            p_name = p.get("name") or p.get("title") or "Place"
        else:
            cat = (p.category or getattr(p, "arm", None) or "").lower()
            name_lower = (p.name or "").lower()
            opening_days = getattr(p, "opening_days", None)
            opening_hours = getattr(p, "opening_hours", None)
            p_prov = getattr(p, "provenance", None)
            is_live = getattr(p_prov, "is_live", False) if p_prov else False
            p_name = getattr(p, "name", "Place")

        # 1. Avoidance Filter (Hard Filter)
        violated_avoidance = False
        if "crowds" in avoidances and cat in ("shopping_local", "food_dining"):
            # Avoid peak congested commercial zones if user avoids crowds
            if "market" in name_lower or "bazaar" in name_lower:
                violated_avoidance = True
        if "heights" in avoidances and (cat == "adventure" or "viewpoint" in name_lower or "peak" in name_lower):
            violated_avoidance = True
        if "steep_walks" in avoidances and ("trek" in name_lower or "hike" in name_lower or "fort" in name_lower):
            violated_avoidance = True
        if "water_activities" in avoidances and ("boat" in name_lower or "rafting" in name_lower or "cruise" in name_lower):
            violated_avoidance = True
        if "nightlife" in avoidances and ("pub" in name_lower or "club" in name_lower or "bar" in name_lower):
            violated_avoidance = True

        if violated_avoidance:
            continue

        # 2. Accessibility & Mobility / Senior Filter (Hard Filter)
        if has_elderly or "wheelchair" in accessibility_needs or "mobility_limitations" in health_factors:
            if "trek" in name_lower or "hike" in name_lower or "steep" in name_lower or "climb" in name_lower:
                continue
            if cat in ("adventure",):
                continue

        # 2b. Children Safety & Family Environment Filter (Hard Filter)
        if has_children:
            if cat in ("nightlife",) or any(w in name_lower for w in ["bar", "pub", "club", "casino", "brewery", "lounge"]):
                continue

        # 3. Physical Demand & Walking Tolerance Filter
        if walking_tolerance in ("minimal", "under_2km") or physical_demand == "low":
            if cat == "adventure" and ("trek" in name_lower or "summit" in name_lower):
                continue

        # 4. Opening Days Check
        if target_day_name and opening_days:
            clean_days = [d.lower() for d in opening_days]
            if target_day_name not in clean_days:
                # Closed on this day
                continue

        # 5. Opening Hours Check & Notes
        if opening_hours:
            used_constraints.append("opening_hours")
        else:
            if is_live:
                warnings.append(f"{p_name}: Opening hours unavailable in live data; check with venue.")

        # 6. Dietary notes on food places
        if cat == "food_dining" and dietary_prefs:
            if is_live:
                # Rule: Never claim live venue is safe for allergies/diet
                warnings.append(f"{p_name}: Dietary/allergen safety cannot be verified for live venues; confirm on arrival.")

        valid.append(p)

    personalization_meta = {
        "used": sorted(list(set(used_constraints))),
        "unavailable": [
            u for u in ["live_venue_allergen_certification", "realtime_crowd_sensors"]
            if u not in used_constraints
        ],
    }

    return valid, warnings, personalization_meta


def rank_places_with_linucb(
    places: List[Place],
    profile: Dict[str, Any],
    user_id: Optional[str] = None,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    stay_anchor: Optional[Any] = None,
    total_days: int = 3,
) -> List[Dict[str, Any]]:
    """Ranks candidate places using Contextual LinUCB policy and user profile.
    
    Data Flow:
    Discovered Places -> Candidate Pool -> LinUCB Context Extraction (24-dim)
    -> Score Prediction -> Proximity Adjustment -> Hard Constraint Filtering
    -> Enriched Scored Results with Provenance & Match Explanations.
    """
    from app.rl_planner import (
        load_user_policy,
        extract_context_vector,
        CANONICAL_ARMS,
        LinUCBPolicy,
    )
    from app.providers.geo import haversine_distance_km
    from app.database import get_connection

    # 1. Normalize profile for RL
    profile_for_rl = dict(profile)
    pace_val = profile.get("pace") or profile.get("travel_pace") or "balanced"
    if isinstance(pace_val, str):
        pace_map = {
            "relaxed": 0.25, "slow": 0.25,
            "balanced": 0.5, "moderate": 0.5,
            "packed": 0.85, "fast": 0.85,
        }
        profile_for_rl["pace"] = pace_map.get(pace_val.lower(), 0.5)
    else:
        try:
            profile_for_rl["pace"] = float(pace_val)
        except Exception:
            profile_for_rl["pace"] = 0.5

    crowd_val = profile.get("crowd_tolerance", 0.5)
    try:
        profile_for_rl["crowd_tolerance"] = float(crowd_val) / 5.0 if float(crowd_val) > 1.0 else float(crowd_val)
    except Exception:
        profile_for_rl["crowd_tolerance"] = 0.5

    profile_for_rl["walking_tolerance"] = profile.get("walking_tolerance", "medium")

    # 2. Load LinUCB policy
    policy = None
    if user_id:
        try:
            with get_connection() as conn:
                policy = load_user_policy(conn, user_id)
        except Exception:
            policy = LinUCBPolicy(user_id or "default")
    if policy is None:
        policy = LinUCBPolicy(user_id or "default")

    trip_config = {
        "duration_days": total_days,
        "travel_pace": profile_for_rl["pace"],
        "budget_tier": profile.get("budget_tier", "balanced"),
    }

    # 3. Filter candidates through hard constraint filters
    filtered_places, _, _ = filter_candidate_places(places, profile)
    valid_ids = {p.get("id") if isinstance(p, dict) else p.id for p in filtered_places}

    user_interests = [str(i).lower() for i in (profile.get("interests") or [])]

    scored_results: List[Dict[str, Any]] = []
    for place in places:
        is_dict = isinstance(place, dict)
        p_id = place.get("id") if is_dict else place.id
        p_name = place.get("name") if is_dict else place.name
        p_cat = (place.get("category") or place.get("arm")) if is_dict else place.category
        p_lat = place.get("lat") if is_dict else place.lat
        p_lon = place.get("lon") if is_dict else place.lon
        p_addr = place.get("address") if is_dict else place.address
        p_neigh = place.get("neighbourhood") if is_dict else place.neighbourhood
        p_cost = place.get("cost_amount", place.get("cost")) if is_dict else place.cost_amount
        p_hours = place.get("opening_hours") if is_dict else place.opening_hours
        p_phone = place.get("phone") if is_dict else place.phone
        p_site = place.get("website") if is_dict else place.website
        p_photo = place.get("photo_url") if is_dict else place.photo_url
        p_prov = place.get("provenance") if is_dict else place.provenance

        is_filtered_out = p_id not in valid_ids

        arm = p_cat if p_cat in CANONICAL_ARMS else "culture_history"
        activity_dict = {
            "id": p_id,
            "category": arm,
            "physical_intensity": 2,  # neutral default for live
            "crowd_level": 2,         # neutral default for live
            "cost_amount": p_cost if p_cost is not None else 0.0,
        }

        ctx = extract_context_vector(profile_for_rl, trip_config, 1, total_days, "afternoon", activity_dict)
        pred_reward, _, _ = policy.predict_score(arm, ctx)

        # Distance calculation
        dist_km = None
        if center_lat is not None and center_lon is not None and p_lat is not None and p_lon is not None:
            dist_km = haversine_distance_km(center_lat, center_lon, p_lat, p_lon)
            if dist_km <= 3.0:
                pred_reward += 0.15
            elif dist_km <= 8.0:
                pred_reward += 0.08

        if stay_anchor and getattr(stay_anchor, "lat", None) and getattr(stay_anchor, "lon", None) and p_lat is not None and p_lon is not None:
            stay_dist = haversine_distance_km(stay_anchor.lat, stay_anchor.lon, p_lat, p_lon)
            if stay_dist <= 5.0:
                pred_reward += 0.10

        # Penalize if hard filtered
        if is_filtered_out:
            pred_reward -= 2.0

        # Explanation logic
        reasons: List[str] = []
        name_lower = (p_name or "").lower()

        # Companion-specific affinity adjustment
        has_kids = bool(profile.get("has_children") or profile.get("companions") in ("family", "family_with_children"))
        has_seniors = bool(profile.get("has_elderly") or profile.get("companions") in ("family_with_elders", "family_multi_gen"))
        if has_kids:
            if arm in ("nature_outdoors", "relaxation_wellness") or any(k in name_lower for k in ["park", "garden", "zoo", "museum", "science", "boat", "beach", "aquarium", "water"]):
                pred_reward += 0.35
                reasons.append("Kid-friendly venue")
        if has_seniors:
            if any(k in name_lower for k in ["palace", "temple", "garden", "cruise", "heritage", "museum", "memorial", "lake"]):
                pred_reward += 0.35
                reasons.append("Senior-accessible gentle pacing")
        if profile.get("companions") in ("partner", "couple"):
            if any(k in name_lower for k in ["lake", "viewpoint", "sunset", "palace", "cruise", "fort"]):
                pred_reward += 0.25
                reasons.append("Scenic experience for couples")

        if any(i in arm for i in user_interests):
            reasons.append(f"Matches stated interest in {arm.replace('_', ' ')}")
        if dist_km is not None:
            reasons.append(f"{dist_km:.1f} km away")
        if p_neigh:
            reasons.append(f"Located in {p_neigh}")
        if not reasons:
            reasons.append(f"Personalized for {arm.replace('_', ' ')}")

        match_reason = " • ".join(reasons)

        scored_results.append({
            "id": p_id,
            "name": p_name,
            "category": p_cat,
            "arm": arm,
            "lat": p_lat,
            "lon": p_lon,
            "address": p_addr,
            "neighbourhood": p_neigh,
            "distance_km": round(dist_km, 2) if dist_km is not None else None,
            "score": round(float(pred_reward), 3),
            "match_reason": match_reason,
            "is_filtered_out": is_filtered_out,
            "opening_hours": p_hours,
            "phone": p_phone,
            "website": p_site,
            "photo_url": p_photo,
            "provenance": p_prov.model_dump() if hasattr(p_prov, "model_dump") else p_prov,
        })

    # Sort descending by LinUCB score
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results
