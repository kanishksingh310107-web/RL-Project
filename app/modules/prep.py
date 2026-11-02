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


# ============================================================================
# D2: Rule-Based Dynamic Packing List
# ============================================================================

def build_packing_list(
    trip: Dict[str, Any],
    weather: Dict[str, Any],
    user_ctx: Dict[str, Any],
    itinerary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generates a transparent, rule-based packing list.
    Inputs:
    - Weather summary (temp_min_c, temp_max_c, wind_kmh, rain_expected)
    - Trip duration and destination
    - Itinerary activities (hiking, beach, culture/temples, dining, etc.)
    - User context (precision profile: cold/heat/wind tolerance, carry-on luggage, medication/allergies)
    """
    items: List[Dict[str, str]] = []
    days = int(trip.get("duration_days") or 4)

    summary = weather.get("summary", {})
    t_min = float(summary.get("temp_min_c", 15.0))
    t_max = float(summary.get("temp_max_c", 22.0))
    wind = float(summary.get("wind_kmh", 15.0))
    rain = bool(summary.get("rain_expected", False))

    # Read precision profile answers if available
    prec = user_ctx.get("precision") or {}
    answers = prec.get("answers_json") or {}

    q78 = answers.get("q78")  # cold tolerance (1-5)
    q79 = answers.get("q79")  # heat tolerance (1-5)
    q80 = answers.get("q80")  # wind tolerance (1-5)
    luggage = answers.get("q61")  # luggage capacity: carry_on / backpack / one_checked
    allergies = answers.get("q10") or []
    medication = answers.get("q11") or []
    food_allergens = answers.get("q95") or []
    med_reqs = answers.get("q103") or []

    # Climate classifications
    is_hot = (t_min >= 20.0 and t_max >= 25.0) and (q78 is None or q78 >= 3)
    is_cold = (t_min < 15.0) or (q78 is not None and q78 <= 2)
    is_windy = (wind >= 25.0) or (q80 is not None and q80 <= 2)
    is_carry_on = (luggage == "carry_on")

    # 1. CLOTHING (Weather and Sensitivity Rules)
    if is_cold and is_windy and not is_hot:
        items.append({
            "name": "Windproof & insulating layer (outer shell jacket)",
            "category": "Clothing",
            "reason": (
                f"Destination low of {t_min:.1f}°C combined with {wind:.1f} km/h wind "
                f"(or user sensitivity q78={q78}, q80={q80}) triggers windproof outer shell (Scotland coat rule)"
            ),
            "quantity": "1",
        })
        items.append({
            "name": "Thermal base layer & warm fleece sweater",
            "category": "Clothing",
            "reason": f"Low temperature forecast ({t_min:.1f}°C) requires warm insulating mid-layer",
            "quantity": "1-2",
        })
    elif is_cold and not is_hot:
        items.append({
            "name": "Thermal base layers / warm fleece sweater",
            "category": "Clothing",
            "reason": f"Expected lows ({t_min:.1f}°C) below 15°C or personal cold sensitivity (q78={q78})",
            "quantity": "1-2",
        })
    elif is_hot:
        items.append({
            "name": "Lightweight breathable shirts (linen / moisture-wicking)",
            "category": "Clothing",
            "reason": f"Warm weather forecast ({t_min:.1f}°C to {t_max:.1f}°C); heavy insulation omitted",
            "quantity": "3-4" if is_carry_on else f"{min(days, 6)}",
        })
        items.append({
            "name": "UV sun protection hat & polarized sunglasses",
            "category": "Clothing",
            "reason": f"Warm sunny weather forecast ({t_max:.1f}°C) and UV protection",
            "quantity": "1 each",
        })
    else:
        # Mild temperate weather
        items.append({
            "name": "Light layering cardigan or jacket",
            "category": "Clothing",
            "reason": f"Mild weather conditions ({t_min:.1f}°C - {t_max:.1f}°C)",
            "quantity": "1",
        })

    # Standard apparel scaling with luggage rule
    if is_carry_on:
        items.append({
            "name": "T-shirts / tops (quick-dry, sink-washable)",
            "category": "Clothing",
            "reason": "Compact count optimized for carry-on only luggage (q61=carry_on)",
            "quantity": "3-4",
        })
        items.append({
            "name": "Travel pants / versatile bottoms",
            "category": "Clothing",
            "reason": "Compact capsule wardrobe for carry-on luggage",
            "quantity": "2",
        })
        items.append({
            "name": "Undergarments & quick-dry socks",
            "category": "Clothing",
            "reason": "Compact set suitable for carry-on rotation",
            "quantity": "4 pairs",
        })
        # Mandatory Liquids Bag for Carry-On
        items.append({
            "name": "Liquids pouch (containers max 100ml in transparent 1L bag)",
            "category": "Toiletries/Health",
            "reason": "Mandatory airport security rule for carry-on cabin luggage (q61=carry_on)",
            "quantity": "1 clear pouch",
        })
    else:
        # Checked baggage: higher quantities plus non-carry-on allowances
        items.append({
            "name": "T-shirts / daytime tops",
            "category": "Clothing",
            "reason": f"Scaled for {days}-day trip with checked luggage capacity",
            "quantity": f"{min(days + 1, 7)}",
        })
        items.append({
            "name": "Comfortable pants / jeans / bottoms",
            "category": "Clothing",
            "reason": f"Standard rotation for {days}-day trip",
            "quantity": f"{min(max(2, days // 2), 4)}",
        })
        items.append({
            "name": "Undergarments & everyday socks",
            "category": "Clothing",
            "reason": f"Full trip supply for {days} days",
            "quantity": f"{min(days + 2, 8)} pairs",
        })
        # Standard luggage items avoided by carry-on users
        items.append({
            "name": "Spare casual walking shoes (alternate pair for rotation)",
            "category": "Footwear",
            "reason": "Checked baggage allows packing a backup pair for shoe rotation and wet days",
            "quantity": "1 pair",
        })
        items.append({
            "name": "Evening dining outfit",
            "category": "Clothing",
            "reason": "Checked luggage allows dedicated evening outfit",
            "quantity": "1 outfit",
        })
        items.append({
            "name": "Full-size toiletries & travel towel pack",
            "category": "Toiletries/Health",
            "reason": "Checked baggage accommodates standard toiletries without 100ml limit",
            "quantity": "1 kit",
        })

    # Rain protection
    if rain:
        items.append({
            "name": "Compact windproof travel umbrella & water-resistant rain jacket",
            "category": "Activity gear",
            "reason": "Precipitation forecast during trip dates",
            "quantity": "1",
        })

    # 2. ACTIVITY-BASED GEAR & FOOTWEAR
    has_itinerary = itinerary is not None and len(itinerary.get("activities", [])) > 0
    if not has_itinerary:
        items.append({
            "name": "Comfortable all-day walking sneakers",
            "category": "Footwear",
            "reason": "Default footwear recommendation (itinerary not generated yet)",
            "quantity": "1 pair",
        })
        items.append({
            "name": "Everyday city daypack (15-20L)",
            "category": "Activity gear",
            "reason": "Default daypack recommendation (itinerary not generated yet)",
            "quantity": "1",
        })
    else:
        acts = itinerary.get("activities", [])
        categories = {a.get("category", "") for a in acts}
        text_corpus = " ".join(
            (a.get("title") or "") + " " + (a.get("description") or "") for a in acts
        ).lower()

        # Hiking / Nature / Adventure
        if (
            "nature_outdoors" in categories
            or "adventure" in categories
            or "hike" in text_corpus
            or "trail" in text_corpus
            or "mountain" in text_corpus
        ):
            items.append({
                "name": "Sturdy hiking boots or trail walking shoes",
                "category": "Footwear",
                "reason": "Planned outdoor nature trails or hiking activities in your itinerary",
                "quantity": "1 pair",
            })
            items.append({
                "name": "Outdoor daypack (20-30L) & reusable water bottle",
                "category": "Activity gear",
                "reason": "Active nature and adventure activities scheduled in itinerary",
                "quantity": "1",
            })

        # Cultural / Religious / Shrines
        if (
            "culture_history" in categories
            or "temple" in text_corpus
            or "shrine" in text_corpus
            or "mosque" in text_corpus
            or "church" in text_corpus
        ):
            items.append({
                "name": "Modest clothing covering shoulders & knees",
                "category": "Clothing",
                "reason": "Visiting religious shrines and historical cultural monuments in itinerary",
                "quantity": "1-2 outfits",
            })
            items.append({
                "name": "Comfortable slip-on walking shoes",
                "category": "Footwear",
                "reason": "Frequent shoe removal required at sacred sites and traditional venues",
                "quantity": "1 pair",
            })
        else:
            items.append({
                "name": "Comfortable cushioned walking sneakers",
                "category": "Footwear",
                "reason": "Urban exploration and general sightseeing",
                "quantity": "1 pair",
            })

        # Water / Beach / Swimming
        if (
            "beach" in text_corpus
            or "swim" in text_corpus
            or "boat" in text_corpus
            or "snorkel" in text_corpus
        ):
            items.append({
                "name": "Swimwear & quick-dry microfiber towel",
                "category": "Activity gear",
                "reason": "Beach, boating, or water activities planned in itinerary",
                "quantity": "1-2 sets",
            })

        # Local markets & shopping
        if "shopping_local" in categories or "market" in text_corpus:
            items.append({
                "name": "Packable lightweight shopping tote",
                "category": "Activity gear",
                "reason": "Visiting local markets and shopping districts in itinerary",
                "quantity": "1",
            })

        # Dining & Food
        if "food_dining" in categories or "food" in text_corpus:
            items.append({
                "name": "Pocket hand sanitizer & refreshing wet wipes",
                "category": "Toiletries/Health",
                "reason": "Dining and street food exploration activities scheduled in itinerary",
                "quantity": "1 pack",
            })

    # 3. HEALTH, ALLERGIES & MEDICATION (Neutral, Non-Medical Information)
    medication_vals = [medication] if isinstance(medication, str) else (medication or [])
    allergies_vals = [allergies] if isinstance(allergies, str) else (allergies or [])

    has_med = (
        any(m in medication_vals for m in ["personal_medication", "medical_equipment", "emergency_supplies"])
        or (med_reqs and "none" not in med_reqs)
    )
    has_allergies = (
        any(a in allergies_vals for a in ["food_allergies", "medication_allergies", "pollen_environmental", "insect_stings"])
        or bool(food_allergens)
    )
    if has_med or has_allergies:
        items.append({
            "name": "Personal prescription medication in original packaging (cabin luggage)",
            "category": "Toiletries/Health",
            "reason": (
                "User indicated personal medication or allergies in profile. Bring in original labeled packaging "
                "in carry-on bag with doctor's prescription copy; check destination border import rules. "
                "(Neutral informational reminder, no medical advice provided)"
            ),
            "quantity": "Trip supply + 2-3 days backup",
        })

    # 4. ELECTRONICS & CORE DOCUMENTS
    items.append({
        "name": "Universal travel plug adapter & USB cables",
        "category": "Electronics",
        "reason": "Required for charging personal devices across international socket standards",
        "quantity": "1 adapter + cables",
    })
    items.append({
        "name": "Portable power bank (10,000mAh, carry-on compliant)",
        "category": "Electronics",
        "reason": "Maintaining phone battery for daylong mobile maps, tickets, and camera",
        "quantity": "1",
    })
    items.append({
        "name": "Printed travel documents in waterproof zip pouch",
        "category": "Documents-related",
        "reason": "Offline backup for boarding passes, insurance policy, and hotel confirmations",
        "quantity": "1 pouch",
    })

    return {
        "trip_id": trip["id"],
        "destination_name": trip["destination_name"],
        "trip_length_days": days,
        "weather_summary": summary,
        "weather_source": weather.get("source"),
        "weather_label": weather.get("label"),
        "itinerary_status": "generated" if has_itinerary else "not_generated",
        "user_luggage_tier": "carry_on" if is_carry_on else "standard",
        "total_items": len(items),
        "items": items,
    }


@router.get("/{trip_id}/packing")
def get_trip_packing_list(trip_id: str):
    """GET /api/prep/{trip_id}/packing
    Returns dynamic rule-based packing list driven by weather, itinerary, and user sensitivities.
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")

    weather = get_weather_for_trip(trip)
    user_ctx = get_user_context(trip["user_id"])
    itinerary = get_itinerary(trip["id"])

    return build_packing_list(trip, weather, user_ctx, itinerary)

