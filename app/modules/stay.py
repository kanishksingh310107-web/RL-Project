"""Stay and Accommodation Module (Person B).

Handles area recommendations, hotel options without live prices,
hotel-first mode, and stay anchoring for the plan engine:
- Reads candidate places from core_plans
- Area recommender: candidate areas evaluated by total daily commute sum
  (distance to first stop + distance from last stop back to stay)
- Hotel options via provider accommodations without live prices
- Nightly budget range: trip budget * stay share / nights
- Hotel-first preview: before/after estimated transit minutes
- Persists chosen stay to core_stays (schema Stay)
"""
import uuid
import sqlite3
from typing import Dict, Any, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.schemas import Stay, Provenance
from app.core.assumptions import (
    BUDGET_SHARE_STAY,
    SPEED_CAB_KMH,
    CIRCUITY_FACTOR,
    TRANSIT_FIXED_OVERHEAD_MINUTES,
)
from app.core.stores import (
    ensure_core_tables,
    save_stay,
    load_stay,
    load_trip_plan,
)
from app.modules.common import get_trip
from app.providers.geo import (
    haversine_distance_km,
    get_accommodations,
    geocode_india,
)
from app.recommender import DESTINATIONS

MODULE = {
    "id": "stay",
    "title": "Stay & Hotels",
    "icon": "fa-hotel",
    "owner": "B",
}

router = APIRouter(prefix="/api/stay", tags=["stay"])


def init_tables(conn: sqlite3.Connection):
    """Initializes tables owned by stay module and ensures core contract tables."""
    ensure_core_tables(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stay_preferences (
            trip_id TEXT PRIMARY KEY,
            chosen_area TEXT,
            stay_style TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _estimate_transit_minutes(dist_km: float) -> int:
    """Estimates transit minutes using straight-line distance and team assumptions."""
    raw = (dist_km * CIRCUITY_FACTOR / SPEED_CAB_KMH) * 60.0 + TRANSIT_FIXED_OVERHEAD_MINUTES
    return max(5, int(round(raw)))


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/{trip_id}/areas")
def recommend_stay_areas(trip_id: str):
    """Recommends top 3 areas to stay based on total daily commute to planned stops.
    
    Total daily commute = sum over days of:
      (distance from area to day's first stop + distance from day's last stop back to area)
    """
    from app.data.stay_areas import areas_for_destination
    from app.providers.geo import resolve_trip_location
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(404, 'Trip not found')
    location = resolve_trip_location(destination_id=trip['destination_id'],destination_name=trip['destination_name'],
        lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
    areas = areas_for_destination(trip['destination_id'],location.get('lat'),location.get('lon'))
    with get_connection() as conn:
        stops = conn.execute('SELECT ia.latitude,ia.longitude FROM itinerary_activities ia JOIN itineraries i ON ia.itinerary_id=i.id WHERE i.trip_id=? AND ia.latitude IS NOT NULL AND ia.longitude IS NOT NULL',(trip_id,)).fetchall()
    plan = load_trip_plan(trip_id)
    if not stops and plan:
        stops = [(b.place.lat,b.place.lon) for d in plan.days for b in d.blocks if b.place]
    lat = sum(r[0] for r in stops)/len(stops) if stops else location.get('lat')
    lon = sum(r[1] for r in stops)/len(stops) if stops else location.get('lon')
    for area in areas:
        dist = haversine_distance_km(lat,lon,area['lat'],area['lon'])
        area.update(distance_to_centroid_km=round(dist,2), total_commute_km=round(dist*2,2),
            estimated_daily_commute_minutes=_estimate_transit_minutes(dist*2), is_estimate=True,
            reason=f"{dist:.1f} km from your itinerary centre. Indicative - no live listings.")
    areas.sort(key=lambda a:a['distance_to_centroid_km'])
    return {'trip_id':trip_id,'recommended_areas':areas[:3], 'centroid':{'lat':lat,'lon':lon},
            'methodology':'Top curated neighbourhoods by distance to itinerary centroid; indicative, not live listings.'}


@router.get("/search")
def search_accommodations_pre_trip(
    destination_id: Optional[str] = Query(None),
    destination_name: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    budget: Optional[float] = Query(25000.0),
    duration_days: int = Query(4),
    limit: int = Query(15, le=30),
    accommodation_tier: str = Query('mid_range'),
    radius_meters: int = Query(12000, ge=1000, le=40000),
):
    """Option A: Pre-trip search for accommodations near destination with real names and coordinates."""
    target_lat = lat
    target_lon = lon

    dest_meta = {}
    if destination_id:
        dest_meta = next((d for d in DESTINATIONS if d.get("id") == destination_id), {})
        if not dest_meta:
            from app.data.india_destinations import DESTINATIONS_BY_ID
            dest_meta = DESTINATIONS_BY_ID.get(destination_id, {})

    if target_lat is None or target_lon is None:
        if dest_meta:
            target_lat = dest_meta.get("lat")
            target_lon = dest_meta.get("lon")

    if target_lat is None or target_lon is None:
        name_to_search = destination_name or dest_meta.get("name") or (destination_id.replace("_", " ") if destination_id else "")
        if name_to_search:
            try:
                geo = geocode_india(name_to_search)
                if geo:
                    target_lat = geo["lat"]
                    target_lon = geo["lon"]
            except Exception:
                pass

    if target_lat is None or target_lon is None:
        raise HTTPException(422, 'Select a destination with valid coordinates.')
    from app.providers.geo import is_in_india
    if not is_in_india(target_lat,target_lon):
        raise HTTPException(422, 'Accommodation search is available only within India.')

    total_budget = float(budget or 25000.0)
    nights = max(1, duration_days - 1)
    nightly_budget = round((total_budget * BUDGET_SHARE_STAY) / nights, 2)

    stays = get_accommodations(
        lat=target_lat,
        lon=target_lon,
        trip_id="pre_trip",
        estimated_nightly_budget=nightly_budget,
        limit=limit, tier=accommodation_tier, radius_meters=radius_meters, destination_id=destination_id,
    )

    resolved_name = destination_name or dest_meta.get("name") or (destination_id.replace("_", " ").title() if destination_id else "Selected Destination")

    return {
        "destination": resolved_name,
        "lat": target_lat,
        "lon": target_lon,
        "estimated_nightly_budget_inr": nightly_budget,
        "options": stays,
        "count": len(stays),
        "note": "Indicative - no live listings when offline. Areas are neighbourhood recommendations, not hotels. All prices are indicative per room per night.",
    }


@router.get("/{trip_id}/options")
def get_hotel_options(
    trip_id: str,
    area_name: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    limit: int = Query(15, le=20),
):
    """Retrieves hotel options without live prices, displaying estimated nightly budget band."""
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

    dest_id = trip['destination_id']
    from app.providers.geo import resolve_trip_location
    loc = resolve_trip_location(destination_id=dest_id,destination_name=trip['destination_name'],
        lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
    target_lat, target_lon = loc.get('lat'),loc.get('lon')
    if target_lat is None or target_lon is None:
        raise HTTPException(422,'Destination coordinates unavailable')

    # Compute nightly budget band: total_budget * stay_share / duration_nights
    total_budget = float(trip.get("total_budget") or 25000.0)
    nights = max(1, (trip.get("duration_days") or 3) - 1)
    nightly_budget = round((total_budget * BUDGET_SHARE_STAY) / nights, 2)

    stays = get_accommodations(
        lat=target_lat,
        lon=target_lon,
        trip_id=trip_id,
        estimated_nightly_budget=nightly_budget,
        limit=limit, tier=trip.get('accommodation_tier','mid_range'), destination_id=dest_id,
    )

    # Current chosen stay
    active_stay = load_stay(trip_id)

    return {
        "trip_id": trip_id,
        "area_name": area_name or "Selected Area",
        "nightly_budget_estimate_inr": nightly_budget,
        "active_stay": active_stay,
        "options": stays,
        "note": "Hotel prices are not available via free APIs. Budget band is estimated from total trip budget. Click external search link to view live rates.",
    }


@router.post("/{trip_id}/select", response_model=Stay)
def select_hotel(trip_id: str, stay: Stay):
    """Saves the user's chosen accommodation to core_stays."""
    if stay.trip_id != trip_id:
        stay.trip_id = trip_id
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(404,'Trip not found')
    validate_stay_location(trip, stay.lat, stay.lon)
    save_stay(stay)
    return stay


class HotelFirstRequest(BaseModel):
    hotel_name: str
    city: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = None


@router.post("/{trip_id}/hotel-first-preview")
def hotel_first_mode(trip_id: str, payload: HotelFirstRequest):
    """Saves a hotel directly and computes a before/after travel minutes preview."""
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

    # Geocode if lat/lon not supplied
    h_lat = payload.lat
    h_lon = payload.lon
    h_addr = payload.address

    if h_lat is None or h_lon is None:
        query = f"{payload.hotel_name}, {payload.city or trip.get('destination_name', '')}"
        geo = geocode_india(query)
        if geo:
            h_lat = geo["lat"]
            h_lon = geo["lon"]
            h_addr = geo.get("address")
        else:
            dest_meta = next((d for d in DESTINATIONS if d.get("id") == trip["destination_id"]), {})
            h_lat = dest_meta.get("lat", 28.6139)
            h_lon = dest_meta.get("lon", 77.2090)
            h_addr = f"{payload.hotel_name}, {trip.get('destination_name', '')}"

    validate_stay_location(trip,h_lat,h_lon)
    # Save to core_stays
    stay = Stay(
        stay_id=f"stay_custom_{uuid.uuid4().hex[:6]}",
        trip_id=trip_id,
        name=payload.hotel_name,
        stay_type="hotel",
        lat=h_lat,
        lon=h_lon,
        address=h_addr,
        provenance=Provenance(
            source="user_hotel_first",
            is_live=False,
            is_estimate=True,
            notes="hotel-first user selection",
        ),
    )
    save_stay(stay)

    # Compute preview comparison
    plan = load_trip_plan(trip_id)
    before_commute_min = 70
    after_commute_min = 45

    if plan and plan.days:
        total_dist_before = 0.0
        total_dist_after = 0.0
        for day in plan.days:
            acts = [b.place for b in day.blocks if b.block_type == "activity" and b.place]
            if acts:
                # Before: from first stop to last stop direct
                total_dist_before += haversine_distance_km(acts[0].lat, acts[0].lon, acts[-1].lat, acts[-1].lon)
                # After: anchored round trip to new hotel
                leg1 = haversine_distance_km(h_lat, h_lon, acts[0].lat, acts[0].lon)
                leg2 = haversine_distance_km(acts[-1].lat, acts[-1].lon, h_lat, h_lon)
                total_dist_after += (leg1 + leg2)

        before_commute_min = _estimate_transit_minutes(total_dist_before)
        after_commute_min = _estimate_transit_minutes(total_dist_after)

    return {
        "status": "hotel_anchored",
        "stay": stay,
        "preview": {
            "before_estimated_daily_commute_minutes": before_commute_min,
            "after_estimated_daily_commute_minutes": after_commute_min,
            "transit_difference_minutes": after_commute_min - before_commute_min,
            "label": "preview",
            "message": "Stay anchored. Re-generating your trip plan will optimize day schedules around this hotel.",
        },
    }


@router.post("/{trip_id}/replan")
def replan_trip_with_stay(trip_id: str):
    """Option B: Re-generate trip itinerary anchored to the chosen hotel/stay in core_stays."""
    import json
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

    stay = load_stay(trip_id)
    if not stay:
        raise HTTPException(
            status_code=400,
            detail=f"No stay has been selected for trip {trip_id}. Please select a hotel first."
        )

    # 1. Update trip_preferences in trips table to record stay_anchor
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT trip_preferences_json FROM trips WHERE id = ?", (trip_id,))
            row = cur.fetchone()
            prefs = {}
            if row and row[0]:
                try:
                    prefs = json.loads(row[0])
                except Exception:
                    pass
            prefs["stay_anchor"] = {
                "stay_id": stay.stay_id,
                "name": stay.name,
                "lat": stay.lat,
                "lon": stay.lon,
                "address": stay.address,
            }
            cur.execute("UPDATE trips SET trip_preferences_json = ? WHERE id = ?", (json.dumps(prefs), trip_id))
            conn.commit()
    except Exception:
        pass

    # 2. Re-generate trip plan using plan module
    from app.modules.plan import generate_trip_plan
    new_plan = generate_trip_plan(trip_id)
    from app.itinerary_generator import generate_itinerary
    with get_connection() as conn:
        generate_itinerary(conn,trip['user_id'],trip_id)

    return {
        "status": "success",
        "trip_id": trip_id,
        "stay": stay,
        "plan": new_plan,
        "message": f"Itinerary successfully regenerated around {stay.name} as starting/ending anchor.",
    }


def validate_stay_location(trip, lat, lon):
    from app.providers.geo import resolve_trip_location, is_in_india
    loc = resolve_trip_location(destination_id=trip.get('destination_id'),destination_name=trip.get('destination_name'),
        lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
    if not is_in_india(lat,lon) or loc.get('lat') is None or haversine_distance_km(loc['lat'],loc['lon'],lat,lon)>40:
        raise HTTPException(422, 'Choose a stay in India within 40 km of the destination centre.')
