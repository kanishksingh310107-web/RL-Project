# Real-Time Locations & Places API Router
# Owner: Person C (Integrator)
# Provides on-demand real-world location geocoding, GPS reverse geocoding,
# real-time place discovery via Geoapify, and Contextual LinUCB personalized ranking
# and itinerary generation for ANY Indian destination.

import re
import uuid
import json
import sqlite3
import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from fastapi import APIRouter, HTTPException, Query, status, Depends, Request
from app.profile_gate import require_profile_complete

from app.database import get_connection
from app.modules.common import get_user_context
from app.providers.geo import (
    is_in_india,
    search_locations_india,
    reverse_geocode_india,
    discover_places_india,
    geocode_india,
    haversine_distance_km,
)
from app.providers.cache import set_cached, TTL_PLACES_SECONDS
from app.planning import rank_places_with_linucb
from app.planning.budget import calculate_minimum_trip_budget, adapt_itinerary_to_budget
from app.itinerary_generator import generate_itinerary
from app.modules.trip_actions import get_timed_itinerary_view

MODULE = {
    "id": "places",
    "title": "Places API",
    "icon": "fa-location-dot",
    "owner": "C"
}

router = APIRouter(prefix="/api/places", tags=["places"])


def load_profile(user_id: str) -> Dict[str, Any]:
    """Loads unified profile dict for LinUCB personalization."""
    ctx = get_user_context(user_id)
    answers = ctx.get("answers", {})
    basic = ctx.get("basic") or {}
    profile = {**basic, **answers}
    if not profile.get("interests"):
        profile["interests"] = basic.get("interests") or answers.get("place_interests") or answers.get("travel_goals") or ["culture_history"]
    return profile


def init_tables(conn: sqlite3.Connection):
    """Ensures tables required by dynamic places and activities."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dynamic_locations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            formatted TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


class PlanDynamicTripRequest(BaseModel):
    model_config = ConfigDict(extra='allow')  # Canonical TripCreate validates extended planning inputs after geocoding.
    party: Optional[Dict[str, int]] = None
    user_id: str
    city_name: Optional[str] = None
    city: Optional[str] = None
    start_date: str = Field(default="2026-11-20", description="YYYY-MM-DD")
    end_date: Optional[str] = None
    duration_days: Optional[int] = Field(None,ge=1,le=90,strict=True)
    pace_preference: str = Field(default="balanced", description="relaxed, balanced, packed")
    travel_pace: Optional[str] = None
    budget_tier: str = Field(default="balanced", description="budget, balanced, luxury")
    accommodation_tier: Optional[str] = "mid_range"
    transit_pref: Optional[str] = "cab_rental"
    companions: Optional[str] = "solo"
    has_children: Optional[bool] = False
    has_elderly: Optional[bool] = False
    departure_location: Optional[str] = "Delhi"
    trip_preferences: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    lat: Optional[float] = None
    longitude: Optional[float] = None
    lon: Optional[float] = None
    state: Optional[str] = "India"
    total_budget: Optional[float] = 25000.0
    travellers_count: Optional[int] = 1
    radius_meters: Optional[int] = 15000
    stay_id: Optional[str] = None
    stay_name: Optional[str] = None
    stay_lat: Optional[float] = None
    stay_lon: Optional[float] = None
    stay_address: Optional[str] = None
    stay_type: Optional[str] = None

    @field_validator('start_date','end_date')
    @classmethod
    def valid_trip_date(cls,value):
        if value is None:return value
        try:
            if datetime.date.fromisoformat(value).isoformat()!=value:raise ValueError
        except (TypeError,ValueError) as exc:
            raise ValueError('Use a valid YYYY-MM-DD trip date.') from exc
        return value


# -----------------------------------------------------------------------------
# 1. Location Autocomplete & Search (Mode A)
# -----------------------------------------------------------------------------

@router.get("/search-locations")
@router.get("/search")
def search_locations_endpoint(
    q: str = Query(..., min_length=2, description="Search term for city/town/region in India"),
    limit: int = Query(6, ge=1, le=15)
):
    """
    Search real cities, towns, and tourist destinations across India.
    Restricted strictly to Indian geographical entities via Geoapify / Curated Catalogue.
    """
    results = search_locations_india(q, limit=limit)
    for r in results:
        if "lat" in r and "latitude" not in r:
            r["latitude"] = r["lat"]
        if "lon" in r and "longitude" not in r:
            r["longitude"] = r["lon"]
    source = results[0]["provenance"]["source"] if results else "offline_catalogue"
    return {
        "query": q,
        "count": len(results),
        "results": results,
        "data_source": source,
    }


# -----------------------------------------------------------------------------
# 2. GPS Reverse Geocoding (Mode B)
# -----------------------------------------------------------------------------

@router.get("/reverse-geocode")
def reverse_geocode_endpoint(
    lat: float = Query(..., description="Latitude from GPS"),
    lon: float = Query(..., description="Longitude from GPS"),
):
    """
    Resolves GPS coordinates into a structured Indian location (city, town, neighbourhood).
    Rejects coordinates that fall outside India.
    """
    if not is_in_india(lat, lon):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coordinates ({lat}, {lon}) are outside India. This travel guide exclusively supports travel within India."
        )

    try:
        location = reverse_geocode_india(lat, lon)
        return {
            "status": "success",
            "city": location.get("city"),
            "state": location.get("state"),
            "country": location.get("country", "India"),
            "formatted": location.get("formatted"),
            "lat": location.get("lat"),
            "lon": location.get("lon"),
            "location": location,
            "provenance": location.get("provenance", {})
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reverse geocoding failed: {str(e)}"
        )


# -----------------------------------------------------------------------------
# 3. Real-Time Place Discovery & LinUCB Personalization
# -----------------------------------------------------------------------------

@router.get("/discover")
def discover_places_endpoint(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_meters: int = Query(15000, ge=1000, le=50000, description="Search radius in meters"),
    category: Optional[str] = Query(None, description="Optional category filter"),
    user_id: Optional[str] = Query(None, description="Optional user ID for personalized LinUCB ranking"),
    limit: int = Query(20, ge=1, le=50)
):
    """
    Discovers actual nearby attractions, monuments, restaurants, nature spots, and shopping.
    When user_id is provided, applies 24-dimensional Contextual LinUCB ranking and hard constraint filters.
    """
    if not is_in_india(lat, lon):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coordinates ({lat}, {lon}) are outside India. Discovery is supported only within India."
        )

    places = discover_places_india(
        lat=lat,
        lon=lon,
        radius_meters=radius_meters,
        categories=category,
        limit=limit
    )

    is_live = any(p.provenance.is_live for p in places) if places else False
    data_source = places[0].provenance.source if places else "none"

    # If user_id provided, rank via LinUCB
    if user_id:
        profile = load_profile(user_id)
        ranked = rank_places_with_linucb(
            places=places,
            profile=profile,
            user_id=user_id,
            center_lat=lat,
            center_lon=lon,
        )
        return {
            "status": "success",
            "center": {"lat": lat, "lon": lon},
            "radius_meters": radius_meters,
            "count": len(ranked),
            "personalized": True,
            "places": ranked,
            "is_live_data": is_live,
            "data_source": data_source,
            "provenance": {"is_live": is_live, "source": data_source},
        }

    # Unauthenticated / unpersonalized view
    plain_places: List[Dict[str, Any]] = []
    for p in places:
        dist_km = haversine_distance_km(lat, lon, p.lat, p.lon)
        plain_places.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "arm": p.category,
            "lat": p.lat,
            "lon": p.lon,
            "address": p.address,
            "neighbourhood": p.neighbourhood,
            "distance_km": dist_km,
            "score": 1.0,
            "match_reason": f"{dist_km:.1f} km away",
            "opening_hours": p.opening_hours,
            "phone": p.phone,
            "website": p.website,
            "photo_url": p.photo_url,
            "provenance": p.provenance.model_dump() if hasattr(p.provenance, "model_dump") else p.provenance,
        })

    return {
        "status": "success",
        "center": {"lat": lat, "lon": lon},
        "radius_meters": radius_meters,
        "count": len(plain_places),
        "personalized": False,
        "places": plain_places,
        "is_live_data": is_live,
        "data_source": data_source,
        "provenance": {"is_live": is_live, "source": data_source},
    }


# -----------------------------------------------------------------------------
# 4. Backward-Compatible /attractions Endpoint
# -----------------------------------------------------------------------------

@router.get("/attractions")
def get_attractions_endpoint(
    city: str = Query(..., description="City or tourist hub name"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lon: Optional[float] = Query(None, description="Longitude"),
    limit: int = Query(10, ge=1, le=20)
):
    """
    Fetch live attractions for any city in India using Geoapify discovery with geocoding fallback.
    """
    if lat is None or lon is None:
        loc = geocode_india(city)
        if loc:
            lat = float(loc["lat"])
            lon = float(loc["lon"])
        else:
            lat = 20.5937
            lon = 78.9629

    places = discover_places_india(lat, lon, radius_meters=15000, limit=limit)
    is_live = any(p.provenance.is_live for p in places) if places else False
    
    attraction_dicts = []
    for p in places:
        attraction_dicts.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "neighborhood": p.neighbourhood or f"Near {city}",
            "latitude": p.lat,
            "longitude": p.lon,
            "description": p.address or f"{p.name} in {city}",
            "duration_minutes": p.typical_duration_minutes or 90,
            "cost_tier": "budget",
            "cost_amount": p.cost_amount or 100.0,
            "physical_intensity": "moderate",
            "crowd_level": "moderate",
            "opening_time": "09:00",
            "closing_time": "18:00",
            "photo_url": p.photo_url,
            "data_source": p.provenance.source,
        })

    return {
        "city": city,
        "count": len(attraction_dicts),
        "attractions": attraction_dicts,
        "is_live_data": is_live,
        "provider": "geoapify_places_api" if is_live else "curated_catalogue",
    }


# -----------------------------------------------------------------------------
# 5. Quick Popular Hubs
# -----------------------------------------------------------------------------

@router.get("/popular")
def get_popular_indian_destinations():
    """Returns curated list of popular real-world Indian hubs for quick selection."""
    hubs = [
        {"city": "Manali", "state": "Himachal Pradesh", "tagline": "Himalayan pine valleys & high-altitude passes", "lat": 32.2432, "lon": 77.1892, "icon": "fa-mountain"},
        {"city": "South Goa", "state": "Goa", "tagline": "Serene crescent beaches & Portuguese heritage", "lat": 15.0100, "lon": 74.0232, "icon": "fa-umbrella-beach"},
        {"city": "Jaipur", "state": "Rajasthan", "tagline": "Pink City palaces, forts & royal bazaars", "lat": 26.9124, "lon": 75.7873, "icon": "fa-landmark"},
        {"city": "Varanasi", "state": "Uttar Pradesh", "tagline": "Ganga Aarti, ancient ghats & spiritual dawn boat tours", "lat": 25.3176, "lon": 82.9739, "icon": "fa-om"},
        {"city": "Udaipur", "state": "Rajasthan", "tagline": "Gleaming marble lake palaces & Pichola boat cruises", "lat": 24.5854, "lon": 73.7125, "icon": "fa-crown"},
        {"city": "Munnar", "state": "Kerala", "tagline": "Rolling emerald tea plantations & misty Western Ghats", "lat": 10.0889, "lon": 77.0595, "icon": "fa-leaf"},
        {"city": "Leh Ladakh", "state": "Ladakh", "tagline": "Pangong turquoise lake & Khardung La passes", "lat": 34.1526, "lon": 77.5771, "icon": "fa-mountain-sun"},
        {"city": "Rishikesh", "state": "Uttarakhand", "tagline": "Ganges river rafting, yoga ashrams & forest falls", "lat": 30.0869, "lon": 78.2676, "icon": "fa-water"},
        {"city": "Amritsar", "state": "Punjab", "tagline": "Golden Temple langar & Wagah border retreat", "lat": 31.6340, "lon": 74.8723, "icon": "fa-place-of-worship"},
        {"city": "Darjeeling", "state": "West Bengal", "tagline": "Himalayan toy train & Kanchenjunga sunrise", "lat": 27.0410, "lon": 88.2663, "icon": "fa-train"},
    ]
    return {"destinations": hubs, "country": "India"}


# -----------------------------------------------------------------------------
# 6. Dynamic Trip Creation & Full LinUCB Plan Generation
# -----------------------------------------------------------------------------

@router.post("/plan-dynamic")
@router.post("/plan-trip")
def plan_dynamic_trip(payload: PlanDynamicTripRequest, request: Request, user=Depends(require_profile_complete)):
    """
    Takes ANY Indian location (e.g. Pune, Srinagar, Shillong, Hampi, Madurai):
    1. Geocodes and verifies actual Indian geographical coordinates.
    2. Dynamically fetches real places via Geoapify Places API.
    3. Seeds the live places into SQLite `destination_activities`.
    4. Caches destination coordinates in `core_place_cache`.
    5. Creates a trip in `trips`.
    6. Runs Contextual LinUCB itinerary generator.
    7. Returns complete timed schedule and trip details.
    """
    if payload.user_id != user['id']:
        raise HTTPException(403, {'detail': 'You cannot plan trips for another account', 'code': 'USER_MISMATCH', 'field': 'user_id'})
    city_raw = payload.city_name or payload.city or ""
    clean_city = city_raw.strip()
    if not clean_city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="City name is required (provide city_name or city)."
        )
    
    # 1. Geocode if coordinates not provided
    lat = payload.latitude if payload.latitude is not None else payload.lat
    lon = payload.longitude if payload.longitude is not None else payload.lon
    state = payload.state or "India"
    
    if lat is None or lon is None:
        loc = geocode_india(clean_city)
        if loc:
            lat = float(loc["lat"])
            lon = float(loc["lon"])
            state = loc.get("state") or state
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not locate '{clean_city}' in India. Please verify spelling or provide coordinates."
            )

    if not is_in_india(lat, lon):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Location '{clean_city}' ({lat}, {lon}) is outside India. Trips are supported exclusively within India."
        )

    dest_id = re.sub(r"[^a-z0-9]+", "_", clean_city.lower()).strip("_") + "_india"
    dest_name = f"{clean_city}, {state}" if state and state != "India" else f"{clean_city}, India"

    # Cache destination coordinates for downstream modules (e.g. Plan and Stay)
    set_cached(f"geo:dest:{dest_id}", {"lat": lat, "lon": lon, "name": dest_name}, TTL_PLACES_SECONDS)

    # 2. Fetch real places via Geoapify Places discovery
    discovery_radius = max(1000, min(int(payload.radius_meters or 15000), 50000))
    live_places = discover_places_india(lat=lat, lon=lon, radius_meters=discovery_radius, limit=20)
    
    # 3. Seed real attractions into SQLite database
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Verify user exists
        u_row = cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,)).fetchone()
        if not u_row:
            raise HTTPException(status_code=404, detail=f"User {payload.user_id} not found. Please log in.")
            
        for a in live_places:
            cursor.execute("""
                INSERT OR REPLACE INTO destination_activities (
                    id, destination_id, name, category, neighborhood,
                    latitude, longitude, duration_minutes, cost_tier,
                    cost_amount, physical_intensity, crowd_level,
                    opening_time, closing_time, tags, avoidance_triggers,
                    description, photo_url, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                a.id,
                dest_id,
                a.name,
                a.category,
                a.neighbourhood or f"Central {clean_city}",
                a.lat,
                a.lon,
                a.typical_duration_minutes or 90,
                a.price_level or "budget",
                a.cost_amount if a.cost_amount is not None else 150.0,
                "moderate",
                "moderate",
                "09:00",
                "18:00",
                json.dumps([a.category]),
                json.dumps([]),
                a.address or f"{a.name} in {clean_city}",
                a.photo_url,
                a.provenance.source
            ))
            
        # Use the canonical trip path for validation, party, deduplication and stays.
        conn.commit()
        from app.api import create_trip
        from app.models import TripCreate
        from pydantic import ValidationError
        start_date = payload.start_date
        end_date = payload.end_date or (datetime.date.fromisoformat(start_date)+datetime.timedelta(days=(payload.duration_days or 3)-1)).isoformat()
        values = payload.model_dump(exclude_unset=True)
        values.update(destination_id=dest_id,destination_name=dest_name,destination_lat=lat,destination_lon=lon,
                      start_date=start_date,end_date=end_date,travel_pace=payload.travel_pace or payload.pace_preference)
        try:
            created = create_trip(payload.user_id, TripCreate.model_validate(values))
        except ValidationError as exc:
            issue=exc.errors()[0]
            raise HTTPException(422,{'detail':issue['msg'].removeprefix('Value error, '),'code':'INVALID_INPUT','field':'.'.join(str(p) for p in issue['loc']) or None})
        if isinstance(created, __import__('starlette.responses',fromlist=['Response']).Response):
            return created
        trip_id = created.id
        duration = created.duration_days
        stay_obj = None  # canonical create_trip already persisted any preselected anchor
        # 5. Generate LinUCB day-by-day Itinerary
        generate_itinerary(conn, user_id=payload.user_id, trip_id=trip_id)

    if stay_obj is not None:
        from app.core.stores import save_stay
        save_stay(stay_obj)

    # 6. Retrieve Timed Itinerary View (Sightseeing + Transit + Meals + Rest breaks)
    timed_view = get_timed_itinerary_view(trip_id, request)

    # 7. Also attempt Plan generation in Plan engine (Person A) if profile is complete
    try:
        from app.modules.plan import generate_plan
        generate_plan(trip_id)
    except Exception:
        pass

    return {
        "status": "success",
        "success": True,
        "trip_id": trip_id,
        "trip": {
            "id": trip_id,
            "destination_id": dest_id,
            "destination_name": dest_name,
            "destination_lat": lat,
            "destination_lon": lon,
            "resolved_location": dest_name,
            "start_date": start_date,
            "end_date": end_date,
            "duration_days": duration,
            "departure_location": payload.departure_location or "Delhi",
            "companions": created.companions,
            "party": created.party.model_dump(),
            "party_label": created.party_label,
            "has_children": bool(payload.has_children),
            "has_elderly": bool(payload.has_elderly),
            "trip_preferences": payload.trip_preferences or {}
        },
        "itinerary": timed_view or {"days": []},
        "destination": {
            "id": dest_id,
            "name": dest_name,
            "city": clean_city,
            "state": state,
            "latitude": lat,
            "longitude": lon,
            "lat": lat,
            "lon": lon,
            "country": "India"
        },
        "places_fetched_count": len(live_places),
        "places_sample": [p.name for p in live_places[:6]],
        "timed_schedule": timed_view
    }
