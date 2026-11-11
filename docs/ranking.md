# Seasonal and Multi-Criteria Ranking Module (`ranking`)

**Module ID:** `ranking`  
**Title:** Ranking  
**Owner:** Person C (Integrator)  
**Router Prefix:** `/api/ranking`  

---

## 1. What It Does

The Ranking Module delivers transparent, explainable destination recommendations across the 16 curated destinations in `app/recommender.py`. It evaluates each destination against user profile preferences, travel timing, budget feasibility, and historical engagement.

Key features:
1. **6-Component Transparent Scoring:** Combines Interest Match (25%), Season Suitability (20%), Catalogue Popularity (15%), Feasibility (15%), Live Conditions (10%), and User Feedback (15%).
2. **Deep Personalization:** Integrates full user profile from `app.core.profile.load_profile`, accounting for stated avoidances, crowd tolerance, preferred climate, and past trip feedback (`core_trip_feedback`).
3. **Live India Destination Search (`GET /api/ranking/india/search`):** Real-time geocoding via Geoapify, Open-Meteo historical climate season scoring, and POI density proxy.
4. **Hard Constraint Filtering:** Hard constraints (budget caps, temporary closures, travel advisories, stated destination avoidances) are treated as absolute filters rather than scoring penalties. Excluded destinations appear in no ranked lists and include clear exclusion rationales.
5. **Four Specialized Output Views:** In addition to the unified overall ranking, provides four distinct ranked views:
   - **Trending Now:** High-demand destinations based on catalogue trend flags.
   - **Best This Season:** Destinations whose optimal seasons align with the requested travel date.
   - **Best For You:** Destinations maximizing overlap with the user's questionnaire goals and tags.
   - **Best Feasible:** Destinations offering the smoothest budget tier and companion fit.
6. **Interactive Explainability:** Every ranked item returns a full point breakdown showing raw value, normalized weight, exact score contribution, and human-readable explanation notes.

---

## 2. How It Works (Method)

### Baseline Assumed Weights
The scoring formula uses 6 linear components summing to 1.0 (100 total possible points):
$$\text{Total Score} = \sum_{c \in \text{Components}} (\text{Value}_c \times \text{Weight}_c \times 100)$$

| Component | Default Weight | Description |
|---|---|---|
| **Interest Match** | 0.25 | Evaluates overlap between destination tags and user interests mapped from `basic['interests']` and `raw_answers_json`. |
| **Season Suitability** | 0.20 | Circular distance (months 1..12) between the requested travel date and destination `best_seasons` ranges. |
| **Popularity** | 0.15 | Static estimate derived from catalogue `crowd_level` and `is_trending` metadata. |
| **Feasibility** | 0.15 | Average of budget alignment (cap fit or tier closeness) and companion suitability. |
| **Live Conditions** | 0.10 | Offline neutral placeholder (0.5) as no real-time telemetry feed is integrated. |
| **User Feedback** | 0.15 | Shortlisted status (1.0), past trip rating $\frac{\text{rating}-1}{4}$, or neutral placeholder (0.5). |

> **Note on Weight Assumptions:** These baseline weights are subjective heuristic assumptions, clearly labelled as such in the API and UI. Callers can override any weight via query parameters (`w_interest`, `w_season`, etc.); overrides are automatically re-normalized to sum to 1.0.

### Month and Season Parsing Logic
Destination `best_seasons` strings (e.g. `"Spring (Mar - May)"`, `"Winter (Dec - Feb) for snow"`, `"November to March (warm summer)"`) are parsed using a strict month regex:
`\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b`
Ranges are mapped to integer sets ($1 \dots 12$), handling year-end wraparound ($11 \dots 12 \dots 1 \dots 3$). Given target month $m_t$:
- If $m_t \in \text{active months}$: **1.0**
- Circular distance $d = \min(|m_t - m|, 12 - |m_t - m|)$:
  - $d = 1$: **0.6**
  - $d = 2$: **0.3**
  - $d \ge 3$: **0.0**

### The Questionnaire Interest Bug Fix & Impact
- **Initial Bug:** `get_user_context(user_id)["basic"]` stores legacy slider interests in `basic["interests"]`, whereas questionnaire answers (`travel_goals` like `["nature", "culture"]`) reside inside `basic["raw_answers_json"]`. Furthermore, user vocabulary (`"historic"`, `"trying_new_foods"`) differs from catalogue tags (`"history"`, `"food"`). A naive reader received 0 shared tags for Kyoto.
- **Consequence:** In that buggy state, Tokyo (0 shared tags with nature/culture) topped the ranking because Season (20%) + Popularity (15%) + Feasibility (15%) = 50% outweighed interest.
- **The Fix:** `extract_user_interests()` aggregates tags across `basic["interests"]`, `raw_answers_json["travel_goals"]`, and `raw_answers_json["place_interests"]`, applying `GOAL_MAPPING`.
- **Verified Outcome:** Kyoto receives 25.0 interest points and ranks #1 overall (83.00 total points), while Tokyo ranks #6 (70.83 total points).

---

## 3. Files

| File | Role |
|---|---|
| `app/modules/ranking.py` | FastAPI router (`/api/ranking/{user_id}`), scoring algorithms, filter logic, weight re-normalization. |
| `static/modules/ranking.js` | Vanilla JS Companion tab, responsive Tailwind cards, stacked breakdown bars, disclosure banners. |
| `tests/test_ranking.py` | Pytest suite covering all 15 test scenarios against an isolated temporary SQLite DB. |
| `docs/ranking.md` | Module documentation, test evidence, methodology, and limitations. |

---

## 4. Test Table (Verified Real Test Runs)

Ran via `pytest tests/test_ranking.py -v`:

| Case | Input | Expected | ACTUAL (Real Run) | Pass? |
|---|---|---|---|---|
| Module Discovery | `GET /api/modules` | Ranking listed with owner `"C"` and id `"ranking"` | `{"id": "ranking", "title": "Ranking", "icon": "fa-ranking-star", "owner": "C"}` found | ✅ Pass |
| Default Weights Sum | Direct check of `DEFAULT_WEIGHTS` | Sum == 1.0 | `sum == 1.0` (difference < 1e-6) | ✅ Pass |
| Override Rescaling | `w_interest=2.0&w_season=2.0` (others 0) | Re-normalized weights sum to 1.0 (0.5 each) | `weights["interest"] == 0.5`, `weights["season"] == 0.5`, sum = 1.0 | ✅ Pass |
| Catalogue Season Parsing | All 16 destinations in `DESTINATIONS` | All best_seasons yield $\ge 1$ active month | 16/16 parsed successfully with active months $\in [1, 12]$ | ✅ Pass |
| Season Wrap-Around | `"Winter (Dec - Feb)"` & `"Nov to Mar"` | Months $\{12, 1, 2\}$ and $\{11, 12, 1, 2, 3\}$ parsed | Sets match expected month numbers exactly | ✅ Pass |
| Date Impact on Score | Kyoto Nov 15 vs Jul 15 | Nov season score > Jul season score | Nov season = 1.0 (Total: 83.0) > Jul season = 0.6 (Total: 75.0) | ✅ Pass |
| Budget Cap Filter | `budget=50.0` USD/day | Swiss Alps ($210 min) & Santorini ($180 min) excluded | Excluded with reason `"exceeds budget cap ($50/day)"`; 0 appearances in ranked lists | ✅ Pass |
| Manual Flags Exclusion | `closed=kyoto_japan&advisory=tokyo_japan` | Both excluded with respective reasons | Both excluded (`"manually marked as closed"`, `"Travel advisory in effect"`) | ✅ Pass |
| Missing Profile Grace | `user_id="non_existent_999"` | HTTP 200, `has_profile=false`, neutral 0.5 | HTTP 200, `has_profile=false`, interest=0.5, live=0.5 | ✅ Pass |
| Interest Personalization | Nature user profile | Mountain/nature destinations top `best_for_you` | Top destination in `best_for_you` is `manali_spiti_india` | ✅ Pass |
| Questionnaire Bug Fix | `demo_user` (`["nature", "culture"]`) | Kyoto has non-zero interest points | Kyoto has `interest.value == 0.67` (25.0 points) | ✅ Pass |
| Shortlist Feedback | `POST /api/shortlist` for Kyoto | Kyoto feedback score becomes 1.0 | `feedback.value == 1.0` with note `"Shortlisted by user"` | ✅ Pass |
| Contribution Sum | Any ranked item | Sum of contributions == `total_score` | `sum(contributions) == total_score` across all 16 items | ✅ Pass |
| Specialized Lists | `limit=3` | 4 lists returned, each length $\le 3$; trending has `is_trending=true` | Returned 4 lists with $\le 3$ items, trending filtered | ✅ Pass |
| Input Validation (400) | Invalid date `2026/11/02` or negative weight | HTTP 400 Bad Request | HTTP 400 with descriptive detail message | ✅ Pass |
| Live India Search | `GET /api/ranking/india/search?q=Jaipur&month=11` | 200 OK, coordinates, climate score, POI proxy, Geoapify attribution | Lat 26.9124, season_score 0.88, density_score present | ✅ Pass |
| India Search Errors | Empty query or unknown location | 400 Bad Request / 404 Not Found | 400 for empty q; 404 for unknown location | ✅ Pass |
| INR Cost Parsing | `₹2,500 - ₹4,500 / day · Budget` | Parsed to USD using `INR_TO_USD_RATE` (30 - 54 USD) | low=30, high=54 USD | ✅ Pass |
| Avoidance Exclusion | User avoids `swiss_alps` | Destination placed in `excluded` with stated reason | swiss_alps excluded with `"in user stated avoidances"` | ✅ Pass |
| Crowd Avoidance Note | User avoids crowds on high crowd destination | Score penalized and warning note attached | Penalty applied, `"avoidance_warning"` attached | ✅ Pass |

---

## 5. Limitations

1. **Static Popularity Data:** Popularity is estimated entirely from static catalogue attributes (`crowd_level` and `is_trending`). No real-time search volume, flight bookings, or foot-traffic feeds are connected.
2. **Synthetic Live Conditions:** Live conditions (weather alerts, transit strikes, air quality) do not have a live ingestion pipeline and default to a neutral 0.5 placeholder score.
3. **Assumed Default Weights:** Weights are subjective heuristics chosen for balanced demonstration and must not be interpreted as learned econometric or machine-learning parameters.
4. **Catalogue Size:** Only 16 curated destinations are present in the mock database; real-world deployment would require full indexing and geospatial search.

---

## 6. Screenshots to Take (For Presentation/Report)

1. **Ranking Modal Overview (`docs/screenshots/ranking_modal_overview.png`):**
   Open the Companion modal on the "Ranking" tab showing the static data notice banner, the date and budget inputs, and the color legend.
2. **Explainability Breakdown (`docs/screenshots/ranking_breakdown_bars.png`):**
   Close-up of the stacked horizontal breakdown bar displaying the 6 color segments (Interest, Season, Popularity, Feasibility, Live, Feedback) and point contributions for Kyoto.
3. **Constraint Filter in Action (`docs/screenshots/ranking_budget_exclusion.png`):**
   Set daily budget cap to `$50` and capture the red "Excluded Destinations" panel showing Swiss Alps and Santorini filtered out with explicit cost reasons.
4. **Specialized Tabs Comparison (`docs/screenshots/ranking_tabs.png`):**
   Show "Trending Now" vs "Best This Season" side by side to illustrate how list sorting shifts with perspective.

---

## 7. AI Assistance and External Libraries/APIs Used

- **AI Assistance:** Architectural design and implementation of `app/modules/ranking.py`, regex pattern authoring for season parsing, and unit test generation in `tests/test_ranking.py` were performed with the assistance of Anthropic / Google DeepMind LLM coding assistants.
- **External Libraries & Frameworks:**
  - `FastAPI` (Python web framework, routing, request validation)
  - `Pydantic` (Data models and schema validation)
  - `pytest` & `httpx` (Automated integration testing via FastAPI `TestClient`)
  - `Tailwind CSS` (Utility-first styling in `ranking.js`)
  - `FontAwesome 6` (Icons in UI: `fa-ranking-star`, `fa-cloud-sun`, `fa-wallet`, etc.)
- **External APIs:** None. All scoring runs offline on local catalogue metadata.
