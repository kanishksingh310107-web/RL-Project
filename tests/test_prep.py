"""Unit and integration tests for Pre-trip Preparation Module (Person A)."""

import pytest
from app.modules import prep


def test_weather_endpoint_404_on_unknown_trip(client):
    """Unknown trip ID must return 404."""
    resp = client.get("/api/prep/non_existent_trip_id_999/weather")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip not found"


def test_weather_offline_fallback(client, demo_trip, monkeypatch):
    """When network call raises or fails, endpoint falls back to offline estimate."""
    uid, trip_id = demo_trip

    def mock_fetch_raise(lat, lon, start, end):
        raise RuntimeError("Network disconnected")

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_fetch_raise)

    resp = client.get(f"/api/prep/{trip_id}/weather")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "offline-estimate"
    assert "not a live forecast" in data["label"]
    assert "fetched_at" in data
    assert "temp_min_c" in data["summary"]
    assert "temp_max_c" in data["summary"]
    assert "wind_kmh" in data["summary"]
    assert "rain_expected" in data["summary"]


def test_weather_live_open_meteo_mock(client, demo_trip, monkeypatch):
    """When Open-Meteo succeeds, source is open-meteo with proper values."""
    uid, trip_id = demo_trip

    def mock_fetch_success(lat, lon, start, end):
        return {
            "temp_min_c": 12.0,
            "temp_max_c": 21.0,
            "wind_kmh": 22.0,
            "rain_expected": True,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_fetch_success)

    resp = client.get(f"/api/prep/{trip_id}/weather")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "open-meteo"
    assert data["label"] == "Live forecast (Open-Meteo)"
    assert data["summary"]["temp_min_c"] == 12.0
    assert data["summary"]["temp_max_c"] == 21.0
    assert data["summary"]["wind_kmh"] == 22.0
    assert data["summary"]["rain_expected"] is True


def test_packing_endpoint_404_on_unknown_trip(client):
    """Unknown trip ID must return 404 for packing endpoint."""
    resp = client.get("/api/prep/non_existent_trip_id_888/packing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip not found"


def test_packing_cold_windy_vs_hot(client, demo_trip, monkeypatch):
    """Cold and windy trip includes windproof layer; hot trip does not."""
    uid, trip_id = demo_trip

    # Case A: Cold and windy weather mock
    def mock_weather_cold_windy(lat, lon, start, end):
        return {
            "temp_min_c": 5.0,
            "temp_max_c": 12.0,
            "wind_kmh": 34.0,  # strong wind
            "rain_expected": True,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather_cold_windy)
    resp_cold = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_cold.status_code == 200
    data_cold = resp_cold.json()

    cold_item_names = [item["name"] for item in data_cold["items"]]
    assert any("Windproof" in name for name in cold_item_names), "Cold+windy must have windproof layer"
    assert any("umbrella" in name.lower() or "rain" in name.lower() for name in cold_item_names)

    # Case B: Hot weather mock
    def mock_weather_hot(lat, lon, start, end):
        return {
            "temp_min_c": 24.0,
            "temp_max_c": 33.0,
            "wind_kmh": 10.0,
            "rain_expected": False,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather_hot)
    resp_hot = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_hot.status_code == 200
    data_hot = resp_hot.json()

    hot_item_names = [item["name"] for item in data_hot["items"]]
    assert not any("Windproof" in name for name in hot_item_names), "Hot trip must NOT have windproof outer shell"
    assert not any("Thermal base" in name for name in hot_item_names), "Hot trip must NOT have thermal base layers"
    assert any("breathable" in name.lower() for name in hot_item_names), "Hot trip must suggest breathable fabrics"


def test_packing_carry_on_shorter_list_and_liquids_reminder(client, demo_trip, monkeypatch):
    """User with carry_on gets a shorter list AND a liquids reminder item."""
    uid, trip_id = demo_trip

    def mock_weather(lat, lon, start, end):
        return {
            "temp_min_c": 16.0,
            "temp_max_c": 22.0,
            "wind_kmh": 12.0,
            "rain_expected": False,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather)

    # Standard packing (no carry-on specified)
    resp_std = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_std.status_code == 200
    data_std = resp_std.json()
    std_items = data_std["items"]
    assert not any("100ml" in i["name"] for i in std_items)

    # Update precision profile with carry_on
    p_resp = client.post(
        f"/api/profile/precision/{uid}",
        json={"answers": {"q61": "carry_on"}},
    )
    assert p_resp.status_code == 200

    resp_carry = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_carry.status_code == 200
    data_carry = resp_carry.json()
    carry_items = data_carry["items"]

    # Carry-on list must be strictly shorter than standard
    assert len(carry_items) < len(std_items), f"Expected carry_on ({len(carry_items)}) < standard ({len(std_items)})"

    # Carry-on must contain liquids reminder
    assert any("Liquids" in i["name"] and "100ml" in i["name"] for i in carry_items)


def test_packing_medication_and_allergy_profile(client, demo_trip, monkeypatch):
    """User with medication/allergy flagged gets neutral cabin bag reminder."""
    uid, trip_id = demo_trip

    def mock_weather(lat, lon, start, end):
        return {
            "temp_min_c": 16.0,
            "temp_max_c": 22.0,
            "wind_kmh": 12.0,
            "rain_expected": False,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather)

    p_resp = client.post(
        f"/api/profile/precision/{uid}",
        json={"answers": {"q11": "personal_medication", "q10": ["food_allergies"]}},
    )
    assert p_resp.status_code == 200

    resp = client.get(f"/api/prep/{trip_id}/packing")
    assert resp.status_code == 200
    items = resp.json()["items"]

    med_item = next((i for i in items if "medication" in i["name"].lower()), None)
    assert med_item is not None
    assert "cabin" in med_item["name"].lower() or "cabin" in med_item["reason"].lower()
    assert "no medical advice" in med_item["reason"].lower()


def test_packing_without_itinerary_and_without_precision_profile(client, demo_user, monkeypatch):
    """Packing endpoint gracefully handles a new trip before itinerary generation."""
    # Create trip without generating itinerary
    t_resp = client.post(
        f"/api/trips/{demo_user}",
        json={
            "destination_id": "reykjavik_iceland",
            "destination_name": "Reykjavik",
            "start_date": "2026-12-01",
            "end_date": "2026-12-05",
            "travellers_count": 1,
            "total_budget": 800,
        },
    )
    assert t_resp.status_code == 200
    trip_id = t_resp.json()["id"]

    resp = client.get(f"/api/prep/{trip_id}/packing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["itinerary_status"] == "not_generated"
    assert len(data["items"]) > 0
    assert any("sneakers" in i["name"].lower() or "shoes" in i["name"].lower() for i in data["items"])

