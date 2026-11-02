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
