"""Record real API responses from Geoapify and Open-Meteo into tests/fixtures/.

Requires GEOAPIFY_API_KEY to be set in .env or environment.
Records real responses for 5 varied Indian cities:
1. Delhi (metro)
2. Jaipur (tourist town)
3. Manali (hill town)
4. Hampi (small town)
5. South Goa (coastal)
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.core.config import is_geoapify_configured
from app.providers.geo import geocode_india, get_places_by_category, get_accommodations
from app.providers.weather import get_weather_forecast, get_historical_climate

TARGET_CITIES = [
    {"name": "Delhi", "type": "metro", "file_prefix": "delhi_metro"},
    {"name": "Jaipur", "type": "tourist_town", "file_prefix": "jaipur_tourist"},
    {"name": "Manali", "type": "hill_town", "file_prefix": "manali_hill"},
    {"name": "Hampi", "type": "small_town", "file_prefix": "hampi_smalltown"},
    {"name": "South Goa", "type": "coastal", "file_prefix": "goa_coastal"},
]


def record_all_fixtures() -> None:
    if not is_geoapify_configured():
        print("[ERROR] GEOAPIFY_API_KEY is not configured. Cannot record live fixtures.")
        sys.exit(1)

    fixtures_dir = root_dir / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    print(f"Recording live API fixtures for {len(TARGET_CITIES)} Indian cities...")

    for city_info in TARGET_CITIES:
        c_name = city_info["name"]
        print(f"\n--- Recording {c_name} ({city_info['type']}) ---")
        geo = geocode_india(c_name)
        if not geo:
            print(f"Warning: could not geocode {c_name}")
            continue

        lat, lon = geo["lat"], geo["lon"]
        places = get_places_by_category(lat, lon, "culture_history", limit=5)
        nature = get_places_by_category(lat, lon, "nature_outdoors", limit=5)
        food = get_places_by_category(lat, lon, "food_dining", limit=5)
        stays = get_accommodations(lat, lon, limit=5)
        weather = get_weather_forecast(lat, lon, days=3)
        climate = get_historical_climate(lat, lon, month=11)

        fixture_payload = {
            "city": c_name,
            "category_type": city_info["type"],
            "fixture_type": "recorded live fixture",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "geocoding": geo,
            "places": [p.model_dump() for p in (places + nature + food)],
            "accommodations": [s.model_dump() for s in stays],
            "weather_forecast": weather,
            "historical_climate": climate,
        }

        out_path = fixtures_dir / f"{city_info['file_prefix']}_live.json"
        out_path.write_text(json.dumps(fixture_payload, indent=2), encoding="utf-8")
        print(f"[OK] Saved {out_path.name} ({len(fixture_payload['places'])} places, {len(stays)} stays)")

    print("\nAll live fixtures recorded successfully.")


if __name__ == "__main__":
    record_all_fixtures()
