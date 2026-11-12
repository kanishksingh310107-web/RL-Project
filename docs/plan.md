# Dynamic Time-Budget Plan Engine Module (`plan`)

**Owner:** Person A  
**Module ID:** `plan`  
**API Prefix:** `/api/plan`  
**UI Component:** `static/modules/plan.js`  
**Contract Tables:** `core_trip_prefs`, `core_plans`, `plan_shopping_priors`  

---

## 1. Overview & Architecture

The Plan Engine replaces the static legacy slot generator with a dynamic, time-budgeted scheduler governed by:
1. **Dynamic Time Windows:** Computes net minutes available `(day end - day start) - meal windows`, applying user pace utilization (Relaxed 65%, Balanced 80%, Packed 95%).
2. **Personalized Constraint Filtering (`app/planning/personalization.py`):** Enforces hard avoidance filters, accessibility requirements, physical demand, and day-of-week opening hours.
3. **Contextual LinUCB Scoring (`app/modules/plan.py`):** Prioritizes candidates with a 24-dimensional context vector across 7 canonical arms.
4. **Multimodal Transport Model (`app/planning/transport.py`):** Calculates transit time using straight-line distance, circuity factor, and local mode speeds (`walk`, `auto`, `cab`, `rental_car`, `scooter`, `bus_metro`).
5. **Shopping & Budget Ledgers:** Evaluates venue tiers and tracks budget health (Green/Amber/Red) across stay, food, transport, activities, shopping, and buffer.
6. **Constraint Validation (`app/planning/validate.py`):** Validates opening hours, day overflow, and budget status.

---

## 2. API Endpoints

- `GET /api/plan/prefs/{trip_id}`: Retrieves trip scheduling preferences.
- `PUT /api/plan/prefs/{trip_id}`: Updates and persists trip preferences to `core_trip_prefs`.
- `POST /api/plan/generate/{trip_id}`: Generates a multi-day `TripPlan` and persists to `core_plans`.
- `GET /api/plan/{trip_id}`: Loads the generated plan.
- `POST /api/plan/feedback`: Records user feedback and updates the LinUCB policy and shopping priors.
- `GET /api/plan/{trip_id}/validation`: Validates constraints and provides non-destructive legacy suggestions.

---

## 3. Test Coverage

Covered in `tests/test_plan.py`:
- `test_personalization_hard_filters`: Verifies avoidance, mobility, and crowd filters.
- `test_multimodal_transport_estimation`: Validates transit mode selection and time estimation.
- `test_shopping_venue_scoring_budget_sensitivity`: Confirms low-budget preference for flea markets over luxury malls.
- `test_scheduler_never_exceeds_day_window`: Asserts day window bounds and leftover management.
- `test_budget_ledger_status_and_unknown_cost`: Validates budget thresholds and `None` cost safety.
- `test_validator_catches_planted_violations`: Verifies detection of schedule and budget violations.

---

## 4. AI assistance and external libraries/APIs used

- **FastAPI & Pydantic:** Schema validation and REST routing.
- **Geoapify API:** Places and category discovery with offline curated fallback.
- **LinUCB Algorithm:** Contextual bandit scoring adapted from Li et al. (2010).
- **iCalendar (.ics):** RFC 5545 format client-side generator.
