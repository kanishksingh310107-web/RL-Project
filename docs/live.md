# Person B: During-Trip Support and Post-Trip Learning Module (`live`)

## 1. What It Does

The `live` module completes the full travel lifecycle for the RL-Based Proactive Travel Guide by connecting the pre-trip planning phase with the **during-trip execution** and **post-trip reinforcement learning** phases:

1. **Today's Itinerary View:** Retrieves the current day's planned activities from the pre-trip itinerary, tracking live activity statuses (`upcoming`, `in_progress`, `completed`, `skipped`, `delayed`).
2. **Environmental & Travel Conditions Simulator:** Simulates disruption events (heavy rain, extreme heat, attraction closures, traffic delays, strikes, fatigue, crowding) with an explicit, uncompromised label marking all data as `source: "simulated"`.
3. **Contextual Alert Engine:** Generates proactive, non-duplicate warnings and advisories adhering to a daily budget limit (max 3 alerts/day) to prevent alert fatigue.
4. **Targeted Activity Replanning:** Swaps out only the disrupted activity using the existing `get_slot_alternatives` candidate pool with condition filtering (e.g., indoor-only during rain, low-intensity during fatigue), preserving the rest of the schedule and isolating temporary modifications from the user's permanent LinUCB policy.
5. **Trip Completion & Post-Trip Evaluation:** Validates trip completion before unlocking structured post-trip questionnaires covering overall satisfaction, pacing, budget realism, and per-activity ratings (1–5 stars).
6. **Genuine LinUCB Reinforcement Learning:** Updates the user's disjoint LinUCB linear bandit policy arms using the original 24-dimensional context vector preserved at schedule time, applying rank-1 Sherman-Morrison updates with duplicate submission protection and user isolation.
7. **Post-Trip Insights:** Transparently reports how post-trip evaluations alter policy arm weights ($\hat{\theta}_a$) without falsely claiming permanent convergence from a single journey.

---

## 2. How It Works (Method & Architecture)

### 2.1 System Architecture
The module is completely self-contained within the four authorized files (`app/modules/live.py`, `static/modules/live.js`, `tests/test_live.py`, `docs/live.md`). It integrates via FastAPI auto-discovery in `app/modules/__init__.py` and the client module loader in `static/modules/loader.js`.

```
Pre-Trip Itinerary (Read-Only)
           │
           ▼
[ live_activity_contexts ] ─── Snapshots original 24-dim context vector x
           │
           ├──▶ [ During-Trip Support ] ─── Live statuses & Conditions (Simulated)
           │                                 │
           │                                 ▼
           │                           Targeted Replanning (is_trip_specific=True, no permanent update)
           │
           ▼
[ Trip Completion ] (live_trip_state.is_completed = 1)
           │
           ▼
[ Post-Trip Feedback ] (Rating 1–5 stars)
           │
           ├──▶ Remember toggle: If True ──▶ LinUCB Sherman-Morrison Update:
           │                                 A_a ← A_a + x * x^T
           │                                 b_a ← b_a + r * x
           │                                 save_user_policy(conn, policy)
           │
           └──▶ Duplicate protection: UNIQUE(trip_id, activity_id)
```

### 2.2 Standardized Rating-to-Reward Mapping
Post-trip activity ratings are mapped to bounded scalar rewards $r \in [-1.0, +1.0]$:

| User Rating | Semantic Label | LinUCB Reward ($r$) | Policy Action |
|:---:|:---|:---:|:---|
| **5 / 5** | Very Satisfied | **+1.0** | Positive rank-1 update to category arm covariance & reward vector |
| **4 / 5** | Satisfied | **+0.5** | Moderate positive update to category arm |
| **3 / 5** | Neutral | **0.0** | No weight update (prevents neutral noise) |
| **2 / 5** | Dissatisfied | **-0.5** | Moderate negative update to category arm |
| **1 / 5** | Very Dissatisfied | **-1.0** | Strong negative rank-1 update to category arm |

### 2.3 Historical Context Preservation
To ensure mathematically rigorous online bandit updates, the original 24-dimensional feature vector $x \in \mathbb{R}^{24}$ must not be re-estimated after the trip with an altered user state. When activities are first loaded in `GET /api/live/{trip_id}/today`, the module checks `live_activity_contexts` or `rl_feedback_log`. If not present, it computes the exact vector at schedule time and persists it in `live_activity_contexts (itinerary_id, activity_id, context_vector_json)`. Post-trip updates directly retrieve this exact historical vector.

### 2.4 Duplicate Feedback & Isolation Invariants
* **Trip-Level Protection:** `live_postrip` has `UNIQUE(trip_id)` — submitting feedback twice yields HTTP 409 Conflict.
* **Activity-Level Protection:** `live_activity_feedback` has `UNIQUE(trip_id, activity_id)` — users cannot game rewards by repeated submissions.
* **Incomplete Trip Rejection:** Calling `POST /api/live/{trip_id}/postrip` before `POST /api/live/{trip_id}/complete` returns HTTP 400 Bad Request.
* **Trip-Specific / "Don't Remember" Isolation:** When `remember_preference=False`, feedback is recorded in the audit log but LinUCB covariance matrices ($A_a$) and reward vectors ($b_a$) remain unchanged.
* **User Isolation:** All operations enforce `_verify_trip_ownership(trip_id, user_id)` (HTTP 403 Forbidden on mismatch). User A's policy parameters can never be modified by User B's actions.

---

## 3. Database Schema (`live_*`)

The module initializes seven dedicated tables via `init_tables(conn)`:

1. `live_trip_state` (`trip_id` PK, `user_id`, `is_started`, `is_completed`, `current_day`, `started_at`, `completed_at`).
2. `live_activity_status` (`id` PK, `trip_id`, `activity_id`, `status`, `notes`, `updated_at`, `UNIQUE(trip_id, activity_id)`).
3. `live_conditions` (`id` PK, `trip_id`, `day_number`, `condition_type`, `severity`, `description`, `source` DEFAULT 'simulated', `created_at`).
4. `live_alerts` (`id` PK, `trip_id`, `day_number`, `activity_id`, `condition_id`, `severity`, `title`, `message`, `suggested_action`, `is_dismissed`, `created_at`).
5. `live_postrip` (`id` PK, `trip_id` UNIQUE, `user_id`, `overall_satisfaction`, `pace_rating`, `budget_accuracy`, `itinerary_realistic`, `enjoyed_most`, `disliked`, `comments`, `submitted_at`).
6. `live_activity_feedback` (`id` PK, `trip_id`, `activity_id`, `rating`, `enjoyed`, `remember_preference`, `reward_assigned`, `arm_id`, `context_vector_json`, `submitted_at`, `UNIQUE(trip_id, activity_id)`).
7. `live_activity_contexts` (`id` PK, `itinerary_id`, `activity_id`, `context_vector_json`, `created_at`, `UNIQUE(itinerary_id, activity_id)`).

---

## 4. Backend REST Endpoints

| Method | Path | Description | Access Control |
|---|---|---|---|
| `GET` | `/api/live/module-info` | Health check & module descriptor | Public |
| `GET` | `/api/live/{trip_id}/state` | Trip execution lifecycle status | Trip Owner |
| `GET` | `/api/live/{trip_id}/today` | Today's enriched activity schedule & conditions | Trip Owner |
| `POST` | `/api/live/{trip_id}/activity/{activity_id}/status` | Update activity live status | Trip Owner |
| `POST` | `/api/live/{trip_id}/simulate` | Trigger simulated condition & evaluate alerts | Trip Owner |
| `GET` | `/api/live/{trip_id}/alerts` | List active alerts for trip/day | Trip Owner |
| `POST` | `/api/live/{trip_id}/alerts/{alert_id}/dismiss` | Dismiss an alert | Trip Owner |
| `GET` | `/api/live/{trip_id}/replan` | Condition-filtered candidate replacements | Trip Owner |
| `POST` | `/api/live/{trip_id}/replan` | Targeted activity swap (preserves remaining itinerary) | Trip Owner |
| `POST` | `/api/live/{trip_id}/complete` | Mark trip as completed | Trip Owner |
| `POST` | `/api/live/{trip_id}/postrip` | Submit post-trip feedback & update LinUCB | Trip Owner |
| `GET` | `/api/live/{trip_id}/postrip` | Retrieve submitted feedback for completed trip | Trip Owner |
| `GET` | `/api/live/{user_id}/learning-summary` | Inspect updated arm weights & feedback history | User Owner |

---

## 5. Frontend Architecture (`static/modules/live.js`)

The frontend registers cleanly via `TravelModules.register("live", { render(container, ctx) })` inside the client companion modal:
* **During-Trip View:**
  * Day-by-day pill navigation (`Day 1`, `Day 2`, etc.).
  * Interactive **Simulated Condition Trigger** dropdown with visible `SIMULATED DEMO` badge.
  * Contextual alert banners with severity indicators and 1-click **"Replan"** trigger.
  * Activity cards showing duration, cost, neighborhood, explanation, and live status dropdown (`upcoming`, `in_progress`, `completed`, `skipped`, `delayed`).
  * Targeted replanning overlay: presents candidate replacements with condition suitability tags and confirms single-slot replacement without touching other days.
* **Post-Trip View:**
  * Displays "Trip In Progress" gate until user clicks "Mark Trip as Completed".
  * Structured survey: 5-star overall satisfaction, pace pills, budget pills, itinerary realism pills, and comments.
  * Individual activity evaluations: 1–5 clickable stars with "Remember this preference" toggle for isolating one-off anomalies.
  * **RL Transparency Table:** Visualizes the 7 canonical LinUCB arms (`culture_history`, `nature_outdoors`, `food_dining`, etc.), pull counts, cumulative rewards, weight vector norms, and directional adaptation indicators ($\uparrow$ Reinforced / $\downarrow$ Penalized).

---

## 6. Screenshots Guide for PPT

For teammate C to compile into the viva presentation:
1. `screenshot_live_today_timeline.png`: During-trip view showing Kyoto Day 1 schedule with activity status badges.
2. `screenshot_simulated_alert.png`: Heavy Rain simulation banner and resulting contextual warning alert card.
3. `screenshot_targeted_replan.png`: Replanning modal showing alternative indoor activity selection.
4. `screenshot_postrip_questionnaire.png`: Completed trip feedback form with star ratings and preference toggles.
5. `screenshot_linucb_learning_summary.png`: LinUCB preference table showing updated pull counts, cumulative rewards, and weight vector norms.

---

## 7. Verification & Test Results

All tests run in `tests/test_live.py` against isolated temporary SQLite databases (`tests/conftest.py`), preserving `travel_guide.db`.

| Test Case | Description / Input | Expected Output | Actual Output | Status |
|---|---|---|---|:---:|
| `test_live_module_registration` | `GET /api/modules` & `/static/modules/live.js` | `live` module found with title & owner 'B'; JS served | Matched metadata & JS | **PASS** |
| `test_live_tables_initialized` | Query SQLite master table list | All 7 `live_*` tables exist | All 7 present | **PASS** |
| `test_module_info_and_trip_state` | Verify module info & trip state access | Status 'active', state default day 1 | Matched & 403 on intruder | **PASS** |
| `test_get_today_itinerary` | `GET /today?day=1` for Kyoto trip | Activities enriched with live status | Returned 4 activities | **PASS** |
| `test_activity_status_updates` | Update status across all 5 valid states | Status updated in DB; rejects invalid | 200 on valid, 400 on invalid | **PASS** |
| `test_simulate_condition_and_alerts` | Simulate `heavy_rain` on Day 1 | `source: "simulated"`, rain alert created | Tagged simulated, alert generated | **PASS** |
| `test_alert_budget_limit` | Trigger 4 conditions on Day 2 | Alerts capped at $\le 3$ per day | Exactly 3 alerts produced | **PASS** |
| `test_targeted_activity_replanning` | Swap 1 activity for heavy rain | Only 1 activity replaced; policy untouched | Target replaced, rest kept, 0 pulls | **PASS** |
| `test_trip_completion_and_incomplete_trip_rejection` | Post-trip on uncompleted vs completed | HTTP 400 before completion, 200 after | 400 rejected, 200 allowed | **PASS** |
| `test_post_trip_feedback_and_genuine_linucb_learning` | Submit ratings 5 (+1.0) and 1 (-1.0) | LinUCB pull count +1, reward +1.0, 24-dim context | Pulled +1, reward +1.0, 24 dims verified | **PASS** |
| `test_dont_remember_preference_isolation` | Submit rating 1 with `remember_preference=False` | Feedback saved, LinUCB policy unchanged | 0 updates applied, pulls unchanged | **PASS** |
| `test_user_isolation_and_unauthorized_feedback` | Intruder submits feedback for another's trip | HTTP 403 Forbidden | HTTP 403 returned | **PASS** |
| `test_learning_summary_endpoint` | `GET /{user_id}/learning-summary` | Arm pull counts, weight norms, explanation; 403 on intruder | 7 arms returned; 403 verified | **PASS** |

**Syntax Verification:** `node -c static/modules/live.js` $\rightarrow$ Exit code 0.  
**Test execution command:** `python -m pytest tests -q`  
**Result:** `15 passed, 2 warnings in 2.06s` (100% passing).

---

## 8. Known Limitations & Academic Boundary

1. **Simulated Weather & Travel Data:** In accordance with project requirements, there is no third-party live weather or traffic API integrated. All condition events are synthetic simulations explicitly labelled `source: "simulated"`.
2. **Single-Trip Convergence:** While rank-1 Sherman-Morrison updates genuinely shift the category arm weights ($\hat{\theta}_a$), full convergence of bandit recommendations cannot be established from a single trip. The system communicates this limitation explicitly in the learning summary.

---

## 9. Instructions for Integrating with Other Members' Branches

Person B has strictly authored only four files:
1. `app/modules/live.py` (Backend logic, routes, and `init_tables`)
2. `static/modules/live.js` (Frontend Companion view)
3. `tests/test_live.py` (Automated pytest test suite)
4. `docs/live.md` (Module documentation and handoff)

### Integration Procedure (for Person C on `main`):
Because Person B never modified shared files (`main.py`, `app/api.py`, `static/index.html`, `static/app.js`, `app/database.py`, `app/rl_planner.py`), integrating `feat/live` produces **zero merge conflicts**:

```bash
# 1. Switch to main
git checkout main
git pull origin main

# 2. Merge Person B's branch
git merge --no-ff origin/feat/live -m "Merge Person B: During-Trip Support and Post-Trip Learning"

# 3. Verify all automated tests pass
python -m pytest tests -q
python run_tests.py
```

FastAPI's auto-discovery (`app/modules/discover()`) will instantly register the `/api/live` routes, initialize tables on server startup, and expose the "During & Post Trip" tab in the Travel Companion modal (`static/modules/loader.js`).

---

## 10. AI Assistance and External Libraries/APIs Used

In accordance with academic integrity guidelines:
* **AI Assistance:** Anthropic Claude / Google DeepMind Antigravity was used to assist in implementing the module backend, designing SQLite schemas, formulating mathematical LinUCB updates, and authoring unit tests.
* **External Libraries Used:**
  * `fastapi`: API routing and HTTP exception handling.
  * `pydantic`: Request payload validation.
  * `sqlite3`: Relational persistence with transaction management.
  * `numpy`: Matrix and vector operations ($A_a \leftarrow A_a + x x^\top$, $b_a \leftarrow b_a + r x$, $\hat{\theta}_a = A_a^{-1} b_a$).
  * `pytest` & `starlette.testclient`: Automated integration and unit testing.
* **External APIs Used:** None. No real-time external weather, transit, or map APIs were called; all environmental conditions are explicitly simulated.
