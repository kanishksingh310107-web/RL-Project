# Pre-trip Preparation Module (`prep`)

**Module Owner:** Person A  
**Git Branch:** `feat/prep`  
**Target Submission:** RL-Based Proactive Travel Guide (B.Tech CSE AI/ML, 3 Nov 2026)

---

## 1. What it does

The Pre-trip Preparation module closes the single largest practical gap identified in the project vision (the classic "Scotland coat" problem: recommending warm, windproof layers before departure rather than leaving travellers unprepared).

Specifically, it provides four core features accessed through the Travel Companion interface:
1. **Weather Forecast with Guaranteed Offline Fallback:** Queries live daily forecasts (min/max temperature, wind speed, precipitation probability) from Open-Meteo for any of the 16 curated destinations, seamlessly falling back to a curated climatological estimate if the network is disconnected, times out, or when dates are outside the forecast window.
2. **Transparent Rule-Based Dynamic Packing List:** Recommends categorized items (Clothing, Footwear, Toiletries/Health, Electronics, Documents, Activity gear) driven jointly by weather conditions, itinerary activities (e.g. hiking boots for nature trails, modest clothing for temples/shrines), and user context from the precision profile (cold/heat/wind tolerance scales, carry-on limits with liquids restrictions, and user-flagged medication/allergies).
3. **Verified Documents and Entry Requirements Checklist:** A standardized pre-trip document checklist covering passport validity (6-month rule), transit bookings, travel insurance, electrical power standards (plug types & voltage for all 16 destinations), mobile connectivity (eSIM/roaming), payment cards, and prescription medication rules. **It strictly avoids inventing visa regulations**, explicitly advising travellers to confirm entry permissions on official embassy portals.
4. **Adaptive Timed Reminders with Thompson Sampling Bandit:** Dynamically schedules pre-trip alerts at fixed countdown offsets ($T - 30$ days for documents, $T - 14$ days for insurance, $T - 3$ days for packing, $T - 2$ days for weather, $T - 1$ day for online check-in and cabin bag prep). A multi-armed bandit using **Thompson Sampling with $\text{Beta}(\alpha, \beta)$ conjugate priors** learns individual category preferences from user feedback (`useful`, `not_useful`, `done`) and orders alerts subject to a daily alert budget ($N=3$).

---

## 2. How it works (method)

### Architecture & Data Flow

```
                                  +---------------------------+
                                  |   Open-Meteo API (HTTP)   |
                                  +-------------+-------------+
                                                | (5s timeout / fallback)
                                                v
+------------------------+        +---------------------------+
| trips & user profile   | -----> |   app/modules/prep.py     | <=====> SQLite (prep_reminders,
| (get_trip, context,    |        | (Weather, Packing Rules,  |                 prep_bandit)
|  get_itinerary)        |        |  Documents, TS Bandit)    |
+------------------------+        +-------------+-------------+
                                                | JSON API
                                                v
                                  +---------------------------+
                                  |   static/modules/prep.js  |
                                  | (Travel Companion UI Tab) |
                                  +---------------------------+
```

### 1. Weather Module (`GET /api/prep/{trip_id}/weather`)
- Central coordinates for each of the 16 destinations are mapped in `DESTINATION_COORDS`.
- `fetch_open_meteo(lat, lon, start, end)` sends a non-blocking request to the Open-Meteo public forecast endpoint.
- If network fails, times out, returns non-200, or if dates are out of range, `get_offline_weather(dest_id, start_date)` extracts the trip month and fetches values from `CLIMATE_ESTIMATES`, a hand-written monthly table covering all 16 destinations.
- The response clearly reports `source` (`"open-meteo"` or `"offline-estimate"`), `fetched_at`, human-readable `label`, and a structured `summary` object.

### 2. Rule-Based Packing Engine (`GET /api/prep/{trip_id}/packing`)
- **Cold + Wind Rule (The Scotland Coat Principle):** If destination lows $< 15^\circ\text{C}$ or user cold sensitivity $q_{78} \le 2$, AND wind speed $\ge 25\text{ km/h}$ or user wind sensitivity $q_{80} \le 2$:
  - Adds *"Windproof & insulating layer (outer shell jacket)"* with reasoning citing the weather and profile sensitivity.
  - Omitted on hot trips ($T_{\min} \ge 20^\circ\text{C}$ and $T_{\max} \ge 25^\circ\text{C}$).
- **Luggage Capacity Constraint ($q_{61} = \text{carry\_on}$):**
  - Scales apparel counts down to capsule counts (3-4 sink-washable tops, 2 bottoms, 4 pairs socks/underwear).
  - Eliminates bulky spares (spare alternate shoes, second dinner outfit, full-size toiletries).
  - Enforces mandatory airport security item: *"Liquids pouch (containers max 100ml in transparent 1L bag)"*.
  - Result: Users with carry-on strictly receive a shorter, cabin-compliant list.
- **Itinerary Activity Rules:**
  - `nature_outdoors` / `adventure` / hiking keywords $\to$ sturdy hiking boots / trail shoes, trail daypack (20-30L).
  - `culture_history` / temples / shrines $\to$ modest clothing covering knees & shoulders, easy slip-on walking shoes.
  - `food_dining` $\to$ pocket hand sanitizer and wipes.
  - `shopping_local` $\to$ packable reusable tote bag.
  - `beach` / water / swimming $\to$ swimwear and quick-dry microfiber towel.
- **Health & Medication Rules:**
  - If user profile indicates medications ($q_{11}$) or allergies ($q_{10}, q_{95}$), generates an informational item: *"Personal prescription medication in original packaging (cabin luggage)"*, explicitly flagged as non-medical advice.
- **Graceful Fallbacks:** If the itinerary has not yet been generated or the precision profile is blank, safe defaults (versatile walking sneakers, everyday daypack) are generated and labelled accordingly.

### 3. Documents Checklist (`GET /api/prep/{trip_id}/documents`)
- Standardized checklist across 8 operational categories: Passport validity (6 months rule), Visa & entry authorization, Travel medical insurance, Travel bookings, Power adapter & voltage, International eSIM/roaming, Payment cards & emergency cash, and Prescription medication in cabin baggage.
- Plug types and voltages are specified for all 16 destination regions via `DESTINATION_POWER_STANDARDS` (e.g. Japan: Type A/B 100V; Switzerland: Type J 230V; India: Type C/D/M 230V; UK/NZ: Type I 230V).
- Every sensitive legal or regulatory item flags `official_check_required: True` and directs the user to the destination government or embassy portal.

### 4. Thompson Sampling Bandit for Reminders (`D4 & D5`)
- **Action Space:** 6 reminder categories $\mathcal{C} = \{\text{documents}, \text{insurance}, \text{packing}, \text{weather}, \text{checkin}, \text{logistics}\}$.
- **Prior Distribution:** Each user-category pair maintains independent conjugate Beta priors:
  $$\theta_c \sim \text{Beta}(\alpha_c, \beta_c), \quad \text{initialized with } \alpha_c = 1.0, \beta_c = 1.0 \text{ (Uniform Prior)}$$
- **Sampling & Ranking:**
  For each reminder category $c$, a sample $\hat{\theta}_c$ is drawn using a seedable pseudo-random generator:
  $$\hat{\theta}_c \sim \text{Beta}(\alpha_c, \beta_c)$$
  Active pending reminders are sorted primarily by $\hat{\theta}_c$ descending, and secondarily by due date ascending.
- **Alert Budget:**
  To prevent notification fatigue, at most $N=3$ reminders are marked `is_active: True` for the current day. Remaining reminders are deferred (`waiting_count`).
- **Feedback & Posterior Updates:**
  Upon receiving feedback for reminder of category $c$:
  - `useful` or `done`: Reward $+1 \implies \alpha_c \leftarrow \alpha_c + 1.0$
  - `not_useful`: Reward $-1 \implies \beta_c \leftarrow \beta_c + 1.0$
  - Dismissed without feedback: Weak negative signal $\implies \beta_c \leftarrow \beta_c + 0.1$
- The learned parameters $(\alpha_c, \beta_c)$ and empirical mean $\mu_c = \frac{\alpha_c}{\alpha_c + \beta_c}$ are persisted in SQLite table `prep_bandit` and exposed in the API.

---

## 3. Files

| File | Purpose |
|---|---|
| `app/modules/prep.py` | Complete backend module: SQLite tables (`prep_reminders`, `prep_bandit`), Open-Meteo HTTP fetcher with offline fallback, rule-based packing generator, documents checklist, reminder scheduler, and Thompson Sampling bandit policy. |
| `static/modules/prep.js` | Frontend UI tab registered into `TravelModules` for the "Companion" button: weather summary card, interactive packing checklist with localStorage persistence, documents cards, and reminder actions (👍 / 👎 / ✔) with live bandit posterior stats strip. |
| `tests/test_prep.py` | Comprehensive test suite (16 tests) covering 404 handlers, Open-Meteo live parsing, offline fallback, cold/windy vs hot packing rules, carry-on luggage caps, medication reminders, reminder due dates, alert budgets, and Thompson Sampling bandit learning shifts. |
| `docs/prep.md` | Module documentation, scientific/algorithmic method specification, test execution tables, limitations, and verification log. |

---

## 4. Test table

*All tests executed against temporary SQLite databases using pytest and FastAPI TestClient. Real output from test run on 2 Nov 2026:*

| Case | Input | Expected | Actual | Pass |
|---|---|---|---|---|
| `test_weather_endpoint_404_on_unknown_trip` | `GET /api/prep/non_existent_trip_id_999/weather` | 404, detail="trip not found" | HTTP 404, detail="trip not found" | PASS |
| `test_weather_offline_fallback` | `GET /api/prep/{trip_id}/weather` with `fetch_open_meteo` monkeypatched to raise exception | 200, source="offline-estimate", label contains "not a live forecast", valid summary | HTTP 200, source="offline-estimate", label="Offline estimate – not a live forecast" | PASS |
| `test_weather_live_open_meteo_mock` | `GET /api/prep/{trip_id}/weather` with mock Open-Meteo response | 200, source="open-meteo", parsed summary values match mock | HTTP 200, source="open-meteo", temp_min=12.0, temp_max=21.0 | PASS |
| `test_packing_endpoint_404_on_unknown_trip` | `GET /api/prep/unknown_trip_888/packing` | 404, detail="trip not found" | HTTP 404, detail="trip not found" | PASS |
| `test_packing_cold_windy_vs_hot` | Cold weather ($5^\circ\text{C}$, $34\text{ km/h}$) vs Hot weather ($24^\circ\text{C}-33^\circ\text{C}$) | Cold includes Windproof layer & rain gear; Hot excludes windproof and thermal layers and includes breathable shirts | Cold has "Windproof & insulating layer"; Hot has breathable clothing and zero windproof/thermal layers | PASS |
| `test_packing_carry_on_shorter_list_and_liquids_reminder` | Kyoto 5-day trip, standard luggage vs user with precision $q_{61} = \text{carry\_on}$ | Carry-on list strictly shorter than standard list AND contains liquids bag $\le 100\text{ml}$ | Standard has 18 items; Carry-on has 16 items and contains "Liquids pouch (max 100ml)" | PASS |
| `test_packing_medication_and_allergy_profile` | User with precision answers $q_{11}=\text{personal\_medication}$, $q_{10}=[\text{food\_allergies}]$ | Item added advising prescription meds in cabin bag with "no medical advice" disclaimer | Item present in Toiletries/Health, specifies cabin bag, includes non-medical disclaimer | PASS |
| `test_packing_without_itinerary_and_without_precision_profile` | Trip created without generating itinerary or precision questionnaire | 200, `itinerary_status="not_generated"`, includes default walking sneakers and daypack | HTTP 200, itinerary_status="not_generated", fallback sneakers present | PASS |
| `test_documents_endpoint_404_on_unknown_trip` | `GET /api/prep/unknown_trip_777/documents` | 404, detail="trip not found" | HTTP 404, detail="trip not found" | PASS |
| `test_documents_checklist_never_invents_visa_rules` | `GET /api/prep/{trip_id}/documents` | 8+ items, passport and visa items mandate official check; power adapter lists Kyoto standards | 8 items; Visa note mandates official embassy check; power adapter lists Type A/B 100V | PASS |
| `test_reminders_generation_and_due_dates` | `POST /api/prep/{trip_id}/reminders/generate` on trip starting 2026-11-10 | Generates 6 reminders with exact $T - N$ dates (docs: 10-11, ins: 10-27, pack: 11-07, etc.); second call returns count 0 (idempotent) | 6 reminders created; due dates match exact countdown; second call creates 0 | PASS |
| `test_reminders_alert_budget_enforcement` | `GET /api/prep/{trip_id}/reminders` | `alert_budget=3`, `active_count=3`, `waiting_count=3` | Active count capped at 3, remaining 3 marked waiting | PASS |
| `test_reminders_feedback_validation_and_errors` | Feedback with invalid trip, invalid reminder, or invalid body `{"feedback": "super_awesome"}` | 404 on invalid trip/reminder; 422 on invalid feedback enum | 404 for unknown trip/reminder; 422 for invalid feedback string | PASS |
| `test_bandit_feedback_updates_and_shifts_preference` | Single feedback updates $\alpha$ or $\beta$; 15x `useful` on packing + 15x `not_useful` on insurance | Packing $\alpha \ge 16$, $\mu > 0.8$; Insurance $\beta \ge 16$, $\mu < 0.2$; under seed=42, packing score $>$ insurance score | Packing $\mu = 0.941$, Insurance $\mu = 0.059$; seeded score $0.943 > 0.056$ | PASS |
| `test_reminders_unknown_trip_returns_404` | `GET` and `POST /generate` on unknown trip | 404, detail="trip not found" | Both return HTTP 404 | PASS |
| `test_packing_user_cold_sensitivity_override` | User with $q_{78}=1$ (high cold sensitivity) in mild $18^\circ\text{C}$ weather | Adds thermal base layer due to personal sensitivity even though weather is mild | Thermal base layer added when $q_{78}=1$, omitted when baseline | PASS |
| `tests/test_scaffold.py::test_modules_endpoint` | `GET /api/modules` | 200, includes prep module definition | HTTP 200, includes `{"id": "prep", "title": "Trip Prep", ...}` | PASS |
| `tests/test_scaffold.py::test_fixtures_work` | Validates shared conftest fixtures | Kyoto demo trip, user context, and generated itinerary verified | Fixtures load clean temporary SQLite environment | PASS |

---

## 5. Limitations

1. **Offline Climatological Estimates:** The hand-written offline climate table provides approximate regional monthly averages for the 16 destinations. It is an engineering fallback for offline/air-gapped environments, not a verified real-time meteorological instrument.
2. **Open-Meteo Forecast Horizon:** Live numerical weather forecasts are typically limited to a 7–14 day operational horizon. Trips booked months in advance automatically transition to the climatological estimate until within the forecast window.
3. **Visa and Entry Regulations:** Border control rules, visa policies, and customs requirements change frequently based on bilateral accords and passport nationality. The documents endpoint deliberately offers informational reminders only, mandating official embassy/government verification. It must not be construed as legal counsel.
4. **Bandit Training Data:** The Thompson Sampling bandit policy is trained strictly on in-app user interactions (`useful`, `not_useful`, `done`) stored in the local SQLite table. It reflects simulated and personal demo feedback, not a large-scale randomized controlled user trial.
5. **No Medical Advice:** Packing and document reminders concerning prescription medication, allergen awareness, or emergency medical supplies are strictly logistical and administrative. They do not provide dosage, pharmaceutical, or clinical advice.

---

## 6. Screenshots to take

When running the application locally (`python main.py` at `http://localhost:8000`):
1. **Weather Card & Source Badge:** Open Companion $\to$ Trip Prep for Kyoto. Capture the weather card displaying the `"Live forecast (Open-Meteo)"` green pill badge, temperature range, and wind speed.
2. **Offline Fallback Card:** Disconnect internet or test with dates outside forecast window to capture the amber `"Offline estimate – not a live forecast"` badge.
3. **Personalized Packing List:** Show the grouped checklist with checkable boxes and reason tags (e.g. Scotland coat windproof layer for cold/windy trips vs lightweight tops for hot trips).
4. **Carry-On Capsule View:** User with carry-on luggage preference showing reduced apparel counts and the 100ml liquids transparent bag item.
5. **Documents Checklist:** Documents table showing the 6-month passport rule, visa notice with the red "Verify on official site" badge, and Japan Type A/B 100V power standards.
6. **Timed Reminders & Bandit Posterior:** Reminders list displaying today's active alerts (alert budget cap = 3), action buttons (👍 / 👎 / ✔), and the bottom bandit strip showing learned $\alpha, \beta$ and mean preference per category.

---

## 7. AI assistance and external libraries/APIs used

- **AI Tools:** Development was assisted by **Google Antigravity** (for architecture, implementation, test development, and documentation) and **Claude** (for independent verification and code review against team specifications).
- **External Libraries & APIs:**
  - `FastAPI` (v0.111.0) & `Starlette`: Modular asynchronous REST API routing and request handling.
  - `Pydantic` (v2.7.4): Strict request/response validation and feedback body schemas.
  - `SQLite3`: ACID-compliant relational persistence for `prep_reminders` and `prep_bandit`.
  - `httpx` (v0.28.1): Resilient HTTP client with short timeouts (5s) for external API integration.
  - `Open-Meteo API` (`open-meteo.com`): Free, public, non-authenticated open-access meteorological API.
  - `pytest` (v9.2.0): Automated test execution and regression suite.
  - `Tailwind CSS` & `FontAwesome`: Frontend styling and iconography aligned with existing platform design.
