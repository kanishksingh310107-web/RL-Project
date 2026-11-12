"""Geoapify provider for geocoding, places, reverse geocoding, and routing.

Features:
- India-restricted geocoding (countrycode:in)
- Category-based circular radius place fetching
- Reverse geocoding for neighbourhood/suburb discovery
- Live routing behind an explicit OFF flag to conserve credits
- Full offline fallback to curated catalogue
- Daily credit guard (2,500/day limit, max 8 calls/request)
- 7-day TTL caching
- Strict null safety: unknown costs/ratings are None, never 0.
"""
import math
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import requests

from app.core.config import get_geoapify_key, is_geoapify_configured
from app.core.assumptions import (
    MODE_SPEEDS_KMH, CIRCUITY_FACTOR, TRANSIT_FIXED_OVERHEAD_MINUTES,
    PROVIDER_HTTP_TIMEOUT_SECONDS
)
from app.core.schemas import Place, Stay, TravelLeg, Provenance
from app.providers.cache import get_cached, set_cached, TTL_PLACES_SECONDS
from app.providers.guard import can_call_geoapify, record_geoapify_call

# Routing API flag: default False to conserve daily free-tier credits
ENABLE_LIVE_ROUTING: bool = False

# Mapping from our 7 canonical arms to Geoapify place categories
CANONICAL_TO_GEOAPIFY_CATEGORIES: Dict[str, str] = {
    "culture_history": "heritage,tourism.attraction,building.historic",
    "nature_outdoors": "natural,leisure.park",
    "food_dining": "catering.restaurant,catering.cafe",
    "adventure": "sport,leisure",
    "relaxation": "leisure.spa,leisure.beach",
    "shopping_local": "commercial.marketplace,commercial.gift_and_souvenir,commercial.shopping_mall",
    "scenic": "tourism.sights,tourism.attraction",
    "accommodation": "accommodation.hotel,accommodation.guest_house,accommodation.motel",
    "pharmacy": "healthcare.pharmacy",
    "hospital": "healthcare.hospital",
    "atm": "service.financial.atm",
}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometres."""
    r = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 3)



INDIA_LAT_MIN: float = 6.0
INDIA_LAT_MAX: float = 38.0
INDIA_LON_MIN: float = 68.0
INDIA_LON_MAX: float = 98.0

INDIAN_OFFLINE_HUBS: List[Dict[str, Any]] = [
    {"name": "Delhi", "city": "Delhi", "state": "Delhi", "lat": 28.6139, "lon": 77.2090, "formatted": "New Delhi, Delhi, India"},
    {"name": "Mumbai", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "lon": 72.8777, "formatted": "Mumbai, Maharashtra, India"},
    {"name": "Bengaluru", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lon": 77.5946, "formatted": "Bengaluru, Karnataka, India"},
    {"name": "Kolkata", "city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lon": 88.3639, "formatted": "Kolkata, West Bengal, India"},
    {"name": "Chennai", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707, "formatted": "Chennai, Tamil Nadu, India"},
    {"name": "Hyderabad", "city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "lon": 78.4867, "formatted": "Hyderabad, Telangana, India"},
    {"name": "Pune", "city": "Pune", "state": "Maharashtra", "lat": 18.5204, "lon": 73.8567, "formatted": "Pune, Maharashtra, India"},
    {"name": "Ahmedabad", "city": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "lon": 72.5714, "formatted": "Ahmedabad, Gujarat, India"},
    {"name": "Jaipur", "city": "Jaipur", "state": "Rajasthan", "lat": 26.9124, "lon": 75.7873, "formatted": "Jaipur, Rajasthan, India"},
    {"name": "Udaipur", "city": "Udaipur", "state": "Rajasthan", "lat": 24.5854, "lon": 73.7125, "formatted": "Udaipur, Rajasthan, India"},
    {"name": "Jodhpur", "city": "Jodhpur", "state": "Rajasthan", "lat": 26.2389, "lon": 73.0243, "formatted": "Jodhpur, Rajasthan, India"},
    {"name": "Varanasi", "city": "Varanasi", "state": "Uttar Pradesh", "lat": 25.3176, "lon": 82.9739, "formatted": "Varanasi, Uttar Pradesh, India"},
    {"name": "Agra", "city": "Agra", "state": "Uttar Pradesh", "lat": 27.1767, "lon": 78.0081, "formatted": "Agra, Uttar Pradesh, India"},
    {"name": "Lucknow", "city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "lon": 80.9462, "formatted": "Lucknow, Uttar Pradesh, India"},
    {"name": "Kochi", "city": "Kochi", "state": "Kerala", "lat": 9.9312, "lon": 76.2673, "formatted": "Kochi, Kerala, India"},
    {"name": "Thiruvananthapuram", "city": "Thiruvananthapuram", "state": "Kerala", "lat": 8.5241, "lon": 76.9366, "formatted": "Thiruvananthapuram, Kerala, India"},
    {"name": "Munnar", "city": "Munnar", "state": "Kerala", "lat": 10.0889, "lon": 77.0595, "formatted": "Munnar, Kerala, India"},
    {"name": "Goa", "city": "Panaji", "state": "Goa", "lat": 15.4909, "lon": 73.8278, "formatted": "Panaji, Goa, India"},
    {"name": "South Goa", "city": "Palolem", "state": "Goa", "lat": 15.0100, "lon": 74.0232, "formatted": "Palolem, South Goa, India"},
    {"name": "Manali", "city": "Manali", "state": "Himachal Pradesh", "lat": 32.2432, "lon": 77.1892, "formatted": "Manali, Himachal Pradesh, India"},
    {"name": "Shimla", "city": "Shimla", "state": "Himachal Pradesh", "lat": 31.1048, "lon": 77.1734, "formatted": "Shimla, Himachal Pradesh, India"},
    {"name": "Rishikesh", "city": "Rishikesh", "state": "Uttarakhand", "lat": 30.0869, "lon": 78.2676, "formatted": "Rishikesh, Uttarakhand, India"},
    {"name": "Dehradun", "city": "Dehradun", "state": "Uttarakhand", "lat": 30.3165, "lon": 78.0322, "formatted": "Dehradun, Uttarakhand, India"},
    {"name": "Leh", "city": "Leh", "state": "Ladakh", "lat": 34.1526, "lon": 77.5771, "formatted": "Leh, Ladakh, India"},
    {"name": "Srinagar", "city": "Srinagar", "state": "Jammu & Kashmir", "lat": 34.0837, "lon": 74.7973, "formatted": "Srinagar, Jammu & Kashmir, India"},
    {"name": "Amritsar", "city": "Amritsar", "state": "Punjab", "lat": 31.6340, "lon": 74.8723, "formatted": "Amritsar, Punjab, India"},
    {"name": "Chandigarh", "city": "Chandigarh", "state": "Chandigarh", "lat": 30.7333, "lon": 76.7794, "formatted": "Chandigarh, India"},
    {"name": "Hampi", "city": "Hampi", "state": "Karnataka", "lat": 15.3350, "lon": 76.4600, "formatted": "Hampi, Karnataka, India"},
    {"name": "Mysuru", "city": "Mysuru", "state": "Karnataka", "lat": 12.2958, "lon": 76.6394, "formatted": "Mysuru, Karnataka, India"},
    {"name": "Ooty", "city": "Ooty", "state": "Tamil Nadu", "lat": 11.4102, "lon": 76.6950, "formatted": "Ooty, Tamil Nadu, India"},
    {"name": "Madurai", "city": "Madurai", "state": "Tamil Nadu", "lat": 9.9252, "lon": 78.1198, "formatted": "Madurai, Tamil Nadu, India"},
    {"name": "Coimbatore", "city": "Coimbatore", "state": "Tamil Nadu", "lat": 11.0168, "lon": 76.9558, "formatted": "Coimbatore, Tamil Nadu, India"},
    {"name": "Shillong", "city": "Shillong", "state": "Meghalaya", "lat": 25.5788, "lon": 91.8933, "formatted": "Shillong, Meghalaya, India"},
    {"name": "Darjeeling", "city": "Darjeeling", "state": "West Bengal", "lat": 27.0410, "lon": 88.2663, "formatted": "Darjeeling, West Bengal, India"},
    {"name": "Gangtok", "city": "Gangtok", "state": "Sikkim", "lat": 27.3389, "lon": 88.6065, "formatted": "Gangtok, Sikkim, India"},
    {"name": "Bhubaneswar", "city": "Bhubaneswar", "state": "Odisha", "lat": 20.2961, "lon": 85.8245, "formatted": "Bhubaneswar, Odisha, India"},
    {"name": "Pondicherry", "city": "Puducherry", "state": "Puducherry", "lat": 11.9416, "lon": 79.8083, "formatted": "Puducherry, India"},
    {"name": "Guwahati", "city": "Guwahati", "state": "Assam", "lat": 26.1445, "lon": 91.7362, "formatted": "Guwahati, Assam, India"},
    {"name": "Indore", "city": "Indore", "state": "Madhya Pradesh", "lat": 22.7196, "lon": 75.8577, "formatted": "Indore, Madhya Pradesh, India"},
    {"name": "Bhopal", "city": "Bhopal", "state": "Madhya Pradesh", "lat": 23.2599, "lon": 77.4126, "formatted": "Bhopal, Madhya Pradesh, India"},
    {"name": "Patna", "city": "Patna", "state": "Bihar", "lat": 25.5941, "lon": 85.1376, "formatted": "Patna, Bihar, India"},
    {"name": "Surat", "city": "Surat", "state": "Gujarat", "lat": 21.1702, "lon": 72.8311, "formatted": "Surat, Gujarat, India"},
    {"name": "Visakhapatnam", "city": "Visakhapatnam", "state": "Andhra Pradesh", "lat": 17.6868, "lon": 83.2185, "formatted": "Visakhapatnam, Andhra Pradesh, India"},
]

def is_in_india(lat: float, lon: float) -> bool:
    """Validate that coordinates fall strictly within India's geographical boundaries."""
    try:
        return INDIA_LAT_MIN <= float(lat) <= INDIA_LAT_MAX and INDIA_LON_MIN <= float(lon) <= INDIA_LON_MAX
    except (TypeError, ValueError):
        return False

def map_geoapify_categories_to_arm(categories: List[str]) -> str:
    """Maps a list of Geoapify category strings to one of our 7 canonical LinUCB arms."""
    cats_str = " ".join(categories).lower()
    if any(k in cats_str for k in ["historic", "heritage", "museum", "culture", "religion", "castle", "monument", "temple", "fort"]):
        return "culture_history"
    if any(k in cats_str for k in ["park", "natural", "forest", "mountain", "lake", "waterfall", "wildlife", "garden"]):
        return "nature_outdoors"
    if any(k in cats_str for k in ["restaurant", "cafe", "food", "dining", "catering", "bakery", "bar"]):
        return "food_dining"
    if any(k in cats_str for k in ["sport", "climbing", "diving", "adventure", "hiking", "trek", "camp"]):
        return "adventure"
    if any(k in cats_str for k in ["spa", "beach", "resort", "wellness", "relaxation"]):
        return "relaxation"
    if any(k in cats_str for k in ["market", "shopping", "mall", "souvenir", "bazaar", "commercial"]):
        return "shopping_local"
    if any(k in cats_str for k in ["sights", "attraction", "viewpoint", "tourism"]):
        return "scenic"
    return "culture_history"

def search_locations_india(query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Search Indian locations (cities, towns, tourist destinations, neighbourhoods).
    
    Uses Geoapify autocomplete or geocoding with strict countrycode:in filter.
    Falls back gracefully to curated Indian catalogue when offline or key is missing.
    """
    clean_query = query.strip()
    if not clean_query or len(clean_query) < 2:
        return []

    cache_key = f"geo:search_loc:{clean_query.lower()}:{limit}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    results: List[Dict[str, Any]] = []
    seen: set = set()

    # 1. Live Geoapify Call
    api_key = get_geoapify_key()
    if is_geoapify_configured() and can_call_geoapify():
        try:
            url = "https://api.geoapify.com/v1/geocode/autocomplete"
            params = {
                "text": clean_query,
                "filter": "countrycode:in",
                "format": "json",
                "apiKey": api_key,
                "limit": limit,
            }
            resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            record_geoapify_call()

            if resp.ok:
                data = resp.json()
                for item in data.get("results") or []:
                    lat = float(item["lat"])
                    lon = float(item["lon"])
                    if not is_in_india(lat, lon):
                        continue
                    
                    city = item.get("city") or item.get("town") or item.get("village") or item.get("county") or clean_query
                    state = item.get("state") or "India"
                    formatted = item.get("formatted") or f"{city}, {state}, India"
                    name = item.get("name") or city

                    dedup_key = (round(lat, 3), round(lon, 3))
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    results.append({
                        "id": f"geo_{item.get('place_id', str(len(results)))}",
                        "name": name,
                        "formatted": formatted,
                        "city": city,
                        "state": state,
                        "country": "India",
                        "lat": lat,
                        "lon": lon,
                        "neighbourhood": item.get("suburb") or item.get("neighbourhood") or item.get("district"),
                        "provenance": {
                            "source": "geoapify",
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "is_live": True,
                            "is_estimate": False,
                            "notes": "Powered by Geoapify | © OpenStreetMap contributors"
                        }
                    })

                if results:
                    set_cached(cache_key, results, TTL_PLACES_SECONDS)
                    return results[:limit]
        except Exception:
            pass

    # 2. Offline Fallback from Curated Indian Catalogue
    q_lower = clean_query.lower()
    for hub in INDIAN_OFFLINE_HUBS:
        if q_lower in hub["name"].lower() or q_lower in hub["city"].lower() or q_lower in hub.get("state", "").lower():
            dedup_key = (round(hub["lat"], 3), round(hub["lon"], 3))
            if dedup_key not in seen:
                seen.add(dedup_key)
                results.append({
                    "id": f"offline_{hub['city'].lower().replace(' ', '_')}",
                    "name": hub["name"],
                    "formatted": hub.get("formatted", f"{hub['name']}, India"),
                    "city": hub["city"],
                    "state": hub.get("state", "India"),
                    "country": "India",
                    "lat": hub["lat"],
                    "lon": hub["lon"],
                    "neighbourhood": hub.get("neighbourhood"),
                    "provenance": {
                        "source": "curated_catalogue",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "is_live": False,
                        "is_estimate": True,
                        "notes": "offline estimate from curated Indian destinations"
                    }
                })

    from app.data.india_destinations import INDIAN_DESTINATIONS, get_indian_destination
    for d in INDIAN_DESTINATIONS:
        d_name = d.get("name", "")
        d_state = d.get("state", "India")
        if q_lower in d_name.lower() or q_lower in d_state.lower() or q_lower in d.get("id", "").lower():
            lat = float(d["lat"])
            lon = float(d["lon"])
            dedup_key = (round(lat, 3), round(lon, 3))
            if dedup_key not in seen:
                seen.add(dedup_key)
                results.append({
                    "id": d["id"],
                    "name": d_name,
                    "formatted": f"{d_name}, {d_state}, India",
                    "city": d_name.split("(")[0].split("&")[0].strip(),
                    "state": d_state,
                    "country": "India",
                    "lat": lat,
                    "lon": lon,
                    "provenance": {
                        "source": "curated_catalogue",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "is_live": False,
                        "is_estimate": True,
                        "notes": "offline estimate from curated Indian destinations"
                    }
                })

    from app.recommender import DESTINATIONS
    for d in DESTINATIONS:
        if d.get("country") == "India" or "india" in d.get("id", ""):
            d_name = d.get("name", "")
            if q_lower in d_name.lower():
                lat_raw = d.get("lat")
                lon_raw = d.get("lon")
                if lat_raw is None or lon_raw is None:
                    matched_ind = get_indian_destination(d["id"])
                    if matched_ind:
                        lat_raw = matched_ind.get("lat")
                        lon_raw = matched_ind.get("lon")
                if lat_raw is None or lon_raw is None:
                    continue
                lat = float(lat_raw)
                lon = float(lon_raw)
                dedup_key = (round(lat, 3), round(lon, 3))
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    results.append({
                        "id": d["id"],
                        "name": d_name,
                        "formatted": f"{d_name}, India",
                        "city": d_name.split("(")[0].split("&")[0].strip(),
                        "state": d.get("region", "India"),
                        "country": "India",
                        "lat": lat,
                        "lon": lon,
                        "provenance": {
                            "source": "curated_catalogue",
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "is_live": False,
                            "is_estimate": True,
                            "notes": "offline estimate from curated catalogue"
                        }
                    })

    set_cached(cache_key, results, TTL_PLACES_SECONDS)
    return results[:limit]

def reverse_geocode_india(lat: float, lon: float) -> Dict[str, Any]:
    """Reverse geocode GPS coordinates into a structured Indian location.
    
    Validates coordinates are inside India.
    Returns:
        Dict with 'name', 'formatted', 'city', 'state', 'neighbourhood', 'lat', 'lon', 'country', 'provenance'.
    Raises:
        ValueError if coordinates are outside India.
    """
    if not is_in_india(lat, lon):
        raise ValueError(f"Coordinates ({lat}, {lon}) are outside India. This travel guide exclusively supports Indian travel.")

    cache_key = f"geo:reverse_loc:{round(lat, 4)}:{round(lon, 4)}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    api_key = get_geoapify_key()
    if is_geoapify_configured() and can_call_geoapify():
        try:
            url = "https://api.geoapify.com/v1/geocode/reverse"
            params = {
                "lat": lat,
                "lon": lon,
                "format": "json",
                "apiKey": api_key,
            }
            resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            record_geoapify_call()

            if resp.ok:
                data = resp.json()
                results = data.get("results") or []
                if results:
                    top = results[0]
                    country_code = (top.get("country_code") or "").lower()
                    if country_code and country_code != "in":
                        raise ValueError(f"Detected location '{top.get('formatted')}' is outside India ({country_code.upper()}).")

                    city = top.get("city") or top.get("town") or top.get("village") or top.get("county") or "Local Area"
                    state = top.get("state") or "India"
                    neighbourhood = top.get("suburb") or top.get("neighbourhood") or top.get("district")
                    name = neighbourhood or city
                    formatted = top.get("formatted") or f"{name}, {city}, {state}, India"

                    loc = {
                        "name": name,
                        "formatted": formatted,
                        "city": city,
                        "state": state,
                        "neighbourhood": neighbourhood,
                        "lat": float(lat),
                        "lon": float(lon),
                        "country": "India",
                        "provenance": {
                            "source": "geoapify",
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "is_live": True,
                            "is_estimate": False,
                            "notes": "Powered by Geoapify | © OpenStreetMap contributors"
                        }
                    }
                    set_cached(cache_key, loc, TTL_PLACES_SECONDS)
                    return loc
        except ValueError:
            raise
        except Exception:
            pass

    # Offline Fallback: find nearest curated Indian hub
    nearest_hub = min(INDIAN_OFFLINE_HUBS, key=lambda h: haversine_distance_km(lat, lon, h["lat"], h["lon"]))
    dist_km = haversine_distance_km(lat, lon, nearest_hub["lat"], nearest_hub["lon"])
    
    area_name = f"Area near {nearest_hub['name']}" if dist_km > 3.0 else nearest_hub['name']
    loc_fallback = {
        "name": area_name,
        "formatted": f"{area_name}, {nearest_hub['state']}, India ({dist_km:.1f} km from center)",
        "city": nearest_hub["city"],
        "state": nearest_hub["state"],
        "neighbourhood": f"Zone near ({round(lat, 2)}, {round(lon, 2)})",
        "lat": float(lat),
        "lon": float(lon),
        "country": "India",
        "provenance": {
            "source": "curated_catalogue",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "is_live": False,
            "is_estimate": True,
            "notes": "offline estimate from nearest curated Indian destination"
        }
    }
    set_cached(cache_key, loc_fallback, TTL_PLACES_SECONDS)
    return loc_fallback

DISCOVERY_CATEGORIES: str = (
    "tourism.attraction,tourism.sights,heritage,building.historic,"
    "entertainment.museum,natural,leisure.park,sport,leisure,"
    "catering.restaurant,catering.cafe,commercial.marketplace,"
    "commercial.shopping_mall,commercial.gift_and_souvenir"
)

def discover_places_india(
    lat: float,
    lon: float,
    radius_meters: int = 15000,
    categories: Optional[str] = None,
    limit: int = 30
) -> List[Place]:
    """Discover real-time nearby places around (lat, lon) in India using Geoapify Places API.
    
    Category mapping maps Geoapify types to our 7 canonical arms.
    Deduplicates places, preserves metadata, and sets unknown costs/ratings to None (never 0).
    """
    if not is_in_india(lat, lon):
        raise ValueError(f"Coordinates ({lat}, {lon}) are outside India. Discovery is supported only within India.")

    cache_key = f"geo:v2:discover_places:{round(lat, 4)}:{round(lon, 4)}:{radius_meters}:{limit}:{categories or 'all'}"
    cached = get_cached(cache_key)
    if cached:
        return [Place.model_validate(p) for p in cached]

    places: List[Place] = []
    seen: set = set()

    api_key = get_geoapify_key()
    cats_to_fetch = categories or DISCOVERY_CATEGORIES

    if is_geoapify_configured() and can_call_geoapify():
        try:
            url = "https://api.geoapify.com/v2/places"
            params = {
                "categories": cats_to_fetch,
                "filter": f"circle:{lon},{lat},{radius_meters}",
                "bias": f"proximity:{lon},{lat}",
                "limit": min(limit, 50),
                "apiKey": api_key,
            }
            resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            record_geoapify_call()

            if resp.ok:
                data = resp.json()
                features = data.get("features") or []
                for f in features:
                    props = f.get("properties") or {}
                    p_name = props.get("name")
                    if not p_name:
                        continue

                    p_lat = float(props.get("lat", lat))
                    p_lon = float(props.get("lon", lon))
                    if not is_in_india(p_lat, p_lon) or haversine_distance_km(lat, lon, p_lat, p_lon) > radius_meters / 1000:
                        continue
                    dedup_key = (p_name.strip().lower(), round(p_lat, 4), round(p_lon, 4))
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    place_categories = props.get("categories") or []
                    arm = map_geoapify_categories_to_arm(place_categories)

                    contact = props.get("contact") or {}
                    phone = contact.get("phone")
                    website = props.get("website")
                    opening_hours = props.get("opening_hours")
                    address = props.get("formatted")
                    suburb = props.get("suburb") or props.get("district") or props.get("neighbourhood")

                    place = Place(
                        id=f"geo_{props.get('place_id', str(len(places) + 1))}",
                        name=p_name.strip(),
                        category=arm,
                        lat=p_lat,
                        lon=p_lon,
                        address=address,
                        neighbourhood=suburb,
                        opening_hours=opening_hours,
                        typical_duration_minutes=None,
                        rating=None,      # NEVER 0 for unknown
                        cost_amount=None, # NEVER 0 for unknown
                        phone=phone,
                        website=website,
                        provenance=Provenance(
                            source="geoapify",
                            is_live=True,
                            is_estimate=False,
                            notes="Powered by Geoapify | © OpenStreetMap contributors"
                        )
                    )
                    places.append(place)

                if places:
                    set_cached(cache_key, [p.model_dump() for p in places], TTL_PLACES_SECONDS)
                    return places
        except Exception:
            pass

    # Offline Fallback from Curated Activities & Nearby Centers
    from app.activity_data import CURATED_ACTIVITIES
    indian_curated = [
        a for a in CURATED_ACTIVITIES
        if (a.get("destination_id") or "").endswith("_india") or "india" in (a.get("destination_id") or "")
    ]
    if not indian_curated:
        indian_curated = CURATED_ACTIVITIES

    # Sort curated by distance to the queried coordinates
    def _act_dist(act_item):
        a_lat = float(act_item.get("lat") or act_item.get("latitude", lat))
        a_lon = float(act_item.get("lon") or act_item.get("longitude", lon))
        return haversine_distance_km(lat, lon, a_lat, a_lon)

    sorted_curated = sorted(indian_curated, key=_act_dist)

    for act in sorted_curated:
        act_lat = float(act.get("lat") or act.get("latitude", lat))
        act_lon = float(act.get("lon") or act.get("longitude", lon))
        dist = haversine_distance_km(lat, lon, act_lat, act_lon)
        
        # If activity is within reasonable vicinity (or first few if very distant)
        if dist <= radius_meters / 1000.0:
            dedup_key = (act["name"].strip().lower(), round(act_lat, 4), round(act_lon, 4))
            if dedup_key not in seen:
                seen.add(dedup_key)
                p = Place(
                    id=act["id"],
                    name=act["name"],
                    category=act.get("category", "culture_history"),
                    destination_id=act.get("destination_id"),
                    lat=act_lat,
                    lon=act_lon,
                    neighbourhood=act.get("neighborhood") or act.get("neighbourhood"),
                    typical_duration_minutes=act.get("duration_minutes") or 60,
                    cost_amount=act.get("cost_amount"),
                    provenance=Provenance(
                        source="curated_catalogue",
                        is_live=False,
                        is_estimate=True,
                        notes="offline estimate from curated Indian activities"
                    )
                )
                places.append(p)
                if len(places) >= limit:
                    break

    set_cached(cache_key, [p.model_dump() for p in places], TTL_PLACES_SECONDS)
    return places


def geocode_india(query: str) -> Optional[Dict[str, Any]]:
    """Geocode a place or city name, strictly filtered to India.
    
    Returns a dict with 'name', 'lat', 'lon', 'formatted', 'city', and 'provenance'.
    Falls back to the curated catalogue when offline or when keys are absent.
    """
    clean_query = query.strip()
    if not clean_query:
        return None

    cache_key = f"geo:geocode:{clean_query.lower()}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    # Live call check
    api_key = get_geoapify_key()
    if is_geoapify_configured() and can_call_geoapify():
        try:
            url = "https://api.geoapify.com/v1/geocode/search"
            params = {
                "text": clean_query,
                "filter": "countrycode:in",
                "format": "json",
                "apiKey": api_key,
            }
            resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            record_geoapify_call()

            if resp.ok:
                data = resp.json()
                results = data.get("results") or []
                if results:
                    best = results[0]
                    result_obj = {
                        "name": best.get("name") or clean_query,
                        "lat": float(best["lat"]),
                        "lon": float(best["lon"]),
                        "formatted": best.get("formatted", clean_query),
                        "city": best.get("city") or clean_query,
                        "provenance": {
                            "source": "geoapify",
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "is_live": True,
                            "is_estimate": False,
                            "notes": "Powered by Geoapify | © OpenStreetMap contributors"
                        }
                    }
                    set_cached(cache_key, result_obj, TTL_PLACES_SECONDS)
                    return result_obj
        except Exception:
            pass

    # Offline Fallback from Curated Destinations & Indian Hubs (with real coordinates)
    q_lower = clean_query.lower()

    from app.data.india_destinations import INDIAN_DESTINATIONS

    def _curated_dest_result(d: Dict[str, Any]) -> Dict[str, Any]:
        fallback = {
            "name": d["name"],
            "lat": float(d["lat"]),
            "lon": float(d["lon"]),
            "formatted": f"{d['name']}, {d.get('state', 'India')}, India",
            "city": d["name"],
            "state": d.get("state", "India"),
            "provenance": {
                "source": "curated_catalogue",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "is_live": False,
                "is_estimate": True,
                "notes": "offline estimate from curated Indian destinations",
            },
        }
        set_cached(cache_key, fallback, TTL_PLACES_SECONDS)
        return fallback

    def _hub_result(hub: Dict[str, Any]) -> Dict[str, Any]:
        fallback = {
            "name": hub["name"],
            "lat": float(hub["lat"]),
            "lon": float(hub["lon"]),
            "formatted": hub.get("formatted", f"{hub['name']}, India"),
            "city": hub["city"],
            "state": hub.get("state", "India"),
            "provenance": {
                "source": "curated_catalogue",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "is_live": False,
                "is_estimate": True,
                "notes": "offline estimate from curated Indian hubs",
            },
        }
        set_cached(cache_key, fallback, TTL_PLACES_SECONDS)
        return fallback

    # 1. Primary destination name match (e.g., "Manali" -> "Manali & Spiti Valley")
    for d in INDIAN_DESTINATIONS:
        d_name = d.get("name", "").lower()
        primary = d_name.split("(")[0].split("&")[0].strip()
        if q_lower == d_name or q_lower == primary or q_lower == d.get("id", "").lower():
            return _curated_dest_result(d)

    # 2. Specific Indian offline hub match (e.g., "Jodhpur", "Pune", "Srinagar")
    for hub in INDIAN_OFFLINE_HUBS:
        h_name = hub["name"].lower()
        h_city = hub["city"].lower()
        if q_lower == h_name or q_lower == h_city or h_name in q_lower or h_city in q_lower:
            return _hub_result(hub)

    # 3. Secondary substring match against curated Indian destinations & hubs
    for d in INDIAN_DESTINATIONS:
        d_name = d.get("name", "").lower()
        d_id = d.get("id", "").lower()
        if q_lower in d_name or q_lower in d_id or d_name in q_lower:
            return _curated_dest_result(d)

    for hub in INDIAN_OFFLINE_HUBS:
        if q_lower in hub["name"].lower() or q_lower in hub["city"].lower():
            return _hub_result(hub)

    return None


CURATED_DESTINATION_COORDS: Dict[str, Dict[str, Any]] = {
    "kyoto_japan": {"lat": 35.0116, "lon": 135.7681, "name": "Kyoto, Japan"},
    "santorini_greece": {"lat": 36.3932, "lon": 25.4615, "name": "Santorini, Greece"},
    "swiss_alps": {"lat": 46.5590, "lon": 7.9854, "name": "Swiss Alps, Switzerland"},
    "rome_florence_italy": {"lat": 41.9028, "lon": 12.4964, "name": "Rome & Florence, Italy"},
    "banff_canada": {"lat": 51.1784, "lon": -115.5708, "name": "Banff, Canada"},
    "chiang_mai_thailand": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai, Thailand"},
    "reykjavik_iceland": {"lat": 64.1466, "lon": -21.9426, "name": "Reykjavik, Iceland"},
    "oaxaca_mexico": {"lat": 17.0732, "lon": -96.7266, "name": "Oaxaca, Mexico"},
    "queenstown_nz": {"lat": -45.0312, "lon": 168.6626, "name": "Queenstown, New Zealand"},
    "barcelona_spain": {"lat": 41.3879, "lon": 2.1699, "name": "Barcelona, Spain"},
    "tokyo_japan": {"lat": 35.6762, "lon": 139.6503, "name": "Tokyo, Japan"},
    "cape_town_south_africa": {"lat": -33.9249, "lon": 18.4241, "name": "Cape Town, South Africa"},
    "jaipur_rajasthan_india": {"lat": 26.9124, "lon": 75.7873, "name": "Jaipur, Rajasthan, India"},
    "varanasi_kashi_india": {"lat": 25.3176, "lon": 82.9739, "name": "Varanasi, Uttar Pradesh, India"},
    "ladakh_leh_india": {"lat": 34.1526, "lon": 77.5771, "name": "Leh Ladakh, India"},
    "udaipur_india": {"lat": 24.5854, "lon": 73.7125, "name": "Udaipur, Rajasthan, India"},
    "hampi_karnataka_india": {"lat": 15.3350, "lon": 76.4600, "name": "Hampi, Karnataka, India"},
    "andaman_havelock_india": {"lat": 11.9761, "lon": 92.9876, "name": "Havelock Island, Andaman, India"},
    "amritsar_punjab_india": {"lat": 31.6340, "lon": 74.8723, "name": "Amritsar, Punjab, India"},
    "rann_of_kutch_india": {"lat": 23.8344, "lon": 69.8396, "name": "Rann of Kutch, Gujarat, India"},
    "agra_braj_india": {"lat": 27.1767, "lon": 78.0081, "name": "Agra, Uttar Pradesh, India"},
    "darjeeling_sikkim_india": {"lat": 27.0410, "lon": 88.2663, "name": "Darjeeling & Sikkim, India"},
}


def resolve_trip_location(
    destination_id: Optional[str] = None,
    destination_name: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    resolved_location: Optional[str] = None,
    allow_live_geocode: bool = True,
) -> Dict[str, Any]:
    """Resolve exact coordinates and canonical location label for a trip.

    Never falls back to another destination (such as Manali or Delhi). Returns None
    coordinates if the location cannot be resolved.
    """
    label = resolved_location or destination_name or destination_id or ""

    # 1. Explicit valid coordinates stored on trip or passed by caller
    if lat is not None and lon is not None:
        try:
            f_lat = float(lat)
            f_lon = float(lon)
            if math.isfinite(f_lat) and math.isfinite(f_lon) and not (f_lat == 0.0 and f_lon == 0.0):
                return {"lat": f_lat, "lon": f_lon, "resolved_location": label}
        except (TypeError, ValueError):
            pass

    dest_id = (destination_id or "").strip()

    # 2. Exact match in curated Indian destinations
    if dest_id:
        from app.data.india_destinations import DESTINATIONS_BY_ID
        ind = DESTINATIONS_BY_ID.get(dest_id)
        if ind and ind.get("lat") is not None and ind.get("lon") is not None:
            ind_label = resolved_location or destination_name or f"{ind['name']}, {ind.get('state', 'India')}"
            return {"lat": float(ind["lat"]), "lon": float(ind["lon"]), "resolved_location": ind_label}

        # 3. Exact match in extended curated destination coordinates
        cur = CURATED_DESTINATION_COORDS.get(dest_id)
        if cur:
            return {
                "lat": float(cur["lat"]),
                "lon": float(cur["lon"]),
                "resolved_location": resolved_location or destination_name or cur["name"],
            }

        # 4. Cached dynamic destination coordinates
        cached_loc = get_cached(f"geo:dest:{dest_id}")
        if cached_loc and cached_loc.get("lat") is not None and cached_loc.get("lon") is not None:
            return {
                "lat": float(cached_loc["lat"]),
                "lon": float(cached_loc["lon"]),
                "resolved_location": resolved_location or cached_loc.get("name") or label,
            }

        # 5. Activity coordinates in destination_activities
        try:
            from app.database import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT AVG(latitude), AVG(longitude)
                    FROM destination_activities
                    WHERE destination_id = ?
                      AND latitude IS NOT NULL AND longitude IS NOT NULL
                      AND NOT (latitude = 0.0 AND longitude = 0.0)
                    """,
                    (dest_id,),
                ).fetchone()
                if row and row[0] is not None and row[1] is not None:
                    return {
                        "lat": float(row[0]),
                        "lon": float(row[1]),
                        "resolved_location": label,
                    }
        except Exception:
            pass

    # 6. Geocode destination_name (or city derived from destination_id)
    query_name = (destination_name or "").strip()
    if not query_name and dest_id:
        query_name = dest_id.replace("geo_", "").replace("_india", "").replace("_", " ").strip()

    if query_name:
        q_low = query_name.lower()
        for hub in INDIAN_OFFLINE_HUBS:
            h_name = hub["name"].lower()
            h_city = hub["city"].lower()
            if q_low == h_name or q_low == h_city or h_name in q_low or h_city in q_low:
                return {
                    "lat": float(hub["lat"]),
                    "lon": float(hub["lon"]),
                    "resolved_location": resolved_location or hub.get("formatted") or f"{hub['name']}, {hub.get('state', 'India')}",
                }

        if allow_live_geocode:
            geo = geocode_india(query_name)
            if geo and geo.get("lat") is not None and geo.get("lon") is not None:
                return {
                    "lat": float(geo["lat"]),
                    "lon": float(geo["lon"]),
                    "resolved_location": resolved_location or geo.get("formatted") or query_name,
                }

    return {"lat": None, "lon": None, "resolved_location": label}


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Resolve coordinates to a neighbourhood or suburb name."""
    cache_key = f"geo:reverse:{round(lat, 4)}:{round(lon, 4)}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    api_key = get_geoapify_key()
    if is_geoapify_configured() and can_call_geoapify():
        try:
            url = "https://api.geoapify.com/v1/geocode/reverse"
            params = {
                "lat": lat,
                "lon": lon,
                "format": "json",
                "apiKey": api_key,
            }
            resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            record_geoapify_call()

            if resp.ok:
                data = resp.json()
                results = data.get("results") or []
                if results:
                    top = results[0]
                    area_name = (
                        top.get("neighbourhood") or
                        top.get("suburb") or
                        top.get("district") or
                        top.get("city") or
                        "Central Area"
                    )
                    set_cached(cache_key, area_name, TTL_PLACES_SECONDS)
                    return area_name
        except Exception:
            pass

    # Fallback
    area_fallback = f"Zone near ({round(lat, 2)}, {round(lon, 2)})"
    set_cached(cache_key, area_fallback, TTL_PLACES_SECONDS)
    return area_fallback


def get_places_by_category(
    lat: float,
    lon: float,
    category: str,
    radius_meters: int = 15000,
    limit: int = 20
) -> List[Place]:
    """Retrieve places matching a category near a point.
    
    Category may be one of the 7 canonical arms, or 'accommodation', 'pharmacy', 'hospital', 'atm'.
    Falls back to curated activities offline.
    """
    cache_key = f"geo:v2:places:{round(lat, 4)}:{round(lon, 4)}:{category}:{radius_meters}:{limit}"
    cached = get_cached(cache_key)
    if cached:
        return [Place.model_validate(p) for p in cached]

    api_key = get_geoapify_key()
    geo_cat = CANONICAL_TO_GEOAPIFY_CATEGORIES.get(category, "tourism.attraction")

    if is_geoapify_configured() and can_call_geoapify():
        try:
            url = "https://api.geoapify.com/v2/places"
            params = {
                "categories": geo_cat,
                "filter": f"circle:{lon},{lat},{radius_meters}",
                "limit": limit,
                "apiKey": api_key,
            }
            resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            record_geoapify_call()

            if resp.ok:
                data = resp.json()
                features = data.get("features") or []
                places: List[Place] = []
                for f in features:
                    props = f.get("properties") or {}
                    p_name = props.get("name")
                    if not p_name:
                        continue

                    # Safe parsing of contact/opening
                    contact = props.get("contact") or {}
                    phone = contact.get("phone")
                    website = props.get("website")

                    place = Place(
                        id=f"geo_{props.get('place_id', str(len(places)))}",
                        name=p_name,
                        category=category if category in CANONICAL_TO_GEOAPIFY_CATEGORIES else "culture_history",
                        lat=float(props.get("lat", lat)),
                        lon=float(props.get("lon", lon)),
                        address=props.get("formatted"),
                        neighbourhood=props.get("suburb") or props.get("district"),
                        opening_hours=props.get("opening_hours"),
                        typical_duration_minutes=None,  # will be assigned from assumptions
                        rating=None,  # unknown = None, NEVER 0
                        cost_amount=None,  # unknown = None, NEVER 0
                        phone=phone,
                        website=website,
                        provenance=Provenance(
                            source="geoapify",
                            is_live=True,
                            is_estimate=False,
                            notes="Powered by Geoapify | © OpenStreetMap contributors"
                        )
                    )
                    places.append(place)

                if places:
                    set_cached(cache_key, [p.model_dump() for p in places], TTL_PLACES_SECONDS)
                    return places
        except Exception:
            pass

    # Facilities must never fall back to attractions.
    if category not in CANONICAL_TO_GEOAPIFY_CATEGORIES or category in ('accommodation', 'pharmacy', 'hospital', 'atm'):
        return []
    # Offline Fallback from Curated Catalogue
    from app.activity_data import CURATED_ACTIVITIES
    curated_matches = [
        a for a in CURATED_ACTIVITIES
        if a.get("category") == category or category == "all"
    ]
    curated_matches = [a for a in curated_matches if haversine_distance_km(lat, lon,
        float(a.get('latitude', a.get('lat', 0))), float(a.get('longitude', a.get('lon', 0)))) <= radius_meters / 1000]

    places = []
    for a in curated_matches[:limit]:
        p = Place(
            id=a["id"],
            name=a["name"],
            category=a["category"],
            destination_id=a.get("destination_id"),
            lat=float(a.get("latitude", a.get("lat", lat))),
            lon=float(a.get("longitude", a.get("lon", lon))),
            neighbourhood=a.get("neighborhood"),
            typical_duration_minutes=a.get("duration_minutes"),
            cost_amount=a.get("cost_amount"),
            provenance=Provenance(
                source="curated_catalogue",
                is_live=False,
                is_estimate=True,
                notes="offline estimate from curated activities"
            )
        )
        places.append(p)

    set_cached(cache_key, [p.model_dump() for p in places], TTL_PLACES_SECONDS)
    return places


def get_accommodations(lat, lon, trip_id="default_trip", estimated_nightly_budget=None,
                       limit=15, radius_meters=12000, tier="mid_range", destination_id=None):
    """Validated live accommodations or explicitly labelled curated stay areas.

    Geoapify star classifications are used only when supplied. Unknown tiers are
    clearly labelled, never claimed to match the requested room price.
    """
    from app.core.cost_model import canonical_tier
    from app.core.assumptions import TIER_LABELS, STAY_RATES_INR
    from app.data.stay_areas import areas_for_destination
    tier = canonical_tier(tier)
    if not is_in_india(lat, lon):
        return []
    key = f"geo:stays:v3:{lat:.4f}:{lon:.4f}:{radius_meters}:{tier}:{estimated_nightly_budget}:{limit}"
    cached = get_cached(key)
    if cached is not None:
        return [Stay.model_validate(dict(row, trip_id=trip_id)) for row in cached]
    stays = []
    if is_geoapify_configured() and can_call_geoapify():
        try:
            record_geoapify_call()
            response = requests.get('https://api.geoapify.com/v2/places', params={
                'categories': 'accommodation', 'filter': f'circle:{lon},{lat},{radius_meters}',
                'bias': f'proximity:{lon},{lat}', 'limit': min(100, limit*3), 'apiKey': get_geoapify_key()},
                timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            if response.ok:
                for feature in response.json().get('features', []):
                    p = feature.get('properties') or {}
                    categories = p.get('categories') or []
                    if not any(c == 'accommodation' or c.startswith('accommodation.') for c in categories):
                        continue
                    if str(p.get('country_code', '')).lower() != 'in' or not p.get('name'):
                        continue
                    a,b = p.get('lat'),p.get('lon')
                    if a is None or b is None or not is_in_india(a,b):
                        continue
                    distance = haversine_distance_km(lat,lon,a,b)
                    if distance > radius_meters/1000:
                        continue
                    stars = (p.get('accommodation') or {}).get('stars') or p.get('stars')
                    stars = float(stars) if stars else None
                    known_tier = 'luxury' if stars and stars >= 5 else 'boutique' if stars and stars >= 4 else 'mid_range' if stars and stars >= 3 else None
                    if known_tier and known_tier != tier:
                        continue
                    if known_tier and estimated_nightly_budget is not None and STAY_RATES_INR[known_tier][0] > estimated_nightly_budget:
                        continue
                    stays.append(Stay(stay_id='stay_'+str(p.get('place_id',len(stays))), trip_id=trip_id,
                        name=p['name'], stay_type=known_tier or 'hotel', tier=known_tier,
                        tier_label=TIER_LABELS.get(known_tier, 'Tier unverified'), lat=a,lon=b,
                        distance_km=round(distance,2),address=p.get('formatted'),
                        neighbourhood=p.get('suburb') or p.get('district'), stars=stars,
                        estimated_nightly_budget=estimated_nightly_budget,
                        external_search_url='https://www.google.com/maps/search/?api=1&query='+urllib.parse.quote(p['name']+' '+str(a)+','+str(b)),
                        label='Live place listing; rates and tier require confirmation',
                        provenance=Provenance(source='geoapify',is_live=True,is_estimate=True,
                            notes='Listing only, not a live price. Filtered by known tier; unknown tiers retained for verification.')))
        except Exception:
            pass
    stays.sort(key=lambda s: (s.tier is None, s.distance_km))
    if not stays:
        for i, area in enumerate(areas_for_destination(destination_id,lat,lon)):
            distance = haversine_distance_km(lat,lon,area['lat'],area['lon'])
            if distance > radius_meters/1000:
                continue
            stays.append(Stay(stay_id=f'area_{destination_id or str(lat)}_{i}', trip_id=trip_id,
                name=area['area_name'],kind='area',stay_type=tier,tier=tier,tier_label=TIER_LABELS[tier],
                lat=area['lat'],lon=area['lon'],estimated_nightly_budget=estimated_nightly_budget,neighbourhood=area['area_name'],distance_km=round(distance,2),
                price_bands=area['price_bands'],label=area['label'],external_search_url=area['external_search_url'],
                provenance=Provenance(source='curated_catalogue',is_live=False,is_estimate=True,
                    notes='Offline estimate. Indicative - no live listings; neighbourhood, not a hotel.')))
    rows = [s.model_dump() for s in stays[:limit]]
    set_cached(key, rows, TTL_PLACES_SECONDS)
    return [Stay.model_validate(row) for row in rows]


def calculate_travel_leg(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    from_place_id: Optional[str] = None,
    to_place_id: Optional[str] = None,
    mode: str = "cab"
) -> TravelLeg:
    """Calculate travel time and distance between two stops.
    
    Uses road circuity model by default, or live Geoapify routing if flag is ON.
    """
    speed_kmh = MODE_SPEEDS_KMH.get(mode, 25.0)

    # 1. Check if live routing is enabled and permitted
    api_key = get_geoapify_key()
    if ENABLE_LIVE_ROUTING and is_geoapify_configured() and can_call_geoapify():
        try:
            cache_key = f"geo:route:{round(from_lat, 4)}:{round(from_lon, 4)}:{round(to_lat, 4)}:{round(to_lon, 4)}:{mode}"
            cached = get_cached(cache_key)
            if cached:
                return TravelLeg.model_validate(cached)

            url = "https://api.geoapify.com/v1/routing"
            waypoints = f"{from_lat},{from_lon}|{to_lat},{to_lon}"
            geo_mode = "drive" if mode in ("cab", "auto", "rental_car") else ("walk" if mode == "walk" else "bicycle")
            params = {
                "waypoints": waypoints,
                "mode": geo_mode,
                "apiKey": api_key,
            }
            resp = requests.get(url, params=params, timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            record_geoapify_call()

            if resp.ok:
                data = resp.json()
                features = data.get("features") or []
                if features:
                    props = features[0].get("properties") or {}
                    dist_km = round(props.get("distance", 0) / 1000.0, 2)
                    dur_mins = max(1, int(round(props.get("time", 0) / 60.0)))
                    leg = TravelLeg(
                        from_place_id=from_place_id,
                        to_place_id=to_place_id,
                        mode=mode,
                        duration_minutes=dur_mins,
                        distance_km=dist_km,
                        provenance=Provenance(
                            source="geoapify",
                            is_live=True,
                            is_estimate=False,
                            notes="Powered by Geoapify Routing API"
                        )
                    )
                    set_cached(cache_key, leg.model_dump(), TTL_PLACES_SECONDS)
                    return leg
        except Exception:
            pass

    # 2. Straight-line Euclidean distance * circuity factor model
    raw_dist_km = haversine_distance_km(from_lat, from_lon, to_lat, to_lon)
    road_dist_km = round(raw_dist_km * CIRCUITY_FACTOR, 2)
    travel_time_hours = road_dist_km / max(1.0, speed_kmh)
    duration_mins = max(2, int(round(travel_time_hours * 60.0 + TRANSIT_FIXED_OVERHEAD_MINUTES)))

    return TravelLeg(
        from_place_id=from_place_id,
        to_place_id=to_place_id,
        mode=mode,
        duration_minutes=duration_mins,
        distance_km=road_dist_km,
        provenance=Provenance(
            source="assumed",
            is_live=False,
            is_estimate=True,
            notes="straight-line haversine x circuity factor / speed + fixed overhead"
        )
    )
