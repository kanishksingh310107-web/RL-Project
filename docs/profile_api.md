# End-to-End Personalisation & Live APIs (`feat/profile-api`)

This document records the architectural improvements, new endpoints, external APIs, caching layers, and transparent attribution mechanisms implemented on the `feat/profile-api` branch of the **RL-Based Proactive Travel Guide**.

---

## 1. Executive Summary: What Changed & Why

Prior to this update:
1. **Partial / Skippable Profiles:** Users could skip sections of the traveller profile or leave them empty. Many questionnaire responses were merely stored in SQLite without affecting downstream decisions.
2. **Fixed Location List:** Trip planning was restricted to a static, hardcoded list of destinations and canned activities.
3. **Implicit Fallbacks & Opaque Attribution:** Recommendations and itineraries did not clearly explain *why* specific places or activities were chosen.

### What Was Done
1. **Mandatory Profile Completion (Task 1):**
   - Every question applicable to the user (passing its dynamic `show_if` condition) across all three levels (Basic, Detailed Sections 2–10, and Level 3 Precision Questions `q1`–`q126`) must be answered before a user can proceed to trip planning or receive recommendations.
   - Profile validation endpoints enforce 100% completion with HTTP 422 containing the exact missing question IDs and labels.
   - Frontend locks the "Generate LinUCB Itinerary" and "Save" controls until all applicable questions are answered, and provides an auto-jump mechanism to resume unfinished sections.
2. **True Personalisation & Attribution (Task 2):**
   - Every single question in the entire bank (`q1` through `q126`) is explicitly mapped to downstream decision-making in `docs/profile_usage.md`.
   - Hard constraints (allergies, mobility limitations, budget caps, noise/crowd avoidances) are strictly filtered out rather than merely down-weighted.
   - Added transparent `"Because you said ..."` explanations citing specific user answers on every destination card and itinerary activity row.
3. **Live, Key-Less External APIs with SQLite Caching (Task 3):**
   - Integrated Open-Meteo Geocoding API to resolve any city worldwide.
   - Integrated Open-Meteo Forecast & Climate Archive APIs for real-time trip weather.
   - Integrated OpenStreetMap Overpass API for live points of interest, dining, and scenic attractions.
   - Integrated REST Countries API for currency, languages, and country profiles.
   - Created an `api_cache` SQLite table (`cache_key, response_json, source, fetched_at, ttl_seconds`) with polite rate-limiting, custom User-Agent, and verified offline estimates.
   - UI and API responses explicitly label the data source (`source: "api" | "cache" | "offline-estimate"`) with `fetched_at` timestamps.

---

## 2. Files Modified and Created

| File | Change Type | Description |
|---|---|---|
| `app/precision.py` | Modified | Added questions `q122`–`q126` to span `q1`–`q126`; added `check_basic_missing`, `check_precision_missing`, `missing_required()`, and `profile_status()` |
| `app/database.py` | Modified | Added `api_cache` table schema with indices on `cache_key` |
| `app/services/live_api_service.py` | Created | Free key-less API client for Geocoding, Weather, Overpass Places, and REST Countries with caching, timeouts, rate-limiting, and offline fallbacks |
| `app/api.py` | Modified | Added `GET /api/profile/{user_id}/status`, `GET /api/geo/search`, `GET /api/weather/live`, `GET /api/places/live-search`, `GET /api/country/info`; enforced profile completeness & trip validation |
| `app/models.py` | Modified | Added `because_you_said: Optional[str] = None` to `DestinationRecommendation` and `ItineraryActivityModel` |
| `app/modules/common.py` | Modified | Unified `get_user_context(user_id)` to extract structured answers, avoidances, allergies, and dietary needs across all profile layers |
| `app/recommender.py` | Modified | Implemented strict hard-constraint filtering and transparent `"Because you said ..."` rationale generator |
| `app/itinerary_generator.py` | Modified | Dynamically pulls live Overpass places for custom destinations; generates explicit `"Because you said ..."` activity explanations |
| `static/index.html` | Modified | Added live city search autocomplete input, destination source attribution badge, and live weather forecast card |
| `static/app.js` | Modified | Enforced section-by-section completion; added debounced geocoding search (`handleCitySearchInput`); wired live weather widget and `"Because you said ..."` UI tags |
| `docs/profile_usage.md` | Created | Comprehensive mapping table detailing how every question from `q1` to `q126` impacts the code |
| `docs/profile_api.md` | Created | Architectural specification and viva explanation guide |

---

## 3. External APIs Used

All external APIs integrated in this project are **free and require zero API keys, tokens, or credit cards**:

### 1. Open-Meteo Geocoding API
- **Endpoint:** `https://geocoding-api.open-meteo.com/v1/search?name={query}&count=8&language=en&format=json`
- **Application Feature:** Powers city search in the "Plan a New Trip" modal and destination coordinate resolution.
- **Rate Limits & Timeout:** Fair-use policy (up to 10,000 requests/day); client uses 5.0-second timeout with SQLite caching (TTL = 7 days).
- **Fallback:** Curated offline geocoding catalog covering major regional hubs.

### 2. Open-Meteo Weather Forecast & Historical Climate API
- **Endpoints:**
  - Forecast (<= 16 days): `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&current_weather=true&timezone=auto`
  - Historical Archive / Climate (> 16 days): `https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto`
- **Application Feature:** Powers the Itinerary Live Weather Card and pre-trip preparation packing advice.
- **Rate Limits & Timeout:** Fair-use policy; client uses 5.0-second timeout with SQLite caching (TTL = 3 hours for live weather, 30 days for climate archive).
- **Fallback:** Offline seasonal climate estimates based on latitude and regional elevation.

### 3. OpenStreetMap Overpass API
- **Endpoint:** `https://overpass-api.de/api/interpreter`
- **Application Feature:** Queries live attractions, museums, heritage sites, viewpoints, and local dining within a specified radius (default 5–7 km) around coordinates.
- **Usage Policy Compliance:**
  - Mandatory descriptive `User-Agent`: `"RL-Proactive-Travel-Guide/1.0 (B.Tech CSE Project; contact: student@travelguide.local)"`
  - Minimum 1.5-second cooldown between queries to prevent server load spikes.
  - Cached in `api_cache` for 24 hours (`ttl_seconds=86400`).
- **Fallback:** Curated local place database in `app/data/india_destinations.py` and `app/services/places_service.py`.

### 4. REST Countries API
- **Endpoint:** `https://restcountries.com/v3.1/name/{country}?fullText=true`
- **Application Feature:** Retrieves official currencies, spoken languages, timezones, and regional metadata.
- **Rate Limits & Timeout:** Free public endpoint; cached for 30 days (`ttl_seconds=2592000`).
- **Fallback:** Pre-computed metadata for South Asian and Asian countries.

---

## 4. SQLite Caching & Transparent Attribution

To ensure that student viva presentations and offline demos run without internet dependency or latency, every external request routes through the SQLite `api_cache` table:

```sql
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key TEXT PRIMARY KEY,
    response_json TEXT NOT NULL,
    source TEXT NOT NULL,           -- 'api' | 'cache' | 'offline-estimate'
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ttl_seconds INTEGER DEFAULT 86400
);
```

### Transparent Source Attribution Policy
The application never fakes or silently obscures the origin of data:
- Every API endpoint returns `"source": "api" | "cache" | "offline-estimate"` and a `"fetched_at"` timestamp.
- The UI displays explicit badges:
  - `Open-Meteo Geocoding · [source: api]` (or `[source: cache]`)
  - `Open-Meteo [source: api · 10:28:45 AM]`
  - Opening hours or admission fees not reported by Overpass are labeled `"curated estimate"` or `"unknown"`, never fabricated.

---

## 5. How to Run and Test

### 1. Installation
```bash
git checkout feat/profile-api
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Run the Application
```bash
python main.py
```
Open your browser at `http://localhost:8000`.

### 3. Testing the Endpoints Directly
You can test the new endpoints using `curl` or Python:

```bash
# Check profile completeness status
curl http://localhost:8000/api/profile/USER_ID/status

# Live city search (Open-Meteo Geocoding)
curl "http://localhost:8000/api/geo/search?q=Shillong"

# Live weather forecast (Open-Meteo Forecast)
curl "http://localhost:8000/api/weather/live?lat=25.5788&lon=91.8933"

# Live attractions around coordinates (OpenStreetMap Overpass)
curl "http://localhost:8000/api/places/live-search?city=Shillong&lat=25.5788&lon=91.8933"

# Country metadata (REST Countries)
curl "http://localhost:8000/api/country/info?country=India"
```

---

## 6. Known Limitations

1. **Overpass Public Server Availability:** During peak European hours, public Overpass instances (`overpass-api.de`) may throttle requests with HTTP 429. When this occurs, our service automatically falls back to curated regional highlights and returns `source: "offline-estimate"`.
2. **Historical Climate Granularity:** The Open-Meteo Historical Archive API covers dates up to the previous day; multi-year future projections rely on the nearest historical climate averages.
3. **OpenStreetMap Hours Formatting:** Many OSM tags provide free-form opening hour strings (e.g., `Mo-Su 10:00-18:00; PH closed`). The system conservatively parses the start time and leaves ambiguous times labeled as `"curated estimate"`.

---

## 7. AI Assistance and External Libraries/APIs Used

- **Generative AI Collaboration:** Code design, refactoring, and integration were developed with pair-programming assistance from Antigravity (Google DeepMind), adhering to B.Tech CSE viva readability guidelines.
- **External Web APIs:**
  - Open-Meteo Geocoding API (`https://geocoding-api.open-meteo.com/v1/search`)
  - Open-Meteo Weather Forecast API (`https://api.open-meteo.com/v1/forecast`)
  - Open-Meteo Historical Archive API (`https://archive-api.open-meteo.com/v1/archive`)
  - OpenStreetMap Overpass API (`https://overpass-api.de/api/interpreter`)
  - REST Countries API (`https://restcountries.com/v3.1/name/`)
- **Python Standard Library & Frameworks:** FastAPI, Pydantic, SQLite3, urllib.request, numpy, pytest.
