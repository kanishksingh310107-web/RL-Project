# Stay & Accommodation Module (`stay`)

**Owner:** Person B  
**Module ID:** `stay`  
**API Prefix:** `/api/stay`  
**UI Component:** `static/modules/stay.js`  
**Contract Tables:** `core_stays`, `stay_preferences`  

---

## 1. Overview & Architectural Role

The Stay module handles accommodation anchoring for the itinerary planner:
1. **Area Recommendation (`GET /api/stay/{trip_id}/areas`):** Recommends the top 3 neighborhoods that minimize total round-trip daily commute time to all scheduled activities:
   $$\text{Daily Commute} = \sum_{\text{day}} (\text{dist}(\text{area}, \text{first\_stop}) + \text{dist}(\text{last\_stop}, \text{area}))$$
2. **Hotel Options (`GET /api/stay/{trip_id}/options`):** Fetches real accommodations within 12 km using Geoapify with offline generic types fallback (`budget_guesthouse`, `boutique_hotel`, `resort`).
3. **Zero Hotel Price Rule:** In accordance with free-tier API reality, **NO hotel prices are shown**. Instead, a dynamic estimated nightly budget band is displayed:
   $$\text{Nightly Budget} = \frac{\text{Total Trip Budget} \times \text{Stay Share (35\%)}}{\text{Number of Nights}}$$
   Each option carries an external search link (`Google Hotels`) for user rate lookup.
4. **Hotel-First Mode (`POST /api/stay/{trip_id}/hotel-first-preview`):** Geocodes a user's pre-booked hotel, saves to `core_stays`, and computes a commute preview comparing before/after daily commute times.

---

## 2. API Endpoints

- `GET /api/stay/{trip_id}/areas`: Evaluates all stops in `core_plans` and returns top 3 ranked areas.
- `GET /api/stay/{trip_id}/options?lat=&lon=&limit=`: Retrieves hotel options with budget band and search URLs.
- `POST /api/stay/{trip_id}/select`: Persists selected `Stay` to `core_stays`.
- `POST /api/stay/{trip_id}/hotel-first-preview`: Anchors custom hotel and returns before/after travel minutes preview.

---

## 3. Test Coverage

Covered in `tests/test_stay.py`:
- `test_commute_area_ranking_with_return_leg`: Confirms round-trip return leg is counted and closer areas rank first.
- `test_no_price_field_in_accommodations`: Enforces absence of fake price fields in hotel records.
- `test_offline_fallback_labeled`: Verifies offline fallback carries `"offline estimate"` provenance.
- `test_save_and_load_stay_contract`: Tests integrity of `core_stays` persistence.
- `test_stay_api_routes`: End-to-end FastAPI test of areas, options, and hotel-first preview.

---

## 4. AI assistance and external libraries/APIs used

- **FastAPI & Pydantic:** Schema validation and REST routing.
- **Geoapify Places API:** Accommodation category retrieval with offline curated fallback.
- **Haversine Formula:** Great-circle geodesic distance calculation.
