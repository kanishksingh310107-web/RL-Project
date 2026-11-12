"""Pre-trip Preparation Module (Person A).
Handles weather forecasts (Open-Meteo with offline fallback), dynamic packing lists,
essential travel documents checklists, and personalized pre-trip reminders
powered by a Thompson Sampling contextual bandit.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import json
import random
import uuid
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

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
    "ladakh_leh_india": (34.1526, 77.5771),
    "leh_ladakh_india": (34.1526, 77.5771),
    "varanasi_kashi_india": (25.3176, 82.9739),
    "varanasi_india": (25.3176, 82.9739),
    "jaipur_rajasthan_india": (26.9124, 75.7873),
    "jaipur_jodhpur_india": (26.9124, 75.7873),
    "udaipur_mewar_india": (24.5854, 73.7125),
    "rishikesh_haridwar_india": (30.0869, 78.2676),
    "hampi_karnataka_india": (15.3350, 76.4600),
    "hampi_india": (15.3350, 76.4600),
    "meghalaya_shillong_india": (25.5788, 91.8933),
    "darjeeling_sikkim_india": (27.0410, 88.2663),
    "darjeeling_gangtok_india": (27.0410, 88.2663),
    "andaman_havelock_india": (11.9761, 92.9876),
    "amritsar_punjab_india": (31.6340, 74.8723),
    "ooty_coorg_india": (11.4102, 76.6950),
    "rann_of_kutch_india": (23.8344, 69.8396),
    "agra_braj_india": (27.1767, 78.0081),
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
    """Compatibility entry point; all normal calls use the shared service."""
    from app.services.trip_weather import weather_for_dates
    return weather_for_dates(lat,lon,start_date,end_date)


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
    from app.services.trip_weather import weather_for_trip, weather_for_dates
    from app.providers.geo import resolve_trip_location
    location = resolve_trip_location(destination_id=trip.get('destination_id'),destination_name=trip.get('destination_name'),
        lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
    if location.get('lat') is None:
        return weather_for_trip(trip)
    try:
        result = fetch_open_meteo(location['lat'],location['lon'],trip['start_date'],trip['end_date'])
    except Exception:
        result = None
    if result and 'summary' in result:
        return dict(result,resolved_location=location.get('resolved_location'))
    if result and 'temp_min_c' in result:
        # Backward-compatible aggregate adapter. No production provider supplies
        # this shape; retained for existing injected weather adapters.
        return {'source':'open-meteo','label':'Live forecast (Open-Meteo)',
            'fetched_at':datetime.now(timezone.utc).isoformat(),'weather_type':'forecast',
            'coordinates':(location['lat'],location['lon']),'summary':{key:result[key]
                for key in ('temp_min_c','temp_max_c','wind_kmh','rain_expected')}}
    return weather_for_trip(trip)


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

    # Read precision profile answers and derive rule insights (Task B7)
    prec = user_ctx.get("precision") or {}
    answers = prec.get("answers_json") or {}
    has_cold_insight = False
    try:
        from app.precision import derive_insights
        res_insights = derive_insights(answers)
        if isinstance(res_insights, list):
            has_cold_insight = any("Cold" in str(ins.get("text", "")) or "cold" in str(ins.get("text", "")) for ins in res_insights if isinstance(ins, dict))
        elif isinstance(res_insights, dict):
            has_cold_insight = bool(res_insights.get("cold_sensitive"))
    except Exception:
        has_cold_insight = False

    q78 = answers.get("q78")  # cold tolerance (1-5)
    q79 = answers.get("q79")  # heat tolerance (1-5)
    q80 = answers.get("q80")  # wind tolerance (1-5)
    luggage = answers.get("q61")  # luggage capacity: carry_on / backpack / one_checked
    allergies = answers.get("q10") or []
    medication = answers.get("q11") or []
    food_allergens = answers.get("q95") or []
    med_reqs = answers.get("q103") or []

    # Climate classifications with insights integration
    is_hot = (t_min >= 20.0 and t_max >= 25.0) and (q78 is None or q78 >= 3)
    is_cold = (t_min < 15.0) or (q78 is not None and q78 <= 2) or has_cold_insight
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

    from app.core.party import normalize_party
    party = normalize_party(trip)
    if party['children']:
        items.append({'name':'Child essentials: spare clothes, snacks and comfort item', 'category':'Family',
            'reason':f"For {party['children']} child traveller(s)", 'quantity':str(party['children'])})
    if party['seniors']:
        items.append({'name':'Accessibility aids and personal essentials', 'category':'Family',
            'reason':f"For {party['seniors']} senior traveller(s); confirm individual needs", 'quantity':str(party['seniors'])})
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
        "cost_estimate": __import__('app.core.cost_model', fromlist=['estimate_cost']).estimate_cost(trip),
        "party": trip.get('party'),
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


# ============================================================================
# D3: Documents and Entry Requirements Checklist
# ============================================================================

# Known electrical plug and voltage standards for the 16 destinations.
# All items require user verification on the official destination site.
DESTINATION_POWER_STANDARDS: Dict[str, Dict[str, str]] = {
    "kyoto_japan": {"plug_types": "Type A / B", "voltage": "100V, 50/60Hz", "country": "Japan"},
    "tokyo_japan": {"plug_types": "Type A / B", "voltage": "100V, 50/60Hz", "country": "Japan"},
    "manali_spiti_india": {"plug_types": "Type C / D / M", "voltage": "230V, 50Hz", "country": "India"},
    "south_goa_india": {"plug_types": "Type C / D / M", "voltage": "230V, 50Hz", "country": "India"},
    "udaipur_india": {"plug_types": "Type C / D / M", "voltage": "230V, 50Hz", "country": "India"},
    "kerala_alleppey_india": {"plug_types": "Type C / D / M", "voltage": "230V, 50Hz", "country": "India"},
    "santorini_greece": {"plug_types": "Type C / F", "voltage": "230V, 50Hz", "country": "Greece"},
    "rome_florence_italy": {"plug_types": "Type C / F / L", "voltage": "230V, 50Hz", "country": "Italy"},
    "barcelona_spain": {"plug_types": "Type C / F", "voltage": "230V, 50Hz", "country": "Spain"},
    "swiss_alps": {"plug_types": "Type J (accepts Europlug C)", "voltage": "230V, 50Hz", "country": "Switzerland"},
    "banff_canada": {"plug_types": "Type A / B", "voltage": "120V, 60Hz", "country": "Canada"},
    "chiang_mai_thailand": {"plug_types": "Type A / B / C", "voltage": "220V, 50Hz", "country": "Thailand"},
    "reykjavik_iceland": {"plug_types": "Type C / F", "voltage": "230V, 50Hz", "country": "Iceland"},
    "oaxaca_mexico": {"plug_types": "Type A / B", "voltage": "127V, 60Hz", "country": "Mexico"},
    "queenstown_nz": {"plug_types": "Type I", "voltage": "230V, 50Hz", "country": "New Zealand"},
    "cape_town_south_africa": {"plug_types": "Type M / C / N", "voltage": "230V, 50Hz", "country": "South Africa"},
}


def build_documents_checklist(trip: Dict[str, Any]) -> Dict[str, Any]:
    """Generates the mandatory pre-trip documents, entry requirements,
    and power adapter checklist. NEVER invents visa regulations.
    """
    dest_id = trip.get("destination_id", "")
    dest_name = trip.get("destination_name", "Destination")
    power_info = DESTINATION_POWER_STANDARDS.get(dest_id)

    if power_info:
        power_note = (
            f"{power_info['country']} uses {power_info['plug_types']} sockets at {power_info['voltage']}. "
            f"Verify your electronics support dual-voltage (100-240V) and verify on the official site."
        )
    else:
        power_note = f"Check electrical plug type and voltage standards for {dest_name} on the official site."

    checklist = [
        {
            "name": "Passport validity (6 months rule)",
            "category": "Identity & Entry",
            "note": (
                f"Most international destinations require at least 6 months validity from your arrival "
                f"or departure date, plus 2 blank pages. Verify requirements on the official government/embassy site."
            ),
            "official_check_required": True,
        },
        {
            "name": "Visa / Entry authorization & border forms",
            "category": "Identity & Entry",
            "note": (
                f"Check requirements on the official government/embassy site for your passport and {dest_name}. "
                f"Verify whether an e-Visa, Visa-on-Arrival, or advance electronic travel authorization is mandated."
            ),
            "official_check_required": True,
        },
        {
            "name": "Comprehensive travel insurance",
            "category": "Insurance & Health",
            "note": (
                "Ensure policy covers medical emergencies, trip disruption/cancellation, and adventurous activities. "
                "Keep emergency hotline number saved offline. Verify terms on the official insurer portal."
            ),
            "official_check_required": True,
        },
        {
            "name": "Transport tickets & lodging confirmations",
            "category": "Transit & Bookings",
            "note": (
                "Save offline digital copies (Apple/Google Wallet, PDFs) and 1 printed copy of flight tickets, "
                "train bookings, and hotel reservation vouchers."
            ),
            "official_check_required": False,
        },
        {
            "name": "Power adapter & voltage compatibility",
            "category": "Electronics & Power",
            "note": power_note,
            "official_check_required": True,
        },
        {
            "name": "International mobile SIM / eSIM",
            "category": "Finance & Connectivity",
            "note": (
                f"Confirm international roaming pass or pre-install a regional travel eSIM for {dest_name} "
                "to ensure immediate connectivity upon arrival."
            ),
            "official_check_required": False,
        },
        {
            "name": "Payment cards & modest emergency cash",
            "category": "Finance & Connectivity",
            "note": (
                "Notify your bank of international travel to prevent card freezes. Carry cards with zero foreign "
                "exchange fees plus a small amount of local currency for transit and markets."
            ),
            "official_check_required": False,
        },
        {
            "name": "Prescription medication in cabin bag",
            "category": "Insurance & Health",
            "note": (
                f"Keep all personal medications in original labeled containers inside your carry-on luggage with a "
                f"physician's prescription note. Verify customs import restrictions for {dest_name} on official government site."
            ),
            "official_check_required": True,
        },
    ]

    return {
        "trip_id": trip["id"],
        "destination_name": dest_name,
        "disclaimer": "Informational checklist only. Always verify entry, visa, and health requirements with official embassy resources.",
        "total_items": len(checklist),
        "items": checklist,
    }


@router.get("/{trip_id}/documents")
def get_trip_documents(trip_id: str):
    """GET /api/prep/{trip_id}/documents
    Returns verified documents checklist with official site verification notices.
    Never invents legal or visa requirements.
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    return build_documents_checklist(trip)


# ============================================================================
# D4 & D5: Reminders Schedule & Thompson Sampling Bandit
# ============================================================================

ALERT_BUDGET = 3  # Maximum number of active reminders displayed per day

REMINDER_TEMPLATES = [
    {
        "category": "documents",
        "days_before": 30,
        "text": "Verify passport validity (at least 6 months) and check official visa requirements.",
    },
    {
        "category": "insurance",
        "days_before": 14,
        "text": "Secure comprehensive travel medical and cancellation insurance.",
    },
    {
        "category": "packing",
        "days_before": 3,
        "text": "Review personalized packing list and prepare activity gear and footwear.",
    },
    {
        "category": "weather",
        "days_before": 2,
        "text": "Check updated destination forecast to make final clothing adjustments.",
    },
    {
        "category": "checkin",
        "days_before": 1,
        "text": "Complete airline / transit online check-in and save boarding passes offline.",
    },
    {
        "category": "logistics",
        "days_before": 1,
        "text": "Prepare cabin bag: verify 100ml liquid limits, pack prescription medications and adapters.",
    },
]

ALL_REMINDER_CATEGORIES = [
    "documents",
    "insurance",
    "packing",
    "weather",
    "checkin",
    "logistics",
]


class ReminderFeedbackRequest(BaseModel):
    feedback: str

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, v: str) -> str:
        allowed = {"useful", "not_useful", "done"}
        if v not in allowed:
            raise ValueError(f"Invalid feedback '{v}'. Must be one of: {', '.join(sorted(allowed))}")
        return v


def generate_reminders_for_trip(trip: Dict[str, Any]) -> int:
    """Creates reminders for a trip if not already created (idempotent).
    Returns count of newly created reminders.
    """
    trip_id = trip["id"]
    start_date_str = trip.get("start_date", "")

    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    except ValueError:
        start_dt = datetime.now(timezone.utc)

    created_count = 0
    with get_connection() as conn:
        for tpl in REMINDER_TEMPLATES:
            # Check if this exact reminder already exists for the trip
            existing = conn.execute(
                "SELECT 1 FROM prep_reminders WHERE trip_id = ? AND category = ? AND text = ?",
                (trip_id, tpl["category"], tpl["text"]),
            ).fetchone()

            if not existing:
                due_dt = start_dt - timedelta(days=tpl["days_before"])
                due_str = due_dt.strftime("%Y-%m-%d")
                rem_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO prep_reminders (id, trip_id, text, category, due_date, status, shown_count)
                    VALUES (?, ?, ?, ?, ?, 'pending', 0)
                    """,
                    (rem_id, trip_id, tpl["text"], tpl["category"], due_str),
                )
                created_count += 1
        conn.commit()

    return created_count


def get_user_bandit_priors(conn, user_id: str) -> Dict[str, Tuple[float, float]]:
    """Loads Beta(alpha, beta) priors per reminder category for a user.
    Unseen categories default to Beta(1.0, 1.0) uniform prior.
    """
    rows = conn.execute(
        "SELECT category, alpha, beta FROM prep_bandit WHERE user_id = ?",
        (user_id,),
    ).fetchall()

    priors: Dict[str, Tuple[float, float]] = {c: (1.0, 1.0) for c in ALL_REMINDER_CATEGORIES}
    for r in rows:
        priors[r["category"]] = (float(r["alpha"]), float(r["beta"]))
    return priors


def sample_bandit_preferences(
    priors: Dict[str, Tuple[float, float]], seed: Optional[int] = None
) -> Dict[str, float]:
    """Thompson Sampling: draws theta ~ Beta(alpha, beta) for each reminder category."""
    rng = random.Random(seed) if seed is not None else random.Random()
    sampled = {}
    for cat, (alpha, beta) in priors.items():
        # Ensure positive parameters for betavariate
        a = max(0.01, alpha)
        b = max(0.01, beta)
        sampled[cat] = rng.betavariate(a, b)
    return sampled


@router.post("/{trip_id}/reminders/generate")
def create_trip_reminders(trip_id: str):
    """POST /api/prep/{trip_id}/reminders/generate
    Idempotently creates scheduled reminders based on trip start date.
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")

    created = generate_reminders_for_trip(trip)
    return {
        "trip_id": trip_id,
        "created_count": created,
        "message": f"Successfully created {created} new reminder(s)." if created else "Reminders already exist (idempotent).",
    }


@router.get("/{trip_id}/reminders")
def list_trip_reminders(trip_id: str, seed: Optional[int] = Query(None)):
    """GET /api/prep/{trip_id}/reminders
    Returns reminders ranked by Thompson Sampling contextual bandit.
    Enforces alert budget (max N active reminders displayed).
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")

    user_id = trip["user_id"]

    with get_connection() as conn:
        # Check if reminders have been generated; if none exist, generate automatically
        count_existing = conn.execute(
            "SELECT COUNT(*) FROM prep_reminders WHERE trip_id = ?", (trip_id,)
        ).fetchone()[0]
        if count_existing == 0:
            generate_reminders_for_trip(trip)

        rows = conn.execute(
            "SELECT * FROM prep_reminders WHERE trip_id = ? ORDER BY due_date ASC",
            (trip_id,),
        ).fetchall()
        priors = get_user_bandit_priors(conn, user_id)

    shared_weather = get_weather_for_trip(trip)
    thetas = sample_bandit_preferences(priors, seed=seed)

    reminders = []
    for r in rows:
        d = dict(r)
        cat = d["category"]
        d["bandit_score"] = round(thetas.get(cat, 0.5), 4)
        if cat == 'weather':
            d['weather'] = shared_weather
            summary = shared_weather.get('summary',{})
            d['text'] = f"{shared_weather.get('label','Weather unavailable')}: {summary.get('temp_min_c','?')}–{summary.get('temp_max_c','?')}°C. {shared_weather.get('message','')}"
        reminders.append(d)

    # Sort logic:
    # 1. 'pending' items come first, ordered by highest sampled Thompson theta, then earlier due_date
    # 2. 'done' and 'dismissed' items follow
    def sort_key(rem):
        is_pending = 0 if rem["status"] == "pending" else 1
        return (is_pending, -rem["bandit_score"], rem["due_date"])

    reminders.sort(key=sort_key)

    # Apply alert budget (max ALERT_BUDGET active pending items)
    pending_shown = 0
    with get_connection() as conn:
        for rem in reminders:
            if rem["status"] == "pending" and pending_shown < ALERT_BUDGET:
                rem["is_active"] = True
                pending_shown += 1
                # Increment shown_count in persistent store
                conn.execute(
                    "UPDATE prep_reminders SET shown_count = shown_count + 1 WHERE id = ?",
                    (rem["id"],),
                )
            else:
                rem["is_active"] = False
        conn.commit()

    bandit_state = [
        {
            "category": cat,
            "alpha": round(priors[cat][0], 2),
            "beta": round(priors[cat][1], 2),
            "mean": round(priors[cat][0] / (priors[cat][0] + priors[cat][1]), 3),
        }
        for cat in ALL_REMINDER_CATEGORIES
    ]

    return {
        "trip_id": trip_id,
        "alert_budget": ALERT_BUDGET,
        "active_count": pending_shown,
        "waiting_count": max(0, sum(1 for r in reminders if r["status"] == "pending") - pending_shown),
        "total_count": len(reminders),
        "reminders": reminders,
        "bandit_state": bandit_state,
        "disclaimer": "learned from your feedback in this app; simulated/demo data, not a real user study",
    }


@router.post("/{trip_id}/reminders/{reminder_id}/feedback")
def submit_reminder_feedback(
    trip_id: str, reminder_id: str, payload: ReminderFeedbackRequest
):
    """POST /api/prep/{trip_id}/reminders/{reminder_id}/feedback
    Records explicit user feedback ('useful', 'not_useful', 'done')
    and updates Thompson Sampling Beta(alpha, beta) parameters.
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")

    user_id = trip["user_id"]
    feedback = payload.feedback

    with get_connection() as conn:
        rem_row = conn.execute(
            "SELECT * FROM prep_reminders WHERE id = ? AND trip_id = ?",
            (reminder_id, trip_id),
        ).fetchone()

        if not rem_row:
            raise HTTPException(status_code=404, detail="reminder not found")

        category = rem_row["category"]

        # 1. Update reminder status
        if feedback == "done":
            new_status = "done"
        elif feedback == "not_useful":
            new_status = "dismissed"
        else:  # 'useful'
            new_status = "done"

        conn.execute(
            "UPDATE prep_reminders SET status = ? WHERE id = ?",
            (new_status, reminder_id),
        )

        # 2. Update Thompson Sampling Beta posterior:
        # - useful / done -> reward = +1 (alpha += 1.0)
        # - not_useful -> reward = -1 (beta += 1.0)
        # - dismissed without feedback -> weak penalty (beta += 0.1)
        bandit_row = conn.execute(
            "SELECT alpha, beta FROM prep_bandit WHERE user_id = ? AND category = ?",
            (user_id, category),
        ).fetchone()

        if bandit_row:
            curr_alpha = float(bandit_row["alpha"])
            curr_beta = float(bandit_row["beta"])
        else:
            curr_alpha = 1.0
            curr_beta = 1.0

        if feedback in ("useful", "done"):
            new_alpha = curr_alpha + 1.0
            new_beta = curr_beta
        elif feedback == "not_useful":
            new_alpha = curr_alpha
            new_beta = curr_beta + 1.0
        else:
            new_alpha = curr_alpha
            new_beta = curr_beta + 0.1

        conn.execute(
            """
            INSERT INTO prep_bandit (user_id, category, alpha, beta, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, category) DO UPDATE SET
                alpha = excluded.alpha,
                beta = excluded.beta,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, category, new_alpha, new_beta),
        )
        conn.commit()

    return {
        "reminder_id": reminder_id,
        "trip_id": trip_id,
        "category": category,
        "feedback": feedback,
        "status": new_status,
        "new_alpha": round(new_alpha, 2),
        "new_beta": round(new_beta, 2),
    }






# ============================================================================
# D4: Safety Essentials (Task B8)
# ============================================================================

# Official verified national and tourist emergency numbers in India
STATIC_EMERGENCY_NUMBERS: List[Dict[str, Any]] = [
    {
        "service": "National Emergency Helpline (All-in-One)",
        "number": "112",
        "notes": "Pan-India single emergency response support system (Police, Fire, Medical)",
        "source": "Ministry of Home Affairs, Govt. of India",
        "as_of": "2026-11-01",
        "is_static": True,
    },
    {
        "service": "Police Control Room",
        "number": "100",
        "notes": "Direct city police dispatch",
        "source": "State Police Departments",
        "as_of": "2026-11-01",
        "is_static": True,
    },
    {
        "service": "Ambulance & Medical Emergency",
        "number": "102 / 108",
        "notes": "National rural & urban emergency medical ambulance service",
        "source": "Ministry of Health & Family Welfare",
        "as_of": "2026-11-01",
        "is_static": True,
    },
    {
        "service": "Tourist Infoline & Assistance",
        "number": "1363",
        "notes": "24/7 multi-lingual toll-free helpline (12 foreign & Indian languages)",
        "source": "Incredible India / Ministry of Tourism",
        "as_of": "2026-11-01",
        "is_static": True,
    },
    {
        "service": "Women Safety Helpline",
        "number": "1091",
        "notes": "24/7 emergency distress response for women travellers",
        "source": "National Commission for Women",
        "as_of": "2026-11-01",
        "is_static": True,
    },
]

# Verified required permits & ticketing guidelines for Indian travel
STATIC_PERMITS_TICKETS: List[Dict[str, Any]] = [
    {
        "requirement": "Inner Line Permit (ILP) & Protected Area Permit (PAP)",
        "applies_to": "Ladakh (Pangong, Nubra, Khardung La), Arunachal Pradesh, Sikkim, Andaman (Tribal)",
        "action": "Apply online at official state portal prior to travel (e.g., lahdclehpermit.in). Keep physical copies.",
        "source": "Ministry of Home Affairs / State Administration",
        "as_of": "2026-11-01",
        "is_static": True,
    },
    {
        "requirement": "ASI Protected Monuments Entry Tickets",
        "applies_to": "Taj Mahal, Red Fort, Qutub Minar, Hampi monuments, Ajanta & Ellora caves",
        "action": "Mandatory QR e-tickets; cash ticketing is discontinued at ASI gates. Book in advance at asi.nic.in.",
        "source": "Archaeological Survey of India (ASI)",
        "as_of": "2026-11-01",
        "is_static": True,
    },
    {
        "requirement": "Wildlife Safari & National Park Permits",
        "applies_to": "Ranthambore, Jim Corbett, Kaziranga, Bandhavgarh, Periyar",
        "action": "Requires advance quota booking via respective state forest department portals 30-90 days prior.",
        "source": "National Tiger Conservation Authority & State Forest Portals",
        "as_of": "2026-11-01",
        "is_static": True,
    },
]


@router.get("/{trip_id}/safety")
def get_trip_safety_essentials(trip_id: str):
    """GET /api/prep/{trip_id}/safety
    Returns safety essentials:
    - Nearest ATM, Pharmacy, and Hospital via provider places
    - Verified static emergency helpline numbers (source & as-of date)
    - Required permits and ticketing checklist (source & as-of date)
    """
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")

    dest_id = trip.get("destination_id", "delhi")
    dest_name = trip.get("destination_name") or dest_id.replace("_", " ").title()

    from app.recommender import DESTINATIONS
    dest_meta = next((d for d in DESTINATIONS if d.get("id") == dest_id), {})
    center_lat = dest_meta.get("lat", 28.6139)
    center_lon = dest_meta.get("lon", 77.2090)

    # Provider lookups for nearest ATM, pharmacy, hospital
    nearby_facilities: List[Dict[str, Any]] = []
    try:
        from app.providers.geo import get_places_by_category
        # 1. Hospital / Healthcare
        hosp_res = get_places_by_category(center_lat, center_lon, "healthcare.hospital", radius_meters=10000, limit=2)
        for f in hosp_res.get("features") or []:
            props = f.get("properties") or {}
            nearby_facilities.append({
                "type": "hospital",
                "name": props.get("name") or "Local District Hospital",
                "address": props.get("formatted"),
                "phone": props.get("contact", {}).get("phone") or "Call 102/108",
                "is_live": True,
            })

        # 2. Pharmacy
        pharm_res = get_places_by_category(center_lat, center_lon, "healthcare.pharmacy", radius_meters=8000, limit=2)
        for f in pharm_res.get("features") or []:
            props = f.get("properties") or {}
            nearby_facilities.append({
                "type": "pharmacy",
                "name": props.get("name") or "Apollo / MedPlus Chemist",
                "address": props.get("formatted"),
                "phone": props.get("contact", {}).get("phone"),
                "is_live": True,
            })

        # 3. ATM
        atm_res = get_places_by_category(center_lat, center_lon, "service.financial.atm", radius_meters=6000, limit=2)
        for f in atm_res.get("features") or []:
            props = f.get("properties") or {}
            nearby_facilities.append({
                "type": "atm",
                "name": props.get("name") or "SBI / HDFC Bank ATM",
                "address": props.get("formatted"),
                "phone": None,
                "is_live": True,
            })
    except Exception:
        pass

    if not nearby_facilities:
        # Transparent offline fallback
        nearby_facilities = [
            {
                "type": "hospital",
                "name": f"{dest_name} Civil Hospital & Trauma Centre",
                "address": f"Main Hospital Road, {dest_name}",
                "phone": "Dial 102 / 108",
                "is_live": False,
            },
            {
                "type": "pharmacy",
                "name": "24/7 City Emergency Chemist",
                "address": f"Near District Hospital, {dest_name}",
                "phone": "Check local listing",
                "is_live": False,
            },
            {
                "type": "atm",
                "name": "Nationalized Bank ATM (SBI / PNB)",
                "address": f"Market Square / Mall Road, {dest_name}",
                "phone": None,
                "is_live": False,
            },
        ]

    return {
        "trip_id": trip_id,
        "destination_name": dest_name,
        "nearby_facilities": nearby_facilities,
        "emergency_numbers": STATIC_EMERGENCY_NUMBERS,
        "permits_and_ticketing": STATIC_PERMITS_TICKETS,
    }
