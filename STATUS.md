# Verified Project Status

**Audit Date:** November 2026  
**Audited By:** Person C (Core Architecture & Evaluation Lead)  
**Verification Method:** Verified by running `python run_tests.py` (passes with isolated temp DB), `pytest tests/`, and auditing source code.

---

## 1. Verified Architecture & Component Status

| Area | Implementation Location | Current Status & Audit Findings |
| :--- | :--- | :--- |
| **Auth System** | `app/auth.py` | Working: Google OAuth (mock fallback if client ID not set), Email/Phone OTP verification, Guest session creation. |
| **User Profiling** | `app/core/profile.py`, `app/vectorizer.py`, `app/precision.py` | **Fixed in Core:** `load_profile(user_id)` resolves vocabulary mismatches (`solo` $\to$ `alone`, `mid_range` $\to$ `balanced`), extracts `travel_goals` & `place_interests` from `raw_answers_json`, and respects privacy levels. |
| **Core Schemas & Stores** | `app/core/schemas.py`, `app/core/stores.py` | **Implemented:** Centralized Pydantic schemas (`Place`, `DayPlan`, `TripPlan`, `Stay`, `TripPrefs`, etc.) and SQLite persistent stores (`core_place_cache`, `core_api_usage`, `core_trip_prefs`, `core_plans`, `core_stays`, `core_trip_feedback`). |
| **Providers (Geo & Weather)** | `app/providers/` (`geo.py`, `weather.py`, `cache.py`, `guard.py`) | **Implemented:** Geoapify geocoding, reverse geocoding, category search, and stay search with 7-day TTL cache and 2,500 calls/day credit guard. Open-Meteo forecast and historical climate seasonality. Fallbacks cleanly to seed catalogue. |
| **LinUCB Recommendation Engine** | `app/rl_planner.py` | **Implemented:** Disjoint Contextual LinUCB (Li et al. 2010) across 7 canonical arms (`culture_history`, `nature_outdoors`, `food_dining`, `adventure`, `relaxation`, `shopping_local`, `scenic`). Context dimension is 24-dim. |
| **Legacy Itinerary Generator** | `app/itinerary_generator.py` | **Identified as Legacy:** Fixed slots by pace (relaxed 3, balanced 4, packed 5), transit minutes hard-coded (8/18/15), opening hours not checked, budget summed but not bounded. Person A is replacing this with a time-budget scheduler in `app/planning/`. |
| **Evaluation Suite** | `app/evaluation.py` | **Legacy Demo (Not Evidence):** Legacy 20-round comparison (73.3% LinUCB vs 80.0% static) was a toy demo using a shared random stream. A rigorous multi-seed, multi-persona benchmark is being deployed in `scripts/evaluate.py`. |

---

## 2. Inaccuracies & Deficiencies Corrected

1. **Hours / Cost / Proximity Claims:** Previous documentation claimed the legacy generator enforced hours, cost, and proximity constraints. In fact, it only summed costs and used hard-coded transit times. Genuine time-budgeting and distance-based travel legs are now specified in `app/core/assumptions.py` and `app/core/schemas.py`.
2. **Database Pollution in Tests:** `run_tests.py` previously wrote to the production database `travel_guide.db`. It has been refactored to run against an isolated `tempfile.TemporaryDirectory()` database.
3. **Attribution Discrepancies:** Legacy docs incorrectly stated the agent was "Q-learning" and claimed "100% completion". The model is Contextual LinUCB, and all AI assistance and external library usages are explicitly cataloged in `ATTRIBUTION.md`.
4. **Hard-coded Catalog Flags:** Destination "Trending" and "Seasonal" badges were previously static boolean flags in `app/activity_data.py`. Person C is implementing live seasonality scoring via Open-Meteo historical climate data in `app/modules/ranking.py`.

---

## 3. Active Phase Roadmap

- [x] **Phase 0 (Foundation & Contracts):** Configuration, Pydantic schemas, assumptions, profile loader, provider caching & credit guard, test DB isolation.
- [ ] **Phase 1 (Ranking Module & Personalization):** 6-factor composite destination ranking (`app/modules/ranking.py`), Open-Meteo climate score, tourist density proxy, interactive frontend (`static/modules/ranking.js`).
- [ ] **Phase 2 (Evaluation & Benchmarks):** Multi-seed benchmark across diverse simulated personas comparing LinUCB against random and popularity baselines.
- [ ] **Phase 3 (Viva & Attribution Documentation):** Comprehensive viva preparation guide (`docs/report/VIVA_QA.md`) and verified system report.
