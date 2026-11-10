# Frontend-Backend Connection Check Report

This report documents the actual connection matrix between frontend UI files (`static/app.js`, `static/index.html`, and `static/modules/*.js`) and the backend API routes, superseding the erroneous preliminary audit table.

## Executive Summary
- **Total Backend Endpoints (FastAPI OpenAPI):** 52
- **Actively Connected in UI:** 43 (82.7%)
- **True Backend Orphans (No UI calls):** 9 (17.3%)
- **Conjectured/Non-existent Routes from Audit:** 8 paths investigated and confirmed not present in backend router.

---

## 1. True Backend Orphans (No UI Calls)

The following 9 backend routes exist in FastAPI but currently have no caller in `static/`:

| Endpoint | HTTP Method | Backend File | Owner | Description / Note |
|---|---|---|---|---|
| `/api/config/options` | GET | `app/api.py` | Karan | Legacy basic options bank. Superseded by `/api/config/questionnaire`. |
| `/api/config/detailed-options` | GET | `app/api.py` | Karan | Legacy detailed options. Superseded by `/api/config/precision-questionnaire`. |
| `/api/trips/detail/{trip_id}` | GET | `app/api.py` | Karan | Single trip detail endpoint. Frontend caches trip state client-side from `GET /api/trips/{user_id}` and `GET /api/itinerary/{trip_id}`. |
| `/api/evaluation/live/{user_id}` | GET | `app/evaluation.py` / `app/api.py` | Atharva | Real-time simulation metrics evaluator. Used in test suite (`run_tests.py`); frontend Academic Inspector queries `/api/rl/policy` and `/api/rl/state`. |
| `/api/places/popular` | GET | `app/modules/places.py` | Atharva | Pre-packaged popular Indian destinations. UI uses recommender destinations and `/api/places/search`. |
| `/api/prep/{trip_id}/reminders/generate` | POST | `app/modules/prep.py` | Atharva | Server-side trigger to generate prep reminders. Reminders are fetched via `GET /api/prep/{trip_id}/reminders`. |
| `/api/itinerary/timed/generate/{trip_id}` | POST | `app/modules/trip_actions.py` | Atharva | Alternative timed generator endpoint. UI calls `/api/itinerary/generate/{trip_id}`. |
| `/api/itinerary/timed/{trip_id}/alternatives/{activity_id}` | GET | `app/modules/trip_actions.py` | Atharva | Timed alternatives lookup. UI calls `/api/itinerary/alternatives/{itinerary_id}/{activity_id}`. |
| `/api/live/module-info` | GET | `app/modules/live.py` | Atharva | Static module metadata. UI dynamically discovers modules through `GET /api/modules`. |

---

## 2. Conjectured / Non-Existent Routes Investigated

The following paths were listed in early audit notes but **do not exist in the backend routing table**:
- `/api/companion/status/{user_id}` — Not defined in backend.
- `/api/places/live-search` — Not defined in backend (live search is `/api/places/search`).
- `/api/country/info` — Not defined in backend.
- `/api/template/{trip_id}` — Not defined in backend.
- `/destinations/india` & `/api/destinations/india` — Not defined in backend.
- `/places/live/{id}` & `/api/places/live/{id}` — Not defined in backend.
- `/itinerary/timed/*` without `/api` prefix — Not defined in backend.

---

## 3. Verified Active Connections (43 Endpoints)

| Backend Route | HTTP Method | Calling UI File & Line | UI Context |
|---|---|---|---|
| `/api/auth` | POST | `static/app.js:239` | Email, password, phone, guest authentication |
| `/api/auth/google-token` | POST | `static/app.js:280` | Official Google GIS token verification |
| `/api/config/google` | GET / POST | `static/app.js:272`, `app.js:316`, `app.js:466` | Google OAuth Client ID read & setup modal |
| `/api/config/questionnaire` | GET | `static/app.js:163` | 10-section basic onboarding questionnaire bank |
| `/api/config/precision-questionnaire` | GET | `static/app.js:1252` | Unified Personal Profile precision questions bank |
| `/api/profile/{user_id}` | GET / POST | `static/app.js:743`, `app.js:764` | Save and load basic traveller profile |
| `/api/profile/detailed/{user_id}` | GET / POST | `static/app.js:899`, `app.js:1560` | Detailed profile avoidances and past trips |
| `/api/profile/precision/{user_id}` | GET / POST | `static/app.js:826`, `app.js:1256`, `app.js:1544` | Load, save, and check Unified Personal Profile |
| `/api/recommendations/{user_id}` | GET | `static/app.js:949` | Recommendations grid (Recommended, Trending, Seasonal) |
| `/api/shortlist/{user_id}` | GET / POST | `static/app.js:1164` | Destination shortlist bookmarking toggle |
| `/api/trips/{user_id}` | GET / POST | `static/app.js:1740`, `app.js:1826` | Plan trip modal submit & user trip listing |
| `/api/itinerary/{trip_id}` | GET | `static/app.js:1876` | Retrieve saved itinerary for active trip |
| `/api/itinerary/generate/{trip_id}` | POST | `static/app.js:1853`, `app.js:1882`, `app.js:2137` | LinUCB itinerary generation & regeneration |
| `/api/itinerary/alternatives/{itinerary_id}/{activity_id}` | GET | `static/app.js:2076` | Slot alternative candidates for Modify modal |
| `/api/itinerary/feedback/{user_id}` | POST | `static/app.js:2017`, `app.js:2047`, `app.js:2113` | Accept, Reject, and Modify LinUCB feedback |
| `/api/rl/state/{user_id}` | GET | `static/app.js:1608` | Academic Inspector preference vector badge & breakdown |
| `/api/rl/policy/{user_id}` | GET | `static/app.js:1631` | Academic Inspector LinUCB arm parameters & pull counts |
| `/api/evaluation/benchmark` | GET | `static/app.js:1709` | Academic Inspector LinUCB vs Baseline benchmark chart |
| `/api/modules` | GET | `static/modules/loader.js:32` | Companion modular tabs dynamic discovery |
| `/api/places/search` | GET | `static/modules/places.js:48` | Real-time Indian location geocoding & autocomplete |
| `/api/places/attractions` | GET | `static/modules/places.js:84` | Real-time live attraction lookup for city |
| `/api/places/plan-trip` | POST | `static/modules/places.js:132` | Dynamic end-to-end trip creation from Places API |
| `/api/prep/{trip_id}/weather` | GET | `static/modules/prep.js:56` | Pre-trip weather forecast card |
| `/api/prep/{trip_id}/packing` | GET | `static/modules/prep.js:84` | Pre-trip packing checklist categorized by profile |
| `/api/prep/{trip_id}/documents` | GET | `static/modules/prep.js:112` | Pre-trip visa/identity documents guidance |
| `/api/prep/{trip_id}/reminders` | GET | `static/modules/prep.js:140` | Pre-trip actionable reminder checklist |
| `/api/prep/{trip_id}/reminders/{reminder_id}/feedback` | POST | `static/modules/prep.js:172` | Pre-trip reminder completion toggle |
| `/api/live/{trip_id}/state` | GET | `static/modules/live.js:98` | Live companion active itinerary state & current step |
| `/api/live/{trip_id}/today` | GET | `static/modules/live.js:112` | Live trip today's scheduled activities |
| `/api/live/{trip_id}/alerts` | GET | `static/modules/live.js:126` | Real-time delay, weather, and crowd alerts |
| `/api/live/{trip_id}/activity/{activity_id}/status` | POST | `static/modules/live.js:178` | Mark live activity arrived/done/skipped |
| `/api/live/{trip_id}/alerts/{alert_id}/dismiss` | POST | `static/modules/live.js:220` | Dismiss live notification alert |
| `/api/live/{trip_id}/complete` | POST | `static/modules/live.js:256` | Complete trip and trigger post-trip feedback |
| `/api/live/{trip_id}/postrip` | GET / POST | `static/modules/live.js:283` | Post-trip questionnaire submission & retrieval |
| `/api/live/{user_id}/learning-summary` | GET | `static/modules/live.js:298` | Post-trip policy update learning summary |
| `/api/live/{trip_id}/replan` | GET / POST | `static/modules/live.js:358` | Live in-trip LinUCB dynamic replanning |
| `/api/live/{trip_id}/simulate` | POST | `static/modules/live.js:380` | Live trip event simulator (delay, rain, crowd) |
| `/api/ranking/{user_id}` | GET | `static/modules/ranking.js:46` | Multi-criteria destination ranking breakdown |
| `/api/trip-actions/{trip_id}/timed-view` | GET | `static/modules/itinerary_editor.js:52` | Timed hour-by-hour itinerary schedule view |
| `/api/trip-actions/{trip_id}/activity/{activity_id}` | DELETE | `static/modules/itinerary_editor.js:85` | Remove activity slot from itinerary editor |
| `/api/trip-actions/{trip_id}/activity/{activity_id}/swap` | POST | `static/modules/itinerary_editor.js:114` | Swap two activities in itinerary editor |
| `/api/trip-actions/{trip_id}/finalize` | POST | `static/modules/itinerary_editor.js:142` | Lock in finalized itinerary |
| `/api/trip-actions/{trip_id}/start` | POST | `static/modules/itinerary_editor.js:160` | Launch live trip guide from finalized itinerary |
