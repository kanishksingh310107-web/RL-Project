"""Open-Meteo weather provider for forecast and historical climate data.

Features:
- Daily weather forecast (temp min/max, rain probability, sunrise/sunset, weather codes)
- Historical climate averages for objective month-by-month seasonality scoring
- 1-hour TTL cache for forecasts, 7-day TTL for historical climate
- CC BY 4.0 Attribution: 'Weather data by Open-Meteo.com'
- Graceful offline fallback with explicit Provenance metadata
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import requests

from app.core.assumptions import (
    PROVIDER_HTTP_TIMEOUT_SECONDS,
    SEASON_TEMP_COMFORT_MIN_C,
    SEASON_TEMP_COMFORT_MAX_C,
    SEASON_RAIN_HEAVY_MONTHLY_MM
)
from app.core.schemas import Provenance
from app.providers.cache import get_cached, set_cached, TTL_WEATHER_SECONDS, TTL_PLACES_SECONDS

# WMO Weather interpretation codes
WMO_DESCRIPTIONS: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_weather_forecast(lat: float, lon: float, days: int = 7) -> Dict[str, Any]:
    """Fetch multi-day weather forecast for coordinates from Open-Meteo."""
    cache_key = f"weather:forecast:{round(lat, 3)}:{round(lon, 3)}:{days}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": (
                "weathercode,temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,precipitation_probability_max,windspeed_10m_max,"
                "sunrise,sunset"
            ),
            "timezone": "Asia/Kolkata",
            "forecast_days": min(14, max(1, days))
        }
        resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
        if resp.ok:
            data = resp.json()
            daily = data.get("daily") or {}
            dates = daily.get("time") or []

            forecast_days: List[Dict[str, Any]] = []
            for i, date_str in enumerate(dates):
                w_code = daily.get("weathercode", [0])[i] if i < len(daily.get("weathercode", [])) else 0
                max_t = daily.get("temperature_2m_max", [28.0])[i] if i < len(daily.get("temperature_2m_max", [])) else 28.0
                min_t = daily.get("temperature_2m_min", [18.0])[i] if i < len(daily.get("temperature_2m_min", [])) else 18.0
                rain_mm = daily.get("precipitation_sum", [0.0])[i] if i < len(daily.get("precipitation_sum", [])) else 0.0
                rain_prob = daily.get("precipitation_probability_max", [0])[i] if i < len(daily.get("precipitation_probability_max", [])) else 0
                wind_kmh = daily.get("windspeed_10m_max", [10.0])[i] if i < len(daily.get("windspeed_10m_max", [])) else 10.0
                sunrise = daily.get("sunrise", ["06:00"])[i] if i < len(daily.get("sunrise", [])) else "06:00"
                sunset = daily.get("sunset", ["18:30"])[i] if i < len(daily.get("sunset", [])) else "18:30"

                forecast_days.append({
                    "date": date_str,
                    "condition": WMO_DESCRIPTIONS.get(w_code, "Fair weather"),
                    "weather_code": w_code,
                    "temp_max_c": max_t,
                    "temp_min_c": min_t,
                    "rain_sum_mm": rain_mm,
                    "rain_probability_pct": rain_prob,
                    "windspeed_kmh": wind_kmh,
                    "sunrise": sunrise,
                    "sunset": sunset,
                })

            result = {
                "latitude": lat,
                "longitude": lon,
                "daily_forecast": forecast_days,
                "provenance": {
                    "source": "open-meteo",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "is_live": True,
                    "is_estimate": False,
                    "notes": "Weather data by Open-Meteo.com (CC BY 4.0)"
                }
            }
            set_cached(cache_key, result, TTL_WEATHER_SECONDS)
            return result
    except Exception:
        pass

    # Offline Estimate Fallback
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fallback = {
        "latitude": lat,
        "longitude": lon,
        "daily_forecast": [
            {
                "date": today_str,
                "condition": "Pleasant seasonal conditions",
                "weather_code": 1,
                "temp_max_c": 28.0,
                "temp_min_c": 18.0,
                "rain_sum_mm": 0.0,
                "rain_probability_pct": 10,
                "windspeed_kmh": 12.0,
                "sunrise": "06:15",
                "sunset": "18:15",
            }
        ],
        "provenance": {
            "source": "assumed",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "is_live": False,
            "is_estimate": True,
            "notes": "offline estimate fallback"
        }
    }
    set_cached(cache_key, fallback, TTL_WEATHER_SECONDS)
    return fallback


def get_historical_climate(lat: float, lon: float, month: int) -> Dict[str, Any]:
    """Retrieve historical climatology (monthly mean temperature & rainfall) for seasonality ranking."""
    month_val = min(12, max(1, month))
    cache_key = f"weather:climate:{round(lat, 3)}:{round(lon, 3)}:m{month_val}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        # Reference year 2023 for monthly averages
        start_d = f"2023-{month_val:02d}-01"
        end_d = f"2023-{month_val:02d}-28"
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_d,
            "end_date": end_d,
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "Asia/Kolkata"
        }
        resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
        if resp.ok:
            data = resp.json()
            daily = data.get("daily") or {}
            temps = [t for t in (daily.get("temperature_2m_mean") or []) if t is not None]
            rains = [r for r in (daily.get("precipitation_sum") or []) if r is not None]

            mean_temp = round(sum(temps) / max(1, len(temps)), 1) if temps else 24.0
            total_rain = round(sum(rains), 1) if rains else 20.0

            # Compute objective season comfort score in [0.0, 1.0]
            # Penalty for excessive rain (monsoon)
            rain_factor = max(0.0, 1.0 - (total_rain / max(1.0, SEASON_RAIN_HEAVY_MONTHLY_MM * 1.5)))
            # Penalty for temperature discomfort
            if mean_temp < SEASON_TEMP_COMFORT_MIN_C:
                temp_factor = max(0.2, 1.0 - (SEASON_TEMP_COMFORT_MIN_C - mean_temp) * 0.08)
            elif mean_temp > SEASON_TEMP_COMFORT_MAX_C:
                temp_factor = max(0.2, 1.0 - (mean_temp - SEASON_TEMP_COMFORT_MAX_C) * 0.08)
            else:
                temp_factor = 1.0

            season_score = round(min(1.0, max(0.1, temp_factor * 0.6 + rain_factor * 0.4)), 2)

            result = {
                "month": month_val,
                "mean_temp_c": mean_temp,
                "total_rain_mm": total_rain,
                "season_score": season_score,
                "is_comfortable": (
                    SEASON_TEMP_COMFORT_MIN_C <= mean_temp <= SEASON_TEMP_COMFORT_MAX_C and
                    total_rain < SEASON_RAIN_HEAVY_MONTHLY_MM
                ),
                "provenance": {
                    "source": "open-meteo-archive",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "is_live": True,
                    "is_estimate": False,
                    "notes": "Weather data by Open-Meteo.com (CC BY 4.0)"
                }
            }
            set_cached(cache_key, result, TTL_PLACES_SECONDS)
            return result
    except Exception:
        pass

    # Offline estimate fallback
    fallback_score = 0.85 if month_val in (10, 11, 12, 1, 2, 3) else 0.55
    fallback = {
        "month": month_val,
        "mean_temp_c": 24.0,
        "total_rain_mm": 30.0,
        "season_score": fallback_score,
        "is_comfortable": True,
        "provenance": {
            "source": "assumed",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "is_live": False,
            "is_estimate": True,
            "notes": "offline estimate historical climate fallback"
        }
    }
    set_cached(cache_key, fallback, TTL_PLACES_SECONDS)
    return fallback


def get_seasonality_score(lat: float, lon: float, month: int) -> float:
    """Convenience helper returning the numeric season score in [0.0, 1.0] from historical climate."""
    climate = get_historical_climate(lat, lon, month)
    return float(climate.get("season_score", 0.5))
