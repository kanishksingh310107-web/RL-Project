# Real-Time Locations & Places API Router
# Owner: Person C (Integrator)
# Provides on-demand real-world location geocoding, live attraction fetching,
# and instant LinUCB-powered itinerary generation for ANY Indian destination.

import re
import uuid
import json
import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query, status

from app.database import get_connection
from app.modules.common import _decode
from app.modules.places_service import search_indian_locations, fetch_real_places_for_city
from app.itinerary_generator import generate_itinerary
from app.modules.trip_actions import get_timed_itinerary_view

MODULE = {
    "id": "places",
    "title": "Places API",
    "icon": "fa-location-dot",
    "owner": "C"
}

router = APIRouter(prefix="/api/places", tags=["places"])


class PlanDynamicTripRequest(BaseModel):
    user_id: str
    city_name: str
    start_date: str = Field(default="2026-11-10", description="YYYY-MM-DD")
    duration_days: int = Field(default=3, ge=1, le=14)
    pace_preference: str = Field(default="balanced", description="relaxed, balanced, packed")
    budget_tier: str = Field(default="balanced", description="budget, balanced, luxury")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    state: Optional[str] = "India"


@router.get("/search")
def search_locations_endpoint(
    q: str = Query(..., min_length=2, description="Search term for city/region in India"),
    limit: int = Query(6, ge=1, le=15)
):
    """
    Search real cities, towns, and tourist destinations across India.
    Powered dynamically by OpenStreetMap Nominatim Geocoding API.
    """
    results = search_indian_locations(q, limit=limit)
    return {
        "query": q,
        "count": len(results),
        "results": results,
        "data_source": "openstreetmap_nominatim_live"
    }


@router.get("/attractions")
def get_attractions_endpoint(
    city: str = Query(..., description="City or tourist hub name"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lon: Optional[float] = Query(None, description="Longitude"),
    limit: int = Query(10, ge=1, le=20)
):
    """
    Fetch live attractions, viewpoints, historic monuments, and dining places
    for ANY city in India on-demand via Wikivoyage & Wikipedia APIs.
    """
    attractions = fetch_real_places_for_city(city, lat=lat, lon=lon, limit=limit)
    return {
        "city": city,
        "count": len(attractions),
        "attractions": attractions,
        "is_live_data": True,
        "provider": "wikivoyage_wikipedia_places_api"
    }


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


@router.post("/plan-trip")
def plan_dynamic_trip(payload: PlanDynamicTripRequest):
    """
    Takes ANY Indian city (e.g. Manali, Goa, Jaipur, Kochi, Pondicherry, Shimla):
    1. Geocodes and retrieves real location coordinates.
    2. Dynamically fetches real places and attractions via the Places API.
    3. Seeds the live attractions into SQLite `destination_activities`.
    4. Creates a trip in `trips`.
    5. Runs Contextual LinUCB scheduler to build a personalized day-by-day plan.
    6. Returns the enriched Timed View with Sightseeing, Transit buffers, Lunch, Dinner, and Rest breaks.
    """
    clean_city = payload.city_name.strip()
    
    # 1. Geocode if coordinates not passed
    lat = payload.latitude
    lon = payload.longitude
    state = payload.state or "India"
    
    if lat is None or lon is None:
        locs = search_indian_locations(clean_city, limit=1)
        if locs:
            lat = locs[0]["latitude"]
            lon = locs[0]["longitude"]
            state = locs[0]["state"]
        else:
            lat, lon = 20.5937, 78.9629

    dest_id = re.sub(r"[^a-z0-9]+", "_", clean_city.lower()).strip("_") + "_india"
    dest_name = f"{clean_city}, {state}" if state and state != "India" else f"{clean_city}, India"

    # 2. Fetch live real attractions from Wikivoyage / Wikipedia Places API
    live_attractions = fetch_real_places_for_city(clean_city, lat=lat, lon=lon, limit=14)
    
    # 3. Seed real attractions into SQLite database
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Verify user exists
        u_row = cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,)).fetchone()
        if not u_row:
            raise HTTPException(status_code=404, detail=f"User {payload.user_id} not found. Please log in.")
            
        for a in live_attractions:
            cursor.execute("""
                INSERT OR REPLACE INTO destination_activities (
                    id, destination_id, name, category, neighborhood,
                    latitude, longitude, duration_minutes, cost_tier,
                    cost_amount, physical_intensity, crowd_level,
                    opening_time, closing_time, tags, avoidance_triggers,
                    description, photo_url, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                a["id"],
                dest_id,
                a["name"],
                a["category"],
                a.get("neighborhood", f"Central {clean_city}"),
                a.get("latitude") or lat,
                a.get("longitude") or lon,
                a.get("duration_minutes", 90),
                a.get("cost_tier", "budget"),
                a.get("cost_amount", 5.0),
                a.get("physical_intensity", "moderate"),
                a.get("crowd_level", "moderate"),
                a.get("opening_time", "09:00"),
                a.get("closing_time", "18:00"),
                json.dumps(a.get("tags", [a["category"]])),
                json.dumps(a.get("avoidance_triggers", [])),
                a["description"],
                a.get("photo_url"),
                a.get("data_source", "live_places_api")
            ))
            
        # 4. Create Trip
        trip_id = str(uuid.uuid4())
        start_date = payload.start_date
        try:
            dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = (dt + datetime.timedelta(days=payload.duration_days)).strftime("%Y-%m-%d")
        except ValueError:
            end_date = start_date

        cursor.execute("""
            INSERT INTO trips (
                id, user_id, destination_id, destination_name,
                start_date, end_date, duration_days, travellers_count,
                total_budget, currency, accommodation_tier, transit_pref,
                travel_pace, specific_interests, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1500.0, 'USD', 'balanced', 'public_transit', ?, '[]', 'planning', CURRENT_TIMESTAMP)
        """, (
            trip_id,
            payload.user_id,
            dest_id,
            dest_name,
            start_date,
            end_date,
            payload.duration_days,
            payload.pace_preference
        ))
        conn.commit()

        # 5. Generate LinUCB day-by-day Itinerary
        generate_itinerary(conn, user_id=payload.user_id, trip_id=trip_id)

    # 6. Retrieve Timed Itinerary View (Sightseeing + Transit + Meals + Rest breaks)
    timed_view = get_timed_itinerary_view(trip_id)

    return {
        "status": "success",
        "trip_id": trip_id,
        "destination": {
            "id": dest_id,
            "name": dest_name,
            "city": clean_city,
            "state": state,
            "latitude": lat,
            "longitude": lon
        },
        "places_fetched_count": len(live_attractions),
        "places_sample": [a["name"] for a in live_attractions[:6]],
        "timed_schedule": timed_view
    }
