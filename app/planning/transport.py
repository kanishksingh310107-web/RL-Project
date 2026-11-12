"""Multimodal Transit Engine & Cost Estimator (Person A).

Calculates estimated travel legs between points using transparent assumptions:
- Modes: walk, auto/e-rickshaw, cab, rental car with driver, scooter, bus/metro
- Formula: travel_time = (distance * CIRCUITY_FACTOR / speed_kmh) * 60 + fixed_overhead
- Filters modes by traveler context (children, elders, mobility, budget)
- Compares 3 daily usage styles: day rental with driver, cab per trip, public transit
- Rough cost bands only; NO fabricated live fares.
"""
from typing import Dict, Any, List, Optional
from app.core.assumptions import (
    CIRCUITY_FACTOR,
    SPEED_WALK_KMH,
    SPEED_AUTO_KMH,
    SPEED_CAB_KMH,
    SPEED_RENTAL_CAR_KMH,
    SPEED_SCOOTER_KMH,
    SPEED_BUS_METRO_KMH,
    TRANSIT_FIXED_OVERHEAD_MINUTES,
)
from app.core.schemas import TravelLeg, Provenance
from app.providers.geo import haversine_distance_km

MODE_SPEEDS: Dict[str, float] = {
    "walk": SPEED_WALK_KMH,
    "auto": SPEED_AUTO_KMH,
    "cab": SPEED_CAB_KMH,
    "rental_car": SPEED_RENTAL_CAR_KMH,
    "scooter": SPEED_SCOOTER_KMH,
    "bus_metro": SPEED_BUS_METRO_KMH,
}

# Rough cost bands (INR per km, team assumption, not measured)
MODE_COST_PER_KM: Dict[str, float] = {
    "walk": 0.0,
    "auto": 18.0,
    "cab": 26.0,
    "rental_car": 32.0,
    "scooter": 8.0,
    "bus_metro": 5.0,
}


def choose_best_mode(
    distance_km: float,
    profile: Dict[str, Any],
    trip_prefs: Optional[Dict[str, Any]] = None,
) -> str:
    """Selects the most appropriate transit mode for a given leg distance and traveler profile."""
    prefs = trip_prefs or {}
    preferred_modes = set(prefs.get("transport_preferences") or [])
    transit_pref = (profile.get("transit_pref") or "").lower()

    companions = profile.get("companions") or []
    if isinstance(companions, str):
        companions = [companions]
    has_children_or_elders = any(c in ["family_with_children", "family_with_elders", "elders", "children"] for c in companions)
    walking_tolerance = profile.get("walking_tolerance") or "moderate"

    # Short distance and user can walk
    if distance_km <= 1.2 and walking_tolerance not in ("minimal", "under_2km") and not has_children_or_elders:
        if "walk" in preferred_modes or not preferred_modes:
            return "walk"

    # If party has children or elders, exclude two-wheelers and long walking
    disallowed_modes = set()
    if has_children_or_elders:
        disallowed_modes.add("scooter")
        disallowed_modes.add("walk")

    # Respect user explicit avoidance / preference
    travel_concerns = profile.get("travel_concerns") or []
    if "no_long_bus_rides" in travel_concerns or "motion_sickness" in travel_concerns:
        disallowed_modes.add("bus_metro")

    # Candidate evaluation based on distance
    if distance_km > 15.0:
        candidates = ["cab", "rental_car", "bus_metro"]
    elif distance_km > 5.0:
        candidates = ["cab", "auto", "rental_car", "bus_metro"]
    else:
        candidates = ["auto", "cab", "scooter", "walk"]

    for c in candidates:
        if c in disallowed_modes:
            continue
        if preferred_modes and c in preferred_modes:
            return c
        if "public" in transit_pref and c in ("auto", "bus_metro", "walk"):
            return c
        if "taxi" in transit_pref or "private" in transit_pref and c in ("cab", "rental_car"):
            return c
        return c

    return "cab"


def estimate_travel_leg(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    from_place_id: Optional[str] = None,
    to_place_id: Optional[str] = None,
    mode: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> TravelLeg:
    """Builds an estimated TravelLeg between two coordinates."""
    dist_km = haversine_distance_km(lat1, lon1, lat2, lon2)

    if not mode:
        mode = choose_best_mode(dist_km, profile or {})

    speed = MODE_SPEEDS.get(mode, SPEED_CAB_KMH)
    overhead = TRANSIT_FIXED_OVERHEAD_MINUTES if mode != "walk" else 0.0

    # Travel time formula: straight-line distance * circuity factor / speed + overhead
    raw_minutes = (dist_km * CIRCUITY_FACTOR / speed) * 60.0 + overhead
    duration_min = max(5, int(round(raw_minutes)))

    # Rough cost estimate
    cost_per_km = MODE_COST_PER_KM.get(mode, 20.0)
    estimated_cost = round(dist_km * cost_per_km + (50.0 if mode in ("auto", "cab") else 0.0), 2)
    if mode == "walk":
        estimated_cost = 0.0

    return TravelLeg(
        from_place_id=from_place_id,
        to_place_id=to_place_id,
        mode=mode,
        duration_minutes=duration_min,
        distance_km=round(dist_km, 2),
        estimated_cost=estimated_cost,
        provenance=Provenance(
            source="assumed",
            is_live=False,
            is_estimate=True,
            notes=f"straight-line {dist_km:.2f}km via {mode} (circuity factor {CIRCUITY_FACTOR})",
        ),
    )


def compare_daily_transit_styles(
    total_day_distance_km: float,
    number_of_trips: int,
) -> Dict[str, Any]:
    """Compares 3 daily transit styles: day rental with driver, cab per trip, public transit."""
    # 1. Day rental with dedicated driver (fixed daily rate + fuel estimate)
    # team assumption, not measured: typical full-day 8hr/80km sedan rental in urban India
    day_rental_cost = 2500.0 + max(0.0, total_day_distance_km - 80.0) * 16.0

    # 2. Point-to-point cabs (base fare + per km per trip)
    cab_cost = number_of_trips * 60.0 + total_day_distance_km * MODE_COST_PER_KM["cab"]

    # 3. Public transit / auto mix
    public_cost = number_of_trips * 25.0 + total_day_distance_km * 12.0

    return {
        "day_rental_with_driver": {
            "style_name": "Full-day Chauffeur / Rental",
            "estimated_cost_inr": round(day_rental_cost, 2),
            "convenience": "high",
            "description": "Vehicle reserved for the day; no wait times between stops.",
        },
        "cab_per_trip": {
            "style_name": "Point-to-Point Cabs",
            "estimated_cost_inr": round(cab_cost, 2),
            "convenience": "moderate",
            "description": "Book a cab per leg; wait times depend on local availability.",
        },
        "public_and_auto": {
            "style_name": "Auto-Rickshaw & Public Transit",
            "estimated_cost_inr": round(public_cost, 2),
            "convenience": "budget",
            "description": "Economical mix of local auto-rickshaws, metro, and short walks.",
        },
    }
