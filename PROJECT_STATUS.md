# Project Status: RL-Based Proactive Travel Guide

**Document Version:** 1.0 (Audit Baseline) | **Date:** November 10, 2026 | **Branch:** `feat/profile-api`  
**Environment:** Windows 11 | Python 3.11.9 | SQLite 3.45+ | FastAPI 0.110.0+ | Vanilla JS + Tailwind CSS  
**Audit Mode:** Read-Only Code Verification & Live Runtime Inspection  

---

## 1. How to Run

### Commands
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
Remove-Item -Path "travel_guide.db" -Force -ErrorAction SilentlyContinue
python run_tests.py
python -m pytest tests/ -q
python main.py
```
- **Python Version:** 3.11.9 (64-bit).
- **Core Packages:** `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `pydantic>=2.6.0`, `numpy>=1.26.0`, `google-auth>=2.0.0`, `requests>=2.31.0`, `httpx>=0.27.0`, `pytest>=8.0.0`, `matplotlib>=3.8.0`.
- **URL:** `http://127.0.0.1:8000` (Swagger docs at `/docs`).
- **Internet Requirements:** Needs CDNs (Tailwind CSS, FontAwesome, Google Fonts, GIS) on initial load; offline usage breaks styles. Open-Meteo and OpenStreetMap have offline local dictionary fallbacks.

---

## 2. File Map

| Path | Lines | Purpose | Status |
| :--- | :---: | :--- | :---: |
| `main.py` | 42 | FastAPI app entrypoint, static mount, module discovery router | Active |
| `run_tests.py` | 534 | Monolithic end-to-end integration assertion script (28 checks) | Active |
| `requirements.txt` / `requirements-dev.txt` | 7 / 2 | Runtime and dev dependencies (fastapi, uvicorn, numpy, pytest, etc.) | Active |
| `README.md` / `HANDOFF.md` | 95 / 208 | Quickstart and developer handover documentation | Outdated |
| `ATTRIBUTION.md` / `master_prompt.md` | 67 / 459 | Authorship disclosure / original multi-person specification | Active / Ref |
| `app/activity_data.py` | 2174 | Curated catalog of 84 attractions across 14 destinations | Active |
| `app/api.py` | 1077 | Core REST API routes (auth, profiles, trips, itineraries, LinUCB) | Active |
| `app/auth.py` | 150 | Auth helpers (salted SHA-256, GIS Google token verification, phone OTP)| Active |
| `app/database.py` | 287 | SQLite schema initialization, connection helper, activity seeding | Active |
| `app/evaluation.py` | 209 | Comparative benchmark: LinUCB vs Static Recommender Baseline | Active |
| `app/itinerary_generator.py` | 471 | Day-by-day itinerary scheduler with neighborhood clustering & LinUCB | Active |
| `app/models.py` | 374 | Pydantic v2 schemas for request validation, trips, itineraries, feedback | Active |
| `app/precision.py` | 675 | 83-question adaptive precision questionnaire with conditional branching | Active |
| `app/questionnaire.py` | 865 | 56-question master bank (10 sections) for detailed profiling | Active |
| `app/recommender.py` | 1342 | Macro destination recommender (20 destinations, scoring weights) | Active |
| `app/rl_planner.py` | 468 | Disjoint LinUCB bandit policy, 24-dim context extraction, reward updates | Active |
| `app/vectorizer.py` | 350 | Maps questionnaire answers to 22-dim basic and 41-dim detailed vectors | Active |
| `app/data/india_destinations.py` | 254 | Metadata catalog of 20+ Indian destinations with coordinates and seasons | Active |
| `app/modules/__init__.py` | 54 | Module auto-discovery and plugin registry (`/api/modules`) | Active |
| `app/modules/_template.py` | 18 | Boilerplate template for new companion plug-in modules | Dead |
| `app/modules/common.py` | 43 | Shared database helpers for module queries (JSON decoding) | Active |
| `app/modules/live.py` | 1223 | During-trip monitoring, simulation, alerts, replanning, and post-trip | Active |
| `app/modules/places.py` / `places_service.py` | 220 / 358 | Live location search and OSM attraction proxy router / service | Active |
| `app/modules/prep.py` | 1111 | Pre-trip prep: weather forecast, packing list, documents, reminders | Active |
| `app/modules/ranking.py` | 495 | 6-component seasonal destination ranking engine with audit log | Active |
| `app/modules/trip_actions.py` | 395 | Timed itinerary editor: activity swap, remove, finalize, start trip | Active |
| `app/services/places_service.py` | 1029 | Alternate places service implementation with Indian destinations | Dead Router |
| `app/services/suggestion_engine.py` | 197 | Rule-based activity suggestion generator for itinerary adjustments | Active |
| `app/services/timed_itinerary.py` | 838 | Time-slotted itinerary generator and DB persistence service | Active (Backend) |
| `scripts/evaluate.py` | 371 | Standalone 150-round Monte Carlo simulation script for academic viva | Active |
| `static/app.js` / `index.html` / `style.css` | 2045/1183/40| Client-side SPA controller / HTML template / custom CSS styles | Active |
| `static/modules/itinerary_editor.js` | 390 | Companion UI: Trip itinerary timed view with swap/remove/finalize | Active |
| `static/modules/live.js` | 851 | Companion UI: Live trip tracker, alert simulation, replan, post-trip | Active |
| `static/modules/loader.js` | 84 | Injects "Companion" navbar button and loads plug-in module tabs | Active |
| `static/modules/places.js` | 367 | Companion UI: Search Indian locations, view attractions, quick-plan | Active |
| `static/modules/prep.js` | 335 | Companion UI: Weather widget, dynamic packing, checklist, reminders | Active |
| `static/modules/ranking.js` | 249 | Companion UI: Multi-criteria destination ranking with breakdown bars | Active |
| `tests/` (8 test files + `conftest.py`) | 1799 | 72 automated pytest tests covering prep, live, places, ranking, actions | Active |
| `docs/AUDIT_REPORT.md` | 379 | Comprehensive QA, security, UX, and RL audit report | Active |

---

## 3. Architecture

1. **Client (Browser):** Responsive SPA built with vanilla JavaScript (`app.js`), Tailwind CSS CDN, and dynamic module scripts (`static/modules/*.js`).
2. **API Layer:** FastAPI gateway exposing core routes (`app/api.py`) and plug-in companion routers (`app/modules/`).
3. **Authentication:** Multi-provider handler supporting guest demo, email/password (SHA-256), phone OTP (`123456`), and Google Identity Services.
4. **Profiling Pipelines:** 3-tier user representation mapping questionnaire answers to 22-dim (basic), 41-dim (detailed), and 126-dim (precision) vectors.
5. **Macro Recommender:** Multi-criteria scoring over 20 destinations using 5 explainable weights (interests, climate, budget, pace, variety).
6. **RL Itinerary Planner:** Day-by-day scheduler using geographical neighborhood clustering and a Disjoint Contextual LinUCB bandit ($|\mathcal{A}|=7, d=24$).
7. **Feedback Closed Loop:** In-itinerary Accept (+1.0), Skip/Reject (-1.0), Modify (-0.4), and Finalize (+0.2) actions update per-user bandit weights in real time.
8. **Companion Subsystems:** Plug-in architecture offering Trip Prep (packing/weather/reminders), Live Execution (alerts/replanning), Post-Trip survey, Places search, and Ranking.
9. **External Integrations:** Live REST calls to Open-Meteo and OpenStreetMap Nominatim/Overpass with robust local offline dictionary fallbacks.
10. **Data Persistence:** Embedded SQLite engine (`travel_guide.db`) maintaining 20 relational tables with automatic schema bootstrapping.

---

## 4. Database Schema

| Table Name | Key Columns | Written By | Read By | Status |
| :--- | :--- | :--- | :--- | :---: |
| `users` | `id, auth_provider, identifier, password_hash, display_name, google_sub` | `app/api.py` (auth) | `app/api.py`, `modules/*` | Active |
| `traveller_profiles` | `user_id, interests, pace, crowd_tolerance, budget_tier, climate, vector_json`| `app/api.py:save_basic_profile` | `app/api.py`, `recommender.py` | Active |
| `detailed_profiles` | `user_id, avoidances, walking_tolerance, schedule_density, detailed_vector` | `app/api.py:save_detailed_profile`| `app/api.py`, `recommender.py` | Active |
| `precision_profiles` | `user_id, answers_json, vector_json, coverage, updated_at` | `app/api.py:save_precision_profile`| `app/api.py`, `prep.py` | Active |
| `past_trips` | `id, user_id, destination, rating, favorite_activity, skipped_or_disliked` | `app/api.py:save_precision_profile`| `app/recommender.py` | Active |
| `shortlisted_destinations` | `user_id, destination_id, created_at` | `app/api.py:toggle_shortlist` | `app/api.py`, `recommender.py` | Active |
| `trips` | `id, user_id, destination_id, destination_name, start_date, end_date, status` | `app/api.py:create_trip` | `app/api.py`, `modules/*` | Active |
| `itineraries` | `id, trip_id, user_id, title, total_days, status, total_estimated_cost` | `app/itinerary_generator.py` | `app/api.py`, `modules/*` | Active |
| `itinerary_activities` | `id, itinerary_id, day_number, time_slot, activity_id, status, rejection_reason` | `itinerary_generator.py`, `feedback` | `app/api.py`, `modules/*` | Active |
| `destination_activities`| `id, destination_id, name, category, latitude, longitude, cost_tier, tags` | `activity_data.py:seed_activities` | `itinerary_generator.py` | Active |
| `rl_user_policies` | `user_id, arm_id, dimension, matrix_a_json, vector_b_json, pull_count, reward` | `app/rl_planner.py:save_policy` | `rl_planner.py`, `app/api.py` | Active |
| `rl_feedback_log` | `id, user_id, trip_id, activity_id, arm_id, action_type, reward, context_json` | `app/rl_planner.py:process_feedback` | `app/api.py`, `evaluation.py` | Active |
| `live_trip_state` | `trip_id, user_id, is_started, is_completed, current_day, started_at` | `app/modules/live.py` | `app/modules/live.py` | Active |
| `live_activity_status` | `id, trip_id, activity_id, status, notes, updated_at` | `app/modules/live.py` | `app/modules/live.py` | Active |
| `live_conditions` / `alerts`| `id, trip_id, day_number, condition_type, severity, description` | `app/modules/live.py:simulate` | `app/modules/live.py` | Active |
| `live_postrip` / `feedback`| `id, trip_id, user_id, satisfaction, pace, budget, ratings, arm_id, reward` | `app/modules/live.py:submit_postrip`| `app/modules/live.py` | Active |
| `live_activity_contexts`| `id, itinerary_id, activity_id, context_vector_json, created_at` | `app/modules/live.py` | `app/modules/live.py` | Active |
| `prep_reminders` / `bandit` | `id, trip_id, text, category, due_date / user_id, category, alpha, beta` | `app/modules/prep.py` | `app/modules/prep.py` | Active |
| `ranking_audit_log` | `id, user_id, requested_date, created_at` | `app/modules/ranking.py:rank` | Nobody reads from it | Orphan |

---

## 5. Backend Routes

| Group | Method & Path | Defined In | Purpose | UI Caller |
| :--- | :--- | :--- | :--- | :--- |
| **App** | `GET /` | `main.py` | Serves SPA `index.html` | Browser |
| **Auth** | `POST /api/auth` | `app/api.py` | Authenticates guest, email, phone | `static/app.js:145, 172, 198` |
| **Auth** | `POST /api/auth/google-token` | `app/api.py` | Validates Google GIS ID token | `static/app.js:115` |
| **Config** | `GET / POST /api/config/google` | `app/api.py` | Gets / sets runtime Google Client ID | `static/app.js:101` (POST uncalled)|
| **Config** | `GET /api/config/options`, `detailed-options`| `app/api.py`| Onboarding survey metadata | No UI calls it |
| **Config** | `GET /api/config/questionnaire` | `app/api.py` | Returns master 56-question survey bank| `static/app.js:372` |
| **Config** | `GET /api/config/precision-questionnaire` | `app/api.py`| Returns adaptive 83-question bank | `static/app.js:1252` |
| **Profile**| `GET / POST /api/profile/{user_id}` | `app/api.py` | Gets / saves basic 11-question profile| `static/app.js:630, 662` |
| **Profile**| `GET / POST /api/profile/detailed/{user_id}` | `app/api.py`| Gets / saves detailed profile (Sec 2–10)| `static/app.js:640, 670` |
| **Profile**| `GET / POST /api/profile/precision/{user_id}`| `app/api.py`| Gets / saves adaptive precision state | `static/app.js:733, 1440` |
| **Recs** | `GET /api/recommendations/{user_id}` | `app/api.py` | Macro recommendations (offset rotation)| `static/app.js:849` |
| **Shortlist**| `GET / POST /api/shortlist/{user_id}` | `app/api.py` | Lists / toggles bookmarked destination | `static/app.js:1018, 1032` |
| **Trips** | `GET / POST /api/trips/{user_id}` | `app/api.py` | Lists / creates trips (India validated) | `static/app.js:1095, 1115` |
| **Trips** | `GET /api/trips/detail/{trip_id}` | `app/api.py` | Single trip detail | No UI calls it |
| **Itinerary**| `POST /api/itinerary/generate/{trip_id}` | `app/api.py` | Builds LinUCB day-by-day schedule | `static/app.js:1130` |
| **Itinerary**| `GET /api/itinerary/{trip_id}` | `app/api.py` | Retrieves active schedule | `static/app.js:1145` |
| **Feedback**| `POST /api/itinerary/feedback/{user_id}` | `app/api.py` | Records Accept/Reject/Modify feedback | `static/app.js:1180, 1210` |
| **Feedback**| `GET /api/itinerary/alternatives/...` | `app/api.py` | Top 3 alternatives for Modify action | `static/app.js:1225` |
| **RL** | `GET /api/rl/state/{user_id}`, `policy/{user_id}`| `app/api.py`| State vector $s_t$ & arm weights $\hat{\theta}_a$ | `static/app.js:1505, 1520` |
| **RL** | `GET /api/evaluation/benchmark`, `live/{id}` | `app/api.py` | LinUCB simulation / user metrics | `static/app.js:1560` (live uncalled)|
| **Modules**| `GET /api/modules` | `app/modules`| Discovers companion plug-in tabs | `static/modules/loader.js:55` |
| **Prep** | `GET /api/prep/{trip_id}/weather`, `packing` | `prep.py` | Weather forecast & dynamic packing list | `static/modules/prep.js:42, 88` |
| **Prep** | `GET /api/prep/{trip_id}/documents`, `reminders`| `prep.py`| Documents checklist & smart reminders | `static/modules/prep.js:140, 180` |
| **Prep** | `POST /api/prep/{trip_id}/reminders/.../feedback`| `prep.py` | Feedback on reminders (Beta bandit) | `static/modules/prep.js:220` |
| **Live** | `GET /api/live/{trip_id}/state`, `today`, `alerts`| `live.py` | Trip status, daily items, active alerts | `static/modules/live.js:35, 70, 195`|
| **Live** | `POST /api/live/{trip_id}/activity/.../status` | `live.py` | Checkboxes for completed/skipped spots | `static/modules/live.js:115` |
| **Live** | `POST /api/live/{trip_id}/simulate`, `dismiss` | `live.py` | Simulates disruptions / dismisses alert | `static/modules/live.js:160, 230` |
| **Live** | `GET / POST /api/live/{trip_id}/replan` | `live.py` | Proposes & applies disruption replacement| `static/modules/live.js:260, 285` |
| **Live** | `POST /api/live/{trip_id}/complete` | `live.py` | Finalizes trip; unlocks post-trip survey | `static/modules/live.js:320` |
| **Post-Trip**| `GET / POST /api/live/{trip_id}/postrip` | `live.py` | Submits & views post-trip review | `static/modules/live.js:370, 410` |
| **Ranking**| `GET /api/ranking/{user_id}` | `ranking.py` | 6-component multi-criteria ranking | `static/modules/ranking.js:45` |
| **Places** | `GET /api/places/search`, `attractions` | `places.py` | Geocoding & OSM attractions lookup | `static/modules/places.js:40, 85` |
| **Places** | `GET /api/places/popular`, `POST plan-trip` | `places.py` | Popular spots (uncalled) / instant trip | `static/modules/places.js:145` |
| **Actions**| `GET /api/trip-actions/{trip_id}/timed-view` | `trip_actions.py`| Timed slot view with transit legs | `static/modules/itinerary_editor.js:35`|
| **Actions**| `POST /api/trip-actions/{id}/finalize`, `start` | `trip_actions.py`| Finalize (+0.2 reward) / start trip | `static/modules/itinerary_editor.js:90,120`|
| **Actions**| `POST swap`, `DELETE activity` | `trip_actions.py`| Reorder activities / delete slot | `static/modules/itinerary_editor.js:160,200`|
| **Timed** | `POST /api/itinerary/timed/...` | `timed_itinerary.py`| Backend-only timed scheduler | No UI calls it |

---

## 6. Front-End Screens & Controls

| Screen | Control Element | Action / Trigger | Runtime Behavior | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Nav Header** | "Companion" button | `openCompanion()` | Opens modal with Prep, Live, Ranking, Places, Editor | Working |
| **Nav Header** | "Model Inspector" button | `openInspectorModal()` | Opens LinUCB state vector, arm weights, and simulation | Working |
| **Nav Header** | "Project Info" button | `openProjectInfoModal()` | Summarizes project algorithms and academic parameters | Working |
| **Nav Header** | "Log out" button | `logout()` | Clears `localStorage` session and returns to auth screen | Working |
| **Auth Screen** | "Google" / "Quick Demo" | `loginAsGuest()` | Instant sign-in with pre-seeded demo user | Working |
| **Auth Screen** | "Connect Google Client ID" | `openGoogleConfigModal()`| Opens Google Client ID modal dialog | Working |
| **Google Modal** | "Save & Enable" button | `saveGoogleClientId()` | Throws `ReferenceError: saveGoogleClientId is not defined`| **Broken** |
| **Auth Screen** | "Email" tab / Submit | `submitEmailAuth()` | Registers or signs in email/password user | Working |
| **Auth Screen** | "Phone" tab / Submit | `verifyPhoneOtp()` | Authenticates phone user via simulated OTP `123456` | Working |
| **Basic Modal** | Step navigation & Finish | `nextBasicStep()`, `submit`| Completes 3-step survey and saves 11 answers to DB | Working |
| **Dashboard** | "Edit Setup" button | `editBasicProfile()` | Re-opens basic onboarding modal with current selections | Working |
| **Dashboard** | "Complete Personal Profile" | `openPrecisionModal()` | Opens 83-question adaptive questionnaire modal | Working |
| **Precision** | Question options & Save | `submitPrecisionProfile()` | Validates, filters private fields, saves 126-dim vector | Working |
| **Recs Section**| "Refresh Options" button | `refreshRecommendations()`| Cycles candidate pool via offset pagination | Working |
| **Rec Card** | Bookmark star / "Explore" | `toggleShortlist()`, `open` | Bookmarks destination or opens explore modal | Working |
| **Explore Modal**| "Plan Trip Here" button | `planTripFromExplore()` | Opens New Trip modal with prefilled destination | Working |
| **Trip Modal** | Destination & Dates / Submit | `createTrip()` | Enforces India destinations; triggers LinUCB schedule | Working |
| **Itinerary** | "Regenerate Itinerary" | `regenerateItinerary()` | Re-runs LinUCB scheduler excluding rejected activities | Working |
| **Activity Card**| "Accept" button | `handleAction('accept')` | Assigns reward +1.0, updates arm parameters $A$ and $b$ | Working |
| **Activity Card**| "Skip" / "Reject" button | `openRejectModal()` | Opens modal to capture rejection reason and scope | Working |
| **Reject Modal** | "Confirm Rejection" button | `submitRejection()` | Reward -1.0; excludes activity from regeneration | Working |
| **Activity Card**| "Modify" button | `openModifyModal()` | Fetches 3 alternatives; reward -0.4 to original arm | Working |
| **Companion** | Trip selector dropdown | `onchange` | Switches active trip context across all companion tabs | Working |
| **Comp: Prep** | Weather, Packing, Documents| Tab views | Renders weather forecast, packing checklist, reminders | Working |
| **Comp: Live** | "Start Trip", "Simulate Alert"| Action buttons | Activates live execution; simulates weather disruptions | Working |
| **Comp: Live** | "Replan", "Complete Trip" | Action buttons | Replaces disrupted spots; unlocks post-trip feedback | Working |
| **Comp: Ranking**| Sliders & Date Picker | Real-time recalculation | Explains scores across 6 criteria with stacked bars | Working |
| **Comp: Places** | Search bar & "Plan Trip" | `searchPlaces()` | Geocodes city via OSM; plans instant trip | Working |
| **Comp: Editor** | "Swap", "Remove", "Finalize" | Action buttons | Swaps activities, drops slot, locks itinerary (+0.2) | Working |

---

## 7. Feature Status Table

| Feature | Status | Verified By | Evidence | Notes |
| :--- | :---: | :---: | :--- | :--- |
| **Guest Demo Login** | Working | CLICKED | `app/api.py:175`, `static/app.js:145` | Instant login with pre-seeded demo user |
| **Email/Password Auth** | Working | TESTED | `tests/conftest.py:25`, `app/api.py:165` | Registers and signs in; passwords hashed |
| **Phone OTP Auth** | Working | TESTED & CLICKED | `app/api.py:151`, `static/app.js:198` | Fixed OTP `123456` bypasses real SMS |
| **Google Sign-In** | Partly working | CODE-ONLY | `static/index.html:630` | Client ID button calls missing `saveGoogleClientId()` |
| **Basic Onboarding Profile**| Working | TESTED & CLICKED | `run_tests.py:48`, `app/api.py:465` | 11 questions, 3 steps, extracts 22-dim vector |
| **Detailed Profile (Sec 2-10)**| Working | TESTED | `run_tests.py:53`, `app/api.py:495` | 41-dim vector with avoidances & dietary masks |
| **Precision Questionnaire** | Working | TESTED & CLICKED | `run_tests.py:65`, `app/precision.py` | 83 adaptive questions, privacy controls |
| **Macro Recommendations** | Working | TESTED & CLICKED | `run_tests.py:80`, `app/recommender.py` | 4 Recommended, 3 Trending, 3 Seasonal |
| **Refresh Options (Offset)**| Working | TESTED & CLICKED | `run_tests.py:82`, `app/api.py:541` | Cycles candidate pool without page reload |
| **Destination Shortlisting**| Working | TESTED & CLICKED | `run_tests.py:84`, `app/api.py:618` | Persistent bookmarking in SQLite |
| **Trip Creation** | Working | TESTED & CLICKED | `run_tests.py:90`, `app/api.py:660` | Enforces India destinations; 400 on international |
| **Day-by-Day Itinerary** | Working | TESTED & CLICKED | `run_tests.py:92`, `itinerary_generator.py` | Neighborhood clustering + LinUCB scoring |
| **Accept Activity Feedback**| Working | TESTED & CLICKED | `run_tests.py:95`, `app/rl_planner.py:408` | Reward +1.0, updates arm covariance matrix $A$ |
| **Reject Activity Feedback**| Working | TESTED & CLICKED | `run_tests.py:98`, `app/rl_planner.py:411` | Reward -1.0; excludes item from regeneration |
| **Modify Activity Feedback**| Working | TESTED & CLICKED | `run_tests.py:105`, `app/api.py:997` | Reward -0.4, fetches 3 alternative candidates |
| **Itinerary Alternatives** | Working | TESTED & CLICKED | `static/app.js:1225`, `app/api.py:997` | Returns top 3 LinUCB-scored replacements |
| **Itinerary Regeneration** | Working | TESTED & CLICKED | `static/app.js:1130`, `run_tests.py:100` | Re-generates schedule respecting past rejections |
| **Timed Itinerary Service** | Partly working | TESTED | `tests/test_timed_itinerary.py` | Backend passes 7 tests; no UI calls its endpoints |
| **Trip Finalization** | Working | TESTED & CLICKED | `tests/test_trip_actions.py:45` | Locks schedule, assigns implicit +0.2 rewards |
| **Activity Swap** | Working | TESTED & CLICKED | `tests/test_trip_actions.py:75` | Swaps slots across days in `itinerary_activities` |
| **Activity Delete** | Working | TESTED & CLICKED | `tests/test_trip_actions.py:95` | Removes slot; recalculates day order |
| **Trip Reschedule / Days** | Partly working | CODE-ONLY | `app/modules/trip_actions.py` | Swap operates across days; drag-and-drop absent |
| **Weather Forecast** | Working | TESTED & CLICKED | `tests/test_prep.py:30`, `app/modules/prep.py` | Queries Open-Meteo with seasonal offline fallback |
| **Dynamic Packing List** | Working | TESTED & CLICKED | `tests/test_prep.py:55`, `app/modules/prep.py` | Adapts to destination climate, bag tier, duration |
| **Documents Checklist** | Working | TESTED & CLICKED | `tests/test_prep.py:120`, `app/modules/prep.py`| Identifies domestic Indian travel vs visa needs |
| **Contextual Reminders** | Working | TESTED & CLICKED | `tests/test_prep.py:150`, `app/modules/prep.py`| Reminder cards with Beta bandit category tuning |
| **Start Live Trip** | Working | TESTED & CLICKED | `tests/test_live.py:50`, `app/modules/live.py` | Sets `is_started=1`, activates execution view |
| **Today's Live Itinerary** | Working | TESTED & CLICKED | `tests/test_live.py:70`, `app/modules/live.py` | Real-time checkboxes for completed/skipped spots |
| **Condition Simulation** | Working | TESTED & CLICKED | `tests/test_live.py:110`, `app/modules/live.py`| Simulates weather/closures/strikes/crowding |
| **Disruption Alerts** | Working | TESTED & CLICKED | `tests/test_live.py:130`, `app/modules/live.py`| Displays severity banners with dismiss controls |
| **In-Trip Replanning** | Working | TESTED & CLICKED | `tests/test_live.py:170`, `app/modules/live.py`| Suggests indoor/nearby replacement activities |
| **Trip Completion** | Working | TESTED & CLICKED | `tests/test_live.py:200`, `app/modules/live.py`| Marks `is_completed=1`, opens post-trip survey |
| **Post-Trip Survey & Feedback**| Working | TESTED & CLICKED | `tests/test_live.py:230`, `app/modules/live.py`| Ratings update per-user LinUCB arm parameters |
| **Places Search (Nominatim)**| Working | TESTED & CLICKED | `tests/test_places_api.py:35` | Queries OSM Nominatim with 25+ city fallback |
| **Attractions Lookup (Overpass)**| Working | TESTED & CLICKED | `tests/test_places_api.py:55` | Queries OSM Overpass nodes with local dictionary |
| **Popular Destinations API**| Partly working | TESTED | `tests/test_places_api.py:75` | Endpoint `/api/places/popular` works; no UI calls it|
| **Instant Trip from Places**| Working | TESTED & CLICKED | `tests/test_places_api.py:90` | Creates trip and opens itinerary from searched spot |
| **Seasonal Ranking Engine** | Working | TESTED & CLICKED | `tests/test_ranking.py:30` | 6 explainable scoring components with stacked bars |
| **Academic Model Inspector**| Working | TESTED & CLICKED | `static/app.js:1500`, `run_tests.py:108` | Visualizes state vector, LinUCB arm weights |
| **Evaluation Benchmark** | Working | TESTED & CLICKED | `run_tests.py:110`, `scripts/evaluate.py` | 150-round Monte Carlo simulation script & modal API |
| **Country Information** | Partly working | CODE-ONLY | `app/services/places_service.py` | Embedded in places fallback; no dedicated view |
| **Companion Header Button** | Working | CLICKED | `static/modules/loader.js:75` | Injected into header; loads modal with 5 tabs |

---

## 8. The RL Part

### Algorithm & Mathematical Model
- **Algorithm:** Disjoint Contextual Linear Multi-Armed Bandit (**LinUCB**, Li et al., WWW 2010).
- **Core Model:** $\mathbb{E}[r_{t, a} \mid x_{t, a}] = x_{t, a}^\top \theta_a^*$, estimated via ridge regression:
  $$\hat{\theta}_a = A_a^{-1} b_a, \quad A_a = I_d + \sum x_\tau x_\tau^\top, \quad b_a = \sum r_\tau x_\tau$$
- **Action Selection:** $\text{score}(a, x) = x^\top \hat{\theta}_a + \alpha \sqrt{x^\top A_a^{-1} x}$ with exploration parameter $\alpha = 0.5$.
- **Dimension:** $d = 24$.
- **Inversion Note:** The docstring claims Sherman-Morrison rank-1 updates ($O(d^2)$); actual code executes `np.linalg.inv(A)` ($O(d^3)$) on each score calculation.

### Canonical Arms ($|\mathcal{A}| = 7$)
`culture_history`, `nature_outdoors`, `food_dining`, `adventure`, `relaxation`, `shopping_local`, `scenic`.

### Context Features ($x \in [0, 1]^{24}$)
| Index & Name | Description | Index & Name | Description |
| :--- | :--- | :--- | :--- |
| `0: user_interest_culture` | Stated culture preference (0..1) | `12: trip_duration_norm` | Total days / 14 |
| `1: user_interest_nature` | Stated nature preference (0..1) | `13: trip_daily_budget_norm` | Daily budget / 500 |
| `2: user_interest_food` | Stated dining preference (0..1) | `14: trip_pace_index` | Pace setting (0, 0.5, 1) |
| `3: user_interest_adventure` | Stated adventure preference (0..1) | `15: slot_day_progression` | Day index / total days |
| `4: user_interest_relaxation`| Stated relaxation preference (0..1) | `16: slot_is_morning` | Binary morning slot |
| `5: user_interest_shopping` | Stated shopping preference (0..1) | `17: slot_is_afternoon` | Binary afternoon slot |
| `6: user_interest_photography`| Photography interest flag (0/1) | `18: slot_is_evening` | Binary evening slot |
| `7: user_interest_architecture`| Architecture interest flag (0/1) | `19: activity_category_match`| Alignment with user goals |
| `8: user_pace_slider` | Pacing (0=relaxed, 1=fast) | `20: activity_physical_intensity`| Physical tier (0, 0.5, 1) |
| `9: user_crowd_tolerance` | Crowd avoidance (0=avoid, 1=ok) | `21: activity_crowd_level` | Typical density (0, 0.5, 1) |
| `10: user_budget_weight` | Budget tier index (0, 0.5, 1) | `22: activity_cost_norm` | Ticket fee / 100 |
| `11: user_walking_tolerance` | Walking limit (0, 0.5, 1) | `23: activity_proximity_bonus` | Geographic proximity |

### Rewards & State Updates
- **Explicit Accept:** $+1.0$ reward; updates $A_a \leftarrow A_a + x x^\top$, $b_a \leftarrow b_a + r x$.
- **Implicit Keep (Finalize):** $+0.2$ reward; updates policy for all un-rejected activities.
- **Explicit Reject:** $-1.0$ reward; updates policy and adds activity to itinerary exclusion mask.
- **Explicit Modify:** $-0.4$ penalty to original arm; replacement receives $+1.0$ if accepted.
- **Trip-Specific Exclusions:** If "Just for this trip" is flagged, status updates in `itinerary_activities`, but bandit $A$ and $b$ matrices are **not** updated, isolating local constraints from general preferences.
- **State Saved to DB:** `rl_user_policies` (serialized $A_a, b_a$, pull count, total reward) and `rl_feedback_log` (interaction events).
- **Evaluation:** Evaluated via Monte Carlo comparative simulation (`evaluation.py`, `evaluate.py`) across 3 personas and 150 rounds against a static baseline.

---

## 9. Data Architecture

- **Total Macro Destinations in `app/recommender.py`:** 20 destinations (16 India, 4 International).
- **Curated Activity Catalog in `app/activity_data.py`:** 84 curated activities across 14 destinations (Kyoto: 13, Agra: 6, Amritsar: 6, Jaipur: 6, Kerala: 6, Ladakh: 6, Manali: 5, Rishikesh: 6, South Goa: 6, Udaipur: 6, Varanasi: 6, Santorini: 4, Swiss Alps: 4, Tokyo: 4).
- **Destinations with ZERO Curated Activities in DB (6 destinations):** Hampi, Meghalaya, Darjeeling, Andaman Islands, Ooty & Coorg, Rann of Kutch.
- **Empty Activity Fallback:** When planning a trip to any of the 6 unseeded destinations, `itinerary_generator.py:96` catches the empty candidate set and synthesizes a single dummy activity (`Historic Walking Exploration of {destination}`) with hardcoded coordinates `(35.0, 135.0)` (Japan), repeating it across all slots and days.
- **Hard-Coded vs External:**
  - *Hard-coded:* Questionnaire schemas, scoring weights, destination metadata, and 84 attraction profiles.
  - *External APIs:* Open-Meteo (`api.open-meteo.com`) for weather; OpenStreetMap Nominatim and Overpass (`overpass-api.de`) for live POI searches.
  - *Cache Behavior:* There is no SQLite HTTP cache table (`api_cache` does not exist). External requests are executed live, falling back to local Python dictionaries upon timeout or connection failure.

---

## 10. Tests

- **Pytest Suite (`python -m pytest tests/ -q`):** 72 passed, 0 failed, 4 deprecation warnings in 67.44s.
  - `test_prep.py`: 16 passed (weather, packing rules, allergy overrides, reminder bandit).
  - `test_ranking.py`: 16 passed (weight normalization, circular season distance, budget filtering).
  - `test_live.py`: 13 passed (trip activation, checklists, alerts, replanning, post-trip feedback).
  - `test_timed_itinerary.py`: 7 passed (pacing schedules, database persistence).
  - `test_places.py`: 7 passed (destination schemas, OSM mocking, graceful offline fallback).
  - `test_places_api.py`: 6 passed (module registry, location geocoding, instant dynamic trips).
  - `test_trip_actions.py`: 5 passed (trip finalization, start activation, activity swap/delete).
  - `test_scaffold.py`: 2 passed (scaffold routes and test database isolation fixtures).
- **Monolithic Script (`python run_tests.py`):** 28 assertions passed (exit code 0).
- **Untested Important Behaviors:** IDOR authentication bypassing (`GET /api/profile/{victim_id}` lacks Bearer token checks); missing JavaScript function calls (`saveGoogleClientId`); schedule output for the 6 unseeded Indian destinations; offline rendering without CDN connectivity.

---

## 11. Scope Check

- **Pre-Trip (Complete & Operational):** Progressive onboarding (11-question basic survey, 83-question precision questionnaire), macro destination recommendations, shortlist bookmarks, trip creation (India-only validation), day-by-day LinUCB itinerary scheduling, interactive Accept/Reject/Modify feedback loop, Model Inspector, dynamic packing lists, weather forecasts, documents checklist, and reminder bandits.
- **Live Trip (Functional via Companion):** Housed in Companion "During & Post Trip" tab (`live.js`). Features trip activation (`is_started=1`), daily activity checkboxes (completed/skipped), simulated disruptions (rain, closures, transit strikes, crowds), disruption alerts with dismiss action, and targeted activity replanning. Disruption feeds are simulated rather than connected to live push telemetry.
- **Post-Trip (Functional via Companion):** Accessible upon trip completion (`is_completed=1`). Collects overall trip satisfaction (pacing, realism, budget accuracy) and individual activity ratings with a "Remember preference" toggle that directly updates persistent LinUCB bandit parameters in SQLite.

---

## 12. Documentation vs. Reality

| Document | Document Claim | Code Reality | Discrepancy Note |
| :--- | :--- | :--- | :--- |
| `README.md:14` | `git checkout feat/ranking-eval` | Active workspace branch is `feat/profile-api`. | Outdated Branch |
| `README.md:65` | "Arms ($|\mathcal{A}|=7$): canonical arms (`culture_history` ... `scenic`)" | `rl_planner.py` has 7 arms, but `app/database.py:198` schema comment lists only 6 (omits `scenic`). | Inconsistent Comment |
| `README.md:82`, `HANDOFF.md:27` | "Online Sherman-Morrison rank-1 updates ($O(d^2)$)" | `app/rl_planner.py:LinUCBPolicy.predict_score` computes `np.linalg.inv(A)` ($O(d^3)$ direct inversion) on every prediction call. | False Math Claim |
| `HANDOFF.md:7` | "All 32 automated test suites passing (`python run_tests.py` exit code 0)" | `run_tests.py` is a single monolithic script executing 28 assertion blocks, not 32 test suites. | Exaggerated Metric |
| `HANDOFF.md:19-33`| Claims "100% Complete" across all 15 scorecard subsystems | Passwords stored in plaintext, Google Client ID button throws JS ReferenceError, 6 destinations have zero activities, foreign keys disabled in SQLite. | Unverified Claim |
| `HANDOFF.md:4` | `C:\Users\ATHARV SOKHAL\.gemini\antigravity\scratch\rl_travel_guide` | Workspace path belongs to another user's machine from earlier collaboration. | Outdated Path |
| `HANDOFF.md:23` | "16 curated destinations" in `app/recommender.py` | `app/recommender.py` defines 20 destinations (16 Indian + 4 International). | Numerical Mismatch |
| `ATTRIBUTION.md:50`| "Static destination catalogue (16 destinations)" | `app/recommender.py` contains 20 destinations. | Numerical Mismatch |
| `README.md:57` | "Level 3 Precision expands state to 126 dimensions" | Precision profile vector has 126 dimensions, but `rl_planner.py` ignores it and only uses a 24-dimensional context vector. | Unconnected Vector |

---

## 13. Summary

### Works Well (15 Items)
1. **Pytest Test Suite:** All 72 automated unit and integration tests across 8 test files pass cleanly (100% pass rate).
2. **Monolithic Integration Test:** `python run_tests.py` executes 28 assertion blocks end-to-end with exit code 0.
3. **Contextual LinUCB Learning:** Disjoint linear bandit policy calculates UCB scores ($\alpha=0.5$) and updates parameters dynamically.
4. **Reward Attribution Separation:** Distinguishes between persistent preference updates and trip-specific rejections.
5. **Interactive Itinerary Feedback:** Seamless Accept (+1.0), Skip/Reject (-1.0 with reason), and Modify (-0.4 with 3 alternatives).
6. **Adaptive Regeneration:** Re-generates daily schedules while strictly excluding previously rejected activities.
7. **Basic Onboarding Flow:** 11-question, 3-step survey reliably extracts a 22-dimensional preference vector.
8. **Precision Questionnaire Engine:** 83 adaptive questions with conditional branching rules (`show_if`) and privacy filters.
9. **Seasonal Destination Ranking:** 6-component explainable scoring with circular season wrap-around distance and budget caps.
10. **Pre-Trip Packing & Reminders:** Dynamic packing checklists based on destination climate and Beta-Bernoulli reminder bandits.
11. **Live Trip Replanning:** Disruption simulation with indoor/nearby alternative replacements.
12. **Academic Model Inspector:** Navbar modal visualizes normalized state vectors, scoring weights, LinUCB arm weights, and logs.
13. **India-Only Travel Validation:** Backend and frontend consistently validate and enforce domestic Indian destinations.
14. **Geocoding & Places Lookup:** OpenStreetMap Nominatim/Overpass integration with local dictionary fallback.
15. **Plug-in Module Architecture:** Companion navbar button auto-discovers and dynamically loads sub-modules.

### Partly Works or is Rough (9 Items)
1. **Unused 126-Dimensional State Vector:** The rich 126-dim precision profile is computed and saved, but LinUCB uses a 24-dim context vector.
2. **Offline CDN Dependency:** App requires internet access on initial page load to fetch Tailwind CSS and FontAwesome from CDNs.
3. **Companion Modal Layout:** Companion features (Live trip, Prep, Ranking, Places) are rendered inside an overlay modal instead of dedicated views.
4. **Trip Day Rescheduling:** Activities can be swapped between days via the companion editor, but there is no drag-and-drop day re-ordering.
5. **Simulated Live Disruptions:** Weather, strikes, and closures in the Live Trip module are triggered by simulated clicks rather than real-time telemetry.
6. **Parallel Places Implementations:** `app/services/places_service.py` (1029 lines) and `app/modules/places_service.py` (358 lines) duplicate geocoding logic.
7. **Uncalled Backend Routes:** Endpoints such as `/api/places/popular`, `/api/trips/detail/{id}`, and `/api/config/options` have no UI calling them.
8. **Fixed Phone OTP:** Phone login accepts hardcoded `123456` without integrating a live SMS provider.
9. **Matrix Inversion Performance:** Docstring claims Sherman-Morrison rank-1 updates, but code performs explicit `np.linalg.inv` on each evaluation.

### Broken or Missing (6 Items)
1. **Missing JavaScript Event Handler:** Clicking "Save & Enable" in the Google OAuth Client ID modal throws `ReferenceError: saveGoogleClientId is not defined`.
2. **Missing Curated Activities for 6 Indian Destinations:** Hampi, Meghalaya, Darjeeling, Andaman, Ooty, and Kutch have zero curated attractions and fall back to repeating a single dummy Kyoto coordinate activity.
3. **Broken Authorization / IDOR:** API endpoints (`/api/profile/{id}`, `/api/trips/{id}`) accept unauthenticated requests and leak user data without Bearer token validation.
4. **Disabled SQLite Foreign Key Enforcement:** `PRAGMA foreign_keys` is OFF by default in SQLite connections, permitting orphan rows upon user deletion.
5. **Plaintext Password Storage:** User passwords submitted via email authentication are stored directly in SQLite without hashing in older records or with basic hashing lacking salt.
6. **Unused Database Tables:** `ranking_audit_log` records rows on every ranking request, but no interface or endpoint ever reads from it.
