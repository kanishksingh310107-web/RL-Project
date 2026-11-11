"""Audit real Geoapify place response fields for 5 varied Indian cities.

Measures the exact percentage of places carrying:
- opening_hours
- cuisine
- diet_tags
- rating
- price or stars
- website
- phone

Saves results to docs/data_audit.csv and docs/data_audit.md.
"""
import sys
import csv
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.core.config import is_geoapify_configured
from app.providers.geo import geocode_india, get_places_by_category
from app.providers.guard import reset_request_counter

AUDIT_CITIES = [
    {"name": "Delhi", "type": "metro"},
    {"name": "Jaipur", "type": "tourist_town"},
    {"name": "Manali", "type": "hill_town"},
    {"name": "Hampi", "type": "small_town"},
    {"name": "South Goa", "type": "coastal"},
]

AUDIT_CATEGORIES = [
    "culture_history",
    "nature_outdoors",
    "food_dining",
    "adventure",
    "relaxation",
    "shopping_local",
    "scenic",
    "accommodation",
]


def run_data_audit() -> None:
    if not is_geoapify_configured():
        print("[ERROR] GEOAPIFY_API_KEY is not configured. Cannot perform data audit.")
        sys.exit(1)

    print("Running real Geoapify field coverage audit across 5 Indian cities...")
    docs_dir = root_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []

    total_places = 0
    total_has_hours = 0
    total_has_cuisine = 0
    total_has_diet = 0
    total_has_rating = 0
    total_has_price = 0
    total_has_website = 0
    total_has_phone = 0

    for city_info in AUDIT_CITIES:
        c_name = city_info["name"]
        c_type = city_info["type"]
        print(f"Auditing {c_name} ({c_type})...")
        reset_request_counter()
        geo = geocode_india(c_name)
        if not geo:
            print(f"Failed to geocode {c_name}")
            continue

        lat, lon = geo["lat"], geo["lon"]
        for cat in AUDIT_CATEGORIES:
            reset_request_counter()
            places = get_places_by_category(lat, lon, cat, limit=10)
            p_count = len(places)
            if p_count == 0:
                continue

            has_hours = sum(1 for p in places if p.opening_hours)
            has_cuisine = sum(1 for p in places if p.cuisine)
            has_diet = sum(1 for p in places if p.diet_tags)
            has_rating = sum(1 for p in places if p.rating is not None)
            has_price = sum(1 for p in places if p.price_level is not None or p.cost_amount is not None)
            has_website = sum(1 for p in places if p.website)
            has_phone = sum(1 for p in places if p.phone)

            total_places += p_count
            total_has_hours += has_hours
            total_has_cuisine += has_cuisine
            total_has_diet += has_diet
            total_has_rating += has_rating
            total_has_price += has_price
            total_has_website += has_website
            total_has_phone += has_phone

            rows.append({
                "city": c_name,
                "city_type": c_type,
                "category": cat,
                "places_sampled": p_count,
                "pct_opening_hours": round((has_hours / p_count) * 100, 1),
                "pct_cuisine": round((has_cuisine / p_count) * 100, 1),
                "pct_diet_tags": round((has_diet / p_count) * 100, 1),
                "pct_rating": round((has_rating / p_count) * 100, 1),
                "pct_price_or_cost": round((has_price / p_count) * 100, 1),
                "pct_website": round((has_website / p_count) * 100, 1),
                "pct_phone": round((has_phone / p_count) * 100, 1),
            })

    # Save CSV
    csv_path = docs_dir / "data_audit.csv"
    fieldnames = [
        "city", "city_type", "category", "places_sampled",
        "pct_opening_hours", "pct_cuisine", "pct_diet_tags",
        "pct_rating", "pct_price_or_cost", "pct_website", "pct_phone"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Save Markdown Summary
    md_path = docs_dir / "data_audit.md"
    overall_hours_pct = round((total_has_hours / max(1, total_places)) * 100, 1)
    overall_cuisine_pct = round((total_has_cuisine / max(1, total_places)) * 100, 1)
    overall_diet_pct = round((total_has_diet / max(1, total_places)) * 100, 1)
    overall_rating_pct = round((total_has_rating / max(1, total_places)) * 100, 1)
    overall_price_pct = round((total_has_price / max(1, total_places)) * 100, 1)
    overall_web_pct = round((total_has_website / max(1, total_places)) * 100, 1)
    overall_phone_pct = round((total_has_phone / max(1, total_places)) * 100, 1)

    md_content = f"""# Real Data Coverage Audit Report

Conducted on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
Cities sampled: Delhi (metro), Jaipur (tourist town), Manali (hill town), Hampi (small town), South Goa (coastal)
Total live places evaluated: {total_places}

## Aggregate Field Availability

| Field | Real Coverage (%) | Architecture Consequence |
|---|---|---|
| **Opening Hours** | {overall_hours_pct}% | When missing, planner must show warning 'check hours at venue' rather than hard filtering. |
| **Cuisine** | {overall_cuisine_pct}% | Partial coverage; fallback to general dining category when missing. |
| **Diet Tags** | {overall_diet_pct}% | Extremely sparse/absent; UI must display 'cannot verify dietary/allergens, check with venue'. |
| **Rating** | {overall_rating_pct}% | No live rating from OSM/Geoapify free tier; LinUCB features must treat missing rating as None/neutral. |
| **Price / Cost** | {overall_price_pct}% | Free APIs rarely provide reliable live ticket/meal prices; budget ledger must use category assumptions. |
| **Website** | {overall_web_pct}% | Available for major landmarks; external link shown when present. |
| **Phone** | {overall_phone_pct}% | Available for established businesses and hotels. |

## AI assistance and external libraries/APIs used
- External API: Geoapify Places API v2 and Geocoding API v1
- Generated by Person C under SHARED specifications
"""
    md_path.write_text(md_content, encoding="utf-8")
    print(f"\n[OK] Data audit complete. Saved {csv_path.name} and {md_path.name}")


if __name__ == "__main__":
    run_data_audit()
