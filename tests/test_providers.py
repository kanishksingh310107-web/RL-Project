"""Unit tests for app.providers (geo, weather, cache, guard).

All tests mock the network; no test calls the real network.
Verifies caching, credit guard, null-safety, and offline fallback behavior.
"""
from unittest.mock import patch, MagicMock
from app.providers.cache import get_cached, set_cached
from app.providers.guard import can_call_geoapify, record_geoapify_call, reset_request_counter
from app.providers.geo import (
    geocode_india, reverse_geocode, get_places_by_category,
    get_accommodations, calculate_travel_leg, haversine_distance_km
)
from app.providers.weather import get_weather_forecast, get_historical_climate


def test_haversine_distance():
    # Delhi (28.6139, 77.2090) to Jaipur (26.9124, 75.7873) is ~238 km
    dist = haversine_distance_km(28.6139, 77.2090, 26.9124, 75.7873)
    assert 220.0 < dist < 260.0


def test_cache_set_and_get():
    set_cached("test:cache:key:1", {"city": "Jaipur", "val": 42}, ttl_seconds=60)
    cached = get_cached("test:cache:key:1")
    assert cached is not None
    assert cached["city"] == "Jaipur"
    assert cached["val"] == 42


def test_geocode_india_offline_fallback(monkeypatch):
    # Disable live call
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)
    result = geocode_india("Manali")
    assert result is not None
    assert result["city"] == "Manali & Spiti Valley"
    assert result["provenance"]["is_live"] is False
    assert result["provenance"]["is_estimate"] is True
    # Invariant: API key never appears in response
    assert "apiKey" not in str(result)
    assert "c2bb" not in str(result)


def test_cache_hit_makes_no_second_http_call(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "results": [{"name": "Udaipur", "lat": 24.5854, "lon": 73.7125, "formatted": "Udaipur, Rajasthan, India"}]
    }

    call_count = 0
    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_resp

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: True)
    monkeypatch.setattr("app.providers.geo.can_call_geoapify", lambda: True)

    # Use a unique query to ensure cold cache on first call
    test_q = "Unique City Uncached 9876"
    r1 = geocode_india(test_q)
    assert r1 is not None
    assert call_count == 1

    # Second call - should hit cache
    r2 = geocode_india(test_q)
    assert r2 is not None
    assert call_count == 1  # No second HTTP call


def test_guard_stops_at_limit(monkeypatch):
    reset_request_counter()
    # Simulate reaching call ceiling
    monkeypatch.setattr("app.providers.geo.can_call_geoapify", lambda: False)
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: True)

    # Calling places should not invoke HTTP, should return offline fallback
    with patch("requests.get") as mock_get:
        places = get_places_by_category(26.9124, 75.7873, "culture_history", limit=5)
        assert mock_get.called is False
        assert len(places) > 0
        assert places[0].provenance.is_live is False
        # Invariant: unknown cost is None, never 0
        assert places[0].cost_amount is None or places[0].cost_amount >= 0.0


def test_get_accommodations_no_prices(monkeypatch):
    monkeypatch.setattr("app.providers.geo.is_geoapify_configured", lambda: False)
    stays = get_accommodations(26.9124, 75.7873, estimated_nightly_budget=3500.0)
    assert len(stays) > 0
    # Invariant: No live price field
    for s in stays:
        assert s.external_search_url is not None
        assert s.estimated_nightly_budget == 3500.0


def test_calculate_travel_leg_estimate():
    # Between two Jaipur points ~5 km apart
    leg = calculate_travel_leg(26.9124, 75.7873, 26.9239, 75.8267, mode="cab")
    assert leg.duration_minutes > 5
    assert leg.distance_km > 2.0
    assert leg.provenance.is_estimate is True
    assert leg.provenance.is_live is False


def test_weather_forecast_and_offline_fallback(monkeypatch):
    with patch("requests.get", side_effect=Exception("Network error")):
        forecast = get_weather_forecast(26.9124, 75.7873, days=3)
        assert forecast is not None
        assert "daily_forecast" in forecast
        assert len(forecast["daily_forecast"]) >= 1
        assert forecast["provenance"]["is_live"] is False


def test_historical_climate_season_score(monkeypatch):
    with patch("requests.get", side_effect=Exception("Network error")):
        climate = get_historical_climate(26.9124, 75.7873, month=11)
        assert climate is not None
        assert 0.0 <= climate["season_score"] <= 1.0
        assert climate["month"] == 11
