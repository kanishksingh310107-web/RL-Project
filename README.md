# RL-Based Proactive Travel Guide

A machine learning-driven web application that personalises travel destination recommendations and activity-level itineraries using a **Contextual Linear Multi-Armed Bandit (Disjoint LinUCB)**.

Developed as a B.Tech Computer Science & Engineering (AI/ML) capstone student project.

---

## Quick Start & Setup

### 1. Environment Setup
```bash
# Clone the repository and enter the directory
git checkout feat/ranking-eval

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # On Windows
source .venv/bin/activate  # On macOS/Linux

# Install required dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Run the Application
```bash
python main.py
```
- **Web Interface:** [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Run Test Suites
```bash
# Run isolated unit & integration test suite (using isolated temporary DB)
python -m pytest tests -v

# Run legacy end-to-end integration test runner
python run_tests.py
```

### 4. Run the RL Evaluation Benchmark
```bash
# Executes 210 simulation runs (3 personas x 10 seeds x 7 policies x 150 rounds)
# Generates docs/eval_results.csv and docs/eval_curve.png
python scripts/evaluate.py
```

---

## System Architecture

The project consists of a FastAPI service backed by SQLite and a responsive vanilla-JS frontend styled with Tailwind CSS:

1. **Progressive Profiling:**
   - **Level 1 (Basic Onboarding):** 3-step questionnaire capturing core goals, companions, and budget tier (22-dim vector).
   - **Level 2 (Deep Personalisation):** Avoidance masks, mobility constraints, stay style, and schedule density (41-dim vector).
   - **Level 3 (Precision Profile):** Adaptive conditional questionnaire expanding the state to 126 dimensions with privacy controls.
2. **Seasonal & Multi-Criteria Destination Ranking (`app/modules/ranking.py`):**
   - 6-component explainable scoring (Interest 25%, Season 20%, Popularity 15%, Feasibility 15%, Live 10%, Feedback 15%).
   - Strict month regex parsing with circular year-end wrap-around distance.
   - Hard constraint filtering (budget caps, closures, travel advisories).
   - Four dedicated perspectives: *Overall*, *Trending Now*, *Best This Season*, *Best For You*, *Best Feasible*.
3. **Contextual LinUCB Itinerary Planner (`app/rl_planner.py`):**
   - Disjoint Contextual Multi-Armed Bandit (Li et al., WWW 2010).
   - **Arms ($|\mathcal{A}| = 7$):** Activity categories (`culture_history`, `nature_outdoors`, `food_dining`, `adventure`, `relaxation`, `shopping_local`, `scenic`).
   - **Context ($x \in \mathbb{R}^{24}$):** User profile + trip duration/budget + slot progression + activity attributes.
   - **Reward Feedback Loop:** Explicit Accept (+1.0), Reject (-1.0), Modify (-0.4 / +1.0), and Implicit Keep (+0.2).
4. **Plugin Architecture (`app/modules/` & `static/modules/`):**
   - Self-registering modules discovered automatically at startup.
   - Accessible via the "Companion" button in the navigation header.

---

## Verified Capability Matrix

| Capability / Subsystem | Verification Status | Location | Notes & Verification Scope |
| :--- | :--- | :--- | :--- |
| **Contextual LinUCB Bandit** | Verified by Automated Test & Click-Through | `app/rl_planner.py` | 7 canonical arms, 24-dim context. Sherman-Morrison rank-1 updates mathematically verified in `tests/test_rl_policy.py`. |
| **Comparative RL Benchmark** | Verified by Automated Test & Click-Through | `app/evaluation.py` | 100-seed Monte Carlo evaluation reporting empirical mean ± 95% CI. Verified in `run_tests.py` and `docs/evaluation_results.md`. |
| **Trip Preparation Module (`prep`)** | Verified by Automated Test & Click-Through | `app/modules/prep.py` | Live Open-Meteo weather forecast, dynamic packing checklist, document requirements, Beta-Bernoulli reminder bandit. 16 tests passing in `tests/test_prep.py`. |
| **Live Trip Companion (`live`)** | Verified by Automated Test & Click-Through | `app/modules/live.py` | During-trip timeline, activity status updates, simulated conditions/alerts, targeted replanning, post-trip feedback questionnaire. 13 tests passing in `tests/test_live.py`. |
| **Real-Time Places & Geocoding (`places`)** | Verified by Automated Test & Click-Through | `app/modules/places.py` | Dynamic India location geocoding & live Overpass attraction queries. 12 tests passing in `tests/test_places.py` & `tests/test_places_api.py`. |
| **Timed Itinerary Engine (`timed_itinerary`)** | Verified by Automated Test & Click-Through | `app/services/timed_itinerary.py` | Structured 09:00–21:00 daily scheduling (Activities, Transit, Meals, Rest), relaxed/balanced/active pace modes. 7 tests passing in `tests/test_timed_itinerary.py`. |
| **Seasonal Ranking Engine (`ranking`)** | Verified by Automated Test & Click-Through | `app/modules/ranking.py` | 6-component multi-criteria scoring, month regex parsing, circular season distance, budget filtering. 16 tests passing in `tests/test_ranking.py`. |
| **Progressive Profiling** | Verified by Automated Test & Click-Through | `app/vectorizer.py`, `app/precision.py` | 22-dim, 41-dim, and 126-dim feature vectors with server privacy filter. Verified in `run_tests.py`. |
| **User Authentication** | Verified by Automated Test & Click-Through | `app/auth.py` | Salted SHA-256 password hashing, Google Identity Services mock, guest login. Verified in `run_tests.py`. |
| **Academic Model Inspector** | Verified by Automated Test & Click-Through | `static/app.js` | State vector breakdown, MDP formulation, policy weights, and comparative simulation panel. Verified in `run_tests.py`. |
| **Destination Catalogue** | Exists But Not Verified (Sample Data) | `app/recommender.py` | 16 curated destinations with sample metadata (offline photo fallbacks, sample attractions). |
| **Live Telemetry in Ranking** | Exists But Not Verified (Simulated) | `app/modules/ranking.py` | Ranking component uses neutral 0.5 score placeholder (live weather is integrated separately in `prep.py`). |
| **Churn Prediction & User Study** | Out of Scope / Roadmap | — | Proposed post-submission academic extensions. |

---

## Academic Disclosure & Authorship

Please refer to [ATTRIBUTION.md](ATTRIBUTION.md) for full authorship details, third-party libraries, and file-by-file AI assistance disclosures.
