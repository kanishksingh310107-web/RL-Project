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

    # Offline Fallback from Curated Catalogue
    from app.recommender import DESTINATIONS
    for d in DESTINATIONS:
        d_name = d.get("name", "").lower()
        d_id = d.get("id", "").lower()
        q_lower = clean_query.lower()
        if q_lower in d_name or q_lower in d_id or d_name in q_lower:
            fallback = {
                "name": d["name"],
                "lat": float(d.get("lat", 20.5937)),
                "lon": float(d.get("lon", 78.9629)),
                "formatted": f"{d['name']}, India",
                "city": d["name"],
                "provenance": {
                    "source": "curated_catalogue",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "is_live": False,
                    "is_estimate": True,
                    "notes": "offline estimate from curated destinations"
                }
            }
            set_cached(cache_key, fallback, TTL_PLACES_SECONDS)
            return fallback

    return None


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
    cache_key = f"geo:places:{round(lat, 4)}:{round(lon, 4)}:{category}:{limit}"
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

    # Offline Fallback from Curated Catalogue
    from app.activity_data import CURATED_ACTIVITIES
    curated_matches = [
        a for a in CURATED_ACTIVITIES
        if a.get("category") == category or category == "all"
    ]
    if not curated_matches:
        curated_matches = CURATED_ACTIVITIES[:limit]

    places = []
    for a in curated_matches[:limit]:
        p = Place(
            id=a["id"],
            name=a["name"],
            category=a["category"],
            destination_id=a.get("destination_id"),
            lat=float(a.get("lat", lat)),
            lon=float(a.get("lon", lon)),
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


def get_accommodations(
    lat: float,
    lon: float,
    trip_id: str = "default_trip",
    estimated_nightly_budget: Optional[float] = None,
    limit: int = 15
) -> List[Stay]:
    """Retrieve candidate accommodations near a coordinate.
    
    NEVER returns a live price (none exists on free APIs).
    Carries an external search link and estimated budget band.
    """
    cache_key = f"geo:stays:{round(lat, 4)}:{round(lon, 4)}:{limit}"
    cached = get_cached(cache_key)
    if cached:
        return [Stay.model_validate(s) for s in cached]

    places = get_places_by_category(lat, lon, "accommodation", radius_meters=12000, limit=limit)
    stays: List[Stay] = []

    for p in places:
        encoded_q = urllib.parse.quote(f"{p.name} hotels")
        ext_url = f"https://www.google.com/travel/hotels?q={encoded_q}"
        stay = Stay(
            stay_id=f"stay_{p.id}",
            trip_id=trip_id,
            name=p.name,
            stay_type="mid_range",
            lat=p.lat,
            lon=p.lon,
            address=p.address,
            neighbourhood=p.neighbourhood,
            stars=None,  # unknown = None, NEVER 0
            estimated_nightly_budget=estimated_nightly_budget,  # budget band, not a price
            external_search_url=ext_url,
            phone=p.phone,
            website=p.website,
            provenance=Provenance(
                source=p.provenance.source,
                is_live=p.provenance.is_live,
                is_estimate=True,
                notes="hotel options without prices; search link opens external site"
            )
        )
        stays.append(stay)

    if not stays:
        # Generic offline types fallback
        generic_types = [
            ("Budget Guesthouse / Homestay", "budget_guesthouse"),
            ("Comfort Boutique Hotel", "boutique_hotel"),
            ("Heritage Resort & Spa", "resort"),
        ]
        for idx, (t_name, t_code) in enumerate(generic_types):
            stays.append(Stay(
                stay_id=f"stay_generic_{idx}",
                trip_id=trip_id,
                name=t_name,
                stay_type=t_code,
                lat=lat,
                lon=lon,
                estimated_nightly_budget=estimated_nightly_budget,
                external_search_url="https://www.google.com/travel/hotels",
                provenance=Provenance(
                    source="curated_catalogue",
                    is_live=False,
                    is_estimate=True,
                    notes="offline estimate generic stay type"
                )
            ))

    set_cached(cache_key, [s.model_dump() for s in stays], TTL_PLACES_SECONDS)
    return stays


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
