"""Tests for Task 6: Unified Trip Creation Location Search, GPS & Nearby Place Discovery.

Verifies:
1. Standalone "Dynamic India Discovery" panel is removed from static/index.html.
2. Unified trip creation modal (#tripFormModal) integrates location search,
   supported destinations, GPS button, radius control, and nearby place preview.
3. Location search, GPS reverse-geocoding, nearby place discovery (with LinUCB
   scoring), and dynamic itinerary planning (with radius and stay anchor) work
   end-to-end after removing the standalone interface.
"""
from pathlib import Path
from unittest.mock import MagicMock

from app.core.stores import load_stay
from app.providers.geo import is_in_india


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def test_standalone_discovery_section_removed_from_ui():
    """Standalone Dynamic India Discovery panel must not exist in static/index.html."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="dynamicDiscoverySection"' not in html
    assert "Discover Real Places Anywhere in India" not in html
    assert 'id="dynamicLocationSearchInput"' not in html
    assert 'id="dynamicPlacesGrid"' not in html

    assert "dynamicDiscoverySection" not in js
    assert "dynamicLocationSearchInput" not in js
    assert "openPlanModalForActiveLocation" not in js


def test_trip_modal_integrates_search_gps_and_nearby_discovery():
    """Trip creation modal must unify location search, GPS, supported destinations, and nearby places."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    modal_start = html.index('id="tripFormModal"')
    modal_end = html.index('id="activityRejectModal"')
    modal_html = html[modal_start:modal_end]

    assert 'id="tripCitySearchInput"' in modal_html
    assert 'oninput="handleCitySearchInput(this.value)"' in modal_html
    assert 'id="citySearchResults"' in modal_html
    assert 'id="gpsDetectBtn"' in modal_html
    assert 'onclick="detectUserLocation()"' in modal_html
    assert 'id="tripDestSelect"' in modal_html
    assert 'onchange="handleFeaturedDestinationChange(this.value)"' in modal_html
    assert 'id="tripDiscoveryRadiusSelect"' in modal_html
    assert 'id="tripNearbyPlacesArea"' in modal_html
    assert 'id="tripNearbyPlacesGrid"' in modal_html


def test_location_search_covers_cities_and_supported_destinations(client, monkeypatch):
    """Location search endpoint must resolve both Indian cities and curated destinations with real coords."""
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)

    for query in ("Pune", "Shillong", "Alleppey", "Coorg"):
        r = client.get(f"/api/places/search-locations?q={query}&limit=5")
        assert r.status_code == 200, f"Failed for query {query}: {r.text}"
        data = r.json()
        assert data["count"] > 0, f"Expected results for {query}"
        first = data["results"][0]
        assert is_in_india(first["lat"], first["lon"]) is True
        # Ensure we didn't fall back to the generic centroid of India
        assert not (abs(first["lat"] - 20.5937) < 1e-4 and abs(first["lon"] - 78.9629) < 1e-4)


def test_gps_reverse_geocode_and_nearby_discovery_linucb(client, demo_user, monkeypatch):
    """GPS reverse-geocoding feeds into nearby place discovery with LinUCB ranking."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "results": [
            {
                "city": "Mysuru",
                "state": "Karnataka",
                "country": "India",
                "country_code": "in",
                "formatted": "Devaraja Mohalla, Mysuru, Karnataka, India",
                "lat": 12.3051,
                "lon": 76.6551,
            }
        ]
    }
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: True)
    monkeypatch.setattr("app.providers.geo.can_call_geoapify", lambda: True)

    gps_res = client.get("/api/places/reverse-geocode?lat=12.3051&lon=76.6551")
    assert gps_res.status_code == 200
    gps_data = gps_res.json()
    loc = gps_data["location"]
    assert loc["city"] == "Mysuru"
    assert loc["state"] == "Karnataka"

    # Disable live geoapify for discovery so curated fallback runs offline cleanly
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)
    disc_res = client.get(
        f"/api/places/discover?lat={loc['lat']}&lon={loc['lon']}&radius_meters=15000&user_id={demo_user}&limit=10"
    )
    assert disc_res.status_code == 200
    disc_data = disc_res.json()
    assert disc_data["personalized"] is True
    assert disc_data["count"] > 0
    assert all("score" in p and "arm" in p for p in disc_data["places"])


def test_gps_discovered_location_feeds_itinerary_and_stay_anchor(client, demo_user, monkeypatch):
    """Trip creation from searched/GPS location passes radius & stay anchor into LinUCB itinerary planner."""
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)

    payload = {
        "user_id": demo_user,
        "city": "Mysuru",
        "state": "Karnataka",
        "lat": 12.2958,
        "lon": 76.6394,
        "start_date": "2026-12-10",
        "end_date": "2026-12-12",
        "travellers_count": 2,
        "total_budget": 24000.0,
        "accommodation_tier": "boutique",
        "transit_pref": "cab_rental",
        "travel_pace": "balanced",
        "radius_meters": 25000,
        "stay_id": "stay_mysuru_palace_1",
        "stay_name": "Royal Orchid Metropole",
        "stay_lat": 12.3106,
        "stay_lon": 76.6413,
        "stay_address": "5 Jhansi Lakshmibai Rd, Mysuru",
        "stay_type": "hotel",
    }

    r = client.post("/api/places/plan-dynamic", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["places_fetched_count"] > 0
    assert len(data["itinerary"]["days"]) == 3

    saved_stay = load_stay(data["trip_id"])
    assert saved_stay is not None
    assert saved_stay.name == "Royal Orchid Metropole"
    assert abs(saved_stay.lat - 12.3106) < 1e-4
