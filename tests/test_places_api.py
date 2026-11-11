# Tests for Real-Time Places API & Dynamic Location Service
# Owner: Person C (Integrator)
# Verifies geocoding, live attraction fetching, and dynamic LinUCB trip planning.

import pytest
from app.modules.places_service import search_indian_locations, fetch_real_places_for_city


def test_places_module_registered(client):
    """Places module must be auto-discovered in the module registry and its routes must respond."""
    from app.modules import discover
    mods = [m.MODULE for m in discover()]
    p_mod = next((m for m in mods if m["id"] == "places"), None)
    assert p_mod is not None, "Places module must be auto-discovered and registered"
    assert p_mod["owner"] == "C"
    assert p_mod["title"] == "Places API"
    r = client.get("/api/places/popular")
    assert r.status_code == 200


def test_search_indian_locations_endpoint(client):
    """Search endpoint must return real geocoded Indian locations with coordinates."""
    r = client.get("/api/places/search?q=Manali")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] > 0
    first = data["results"][0]
    assert "city" in first
    assert "state" in first
    assert "latitude" in first and isinstance(first["latitude"], (int, float))
    assert "longitude" in first and isinstance(first["longitude"], (int, float))
    assert first["country"] == "India"


def test_get_attractions_endpoint(client):
    """Attractions endpoint must return real live tourist places with LinUCB arm categories."""
    r = client.get("/api/places/attractions?city=Manali&lat=32.2432&lon=77.1892")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] > 0
    first = data["attractions"][0]
    assert "name" in first
    assert "category" in first
    assert "description" in first
    assert first["duration_minutes"] > 0


def test_get_popular_destinations(client):
    """Popular destinations endpoint must return Indian hubs with tags and coordinates."""
    r = client.get("/api/places/popular")
    assert r.status_code == 200
    dests = r.json().get("destinations", [])
    assert len(dests) >= 8
    cities = {d["city"] for d in dests}
    assert "Manali" in cities
    assert "Jaipur" in cities
    assert "South Goa" in cities or "Goa" in cities


def test_plan_dynamic_trip_end_to_end(client):
    """
    End-to-end dynamic workflow:
    1. User picks any Indian city (e.g., Pondicherry).
    2. API geocodes and fetches live attractions on-demand.
    3. Ingests into SQLite database.
    4. Generates Contextual LinUCB itinerary.
    5. Returns enriched Timed View with Sightseeing, Transit buffers, Lunch, Dinner, and Rest breaks.
    """
    # Create test user
    auth = client.post(
        "/api/auth",
        json={"provider": "email", "identifier": "dyn_plan@test.com", "password": "pass123456", "display_name": "Karan"}
    ).json()
    uid = auth["user_id"]

    # Plan dynamic trip for Pondicherry
    r = client.post("/api/places/plan-trip", json={
        "user_id": uid,
        "city_name": "Pondicherry",
        "duration_days": 2,
        "pace_preference": "balanced",
        "budget_tier": "balanced"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert "trip_id" in data
    assert data["places_fetched_count"] > 0

    timed = data["timed_schedule"]
    assert "days" in timed
    assert len(timed["days"]) == 2

    # Verify structured blocks inside each day
    day1 = timed["days"][0]
    block_types = [b["type"] for b in day1["timeline"]]
    assert "activity" in block_types
    assert "transit" in block_types
    assert "meal" in block_types
    assert "rest" in block_types


def test_places_service_fallback_offline():
    """Fallback search should return valid hubs even when offline."""
    from app.modules.places_service import _fallback_search
    res = _fallback_search("Goa")
    assert len(res) > 0
    assert any("Goa" in r["city"] for r in res)
    assert all(r["country"] == "India" for r in res)


def test_plan_trip_unknown_city_returns_404(client):
    """Unknown or unlocatable city should return HTTP 404 rather than silent India centroid fallback."""
    auth = client.post(
        "/api/auth",
        json={"provider": "email", "identifier": "unknown_city_test@test.com", "password": "pass123456", "display_name": "Karan"}
    ).json()
    uid = auth["user_id"]

    r = client.post("/api/places/plan-trip", json={
        "user_id": uid,
        "city_name": "NonExistentAtlantisXYZCity999",
        "duration_days": 2,
    })
    assert r.status_code == 404
    assert "Could not locate 'NonExistentAtlantisXYZCity999' in India" in r.json()["detail"]
