"""Dynamic Time-Budget Plan Engine Module (Person A).

Implements the contract endpoints for travel plan generation:
- Trip preferences: GET/PUT /api/plan/prefs/{trip_id} (stored in core_trip_prefs)
- Candidate pool: places mapped to 7 canonical LinUCB arms
- Plan generation: POST /api/plan/generate/{trip_id} (saves TripPlan to core_plans)
- Plan retrieval: GET /api/plan/{trip_id}
- Feedback: POST /api/plan/feedback (updates LinUCB policy via read-only imports)
- Validation: GET /api/plan/{trip_id}/validation
"""
import uuid
import json
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.config import get_setting, is_geoapify_configured
from app.providers.guard import can_call_geoapify
from app.core.schemas import (
    Provenance,
    Place,
    TripPrefs,
    TripPlan,
    DayPlan,
    MealWindow,
    Stay,
)
from app.core.profile import load_profile
from app.core.stores import (
    ensure_core_tables,
    save_trip_prefs,
    load_trip_prefs,
    save_trip_plan,
    load_trip_plan,
    load_stay,
)
from app.modules.common import get_trip
from app.activity_data import CURATED_ACTIVITIES
from app.recommender import DESTINATIONS
from app.rl_planner import (
    LinUCBPolicy,
    load_user_policy,
    extract_context_vector,
    process_activity_feedback,
    CANONICAL_ARMS,
)
from app.providers.geo import get_places_by_category, geocode_india
from app.planning.personalization import filter_candidate_places
from app.planning.scheduler import schedule_day
from app.planning.budget import build_budget_ledger
from app.planning.shopping import ensure_shopping_tables, record_shopping_feedback
from app.planning.validate import validate_trip_plan, check_legacy_itinerary_overflows

MODULE = {
    "id": "plan",
    "title": "Trip Plan",
    "icon": "fa-calendar-days",
    "owner": "A",
}

router = APIRouter(prefix="/api/plan", tags=["plan"])


def init_tables(conn: sqlite3.Connection):
    """Initializes tables owned by planning and ensures core contract tables."""
    ensure_core_tables(conn)
    ensure_shopping_tables(conn)


# Map Geoapify categories to our 7 canonical arms
GEOAPIFY_TO_ARM_MAP: Dict[str, str] = {
    "tourism.sights": "culture_history",
    "heritage": "culture_history",
    "building.historic": "culture_history",
    "entertainment.culture": "culture_history",
    "natural": "nature_outdoors",
    "leisure.park": "nature_outdoors",
    "national_park": "nature_outdoors",
    "catering.restaurant": "food_dining",
    "catering.cafe": "food_dining",
    "catering.fast_food": "food_dining",
    "sport": "adventure",
    "activity.sport_club": "adventure",
    "leisure.spa": "relaxation",
    "beach": "relaxation",
    "commercial.shopping_mall": "shopping_local",
    "commercial.marketplace": "shopping_local",
    "viewpoint": "scenic",
}


def _convert_curated_to_place(act: Dict[str, Any], dest_id: str) -> Place:
    """Converts a legacy curated activity dict to normalized Place schema."""
    arm = act.get("category") or "culture_history"
    if arm not in CANONICAL_ARMS:
        arm = "culture_history"

    return Place(
        id=act.get("id") or str(uuid.uuid4())[:8],
        name=act.get("name") or "Local Activity",
        category=arm,
        destination_id=dest_id,
        lat=float(act.get("lat") or 28.6139),
        lon=float(act.get("lon") or 77.2090),
        address=act.get("address"),
        neighbourhood=act.get("neighbourhood"),
        opening_hours=act.get("opening_hours"),
        typical_duration_minutes=act.get("duration_minutes") or 60,
        price_level=act.get("cost_tier") or "mid_range",
        cost_amount=float(act.get("cost_amount")) if act.get("cost_amount") is not None else None,
        provenance=Provenance(
            source="curated_catalogue",
            is_live=False,
            is_estimate=False,
            notes="offline curated seed activity",
        ),
    )


def _convert_geoapify_to_place(feat: Dict[str, Any], dest_id: str, default_arm: str) -> Place:
    """Converts a Geoapify GeoJSON feature to normalized Place schema."""
    props = feat.get("properties") or {}
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") or [77.2090, 28.6139]

    # Map Geoapify categories
    cats = props.get("categories") or []
    arm = default_arm
    for c in cats:
        if c in GEOAPIFY_TO_ARM_MAP:
            arm = GEOAPIFY_TO_ARM_MAP[c]
            break

    # Cost amount is None for live places (never 0)
    return Place(
        id=str(props.get("place_id") or uuid.uuid4())[:12],
        name=props.get("name") or props.get("formatted") or "Local Place",
        category=arm,
        destination_id=dest_id,
        city=props.get("city"),
        lat=coords[1],
        lon=coords[0],
        address=props.get("formatted"),
        neighbourhood=props.get("suburb") or props.get("district"),
        opening_hours=props.get("opening_hours"),
        typical_duration_minutes=None,  # Live places lack fixed duration
        rating=props.get("rank", {}).get("popularity"),
        price_level=None,
        cost_amount=None,  # Rule: None if unknown, NEVER 0
        phone=props.get("contact", {}).get("phone"),
        website=props.get("website"),
        provenance=Provenance(
            source="geoapify",
            is_live=True,
            is_estimate=False,
            notes="live Geoapify place feature",
        ),
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/prefs/{trip_id}", response_model=TripPrefs)
def get_trip_preferences(trip_id: str):
    """Retrieves user trip preferences, falling back to team assumptions."""
    prefs = load_trip_prefs(trip_id)
    if prefs:
        return prefs

    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

    # Default assumptions
    return TripPrefs(
        trip_id=trip_id,
        user_id=trip["user_id"],
        pace=trip.get("travel_pace") or "balanced",
        start_time="09:00",
        end_time="21:00",
        meal_windows=[
            MealWindow(meal_type="lunch", start_time="13:00", end_time="14:00", duration_minutes=60),
            MealWindow(meal_type="dinner", start_time="19:30", end_time="20:30", duration_minutes=60),
        ],
        shopping_style="mix",
        transport_preferences=["auto", "cab", "walk"],
        provenance=Provenance(source="assumed", is_estimate=True, notes="default assumptions"),
    )


@router.put("/prefs/{trip_id}", response_model=TripPrefs)
def update_trip_preferences(trip_id: str, prefs: TripPrefs):
    """Updates and saves user trip preferences to core_trip_prefs."""
    if prefs.trip_id != trip_id:
        prefs.trip_id = trip_id
    save_trip_prefs(prefs)
    return prefs


@router.post("/generate/{trip_id}", response_model=TripPlan)
def generate_trip_plan(trip_id: str):
    """Generates a multi-day TripPlan using LinUCB scoring and time-budget scheduling."""
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

    user_id = trip["user_id"]
    dest_id = trip["destination_id"]
    dest_name = trip.get("destination_name") or dest_id.replace("_", " ").title()
    total_days = max(1, trip.get("duration_days") or 3)
    total_budget = float(trip.get("total_budget") or 25000.0)

    # 1. Load profile and preferences
    profile = load_profile(user_id)
    prefs = load_trip_prefs(trip_id)
    pace = prefs.pace if prefs else (trip.get("travel_pace") or "balanced")
    start_time = prefs.start_time if prefs else "09:00"
    end_time = prefs.end_time if prefs else "21:00"
    shopping_style = prefs.shopping_style if prefs else "mix"

    # 2. Check Stay anchor from core_stays
    stay_anchor = load_stay(trip_id)

    # 3. Destination coordinates (Dynamic India Resolution - Never silent Delhi)
    center_lat = None
    center_lon = None

    if stay_anchor and getattr(stay_anchor, "lat", None) and getattr(stay_anchor, "lon", None):
        center_lat = stay_anchor.lat
        center_lon = stay_anchor.lon

    if center_lat is None or center_lon is None:
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                row = cur.execute(
                    "SELECT AVG(latitude), AVG(longitude) FROM destination_activities WHERE destination_id = ? AND latitude IS NOT NULL",
                    (dest_id,)
                ).fetchone()
                if row and row[0] is not None and row[1] is not None:
                    center_lat = float(row[0])
                    center_lon = float(row[1])
        except Exception:
            pass

    if center_lat is None or center_lon is None:
        try:
            from app.providers.cache import get_cached
            cached_loc = get_cached(f"geo:dest:{dest_id}")
            if cached_loc and "lat" in cached_loc and "lon" in cached_loc:
                center_lat = float(cached_loc["lat"])
                center_lon = float(cached_loc["lon"])
        except Exception:
            pass

    if center_lat is None or center_lon is None:
        try:
            from app.providers.geo import geocode_india
            geo_res = geocode_india(dest_name)
            if geo_res:
                center_lat = float(geo_res["lat"])
                center_lon = float(geo_res["lon"])
        except Exception:
            pass

    if center_lat is None or center_lon is None:
        dest_meta = next((d for d in DESTINATIONS if d.get("id") == dest_id), {})
        if dest_meta.get("lat") and dest_meta.get("lon"):
            center_lat = float(dest_meta["lat"])
            center_lon = float(dest_meta["lon"])

    if center_lat is None or center_lon is None:
        center_lat = 20.5937  # Geographic center of India
        center_lon = 78.9629

    # 4. Assemble candidate places (database activities, live Geoapify discovery, or curated)
    candidates: List[Place] = []
    seen_cand_ids: set = set()

    # 4A: Check destination_activities seeded from real-time discovery
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (dest_id,))
            for r in cur.fetchall():
                row_dict = dict(r)
                p = Place(
                    id=row_dict["id"],
                    name=row_dict["name"],
                    category=row_dict["category"],
                    destination_id=dest_id,
                    lat=float(row_dict["latitude"]) if row_dict.get("latitude") is not None else center_lat,
                    lon=float(row_dict["longitude"]) if row_dict.get("longitude") is not None else center_lon,
                    neighbourhood=row_dict.get("neighborhood"),
                    typical_duration_minutes=row_dict.get("duration_minutes") or 90,
                    cost_amount=row_dict.get("cost_amount"),
                    opening_hours=f"{row_dict.get('opening_time', '09:00')}-{row_dict.get('closing_time', '18:00')}",
                    provenance=Provenance(
                        source=row_dict.get("data_source", "destination_activities"),
                        is_live=True
                    )
                )
                candidates.append(p)
                seen_cand_ids.add(p.id)
    except Exception:
        pass

    # 4B: Live place discovery via Geoapify
    try:
        from app.providers.geo import discover_places_india
        live_places = discover_places_india(center_lat, center_lon, radius_meters=15000, limit=20)
        for lp in live_places:
            if lp.id not in seen_cand_ids:
                candidates.append(lp)
                seen_cand_ids.add(lp.id)
    except Exception:
        pass

    # 4C: Augment/fallback with curated catalog activities
    for act in CURATED_ACTIVITIES:
        act_dest = (act.get("destination") or "").lower()
        if act_dest in (dest_id.lower(), dest_name.lower()) or dest_id in act_dest:
            cp = _convert_curated_to_place(act, dest_id)
            if cp.id not in seen_cand_ids:
                candidates.append(cp)
                seen_cand_ids.add(cp.id)

    if not candidates:
        # Ultimate fallback: generate synthetic seeds from destination center
        for i, arm in enumerate(CANONICAL_ARMS):
            candidates.append(
                Place(
                    id=f"{dest_id}_spot_{i+1}",
                    name=f"{dest_name} {arm.replace('_', ' ').title()} Center",
                    category=arm,
                    destination_id=dest_id,
                    lat=center_lat + (i * 0.005),
                    lon=center_lon + (i * 0.005),
                    typical_duration_minutes=60,
                    cost_amount=250.0,
                    provenance=Provenance(source="curated_catalogue", is_estimate=True),
                )
            )

    # 5. Fetch shopping venues and dining options
    shopping_venues: List[Place] = []
    restaurants: List[Place] = []
    has_key = is_geoapify_configured() and can_call_geoapify()
    if has_key:
        try:
            shop_res = get_places_by_category(center_lat, center_lon, "commercial.marketplace", radius_meters=12000, limit=6)
            for f in shop_res.get("features") or []:
                shopping_venues.append(_convert_geoapify_to_place(f, dest_id, "shopping_local"))

            dine_res = get_places_by_category(center_lat, center_lon, "catering.restaurant", radius_meters=10000, limit=8)
            for f in dine_res.get("features") or []:
                restaurants.append(_convert_geoapify_to_place(f, dest_id, "food_dining"))
        except Exception:
            pass

    if not shopping_venues:
        shopping_venues = [
            Place(
                id=f"{dest_id}_local_craft_market",
                name=f"{dest_name} Traditional Handicrafts Bazaar",
                category="shopping_local",
                destination_id=dest_id,
                lat=center_lat + 0.008,
                lon=center_lon + 0.008,
                typical_duration_minutes=60,
                cost_amount=500.0,
                provenance=Provenance(source="curated_catalogue", is_estimate=True),
            )
        ]

    # 6. Score candidate places using LinUCB
    with get_connection() as conn:
        policy = load_user_policy(conn, user_id)

    # Convert pace and crowd_tolerance to numeric float for extract_context_vector
    profile_for_rl = dict(profile)
    pace_str = str(profile.get("pace") or "balanced")
    pace_map = {"relaxed": 0.25, "balanced": 0.5, "packed": 0.85}
    profile_for_rl["pace"] = pace_map.get(pace_str, 0.5)
    crowd_val = profile.get("crowd_tolerance", 0.5)
    try:
        profile_for_rl["crowd_tolerance"] = float(crowd_val) / 5.0 if float(crowd_val) > 1.0 else float(crowd_val)
    except Exception:
        profile_for_rl["crowd_tolerance"] = 0.5

    scored_candidates: List[Tuple[float, Place]] = []
    for place in candidates:
        arm = place.category if place.category in CANONICAL_ARMS else "culture_history"
        # Extract 24-dim context vector
        activity_dict = {
            "id": place.id,
            "category": arm,
            "physical_intensity": 2,  # neutral default for live
            "crowd_level": 2,
            "cost_amount": place.cost_amount or 0.0,
        }
        ctx = extract_context_vector(profile_for_rl, trip, 1, total_days, "afternoon", activity_dict)
        pred_reward, _, _ = policy.predict_score(arm, ctx)

        # Proximity bonus if stay anchor exists
        if stay_anchor:
            from app.providers.geo import haversine_distance_km
            dist = haversine_distance_km(stay_anchor.lat, stay_anchor.lon, place.lat, place.lon)
            if dist <= 5.0:
                pred_reward += 0.10

        scored_candidates.append((pred_reward, place))

    # Sort descending by predicted LinUCB score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    sorted_places = [p for _, p in scored_candidates]

    # 7. Apply Personalization Hard Filters
    start_date_str = trip.get("start_date")
    filtered_places, warnings, pers_meta = filter_candidate_places(sorted_places, profile, start_date_str)

    # 8. Schedule Day Plans
    day_plans: List[DayPlan] = []
    current_pool = list(filtered_places)
    actual_spent_by_category: Dict[str, float] = {
        "stay": (total_budget * 0.35),
        "food": 0.0,
        "transport": 0.0,
        "activities": 0.0,
        "shopping": 0.0,
        "buffer": 0.0,
    }

    for day_idx in range(1, total_days + 1):
        d_plan, remaining = schedule_day(
            day_number=day_idx,
            date_str=None,
            candidate_places=current_pool,
            profile=profile,
            pace=pace,
            start_time=start_time,
            end_time=end_time,
            stay_anchor=stay_anchor,
            shopping_venues=shopping_venues,
            restaurants=restaurants,
        )
        day_plans.append(d_plan)
        current_pool = remaining

    # Shared model is authoritative for all components of the planning ledger.
    from app.core.cost_model import estimate_cost
    cost = estimate_cost(trip)
    from app.core.schemas import BudgetLine
    budget_ledger = []
    for category, values in cost['cost_breakdown'].items():
        allocated = total_budget * values['per_party'] / max(cost['total'],1)
        budget_ledger.append(BudgetLine(category=category, allocated_amount=round(allocated,2),
            estimated_spent=values['per_party'],currency='INR',status='red' if cost['total']>total_budget else 'green',
            notes='Indicative planning assumption, not a live price'))
    overall_status = 'red' if cost['total']>total_budget else 'green'

    # 10. Assemble and Save TripPlan
    trip_plan = TripPlan(
        trip_id=trip_id,
        user_id=user_id,
        destination_id=dest_id,
        destination_name=dest_name,
        total_days=total_days,
        days=day_plans,
        budget_ledger=budget_ledger,
        overall_budget_status=overall_status,
        stay_anchor=stay_anchor,
        provenance=Provenance(
            source="plan_engine",
            is_live=has_key,
            is_estimate=True,
            notes=f"Generated via LinUCB + Time-Budget Scheduler ({pace} pace)",
        ),
    )

    save_trip_plan(trip_plan)
    return trip_plan


@router.get("/{trip_id}", response_model=TripPlan)
def get_trip_plan(trip_id: str):
    """Retrieves an existing TripPlan, generating it if not yet present."""
    plan = load_trip_plan(trip_id)
    if plan:
        return plan
    # Generate on demand
    return generate_trip_plan(trip_id)


class PlanFeedbackRequest(BaseModel):
    user_id: str
    trip_id: str
    activity_id: str
    action_type: str  # accept, reject, modify
    rejection_reason: Optional[str] = None
    venue_type: Optional[str] = None  # for shopping


@router.post("/feedback")
def submit_plan_feedback(payload: PlanFeedbackRequest):
    """Applies feedback update to LinUCB policy and shopping priors."""
    with get_connection() as conn:
        try:
            res = process_activity_feedback(
                conn=conn,
                user_id=payload.user_id,
                trip_id=payload.trip_id,
                itinerary_id=f"plan_{payload.trip_id}",
                activity_id=payload.activity_id,
                action_type=payload.action_type,
                rejection_reason=payload.rejection_reason,
                is_trip_specific=False,
            )
        except ValueError:
            # Dynamic plan block update: update policy directly using read-only functions
            from app.rl_planner import save_user_policy
            policy = load_user_policy(conn, payload.user_id)
            plan = load_trip_plan(payload.trip_id)
            target_place = None
            if plan:
                for d in plan.days:
                    for b in d.blocks:
                        if b.place and b.place.id == payload.activity_id:
                            target_place = b.place
                            break
            arm = target_place.category if target_place and target_place.category in CANONICAL_ARMS else "culture_history"
            reward = 1.0 if payload.action_type.lower() == "accept" else (-1.0 if payload.action_type.lower() == "reject" else 0.4)
            profile_for_rl = dict(load_profile(payload.user_id))
            pace_map = {"relaxed": 0.25, "balanced": 0.5, "packed": 0.85}
            profile_for_rl["pace"] = pace_map.get(str(profile_for_rl.get("pace")), 0.5)
            crowd_val = profile_for_rl.get("crowd_tolerance", 0.5)
            try:
                profile_for_rl["crowd_tolerance"] = float(crowd_val) / 5.0 if float(crowd_val) > 1.0 else float(crowd_val)
            except Exception:
                profile_for_rl["crowd_tolerance"] = 0.5

            trip = get_trip(payload.trip_id) or {"duration_days": 3}
            ctx = extract_context_vector(
                profile_for_rl,
                trip,
                1,
                trip.get("duration_days", 3),
                "afternoon",
                {"id": payload.activity_id, "category": arm, "cost_amount": 0.0},
            )
            policy.update(arm, ctx, reward)
            save_user_policy(conn, policy)
            res = {"status": "updated", "arm": arm, "reward": reward}

    # If shopping venue feedback, update shopping prior
    if payload.venue_type:
        record_shopping_feedback(payload.user_id, payload.venue_type, payload.action_type)

    return {"status": "ok", "feedback_result": res}


@router.get("/{trip_id}/validation")
def get_plan_validation(trip_id: str):
    """Checks constraint violations on the plan and advisory legacy warnings."""
    plan = load_trip_plan(trip_id)
    if not plan:
        plan = generate_trip_plan(trip_id)

    profile = load_profile(plan.user_id)
    violations = validate_trip_plan(plan, profile)
    legacy_suggestions = check_legacy_itinerary_overflows(trip_id)

    return {
        "trip_id": trip_id,
        "is_valid": len([v for v in violations if v.get("severity") == "critical"]) == 0,
        "violations": violations,
        "legacy_overflow_suggestions": legacy_suggestions,
    }
