"""Tests for Pan-India Destinations and Real-Time Places Service."""

import pytest
import app.services.places_service as places_service
from app.data.india_destinations import INDIAN_DESTINATIONS, get_all_indian_destinations


def test_indian_destinations_structure_and_regions():
    """Validates that all curated destinations have required fields, valid lat/lon, and all 4 regions."""
    destinations = get_all_indian_destinations()
    assert len(destinations) >= 12

    regions_present = {d["region"] for d in destinations}
    expected_regions = {"North", "West", "South", "East & NE"}
    assert expected_regions.issubset(regions_present)

    for d in destinations:
        assert "id" in d
        assert "name" in d
        assert "state" in d
        assert d["country"] == "India"
        assert isinstance(d["tags"], list) and len(d["tags"]) > 0
        assert d["budget_tier"] in ("budget", "mid_range", "luxury")
        assert isinstance(d["estimated_cost_inr"], int) and d["estimated_cost_inr"] > 0
        assert isinstance(d["best_seasons"], list) and len(d["best_seasons"]) > 0

        # Geographical bounding coordinates for India
        assert 8.0 <= d["lat"] <= 37.0, f"Latitude {d['lat']} out of India bounds for {d['name']}"
        assert 68.0 <= d["lon"] <= 98.0, f"Longitude {d['lon']} out of India bounds for {d['name']}"


def test_destinations_endpoint_unfiltered(client):
    """GET /api/destinations/india returns all destinations."""
    resp = client.get("/api/destinations/india")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 12
    assert len(data["destinations"]) == data["total"]

    first = data["destinations"][0]
    assert first["country"] == "India"
    assert "lat" in first and "lon" in first


def test_destinations_endpoint_filtering(client):
    """Tests budget tier, region, and interest filtering."""
    # Filter by budget tier
    resp_budget = client.get("/api/destinations/india?budget_tier=budget")
    assert resp_budget.status_code == 200
    budget_items = resp_budget.json()["destinations"]
    assert len(budget_items) > 0
    assert all(d["budget_tier"] == "budget" for d in budget_items)

    # Filter by interest 'beach'
    resp_beach = client.get("/api/destinations/india?interest=beach")
    assert resp_beach.status_code == 200
    beach_items = resp_beach.json()["destinations"]
    assert any("Goa" in d["name"] for d in beach_items)

    # Filter by maximum budget in INR
    resp_cost = client.get("/api/destinations/india?max_budget_inr=15000")
    assert resp_cost.status_code == 200
    cost_items = resp_cost.json()["destinations"]
    assert all(d["estimated_cost_inr"] <= 15000 for d in cost_items)

    # Filter by region
    resp_south = client.get("/api/destinations/india?region=South")
    assert resp_south.status_code == 200
    south_items = resp_south.json()["destinations"]
    assert all(d["region"] == "South" for d in south_items)


def test_places_endpoint_offline_fallback(client):
    """GET /api/places/live/{destination_id} returns guaranteed offline fallback places."""
    resp = client.get("/api/places/live/manali_spiti_india?force_offline=true")
    assert resp.status_code == 200
    data = resp.json()

    assert data["destination_id"] == "manali_spiti_india"
    assert data["source"] == "offline-fallback"
    assert data["total_places"] >= 5
    assert "coordinates" in data
    assert 32.0 <= data["coordinates"]["lat"] <= 33.0

    # Validate categories breakdown
    by_cat = data["by_category"]
    assert "culture" in by_cat
    assert "adventure" in by_cat
    assert "food" in by_cat
    assert "nature" in by_cat

    for p in data["places"]:
        assert "place_id" in p
        assert "name" in p
        assert p["category"] in ("culture", "nature", "food", "adventure", "rest")
        assert 8.0 <= p["lat"] <= 37.0
        assert 68.0 <= p["lon"] <= 98.0
        assert "opening_hours" in p
        assert isinstance(p["typical_duration_hours"], (int, float))
        assert isinstance(p["rating"], (int, float))


def test_places_endpoint_category_filter(client):
    """Test filtering live places by specific category (e.g. food in Goa)."""
    resp = client.get("/api/places/live/south_goa_india?category=food&force_offline=true")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_places"] > 0
    assert all(p["category"] == "food" for p in data["places"])
    assert any("Martin" in p["name"] for p in data["places"])


def test_places_endpoint_live_osm_mock(client, monkeypatch):
    """Test live OpenStreetMap Overpass parsing when mock API succeeds."""
    mock_osm_nodes = [
        {
            "place_id": "osm_101",
            "name": "Live Amber Fort View",
            "category": "culture",
            "lat": 26.9855,
            "lon": 75.8513,
            "opening_hours": "09:00 - 18:00",
            "typical_duration_hours": 2.0,
            "rating": 4.5,
        },
        {
            "place_id": "osm_102",
            "name": "Live Pink City Heritage Diner",
            "category": "food",
            "lat": 26.9200,
            "lon": 75.7980,
            "opening_hours": "10:00 - 22:00",
            "typical_duration_hours": 1.5,
            "rating": 4.5,
        },
    ]

    monkeypatch.setattr(places_service, "fetch_osm_live_places", lambda lat, lon, **kw: mock_osm_nodes)

    resp = client.get("/api/places/live/jaipur_jodhpur_india")
    assert resp.status_code == 200
    data = resp.json()

    assert data["source"] == "openstreetmap-live"
    assert data["total_places"] == 2
    assert data["places"][0]["name"] == "Live Amber Fort View"
    assert data["places"][0]["category"] == "culture"


def test_places_endpoint_graceful_unknown_destination(client):
    """Unknown destination falls back safely without 500 error."""
    resp = client.get("/api/places/live/unknown_destination_xyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_places"] > 0
    assert data["source"] == "offline-fallback"
