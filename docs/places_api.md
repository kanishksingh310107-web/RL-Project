# Real-Time Places & Dynamic Location API

**Owner:** Person C (Integrator)  
**Router Prefix:** `/api/places`  
**UI Module:** `static/modules/places.js`  
**Test Suite:** `tests/test_places_api.py` (6 unit tests, 100% passing)

---

## 1. What It Does

Instead of relying solely on hardcoded static destinations in Python dictionaries, the **Real-Time Places API** enables the travel guide to dynamically search, geocode, and fetch real points of interest (attractions, temples, viewpoints, beaches, heritage walks, and dining places) on-demand for **ANY city, town, or tourist hub in India**.

Once places are fetched in real-time, the system automatically feeds them into the Contextual LinUCB bandit engine, generating a realistic timed day-by-day itinerary (morning, transit buffers, lunch breaks, afternoon sights, tea/rest breaks, and evening experiences) that the traveller can edit, swap, finalize, and start.

---

## 2. Architecture & Data Flow

```
[Traveller UI]
     │
     ▼
[GET /api/places/search?q=...] ──► OpenStreetMap Nominatim API (Real-Time Geocoding)
     │                                    │
     ▼                                    ▼
[Selected Indian Location] ◄──────────────┘ (Coordinates: Lat, Lon, State)
     │
     ▼
[GET /api/places/attractions] ──► Wikivoyage & Wikipedia Travel API
     │                                    │ (Real Sights, Viewpoints, Categories, Timings)
     ▼                                    ▼
[POST /api/places/plan-trip] ──► SQLite `destination_activities` (Live Ingestion)
     │
     ▼
[Contextual LinUCB Policy] ──► Balances Exploration & Exploitation by Category Arm
     │
     ▼
[Timed Day-by-Day Schedule] ──► Morning, Transit (15m), Lunch (90m), Afternoon, Rest (90m), Evening
```

---

## 3. Endpoints

| Method | Endpoint | Query / Body | Description |
|---|---|---|---|
| `GET` | `/api/places/search` | `?q={city}&limit=6` | Real-time geocoding across India using OpenStreetMap Nominatim. |
| `GET` | `/api/places/attractions` | `?city={city}&lat={lat}&lon={lon}` | Fetches live attractions, sights, viewpoints, and dining places via Wikivoyage/Wikipedia. |
| `GET` | `/api/places/popular` | — | Returns 10 trending real Indian destinations for quick selection. |
| `POST` | `/api/places/plan-trip` | `PlanDynamicTripRequest` JSON | Takes any city in India, fetches real places via API, generates LinUCB schedule, and returns Timed View. |

### Sample Dynamic Plan Request
```json
POST /api/places/plan-trip
{
  "user_id": "usr_abc123",
  "city_name": "Pondicherry",
  "duration_days": 3,
  "pace_preference": "balanced",
  "budget_tier": "balanced"
}
```

---

## 4. Test Verification

Run command: `pytest tests/test_places_api.py -v`

| Test Case | Inputs | Expected Output | Status |
|---|---|---|---|
| `test_places_module_registered` | `GET /api/modules` | Module with `id="places"` and `owner="C"` found | **PASS** |
| `test_search_indian_locations_endpoint` | `?q=Manali` | Returns coordinates, state, and `country="India"` | **PASS** |
| `test_get_attractions_endpoint` | `city=Manali&lat=32.24&lon=77.18` | Returns real sights with duration, categories, and descriptions | **PASS** |
| `test_get_popular_destinations` | `GET /api/places/popular` | Returns $\ge 8$ popular Indian hubs | **PASS** |
| `test_plan_dynamic_trip_end_to_end` | `city_name="Pondicherry", duration_days=2` | Dynamically fetches 14 places, runs LinUCB, produces 2-day timed schedule with transit, meal, and rest blocks | **PASS** |
| `test_places_service_fallback_offline` | Query: `"Goa"` | Resilient cached dictionary returns valid coordinates if network drops | **PASS** |

---

## 5. External APIs & AI Assistance

- **External APIs Used:**
  - **OpenStreetMap Nominatim API:** Real-time geocoding and reverse geocoding for Indian cities and towns (`https://nominatim.openstreetmap.org/search`).
  - **Wikimedia Wikivoyage Travel API:** Structured travel listings (`{{see}}`, `{{do}}`, `{{eat}}`) providing descriptions, opening hours, and pricing (`https://en.wikivoyage.org/w/api.php`).
  - **Wikipedia MediaWiki Geosearch & Summary REST API:** Geographically clustered landmarks, verified encyclopedic summaries, and authentic thumbnail photographs (`https://en.wikipedia.org/api/rest_v1/page/summary`).
  - **Google Places API (Optional):** Supported as an alternative provider if `GOOGLE_PLACES_API_KEY` is configured in the environment.
- **AI Assistance:** Anthropic Claude / Google DeepMind Agentic Pair Programmer was used for scaffolding regular expression parsers for wikitext and designing the LinUCB category mapping.
