# Comprehensive Project Audit: RL-Based Proactive Travel Guide

**Auditor Role:** Senior QA Engineer, Security Reviewer & UX Auditor
**Date:** November 2026 | **Target:** FastAPI + SQLite + Vanilla JS Web Application
**Database State:** Fresh initialization (tested from deleted `travel_guide.db`)

---
## Section 0: Executive Summary

### Finding Totals by Severity
- **Critical:** 4
- **High:** 7
- **Medium:** 4
- **Low:** 2
- **Total Identified Findings:** 17

### Finding Totals by Area
- **Security:** 5
- **Tests:** 3
- **Docs:** 2
- **Data:** 1
- **API:** 1
- **UI:** 1
- **Performance:** 1
- **Accessibility:** 1
- **UX:** 1
- **RL:** 1

### Top 10 Critical & Worst Problems
1. **[Critical] Broken Access Control: No Bearer Token Validation on User Endpoints (IDOR)** (`app/api.py:455,541,614`): Endpoints return 200 OK and leak full traveller profiles, trips, and schedules to any unauthenticated caller.
2. **[Critical] Potential SQL Injection via F-string in common.py** (`app\modules\common.py:28`): Query constructed using dynamic Python string formatting: r = conn.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)).fetchone()
3. **[Critical] Plaintext Passwords Stored Directly in SQLite Database** (`app/database.py:16, app/api.py:165`): Database stores raw plaintext string 'secret123' without salt or hashing.
4. **[Critical] Hardcoded Phone OTP '123456' Permits Authentication Bypass for Any Phone Number** (`app/api.py:151`): Any phone account is instantly authenticated or created by submitting fixed string '123456'.
5. **[High] SQLite Foreign Key Constraints Disabled By Default** (`app/database.py:27`): PRAGMA foreign_keys is 0 (OFF). Deleting a user leaves orphan trips, itineraries, feedback, and precision profiles.
6. **[High] International Destination Fails to Return 400 When User Does Not Exist First** (`app/api.py:create_trip`): Returned status 404 ('{"detail":"User not found"}') because user check happens before destination check.
7. **[High] Missing Event Handler 'saveGoogleClientId' referenced in HTML** (`static/index.html`): Browser throws `ReferenceError: saveGoogleClientId is not defined`.
8. **[High] Widespread Unescaped innerHTML Templating (68 instances)** (`static/app.js`): 68 instances of direct innerHTML template literal interpolation without HTML escaping.
9. **[High] run_tests.py Mixes Assertions (141) with Informational Prints (35) and Crashes on Line 81** (`run_tests.py:81`): run_tests.py crashes on line 81 with AssertionError because profile endpoint requires mandatory travel_goals and place_interests.
10. **[High] Unreadable '[object Object]' Error Alert Displayed on 422 Profile Validation Rejection** (`static/app.js:235, app/api.py:465`): Browser displays alert dialog containing: `Error: [object Object],[object Object],[object Object],[object Object],[object Object]`.

---
## Section 1: Audit Environment & Methodology
- **Platform:** Windows 11, Python 3.11.9, SQLite 3.45+, Node.js v20+, Chrome (Chromium Playwright).
- **Test Harnesses:**
  1. Clean database state initialized via `rm travel_guide.db && python main.py`.
  2. Pytest suite executed against all 8 test modules (`pytest tests/`).
  3. Custom test harness executed via `python run_tests.py`.
  4. Full browser automation driving UI through Playwright across 1366px, 768px, and 360px viewports with dialog, console, and network listeners.
  5. Fuzzing of all FastAPI endpoints via TestClient.
  6. 100-seed comparative LinUCB vs Baseline Monte Carlo simulation.

---
## Section 2: Detailed Findings Table

| ID | Severity | Area | Title | Location | Status | Effort | Files Affected |
|---|---|---|---|---|---|---|---|
| F-001 | **Critical** | Security | Broken Access Control: No Bearer Token Validation on User Endpoints (IDOR) | `app/api.py:455,541,614` | VERIFIED | L | `app/api.py, app/modules/*.py` |
| F-002 | **High** | Data | SQLite Foreign Key Constraints Disabled By Default | `app/database.py:27` | VERIFIED | S | `app/database.py` |
| F-003 | **Critical** | Security | Potential SQL Injection via F-string in common.py | `app\modules\common.py:28` | VERIFIED | S | `app\modules\common.py` |
| F-004 | **High** | API | International Destination Fails to Return 400 When User Does Not Exist First | `app/api.py:create_trip` | VERIFIED | S | `app/api.py` |
| F-005 | **High** | UI | Missing Event Handler 'saveGoogleClientId' referenced in HTML | `static/index.html` | VERIFIED | S | `static/index.html, static/app.js` |
| F-006 | **High** | Security | Widespread Unescaped innerHTML Templating (68 instances) | `static/app.js` | VERIFIED | M | `static/app.js` |
| F-007 | **Medium** | Performance | Hard External CDN Dependencies Break Offline / Airgapped Usage | `static/index.html:7-14` | VERIFIED | M | `static/index.html` |
| F-008 | **Medium** | Accessibility | Modals Cannot Be Closed With Keyboard 'Escape' Key | `static/app.js` | VERIFIED | S | `static/app.js` |
| F-009 | **Low** | Docs | Unverifiable '100% complete' Claims in Documentation | `README.md / HANDOFF.md` | VERIFIED | S | `README.md, HANDOFF.md` |
| F-010 | **High** | Tests | run_tests.py Mixes Assertions (141) with Informational Prints (35) and Crashes on Line 81 | `run_tests.py:81` | VERIFIED | S | `run_tests.py` |
| F-011 | **Medium** | Tests | Lack of Negative and Boundary Tests for Input Validation and Auth | `tests/` | VERIFIED | M | `tests/` |
| F-012 | **Critical** | Security | Plaintext Passwords Stored Directly in SQLite Database | `app/database.py:16, app/api.py:165` | VERIFIED | M | `app/database.py, app/api.py` |
| F-013 | **Critical** | Security | Hardcoded Phone OTP '123456' Permits Authentication Bypass for Any Phone Number | `app/api.py:151` | VERIFIED | M | `app/api.py` |
| F-014 | **High** | UX | Unreadable '[object Object]' Error Alert Displayed on 422 Profile Validation Rejection | `static/app.js:235, app/api.py:465` | VERIFIED | S | `static/app.js` |
| F-015 | **High** | Tests | Pytest Suite Fails 3 Tests Due to Module Registry Filtering and Destination Order | `tests/test_places_api.py:15, tests/test_ranking.py:22, tests/test_trip_india_validation.py:77` | VERIFIED | M | `app/modules/__init__.py, app/api.py, tests/` |
| F-016 | **Medium** | RL | Empirical 100-Seed Benchmark Proves Static Baseline Outperforms LinUCB Over 20 Rounds | `app/evaluation.py:run_comparative_simulation` | VERIFIED | M | `app/evaluation.py, app/rl_planner.py` |
| F-017 | **Low** | Docs | Sherman-Morrison Inversion Claimed in Docstrings But np.linalg.inv O(d^3) Executed | `app/rl_planner.py:LinUCBPolicy.update` | VERIFIED | S | `app/rl_planner.py` |

### Detailed Finding Specifications

#### [F-001] Broken Access Control: No Bearer Token Validation on User Endpoints (IDOR)
- **Severity:** Critical | **Area:** Security | **Status:** VERIFIED | **Estimated Effort:** L
- **Location:** `app/api.py:455,541,614`
- **Files to Change:** `app/api.py, app/modules/*.py`
- **Steps to Reproduce:** Call GET /api/profile/{victim_user_id} or GET /api/trips/{victim_user_id} without any Authorization header.
- **Expected Behavior:** Requests should be rejected with 401 Unauthorized if Bearer token is missing or invalid, and 403 Forbidden if requesting another user's data.
- **Actual Observed Behavior:** Endpoints return 200 OK and leak full traveller profiles, trips, and schedules to any unauthenticated caller.
- **Evidence:** curl -s http://localhost:8000/api/profile/<any-id> returns data without requiring tokens.
- **Suggested Remediation:** Add FastAPI security dependency `Depends(get_current_user)` enforcing JWT/session tokens.

#### [F-002] SQLite Foreign Key Constraints Disabled By Default
- **Severity:** High | **Area:** Data | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `app/database.py:27`
- **Files to Change:** `app/database.py`
- **Steps to Reproduce:** Execute PRAGMA foreign_keys in database connection.
- **Expected Behavior:** PRAGMA foreign_keys should be ON to enforce relational integrity.
- **Actual Observed Behavior:** PRAGMA foreign_keys is 0 (OFF). Deleting a user leaves orphan trips, itineraries, feedback, and precision profiles.
- **Evidence:** Query returned: PRAGMA foreign_keys = 0
- **Suggested Remediation:** Add `conn.execute('PRAGMA foreign_keys = ON')` in database connection factory.

#### [F-003] Potential SQL Injection via F-string in common.py
- **Severity:** Critical | **Area:** Security | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `app\modules\common.py:28`
- **Files to Change:** `app\modules\common.py`
- **Steps to Reproduce:** Inspect line 28 in app\modules\common.py.
- **Expected Behavior:** All SQL queries must use parameterized query placeholders (?).
- **Actual Observed Behavior:** Query constructed using dynamic Python string formatting: r = conn.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)).fetchone()
- **Evidence:** Found pattern: r = conn.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)).fetchone()
- **Suggested Remediation:** Replace string interpolation with parameterized queries.

#### [F-004] International Destination Fails to Return 400 When User Does Not Exist First
- **Severity:** High | **Area:** API | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `app/api.py:create_trip`
- **Files to Change:** `app/api.py`
- **Steps to Reproduce:** POST /api/trips/non_existent_user with international destination.
- **Expected Behavior:** Should return 400 Bad Request indicating destination is not permitted in India-only scope.
- **Actual Observed Behavior:** Returned status 404 ('{"detail":"User not found"}') because user check happens before destination check.
- **Evidence:** Response: {"detail":"User not found"}
- **Suggested Remediation:** Validate destination_id before checking user existence.

#### [F-005] Missing Event Handler 'saveGoogleClientId' referenced in HTML
- **Severity:** High | **Area:** UI | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `static/index.html`
- **Files to Change:** `static/index.html, static/app.js`
- **Steps to Reproduce:** Click element with handler `saveGoogleClientId()`.
- **Expected Behavior:** Function `saveGoogleClientId` should be defined and execute expected action.
- **Actual Observed Behavior:** Browser throws `ReferenceError: saveGoogleClientId is not defined`.
- **Evidence:** HTML line contains `saveGoogleClientId()` but `saveGoogleClientId` is nowhere in static/app.js.
- **Suggested Remediation:** Define `saveGoogleClientId` in static/app.js or remove dead HTML attribute.

#### [F-006] Widespread Unescaped innerHTML Templating (68 instances)
- **Severity:** High | **Area:** Security | **Status:** VERIFIED | **Estimated Effort:** M
- **Location:** `static/app.js`
- **Files to Change:** `static/app.js`
- **Steps to Reproduce:** Inject `<img src=x onerror=alert(1)>` into user display_name or activity title.
- **Expected Behavior:** Data inserted into DOM should be sanitized or set via textContent.
- **Actual Observed Behavior:** 68 instances of direct innerHTML template literal interpolation without HTML escaping.
- **Evidence:** Examples: `container.innerHTML = ... ${activity.title} ...`
- **Suggested Remediation:** Use safe templating function that escapes HTML entities (&, <, >, ", ').

#### [F-007] Hard External CDN Dependencies Break Offline / Airgapped Usage
- **Severity:** Medium | **Area:** Performance | **Status:** VERIFIED | **Estimated Effort:** M
- **Location:** `static/index.html:7-14`
- **Files to Change:** `static/index.html`
- **Steps to Reproduce:** Disconnect network and load http://localhost:8000.
- **Expected Behavior:** App styling, icons, and fonts should remain functional offline.
- **Actual Observed Behavior:** Tailwind CSS, FontAwesome, Righteous/Poppins Google Fonts, and Google GIS are loaded from external CDNs (tailwindcss.com, cdnjs, fonts.googleapis.com, accounts.google.com).
- **Evidence:** External CDNs detected: console.cloud.google.com, cdnjs.cloudflare.com, fonts.googleapis.com">
  <link rel="preconnect" href="https:, cdn.tailwindcss.com"><, localhost:8000<, 127.0.0.1:8000<, fonts.googleapis.com, accounts.google.com
- **Suggested Remediation:** Bundle Tailwind CSS and FontAwesome locally in static/vendor.

#### [F-008] Modals Cannot Be Closed With Keyboard 'Escape' Key
- **Severity:** Medium | **Area:** Accessibility | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `static/app.js`
- **Files to Change:** `static/app.js`
- **Steps to Reproduce:** Open any modal (Model Inspector, Plan Trip, Reject Activity) and press ESC key.
- **Expected Behavior:** Modal should dismiss when ESC key is pressed.
- **Actual Observed Behavior:** No keydown listener for Escape key exists in app.js; user is trapped unless clicking the close button.
- **Evidence:** Code search for 'Escape' in app.js yielded 0 matches.
- **Suggested Remediation:** Add global window.addEventListener('keydown', (e) => { if(e.key === 'Escape') closeOpenModals(); }).

#### [F-009] Unverifiable '100% complete' Claims in Documentation
- **Severity:** Low | **Area:** Docs | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `README.md / HANDOFF.md`
- **Files to Change:** `README.md, HANDOFF.md`
- **Steps to Reproduce:** Search for '100%' claims in documentation.
- **Expected Behavior:** Documentation should accurately delineate completed modules from experimental or prototype features.
- **Actual Observed Behavior:** Documentation states '100% complete' despite known test failures, broken handler, and missing auth protection.
- **Evidence:** Docs claim 100% completion.
- **Suggested Remediation:** Replace blanket completion claims with a verified capability matrix.

#### [F-010] run_tests.py Mixes Assertions (141) with Informational Prints (35) and Crashes on Line 81
- **Severity:** High | **Area:** Tests | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `run_tests.py:81`
- **Files to Change:** `run_tests.py`
- **Steps to Reproduce:** Execute `python run_tests.py` from clean environment.
- **Expected Behavior:** run_tests.py should execute all test blocks and exit with 0.
- **Actual Observed Behavior:** run_tests.py crashes on line 81 with AssertionError because profile endpoint requires mandatory travel_goals and place_interests.
- **Evidence:** Line 81: assert p_res.status_code == 200 (actual was 422)
- **Suggested Remediation:** Update test payload on line 76 to include mandatory fields `travel_goals` and `place_interests`.

#### [F-011] Lack of Negative and Boundary Tests for Input Validation and Auth
- **Severity:** Medium | **Area:** Tests | **Status:** VERIFIED | **Estimated Effort:** M
- **Location:** `tests/`
- **Files to Change:** `tests/`
- **Steps to Reproduce:** Inspect existing tests in tests/ directory.
- **Expected Behavior:** Test suite should cover negative cases: invalid tokens, wrong types, missing required fields, SQL special characters, cross-tenant access.
- **Actual Observed Behavior:** Almost all existing tests only execute happy paths with valid mock data.
- **Evidence:** No tests verify 401 Unauthorized or 403 Forbidden on profile/trips endpoints.
- **Suggested Remediation:** Add comprehensive test file `test_security_and_validation.py` covering all error paths.

#### [F-012] Plaintext Passwords Stored Directly in SQLite Database
- **Severity:** Critical | **Area:** Security | **Status:** VERIFIED | **Estimated Effort:** M
- **Location:** `app/database.py:16, app/api.py:165`
- **Files to Change:** `app/database.py, app/api.py`
- **Steps to Reproduce:** Register a new user via POST /api/auth with provider='email', password='secret123'. Inspect database: `SELECT password FROM users WHERE identifier='...'`.
- **Expected Behavior:** Passwords should be securely hashed using salted bcrypt, argon2, or PBKDF2.
- **Actual Observed Behavior:** Database stores raw plaintext string 'secret123' without salt or hashing.
- **Evidence:** travel_guide.db users table contains unhashed password column; app/database.py: `password TEXT`.
- **Suggested Remediation:** Integrate bcrypt/passlib to hash password upon registration and verify during login.

#### [F-013] Hardcoded Phone OTP '123456' Permits Authentication Bypass for Any Phone Number
- **Severity:** Critical | **Area:** Security | **Status:** VERIFIED | **Estimated Effort:** M
- **Location:** `app/api.py:151`
- **Files to Change:** `app/api.py`
- **Steps to Reproduce:** Send POST /api/auth with provider='phone', identifier='9999999999', otp='123456'.
- **Expected Behavior:** Server should generate cryptographically secure random OTP with 5-minute expiry and rate-limiting.
- **Actual Observed Behavior:** Any phone account is instantly authenticated or created by submitting fixed string '123456'.
- **Evidence:** app/api.py line 151: `if payload.otp and payload.otp.strip() == '123456':`.
- **Suggested Remediation:** Implement proper OTP cache with random generation, attempt limits, and SMS gateway integration.

#### [F-014] Unreadable '[object Object]' Error Alert Displayed on 422 Profile Validation Rejection
- **Severity:** High | **Area:** UX | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `static/app.js:235, app/api.py:465`
- **Files to Change:** `static/app.js`
- **Steps to Reproduce:** Sign in as fresh user, leave mandatory fields unselected, and submit basic profile onboarding form.
- **Expected Behavior:** A clear, descriptive validation message listing missing questions.
- **Actual Observed Behavior:** Browser displays alert dialog containing: `Error: [object Object],[object Object],[object Object],[object Object],[object Object]`.
- **Evidence:** Playwright alert log in AUDIT_EVIDENCE/dialog_logs.json; app.js `throw new Error(data.detail)`.
- **Suggested Remediation:** Parse `data.detail.missing` array and format missing questions into human-readable list.

#### [F-015] Pytest Suite Fails 3 Tests Due to Module Registry Filtering and Destination Order
- **Severity:** High | **Area:** Tests | **Status:** VERIFIED | **Estimated Effort:** M
- **Location:** `tests/test_places_api.py:15, tests/test_ranking.py:22, tests/test_trip_india_validation.py:77`
- **Files to Change:** `app/modules/__init__.py, app/api.py, tests/`
- **Steps to Reproduce:** Execute `python -m pytest tests/`.
- **Expected Behavior:** All unit and integration tests in `tests/` pass with exit code 0.
- **Actual Observed Behavior:** 3 tests fail: `test_places_module_registered` and `test_module_registered` fail because `GET /api/modules` intentionally filtered them out; `test_international_destination_rejection` fails with 404 instead of 400.
- **Evidence:** AUDIT_EVIDENCE/pytest.log: short test summary shows 3 failed, 76 passed, 4 warnings in 212.98s.
- **Suggested Remediation:** Reconcile test expectations with module visibility architecture and adjust destination validation precedence.

#### [F-016] Empirical 100-Seed Benchmark Proves Static Baseline Outperforms LinUCB Over 20 Rounds
- **Severity:** Medium | **Area:** RL | **Status:** VERIFIED | **Estimated Effort:** M
- **Location:** `app/evaluation.py:run_comparative_simulation`
- **Files to Change:** `app/evaluation.py, app/rl_planner.py`
- **Steps to Reproduce:** Run `app/evaluation.py:run_comparative_simulation` over 100 random seeds.
- **Expected Behavior:** LinUCB should demonstrate superior or equal cumulative reward compared to baseline.
- **Actual Observed Behavior:** LinUCB cumulative reward is 9.1800 +/- 0.8285 vs Static Baseline of 11.9000 +/- 0.6435 (95% CI). Baseline wins due to short horizon and exploration penalties.
- **Evidence:** AUDIT_EVIDENCE/benchmark_100_seeds.json: LinUCB mean 9.18 vs Baseline mean 11.90 across 100 seeds.
- **Suggested Remediation:** Warm-start LinUCB prior matrix b with user stated preferences or evaluate over longer horizons (T>=50).

#### [F-017] Sherman-Morrison Inversion Claimed in Docstrings But np.linalg.inv O(d^3) Executed
- **Severity:** Low | **Area:** Docs | **Status:** VERIFIED | **Estimated Effort:** S
- **Location:** `app/rl_planner.py:LinUCBPolicy.update`
- **Files to Change:** `app/rl_planner.py`
- **Steps to Reproduce:** Read docstring and implementation in `app/rl_planner.py`.
- **Expected Behavior:** Code should match docstring claim of maintaining covariance inverse incrementally via Sherman-Morrison rank-1 updates.
- **Actual Observed Behavior:** Update method only does `A += x x^T` and `predict_score` performs full `np.linalg.inv(A)` at O(d^3).
- **Evidence:** Docstring: 'using closed-form Sherman-Morrison update'; Code: `A_inv = np.linalg.inv(A)`.
- **Suggested Remediation:** Implement incremental Sherman-Morrison inverse update or correct docstring.

---
## Section 3: Frontend-Backend Connection Matrix

| Route Method | Route Path | Defined in Backend | Called by Frontend | Status | Notes |
|---|---|---|---|---|---|
| GET | `/api/config/questionnaire` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/config/options` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/config/detailed-options` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| POST | `/api/auth` | `api.py` | Yes | **Connected** | Active in app.js |
| POST | `/api/auth/google-token` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/config/google` | `api.py` | Yes | **Connected** | Active in app.js |
| POST | `/api/config/google` | `api.py` | Yes | **Connected** | Active in app.js |
| POST | `/api/profile/{user_id}` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/profile/{user_id}` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/profile/{user_id}/status` | `api.py` | Yes | **Connected** | Active in app.js |
| POST | `/api/profile/detailed/{user_id}` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/profile/detailed/{user_id}` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/rl/state/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/recommendations/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| POST | `/api/shortlist/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/shortlist/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/config/precision-questionnaire` | `api.py` | Yes | **Connected** | Active in app.js |
| POST | `/api/profile/precision/{user_id}` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/profile/precision/{user_id}` | `api.py` | Yes | **Connected** | Active in app.js |
| POST | `/api/trips/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/trips/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/trips/detail/{trip_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| POST | `/api/itinerary/generate/{trip_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/itinerary/{trip_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| POST | `/api/itinerary/feedback/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/itinerary/alternatives/{itinerary_id}/{activity_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/rl/policy/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/evaluation/benchmark` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/evaluation/live/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/companion/status/{user_id}` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/geo/search` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/weather/live` | `api.py` | Yes | **Connected** | Active in app.js |
| GET | `/api/places/live-search` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/country/info` | `api.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/live/module-info` | `live.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/live/{trip_id}/state` | `live.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/live/{trip_id}/today` | `live.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| POST | `/api/live/{trip_id}/activity/{activity_id}/status` | `live.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| POST | `/api/live/{trip_id}/simulate` | `live.py` | No | **Not Connected** | Backend endpoint uncalled by UI |
| GET | `/api/live/{trip_id}/alerts` | `live.py` | No | **Not Connected** | Backend endpoint uncalled by UI |

*(Remaining 34 module/service endpoints are cataloged in `AUDIT_EVIDENCE/connection_matrix.json`)*

---
## Section 4: Features Partially Implemented or Unreachable
1. **Google Cloud Client ID Customization (`#googleConfigModal`):** UI contains modal with Client ID input, but 'Save & Enable' button triggers missing handler `saveGoogleClientId()`, throwing a ReferenceError.
2. **Module Registry Tabs (`/api/modules`):** Module registration is implemented, but `places` and `ranking` are explicitly excluded from `GET /api/modules` to hide standalone tabs, breaking automated tests.
3. **LinUCB Continuous Policy Learning:** Policy update endpoint exists (`POST /api/rl/feedback`), but accepts/skips in itinerary UI only partially serialize full state context back to SQLite storage.
4. **Offline Mode & Caching:** Open-Meteo and Overpass feature SQLite caching, but external CDN CSS/JS (Tailwind, FontAwesome, Righteous) fail completely if loaded without internet connection.

---
## Section 5: Findings Grouped by File (Work Allocation)

### File: `app/api.py`
**Total Findings in File:** 5
- **[F-001] [Critical]** Broken Access Control: No Bearer Token Validation on User Endpoints (IDOR) (Effort: L)
- **[F-004] [High]** International Destination Fails to Return 400 When User Does Not Exist First (Effort: S)
- **[F-012] [Critical]** Plaintext Passwords Stored Directly in SQLite Database (Effort: M)
- **[F-013] [Critical]** Hardcoded Phone OTP '123456' Permits Authentication Bypass for Any Phone Number (Effort: M)
- **[F-015] [High]** Pytest Suite Fails 3 Tests Due to Module Registry Filtering and Destination Order (Effort: M)

### File: `static/app.js`
**Total Findings in File:** 4
- **[F-005] [High]** Missing Event Handler 'saveGoogleClientId' referenced in HTML (Effort: S)
- **[F-006] [High]** Widespread Unescaped innerHTML Templating (68 instances) (Effort: M)
- **[F-008] [Medium]** Modals Cannot Be Closed With Keyboard 'Escape' Key (Effort: S)
- **[F-014] [High]** Unreadable '[object Object]' Error Alert Displayed on 422 Profile Validation Rejection (Effort: S)

### File: `app/database.py`
**Total Findings in File:** 2
- **[F-002] [High]** SQLite Foreign Key Constraints Disabled By Default (Effort: S)
- **[F-012] [Critical]** Plaintext Passwords Stored Directly in SQLite Database (Effort: M)

### File: `static/index.html`
**Total Findings in File:** 2
- **[F-005] [High]** Missing Event Handler 'saveGoogleClientId' referenced in HTML (Effort: S)
- **[F-007] [Medium]** Hard External CDN Dependencies Break Offline / Airgapped Usage (Effort: M)

### File: `tests/`
**Total Findings in File:** 2
- **[F-011] [Medium]** Lack of Negative and Boundary Tests for Input Validation and Auth (Effort: M)
- **[F-015] [High]** Pytest Suite Fails 3 Tests Due to Module Registry Filtering and Destination Order (Effort: M)

### File: `app/rl_planner.py`
**Total Findings in File:** 2
- **[F-016] [Medium]** Empirical 100-Seed Benchmark Proves Static Baseline Outperforms LinUCB Over 20 Rounds (Effort: M)
- **[F-017] [Low]** Sherman-Morrison Inversion Claimed in Docstrings But np.linalg.inv O(d^3) Executed (Effort: S)

### File: `app/modules/*.py`
**Total Findings in File:** 1
- **[F-001] [Critical]** Broken Access Control: No Bearer Token Validation on User Endpoints (IDOR) (Effort: L)

### File: `app\modules\common.py`
**Total Findings in File:** 1
- **[F-003] [Critical]** Potential SQL Injection via F-string in common.py (Effort: S)

### File: `README.md`
**Total Findings in File:** 1
- **[F-009] [Low]** Unverifiable '100% complete' Claims in Documentation (Effort: S)

### File: `HANDOFF.md`
**Total Findings in File:** 1
- **[F-009] [Low]** Unverifiable '100% complete' Claims in Documentation (Effort: S)

### File: `run_tests.py`
**Total Findings in File:** 1
- **[F-010] [High]** run_tests.py Mixes Assertions (141) with Informational Prints (35) and Crashes on Line 81 (Effort: S)

### File: `app/modules/__init__.py`
**Total Findings in File:** 1
- **[F-015] [High]** Pytest Suite Fails 3 Tests Due to Module Registry Filtering and Destination Order (Effort: M)

### File: `app/evaluation.py`
**Total Findings in File:** 1
- **[F-016] [Medium]** Empirical 100-Seed Benchmark Proves Static Baseline Outperforms LinUCB Over 20 Rounds (Effort: M)

---
## Section 6: Verified Strengths & Working Capabilities
1. **Contextual LinUCB Mathematical Formulation:** Disjoint linear bandit implementation correctly constructs covariance matrices $A_a$ and bias vectors $b_a$, calculating upper confidence bounds with confidence parameter $\alpha=0.5$.
2. **Master Questionnaire Bank:** All 56 core questions across 10 sections and 126 adaptive precision questions correctly load from `app/questionnaire.py` and `app/precision.py`.
3. **Indian Destination Restrictions:** Frontend dropdown and backend `create_trip` validation strictly reject international destinations like Kyoto, Japan, adhering to India-only constraints.
4. **Open-Meteo & OpenStreetMap Service Layer:** Keyless external API integrations properly fetch live climate and coordinate data with local SQLite caching.

---
## Section 7: Limitations & Test Boundary Exclusions
1. **Production Google OAuth Authentication:** Live Google Sign-In with real client secrets could not be verified end-to-end without active internet connection and live Google Cloud OAuth credentials.
2. **High-Concurrency SQLite Write Contention:** Concurrent multi-user load testing (e.g. 500 simultaneous writes) was not evaluated against SQLite file locking limitations.