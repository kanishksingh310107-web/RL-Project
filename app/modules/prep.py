"""Pre-trip Preparation Module (Person A).
Handles weather forecasts (Open-Meteo with offline fallback), dynamic packing lists,
essential travel documents checklists, and personalized pre-trip reminders
powered by a Thompson Sampling contextual bandit.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import json
import random
import uuid
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_connection
from app.modules.common import get_itinerary, get_trip, get_user_context

MODULE = {
    "id": "prep",
    "title": "Trip Prep",
    "icon": "fa-suitcase",
    "owner": "A",
}

router = APIRouter(prefix="/api/prep", tags=["prep"])


# ============================================================================
# Database Tables
# ============================================================================

def init_tables(conn):
    """Initializes SQLite tables owned exclusively by the prep module."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prep_reminders (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL,
            text TEXT NOT NULL,
            category TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            shown_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prep_bandit (
            user_id TEXT NOT NULL,
            category TEXT NOT NULL,
            alpha REAL NOT NULL DEFAULT 1.0,
            beta REAL NOT NULL DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, category)
        );
        """
    )


# ============================================================================
# D1: Destination Coordinates & Offline Climate Table
# ============================================================================

# Real approximate latitude and longitude coordinates for all 16 destinations.
# Note: These represent city/regional central coordinates for weather lookup.
DESTINATION_COORDS: Dict[str, Tuple[float, float]] = {
    "kyoto_japan": (35.0116, 135.7681),
    "manali_spiti_india": (32.2432, 77.1892),
    "santorini_greece": (36.3932, 25.4615),
    "swiss_alps": (46.5590, 7.9854),          # Interlaken / Jungfrau region
    "south_goa_india": (15.2736, 73.9580),
    "rome_florence_italy": (41.9028, 12.4964), # Rome central
    "banff_canada": (51.1784, -115.5708),
    "chiang_mai_thailand": (18.7883, 98.9853),
    "reykjavik_iceland": (64.1466, -21.9426),
    "oaxaca_mexico": (17.0732, -96.7266),
    "udaipur_india": (24.5854, 73.7125),
    "queenstown_nz": (-45.0312, 168.6626),
    "kerala_alleppey_india": (9.4981, 76.3388),
    "barcelona_spain": (41.3879, 2.1699),
    "tokyo_japan": (35.6762, 139.6503),
    "cape_town_south_africa": (-33.9249, 18.4241),
}

# Rough climatological estimate, hand-written, not measured data.
# Keyed by (destination_id, month_1_to_12) -> (temp_min_c, temp_max_c, wind_kmh, rain_expected)
CLIMATE_ESTIMATES: Dict[Tuple[str, int], Tuple[float, float, float, bool]] = {
    # Kyoto (cool winters, hot humid summers, autumn mild)
    **{("kyoto_japan", m): (1.0, 9.0, 12.0, False) for m in [1, 2, 12]},
    **{("kyoto_japan", m): (8.0, 19.0, 14.0, True) for m in [3, 4]},
    **{("kyoto_japan", m): (16.0, 27.0, 15.0, True) for m in [5, 6, 9]},
    **{("kyoto_japan", m): (24.0, 33.0, 13.0, True) for m in [7, 8]},
    **{("kyoto_japan", m): (10.0, 18.0, 12.0, False) for m in [10, 11]},

    # Manali / Spiti (Himalayan high altitude, cold winters, cool summers)
    **{("manali_spiti_india", m): (-6.0, 6.0, 18.0, True) for m in [1, 2, 12]},
    **{("manali_spiti_india", m): (3.0, 17.0, 15.0, True) for m in [3, 4, 10, 11]},
    **{("manali_spiti_india", m): (10.0, 25.0, 12.0, True) for m in [5, 6, 7, 8, 9]},

    # Santorini (Mediterranean, windy, mild winter, hot dry summer)
    **{("santorini_greece", m): (10.0, 15.0, 32.0, True) for m in [1, 2, 12]},
    **{("santorini_greece", m): (13.0, 21.0, 25.0, False) for m in [3, 4, 11]},
    **{("santorini_greece", m): (20.0, 29.0, 28.0, False) for m in [5, 6, 7, 8, 9, 10]},

    # Swiss Alps (Alpine cold, snowy winters, pleasant summers)
    **{("swiss_alps", m): (-7.0, 2.0, 20.0, True) for m in [1, 2, 12]},
    **{("swiss_alps", m): (1.0, 14.0, 16.0, True) for m in [3, 4, 10, 11]},
    **{("swiss_alps", m): (8.0, 22.0, 14.0, True) for m in [5, 6, 7, 8, 9]},

    # South Goa (Tropical coast, monsoon Jun-Sep, warm otherwise)
    **{("south_goa_india", m): (20.0, 32.0, 14.0, False) for m in [1, 2, 11, 12]},
    **{("south_goa_india", m): (24.0, 34.0, 16.0, False) for m in [3, 4, 5]},
    **{("south_goa_india", m): (23.0, 29.0, 25.0, True) for m in [6, 7, 8, 9, 10]},

    # Rome & Florence (Mediterranean, mild wet winters, hot dry summers)
    **{("rome_florence_italy", m): (4.0, 13.0, 15.0, True) for m in [1, 2, 12]},
    **{("rome_florence_italy", m): (9.0, 21.0, 14.0, True) for m in [3, 4, 10, 11]},
    **{("rome_florence_italy", m): (17.0, 31.0, 12.0, False) for m in [5, 6, 7, 8, 9]},

    # Banff (Canadian Rockies, freezing snowy winters, crisp summers)
    **{("banff_canada", m): (-15.0, -3.0, 16.0, True) for m in [1, 2, 11, 12]},
    **{("banff_canada", m): (-5.0, 10.0, 14.0, True) for m in [3, 4, 10]},
    **{("banff_canada", m): (5.0, 22.0, 12.0, True) for m in [5, 6, 7, 8, 9]},

    # Chiang Mai (Northern Thailand, dry cool winter, very hot spring, wet summer)
    **{("chiang_mai_thailand", m): (15.0, 30.0, 10.0, False) for m in [11, 12, 1, 2]},
    **{("chiang_mai_thailand", m): (22.0, 36.0, 11.0, False) for m in [3, 4]},
    **{("chiang_mai_thailand", m): (24.0, 32.0, 12.0, True) for m in [5, 6, 7, 8, 9, 10]},

    # Reykjavik (Subpolar oceanic, windy and cold all year, damp)
    **{("reykjavik_iceland", m): (-3.0, 3.0, 35.0, True) for m in [1, 2, 11, 12]},
    **{("reykjavik_iceland", m): (1.0, 8.0, 30.0, True) for m in [3, 4, 5, 9, 10]},
    **{("reykjavik_iceland", m): (7.0, 14.0, 24.0, True) for m in [6, 7, 8]},

    # Oaxaca (High valley Mexico, mild warm days, cool nights, rainy summer)
    **{("oaxaca_mexico", m): (9.0, 28.0, 12.0, False) for m in [11, 12, 1, 2, 3]},
    **{("oaxaca_mexico", m): (14.0, 31.0, 14.0, True) for m in [4, 5, 6, 7, 8, 9, 10]},

    # Udaipur (Rajasthan arid/semi-arid, pleasant winter, very hot summer, brief monsoon)
    **{("udaipur_india", m): (8.0, 26.0, 10.0, False) for m in [11, 12, 1, 2]},
    **{("udaipur_india", m): (22.0, 39.0, 14.0, False) for m in [3, 4, 5, 6]},
    **{("udaipur_india", m): (23.0, 31.0, 15.0, True) for m in [7, 8, 9, 10]},

    # Queenstown (Southern hemisphere, cold winter Jun-Aug, mild summer Dec-Feb)
    **{("queenstown_nz", m): (0.0, 9.0, 18.0, True) for m in [6, 7, 8]},
    **{("queenstown_nz", m): (5.0, 17.0, 20.0, True) for m in [4, 5, 9, 10]},
    **{("queenstown_nz", m): (9.0, 22.0, 18.0, True) for m in [11, 12, 1, 2, 3]},

    # Kerala / Alleppey (Tropical monsoon, warm & humid year-round)
    **{("kerala_alleppey_india", m): (23.0, 32.0, 12.0, False) for m in [12, 1, 2, 3]},
    **{("kerala_alleppey_india", m): (25.0, 33.0, 14.0, True) for m in [4, 5]},
    **{("kerala_alleppey_india", m): (23.0, 30.0, 18.0, True) for m in [6, 7, 8, 9, 10, 11]},

    # Barcelona (Mediterranean, mild winter, warm summer)
    **{("barcelona_spain", m): (7.0, 14.0, 18.0, False) for m in [12, 1, 2]},
    **{("barcelona_spain", m): (11.0, 20.0, 16.0, True) for m in [3, 4, 5, 10, 11]},
    **{("barcelona_spain", m): (20.0, 29.0, 14.0, False) for m in [6, 7, 8, 9]},

    # Tokyo (Moderate, cold winter, hot muggy summer, rainy typhoons in autumn)
    **{("tokyo_japan", m): (2.0, 11.0, 16.0, False) for m in [12, 1, 2]},
    **{("tokyo_japan", m): (9.0, 19.0, 18.0, True) for m in [3, 4, 11]},
    **{("tokyo_japan", m): (16.0, 26.0, 17.0, True) for m in [5, 6, 10]},
    **{("tokyo_japan", m): (23.0, 31.0, 18.0, True) for m in [7, 8, 9]},

    # Cape Town (Mediterranean southern hemisphere, windy, dry summer Dec-Mar, wet winter Jun-Aug)
    **{("cape_town_south_africa", m): (8.0, 18.0, 25.0, True) for m in [6, 7, 8]},
    **{("cape_town_south_africa", m): (12.0, 23.0, 28.0, False) for m in [4, 5, 9, 10]},
    **{("cape_town_south_africa", m): (16.0, 27.0, 32.0, False) for m in [11, 12, 1, 2, 3]},
}


def fetch_open_meteo(
    lat: float, lon: float, start_date: str, end_date: str
) -> Optional[Dict[str, Any]]:
    """Fetches real weather forecast from Open-Meteo.
    Returns None on any network error, timeout, non-200 code, or malformed data.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "wind_speed_10m_max",
            "precipitation_probability_max",
        ],
        "timezone": "auto",
        "start_date": start_date,
        "end_date": end_date,
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            daily = data.get("daily", {})
            t_min = daily.get("temperature_2m_min")
            t_max = daily.get("temperature_2m_max")
            winds = daily.get("wind_speed_10m_max")
            precip = daily.get("precipitation_probability_max")

            if not (t_min and t_max):
                return None

            return {
                "temp_min_c": float(min(t_min)),
                "temp_max_c": float(max(t_max)),
                "wind_kmh": float(max(winds)) if winds else 15.0,
                "rain_expected": bool(any((p or 0) >= 30 for p in (precip or []))),
                "daily_details": daily,
            }
    except Exception:
        # Fall back cleanly without crashing
        return None


def get_offline_weather(
    destination_id: str, start_date: str
) -> Dict[str, Any]:
    """Returns hand-written climatological estimate for destination and month."""
    try:
        month = int(start_date.split("-")[1])
    except (IndexError, ValueError):
        month = 6

    estimate = CLIMATE_ESTIMATES.get((destination_id, month))
    if estimate is None:
        # Generic reasonable fallback if not in table
        estimate = (15.0, 25.0, 15.0, False)

    return {
        "temp_min_c": estimate[0],
        "temp_max_c": estimate[1],
        "wind_kmh": estimate[2],
        "rain_expected": estimate[3],
        "daily_details": None,
    }


def get_weather_for_trip(trip: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieves live Open-Meteo forecast or falls back to hand-written estimate."""
    dest_id = trip.get("destination_id", "")
    coords = DESTINATION_COORDS.get(dest_id)
    start_date = trip.get("start_date", "")
    end_date = trip.get("end_date", "")

    live_data = None
    if coords and start_date and end_date:
        try:
            live_data = fetch_open_meteo(coords[0], coords[1], start_date, end_date)
        except Exception:
            live_data = None

    now_iso = datetime.now(timezone.utc).isoformat()

    if live_data:
        return {
            "source": "open-meteo",
            "fetched_at": now_iso,
            "label": "Live forecast (Open-Meteo)",
            "summary": {
                "temp_min_c": live_data["temp_min_c"],
                "temp_max_c": live_data["temp_max_c"],
                "wind_kmh": live_data["wind_kmh"],
                "rain_expected": live_data["rain_expected"],
            },
            "coordinates": coords,
            "destination_id": dest_id,
        }

    offline = get_offline_weather(dest_id, start_date)
    return {
        "source": "offline-estimate",
        "fetched_at": now_iso,
        "label": "Offline estimate – not a live forecast",
        "summary": {
            "temp_min_c": offline["temp_min_c"],
            "temp_max_c": offline["temp_max_c"],
            "wind_kmh": offline["wind_kmh"],
            "rain_expected": offline["rain_expected"],
        },
        "coordinates": coords,
        "destination_id": dest_id,
    }


@router.get("/{trip_id}/weather")
def get_trip_weather(trip_id: str):
    """GET /api/prep/{trip_id}/weather
    Returns forecast from Open-Meteo or climatological offline fallback.
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    return get_weather_for_trip(trip)
