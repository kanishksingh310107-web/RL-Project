"""Tests for Task 7: Trip-Specific Weather & Resolved Location Integrity.

Verifies:
1. search_geocoding never falls back silently to Manali when offline.
2. Trips and itineraries retain their own destination_lat, destination_lon,
   resolved_location, start_date, and end_date.
3. Switching between trips (e.g., Jodhpur vs Manali) queries weather with each
   trip's actual coordinates and dates, across /api/weather/live, /api/prep/{id}/weather,
   and /api/live/{id}/weather-alerts.
4. Weather cache is keyed by exact (lat, lon, start_date, end_date) so switching
   destinations or changing trip dates never serves stale cross-city/date data.
5. Current forecasts (<= 15 days) and historical climate estimates (> 15 days)
   are clearly distinguished.
6. Unavailable weather returns "Weather information unavailable" cleanly.
7. Frontend weather loader in static/app.js passes trip coordinates/dates, guards
   against trip-switch race conditions, and handles unavailable states.
"""
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from app.services import live_api_service


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def test_search_geocoding_no_silent_manali_fallback(monkeypatch):
    """Offline geocoding must resolve Jodhpur accurately and return [] for unknown cities (never Manali)."""
    monkeypatch.setattr(
        live_api_service,
        "_http_get_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    jodhpur = live_api_service.search_geocoding("Jodhpur")
    assert len(jodhpur["results"]) >= 1
    assert any("Jodhpur" in r["name"] for r in jodhpur["results"])
    assert abs(jodhpur["results"][0]["latitude"] - 26.2389) < 0.1

    unknown = live_api_service.search_geocoding("NonExistentAtlantisTown999")
    assert unknown["results"] == []


def test_trips_and_itineraries_retain_resolved_coordinates_on_switch(client, demo_user, monkeypatch):
    """Switching between Jodhpur and Manali trips preserves each trip's distinct coordinates and dates."""
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)

    # Trip 1: Jodhpur, Rajasthan
    r_jodhpur = client.post(
        "/api/places/plan-dynamic",
        json={
            "user_id": demo_user,
            "city": "Jodhpur",
            "state": "Rajasthan",
            "lat": 26.2389,
            "lon": 73.0243,
            "start_date": "2026-12-01",
            "end_date": "2026-12-03",
            "travellers_count": 2,
            "total_budget": 25000.0,
        },
    )
    assert r_jodhpur.status_code == 200, r_jodhpur.text
    jodhpur_trip_id = r_jodhpur.json()["trip_id"]

    # Trip 2: Manali, Himachal Pradesh
    r_manali = client.post(
        f"/api/trips/{demo_user}",
        json={
            "destination_id": "manali_spiti_india",
            "destination_name": "Manali & Spiti Valley (Himachal Pradesh)",
            "start_date": "2026-12-10",
            "end_date": "2026-12-13",
            "travellers_count": 2,
            "total_budget": 28000.0,
        },
    )
    assert r_manali.status_code == 200, r_manali.text
    manali_trip_id = r_manali.json()["id"]
    assert client.post(f"/api/itinerary/generate/{manali_trip_id}?user_id={demo_user}").status_code == 200

    # Verify trips list retains separate coordinates and dates
    trips_resp = client.get(f"/api/trips/{demo_user}")
    assert trips_resp.status_code == 200
    by_id = {t["id"]: t for t in trips_resp.json()}

    assert abs(by_id[jodhpur_trip_id]["destination_lat"] - 26.2389) < 0.01
    assert abs(by_id[jodhpur_trip_id]["destination_lon"] - 73.0243) < 0.01
    assert "Jodhpur" in by_id[jodhpur_trip_id]["resolved_location"]
    assert by_id[jodhpur_trip_id]["start_date"] == "2026-12-01"

    assert abs(by_id[manali_trip_id]["destination_lat"] - 32.2432) < 0.01
    assert abs(by_id[manali_trip_id]["destination_lon"] - 77.1892) < 0.01
    assert by_id[manali_trip_id]["start_date"] == "2026-12-10"

    # Verify itinerary endpoints also carry trip-specific coordinates & dates
    itin_j = client.get(f"/api/itinerary/{jodhpur_trip_id}?user_id={demo_user}").json()
    itin_m = client.get(f"/api/itinerary/{manali_trip_id}?user_id={demo_user}").json()
    assert abs(itin_j["destination_lat"] - 26.2389) < 0.01
    assert abs(itin_j["destination_lon"] - 73.0243) < 0.01
    assert itin_j["start_date"] == "2026-12-01"
    assert itin_j["end_date"] == "2026-12-03"

    assert abs(itin_m["destination_lat"] - 32.2432) < 0.01
    assert abs(itin_m["destination_lon"] - 77.1892) < 0.01
    assert itin_m["start_date"] == "2026-12-10"
    assert itin_m["end_date"] == "2026-12-13"


def test_weather_cache_keyed_by_location_and_dates_and_distinguishes_forecast_vs_climate(client, monkeypatch):
    """Weather cache must isolate different locations/dates and distinguish forecast vs historical climate."""
    calls = []

    def mock_http_get(url, timeout=3.5):
        calls.append(url)
        if "latitude=26.2389" in url:
            return {
                "daily": {
                    "weathercode": [0, 1, 0],
                    "temperature_2m_max": [29.0, 30.0, 28.5],
                    "temperature_2m_min": [14.0, 15.0, 13.5],
                    "precipitation_probability_max": [5, 0, 5],
                    "precipitation_sum": [0.0, 0.0, 0.0],
                    "wind_speed_10m_max": [11.0, 12.0, 10.0],
                }
            }
        if "latitude=32.2432" in url:
            return {
                "daily": {
                    "weathercode": [71, 73, 3],
                    "temperature_2m_max": [7.0, 6.0, 8.0],
                    "temperature_2m_min": [-3.0, -4.0, -2.0],
                    "precipitation_probability_max": [60, 70, 40],
                    "precipitation_sum": [5.0, 8.0, 2.0],
                    "wind_speed_10m_max": [22.0, 24.0, 19.0],
                }
            }
        raise RuntimeError("Unexpected coordinates")

    monkeypatch.setattr(live_api_service, "_http_get_json", mock_http_get)

    today = date.today()
    near_start = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    near_end = (today + timedelta(days=4)).strftime("%Y-%m-%d")
    alt_start = (today + timedelta(days=6)).strftime("%Y-%m-%d")
    alt_end = (today + timedelta(days=8)).strftime("%Y-%m-%d")
    far_start = (today + timedelta(days=45)).strftime("%Y-%m-%d")
    far_end = (today + timedelta(days=47)).strftime("%Y-%m-%d")

    # 1. Near-term Jodhpur forecast
    r_j = client.get(f"/api/weather/live?lat=26.2389&lon=73.0243&start_date={near_start}&end_date={near_end}")
    assert r_j.status_code == 200
    d_j = r_j.json()
    assert d_j["available"] is True
    assert d_j["weather_type"] == "forecast"
    assert d_j["weather_type_label"] == "Current Forecast"
    assert d_j["temp_max_c"] == 30.0
    assert d_j["source"] == "api"

    # 2. Switch to Manali for the same dates -> must NOT reuse Jodhpur cache
    r_m = client.get(f"/api/weather/live?lat=32.2432&lon=77.1892&start_date={near_start}&end_date={near_end}")
    assert r_m.status_code == 200
    d_m = r_m.json()
    assert d_m["available"] is True
    assert d_m["weather_type"] == "forecast"
    assert d_m["temp_min_c"] == -4.0
    assert d_m["source"] == "api"

    # 3. Same Jodhpur coordinates with different dates -> must NOT reuse previous dates' cache
    calls_before_alt = len(calls)
    r_j_alt = client.get(f"/api/weather/live?lat=26.2389&lon=73.0243&start_date={alt_start}&end_date={alt_end}")
    assert r_j_alt.status_code == 200
    assert len(calls) == calls_before_alt + 1
    assert f"start_date={alt_start}" in calls[-1]

    # 4. Repeating exact Jodhpur (lat, lon, near_start, near_end) -> hits cache
    calls_before_cache = len(calls)
    r_j_cached = client.get(f"/api/weather/live?lat=26.2389&lon=73.0243&start_date={near_start}&end_date={near_end}")
    assert r_j_cached.status_code == 200
    assert len(calls) == calls_before_cache
    assert r_j_cached.json()["source"] == "cache"
    assert r_j_cached.json()["weather_type"] == "forecast"

    # 5. Far-future Jodhpur (> 15 days) -> uses historical climate archive & labels clearly
    r_j_far = client.get(f"/api/weather/live?lat=26.2389&lon=73.0243&start_date={far_start}&end_date={far_end}")
    assert r_j_far.status_code == 200
    d_j_far = r_j_far.json()
    assert d_j_far["available"] is True
    assert d_j_far["weather_type"] == "historical_climate_estimate"
    assert d_j_far["weather_type_label"] == "Historical Climate Estimate"
    assert d_j_far["api_type"] == "open-meteo-historical-archive"


def test_weather_unavailable_never_returns_other_destination(client, monkeypatch):
    """When Open-Meteo fails, /api/weather/live must report Weather information unavailable."""
    monkeypatch.setattr(
        live_api_service,
        "_http_get_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Open-Meteo unreachable")),
    )

    r = client.get("/api/weather/live?lat=26.2389&lon=73.0243&start_date=2027-01-10&end_date=2027-01-12")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False
    assert data["weather_type"] == "unavailable"
    assert data["message"] == "Weather information unavailable"
    assert data["source"] == "unavailable"


def test_prep_and_live_weather_alerts_use_trip_specific_coordinates(client, demo_user, monkeypatch):
    """Both /api/prep/{trip_id}/weather and /api/live/{trip_id}/weather-alerts must use the trip's actual coords."""
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)

    r_jodhpur = client.post(
        "/api/places/plan-dynamic",
        json={
            "user_id": demo_user,
            "city": "Jodhpur",
            "state": "Rajasthan",
            "lat": 26.2389,
            "lon": 73.0243,
            "start_date": "2026-12-01",
            "end_date": "2026-12-03",
        },
    )
    assert r_jodhpur.status_code == 200
    trip_id = r_jodhpur.json()["trip_id"]

    seen_prep_coords = []
    from app.modules import prep
    monkeypatch.setattr(
        prep,
        "fetch_open_meteo",
        lambda lat, lon, s, e: (
            seen_prep_coords.append((lat, lon, s, e))
            or {"temp_min_c": 14.0, "temp_max_c": 29.0, "wind_kmh": 11.0, "rain_expected": False}
        ),
    )

    prep_w = client.get(f"/api/prep/{trip_id}/weather")
    assert prep_w.status_code == 200
    assert len(seen_prep_coords) == 1
    assert abs(seen_prep_coords[0][0] - 26.2389) < 0.01
    assert abs(seen_prep_coords[0][1] - 73.0243) < 0.01
    assert seen_prep_coords[0][2] == "2026-12-01"
    assert seen_prep_coords[0][3] == "2026-12-03"

    seen_live_coords = []
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"daily": {"time": ["2026-12-01"], "weathercode": [0]}}

    def mock_requests_get(url, params=None, timeout=5):
        if "open-meteo.com" in url and params:
            seen_live_coords.append((params.get("latitude"), params.get("longitude")))
        return mock_resp

    monkeypatch.setattr("requests.get", mock_requests_get)
    live_w = client.get(f"/api/live/{trip_id}/weather-alerts")
    assert live_w.status_code == 200
    live_data = live_w.json()
    assert abs(live_data["coordinates"]["lat"] - 26.2389) < 0.01
    assert abs(live_data["coordinates"]["lon"] - 73.0243) < 0.01
    assert len(seen_live_coords) == 1
    assert abs(seen_live_coords[0][0] - 26.2389) < 0.01
    assert abs(seen_live_coords[0][1] - 73.0243) < 0.01


def test_frontend_weather_loader_uses_trip_context_and_race_guard():
    """static/app.js must pass trip coords/dates, avoid /api/geo/search, and guard against stale switches."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/geo/search" not in js
    assert "resetItineraryWeatherBanner" in js
    assert "_weatherRequestSeq" in js
    assert "Weather information unavailable" in js
    assert "Current Forecast" in js
    assert "Historical Climate Estimate" in js
    assert 'params.set("start_date"' in js
    assert 'params.set("end_date"' in js
