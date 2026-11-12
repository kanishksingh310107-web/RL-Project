# Real-Time Places & Dynamic India Location Discovery API

**Owner:** Person C (Integrator)  
**Router Prefix:** `/api/places`  
**Test Suites:** 
- `tests/test_places_api.py` (6 unit tests, 100% passing)
- `tests/test_places_dynamic.py` (14 unit tests, 100% passing)

---

## 1. Executive Summary

The **Dynamic India-Wide Location & Real-Time Places Recommendation Engine** transforms the application from a 16-destination fixed-catalogue into a genuinely dynamic, country-wide travel intelligence system covering **all 28 states and 8 union territories of India**.

Travellers can discover destinations in two primary modes:
1. **MODE A (Search Any Location in India):** Instant autocomplete across cities, towns, heritage hubs, hill stations, and neighbourhoods with coordinates resolution and radius selection.
2. **MODE B (Detect My Current Location):** One-click GPS location detection via HTML5 Geolocation API, reverse geocoding within Indian geographic bounds, and nearby attraction discovery.

Discovered attractions, viewpoints, dining options, and shopping bazaars are dynamically ranked using the **24-dimensional Contextual LinUCB bandit policy**, ensuring personal profiles and constraints (avoidances, accessibility, pace) dictate recommendations.

---

## 2. Architecture & Data Flow

```
   ┌─────────────────────────────────────────────────────────┐
   │             Traveller Frontend (static/app.js)          │
   ├────────────────────────────┬────────────────────────────┤
   │   MODE A: Search India     │   MODE B: Use Current GPS  │
   │  (/search-locations)       │    (/reverse-geocode)      │
   └─────────────┬──────────────┴──────────────┬─────────────┘
                 │                             │
                 ▼                             ▼
   ┌─────────────────────────────────────────────────────────┐
   │             Backend Geo Provider (geo.py)               │
   │  - Strict India Bounding Box: 6.0°N–38.0°N, 68.0°E–98.0°E│
   │  - Geoapify Places v2 with countrycode:in filter        │
   │  - Null-Safety: Unknown prices/ratings remain None      │
   │  - Curated Indian Hubs Fallback (43+ cities)            │
   └─────────────────────────────┬───────────────────────────┘
                                 │
                                 ▼
   ┌─────────────────────────────────────────────────────────┐
   │          Category Mapping to 7 Canonical Arms           │
   │  - tourism.sights / heritage     ──► culture_history    │
   │  - catering.restaurant           ──► food_dining        │
   │  - commercial.shopping / bazaar  ──► shopping_local     │
   │  - natural / forest / mountain   ──► nature_outdoors    │
   │  - sport / climbing / trekking   ──► adventure          │
   │  - leisure.spa / wellness        ──► relaxation         │
   │  - tourism.attraction / viewpoint──► scenic             │
   └─────────────────────────────┬───────────────────────────┘
                                 │
                                 ▼
   ┌─────────────────────────────────────────────────────────┐
   │      Personalized Ranking Engine (personalization.py)    │
   │  - 24-dim LinUCB Context Vector extraction              │
   │  - Exploitation reward + Exploration UCB bonus          │
   │  - Proximity distance bonus (≤3km: +0.15, ≤8km: +0.08)  │
   │  - Hard Constraint Filtering (crowds, walking, stairs)  │
   └─────────────────────────────┬───────────────────────────┘
                                 │
                                 ▼
   ┌─────────────────────────────────────────────────────────┐
   │        Dynamic Itinerary Generation (plan-dynamic)      │
   │  - Seeds discovered places into SQLite                  │
   │  - Caches destination center coords (core_place_cache)  │
   │  - Never falls back silently to Delhi                   │
   │  - Outputs Timed Day-by-Day Schedule with transit & rest│
   └─────────────────────────────────────────────────────────┘
```

---

## 3. Endpoints

| Method | Endpoint | Query / Body | Description |
|---|---|---|---|
| `GET` | `/api/places/search-locations` | `?q={city}&limit=6` | Real-time Indian location autocomplete via Geoapify / curated hubs fallback. |
| `GET` | `/api/places/reverse-geocode` | `?lat={lat}&lon={lon}` | GPS reverse geocoding to structured Indian city/state. Rejects non-Indian coordinates (HTTP 400). |
| `GET` | `/api/places/discover` | `?lat={lat}&lon={lon}&radius_meters={r}&user_id={uid}` | Discovers live places within radius (5–50 km) and personalizes using LinUCB bandit policy. |
| `POST` | `/api/places/plan-dynamic` | `PlanDynamicTripRequest` JSON | Takes any Indian location, seeds places into `destination_activities`, and generates a full LinUCB itinerary. |
| `GET` | `/api/places/popular` | — | Returns popular Indian travel hubs with tags and coordinates. |

### Sample Plan Dynamic Trip Request
```json
POST /api/places/plan-dynamic
{
  "user_id": "usr_demo",
  "city": "Pune",
  "state": "Maharashtra",
  "lat": 18.5204,
  "lon": 73.8567,
  "start_date": "2026-12-01",
  "end_date": "2026-12-03",
  "travellers_count": 2,
  "total_budget": 20000.0,
  "accommodation_tier": "mid_range",
  "transit_pref": "cab_rental",
  "travel_pace": "balanced",
  "radius_meters": 15000
}
```

---

## 4. Bounding Box & Geographical Invariants

- **India Bounding Box:** `6.0°N` to `38.0°N`, `68.0°E` to `98.0°E`.
- **Validation Rule:** All coordinates received via `/reverse-geocode`, `/discover`, or `/plan-dynamic` are verified against `is_in_india(lat, lon)`. Any coordinate outside this bounding box is strictly rejected with HTTP 400 Bad Request.
- **No Delhi Fallback:** If coordinates for an uncatalogued city (e.g. Pune or Hampi) are processed, the system resolves its real coordinates and centers the trip at that exact location.
- **Null Safety:** Unknown prices or ratings in third-party place feeds remain `None` (never `0.0`), preventing artificial "free activity" distortions in budget calculations.

---

## 5. Verification & Test Suite

All tests mock external HTTP calls with zero external network dependencies.

```bash
# Run the dynamic places test suite
python -m pytest tests/test_places_dynamic.py -v

# Run the complete test suite
python -m pytest tests/test_places_api.py tests/test_places_dynamic.py -v
```

| Test Case | Description | Result |
|---|---|---|
| `test_is_in_india_valid_coordinates` | Verifies coordinates across Delhi, Mumbai, Chennai, Kolkata, Leh, Guwahati, Kanyakumari | **PASS** |
| `test_is_in_india_invalid_coordinates` | Rejects London, New York, Tokyo, Sydney, and null values | **PASS** |
| `test_map_geoapify_categories_to_arm` | Verifies mapping from Geoapify categories to 7 canonical LinUCB arms | **PASS** |
| `test_search_locations_india_offline_fallback` | Resilient offline Indian hubs fallback when network is unconfigured | **PASS** |
| `test_search_locations_india_mocked_geoapify` | Autocomplete parsing with live Geoapify provenance | **PASS** |
| `test_reverse_geocode_india_rejects_out_of_bounds` | Non-Indian coordinates raise ValueError | **PASS** |
| `test_reverse_geocode_india_success` | Resolves real coordinates into structured city and state | **PASS** |
| `test_discover_places_india_mocked` | Geoapify Places discovery with 7-arm categories and null safety | **PASS** |
| `test_rank_places_with_linucb` | Contextual 24-dim LinUCB ranking with proximity bonus and avoidance filtering | **PASS** |
| `test_api_places_search_locations` | `GET /api/places/search-locations` responds with valid Indian results | **PASS** |
| `test_api_places_reverse_geocode_bounds` | `GET /api/places/reverse-geocode` returns HTTP 400 for non-Indian coordinates | **PASS** |
| `test_api_places_reverse_geocode_in_india` | `GET /api/places/reverse-geocode` returns 200 with structured location | **PASS** |
| `test_api_places_discover` | `GET /api/places/discover` discovers places around coordinates | **PASS** |
| `test_api_places_plan_dynamic_end_to_end` | `POST /api/places/plan-dynamic` creates trip, populates places, and generates itinerary without Delhi fallback | **PASS** |
