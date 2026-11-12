"""
Comprehensive tests for Dynamic India-Wide Location & Live Place Recommendation Engine.
Tests Mode A (Search Any Location in India), Mode B (GPS Location Detection),
Geoapify Places discovery, 7-arm LinUCB ranking, and dynamic itinerary generation.
All external network calls are mocked with monkeypatch (strictly offline in tests).
"""
import pytest
from unittest.mock import MagicMock
from app.providers.geo import (
    is_in_india,
    search_locations_india,
    reverse_geocode_india,
    discover_places_india,
    map_geoapify_categories_to_arm,
    haversine_distance_km,
    INDIAN_OFFLINE_HUBS
)
from app.planning.personalization import rank_places_with_linucb


# ==========================================
# 1. INDIA BOUNDING BOX VALIDATION
# ==========================================

def test_is_in_india_valid_coordinates():
    """Valid locations across India must return True."""
    # Delhi (North)
    assert is_in_india(28.6139, 77.2090) is True
    # Mumbai (West)
    assert is_in_india(19.0760, 72.8777) is True
    # Chennai (South)
    assert is_in_india(13.0827, 80.2707) is True
    # Kolkata (East)
    assert is_in_india(22.5726, 88.3639) is True
    # Leh Ladakh (Far North)
    assert is_in_india(34.1526, 77.5771) is True
    # Kanyakumari (Southern tip)
    assert is_in_india(8.0883, 77.5385) is True
    # Guwahati, Assam (North-East)
    assert is_in_india(26.1445, 91.7362) is True


def test_is_in_india_invalid_coordinates():
    """Coordinates outside the Indian subcontinent must return False."""
    # London, UK
    assert is_in_india(51.5074, -0.1278) is False
    # New York, USA
    assert is_in_india(40.7128, -74.0060) is False
    # Tokyo, Japan
    assert is_in_india(35.6762, 139.6503) is False
    # Sydney, Australia
    assert is_in_india(-33.8688, 151.2093) is False
    # Null / Invalid values
    assert is_in_india(None, 77.0) is False
    assert is_in_india(28.0, None) is False


# ==========================================
# 2. CATEGORY TO 7 CANONICAL ARMS MAPPING
# ==========================================

def test_map_geoapify_categories_to_arm():
    """Categories must correctly map to the 7 canonical LinUCB arms."""
    assert map_geoapify_categories_to_arm(["tourism.sights", "heritage"]) == "culture_history"
    assert map_geoapify_categories_to_arm(["catering.restaurant", "catering.fast_food"]) == "food_dining"
    assert map_geoapify_categories_to_arm(["commercial.shopping", "commercial.supermarket"]) == "shopping_local"
    assert map_geoapify_categories_to_arm(["natural.mountain", "natural.water"]) == "nature_outdoors"
    assert map_geoapify_categories_to_arm(["sport.diving", "activity.climbing"]) == "adventure"
    assert map_geoapify_categories_to_arm(["leisure.spa", "wellness"]) == "relaxation"
    assert map_geoapify_categories_to_arm(["tourism.attraction", "tourism.viewpoint"]) == "scenic"
    assert map_geoapify_categories_to_arm(["unknown.custom.tag"]) == "culture_history"


# ==========================================
# 3. LOCATION SEARCH (MODE A)
# ==========================================

def test_search_locations_india_offline_fallback(monkeypatch):
    """When Geoapify fails or is unconfigured, Indian offline hubs are returned."""
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)

    results = search_locations_india("Udaipur", limit=5)
    assert len(results) > 0
    first = results[0]
    assert "Udaipur" in first["city"] or "Udaipur" in first["name"]
    assert is_in_india(first["lat"], first["lon"]) is True
    assert first["provenance"]["is_live"] is False
    assert first["provenance"]["source"] in ("curated_catalogue", "curated_offline_hub")


def test_search_locations_india_mocked_geoapify(monkeypatch):
    """Geoapify autocomplete response must be parsed correctly with live provenance."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "results": [
            {
                "name": "HampiLive",
                "city": "Hampi",
                "state": "Karnataka",
                "country": "India",
                "formatted": "Hampi, Vijayanagara, Karnataka, India",
                "lat": 15.3350,
                "lon": 76.4600
            }
        ]
    }

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: True)
    monkeypatch.setattr("app.providers.geo.can_call_geoapify", lambda: True)

    results = search_locations_india("HampiLiveTestQueryUnique", limit=5)
    assert len(results) >= 1
    hampi = results[0]
    assert hampi["name"] == "HampiLive"
    assert hampi["city"] == "Hampi"
    assert hampi["state"] == "Karnataka"
    assert hampi["provenance"]["is_live"] is True
    assert hampi["provenance"]["source"] == "geoapify"


# ==========================================
# 4. REVERSE GEOCODING (MODE B)
# ==========================================

def test_reverse_geocode_india_rejects_out_of_bounds():
    """Coordinates outside India must raise ValueError."""
    with pytest.raises(ValueError) as excinfo:
        reverse_geocode_india(51.5074, -0.1278)  # London
    assert "outside India" in str(excinfo.value)


def test_reverse_geocode_india_success(monkeypatch):
    """Coordinates inside India must resolve to structured location with provenance."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "results": [
            {
                "city": "MumbaiLive",
                "state": "Maharashtra",
                "country": "India",
                "country_code": "in",
                "formatted": "Nariman Point, Mumbai, Maharashtra, 400021, India",
                "lat": 18.9220,
                "lon": 72.8238
            }
        ]
    }

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: True)
    monkeypatch.setattr("app.providers.geo.can_call_geoapify", lambda: True)

    loc = reverse_geocode_india(18.9220, 72.8238)
    assert loc["city"] == "MumbaiLive"
    assert loc["state"] == "Maharashtra"
    assert loc["country"] == "India"
    assert loc["provenance"]["is_live"] is True
    assert loc["provenance"]["source"] == "geoapify"


# ==========================================
# 5. DISCOVER REAL PLACES (PLACES API v2)
# ==========================================

def test_discover_places_india_mocked(monkeypatch):
    """Discovered places must have 7 canonical arms, null-safe ratings/prices, and distances."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "features": [
            {
                "properties": {
                    "name": "Shaniwar Wada",
                    "categories": ["tourism.sights", "heritage"],
                    "formatted": "Shaniwar Peth, Pune, Maharashtra",
                    "lat": 18.5196,
                    "lon": 73.8553,
                    "opening_hours": "08:00-18:30"
                }
            },
            {
                "properties": {
                    "name": "Kayani Bakery",
                    "categories": ["catering.restaurant"],
                    "formatted": "Camp, Pune, Maharashtra",
                    "lat": 18.5140,
                    "lon": 73.8780
                }
            }
        ]
    }

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: True)
    monkeypatch.setattr("app.providers.geo.can_call_geoapify", lambda: True)

    places = discover_places_india(18.5204, 73.8567, radius_meters=15000, limit=10)
    assert len(places) == 2

    fort = places[0]
    assert fort.name == "Shaniwar Wada"
    assert fort.category == "culture_history"
    assert fort.provenance.is_live is True
    # Null safety: unknown cost and rating must be None, never 0.0
    assert fort.cost_amount is None
    assert fort.rating is None
    dist = haversine_distance_km(18.5204, 73.8567, fort.lat, fort.lon)
    assert dist >= 0.0

    bakery = places[1]
    assert bakery.name == "Kayani Bakery"
    assert bakery.category == "food_dining"


# ==========================================
# 6. LINUCB PERSONALIZATION OF DISCOVERED PLACES
# ==========================================

def test_rank_places_with_linucb():
    """Discovered places must be ranked using 24-dim LinUCB context vector and proximity bonus."""
    places = [
        {
            "id": "p1",
            "name": "Heritage Palace",
            "arm": "culture_history",
            "category": "culture_history",
            "lat": 18.5200,
            "lon": 73.8560,
            "cost": None
        },
        {
            "id": "p2",
            "name": "Bustling Bazaar",
            "arm": "shopping_local",
            "category": "shopping_local",
            "lat": 18.6500,
            "lon": 73.9900,
            "cost": None
        }
    ]

    profile = {
        "interests": ["culture_history", "sightseeing"],
        "pace": 0.7,
        "crowd_tolerance": 0.2,  # Dislikes heavy crowds
        "budget_tier": "balanced"
    }

    ranked = rank_places_with_linucb(
        places=places,
        profile=profile,
        user_id="user_test_123",
        center_lat=18.5204,
        center_lon=73.8567,
        total_days=3
    )

    assert len(ranked) == 2
    # First item should be the close culture attraction
    assert ranked[0]["id"] == "p1"
    assert "score" in ranked[0]
    assert "match_reason" in ranked[0]
    assert ranked[0]["score"] > ranked[1]["score"]


# ==========================================
# 7. END-TO-END FASTAPI API ROUTES
# ==========================================

def test_api_places_search_locations(client):
    """GET /api/places/search-locations must return valid Indian results."""
    r = client.get("/api/places/search-locations?q=Pune&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] > 0
    assert len(data["results"]) > 0
    first = data["results"][0]
    assert "lat" in first and "lon" in first
    assert is_in_india(first["lat"], first["lon"]) is True


def test_api_places_reverse_geocode_bounds(client):
    """GET /api/places/reverse-geocode must reject non-Indian coordinates with 400."""
    # Out of India: London (lat 51.5, lon -0.12)
    r = client.get("/api/places/reverse-geocode?lat=51.5074&lon=-0.1278")
    assert r.status_code == 400
    assert "outside India" in r.json()["detail"]


def test_api_places_reverse_geocode_in_india(client, monkeypatch):
    """GET /api/places/reverse-geocode inside India must return 200 and structured location."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "results": [
            {
                "city": "BengaluruLive",
                "state": "Karnataka",
                "country": "India",
                "country_code": "in",
                "formatted": "MG Road, Bengaluru, Karnataka, India",
                "lat": 12.9716,
                "lon": 77.5946
            }
        ]
    }

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: True)
    monkeypatch.setattr("app.providers.geo.can_call_geoapify", lambda: True)

    r = client.get("/api/places/reverse-geocode?lat=12.9716&lon=77.5946")
    assert r.status_code == 200
    data = r.json()
    assert data["city"] == "BengaluruLive"
    assert data["state"] == "Karnataka"
    assert data["country"] == "India"
    assert data["provenance"]["is_live"] is True


def test_api_places_discover(client):
    """GET /api/places/discover must return places for valid Indian coordinates."""
    r = client.get("/api/places/discover?lat=18.5204&lon=73.8567&radius_meters=15000&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "places" in data
    assert "provenance" in data
    assert len(data["places"]) > 0


def test_api_places_plan_dynamic_end_to_end(client, demo_user):
    """POST /api/places/plan-dynamic must plan a trip with discovered places without falling back to Delhi."""
    payload = {
        "user_id": demo_user,
        "city": "Pune",
        "state": "Maharashtra",
        "lat": 18.5204,
        "lon": 73.8567,
        "start_date": "2026-12-01",
        "end_date": "2026-12-03",
        "travellers_count": 2,
        "total_budget": 20000.0,
        "accommodation_tier": "mid_range",
        "transit_pref": "cab_rental",
        "travel_pace": "balanced",
        "radius_meters": 15000
    }

    r = client.post("/api/places/plan-dynamic", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert "trip" in data
    assert "itinerary" in data
    assert data["trip"]["destination_id"].startswith("pune_")
    assert data["trip"]["destination_name"] == "Pune, Maharashtra"
    assert len(data["itinerary"]["days"]) > 0
    # Center coordinates must match Pune (lat ~18.52, lon ~73.85) and NEVER fall back to Delhi
    assert abs(data["destination"]["lat"] - 18.5204) < 1.0
    assert abs(data["destination"]["lon"] - 73.8567) < 1.0
