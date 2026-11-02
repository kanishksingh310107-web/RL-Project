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

## Status of Project Components

| Component | Status | Location | Notes |
| :--- | :--- | :--- | :--- |
| **User Authentication** | **IMPLEMENTED** | `app/auth.py` | Google Identity, email/password, phone, guest demo paths. |
| **Progressive Profiling** | **IMPLEMENTED** | `app/vectorizer.py`, `app/precision.py` | 22-dim, 41-dim, and 126-dim feature vectors with server privacy filter. |
| **Seasonal Ranking Engine** | **IMPLEMENTED** | `app/modules/ranking.py` | 6-component scoring, constraint filters, 4 views, questionnaire bug fix. |
| **Ranking Companion Tab** | **IMPLEMENTED** | `static/modules/ranking.js` | Stacked breakdown bars, date/budget inputs, static sample disclosure. |
| **Contextual LinUCB Bandit** | **IMPLEMENTED** | `app/rl_planner.py` | 7 canonical arms, 24-dim context, online Sherman-Morrison updates. |
| **Feedback Loop** | **IMPLEMENTED** | `app/api.py` | Accept/reject/modify actions update per-user bandit weights in SQLite. |
| **Honest RL Benchmark** | **IMPLEMENTED** | `scripts/evaluate.py` | Multi-seed, multi-persona, 150-round benchmark vs baseline, random, oracle. |
| **Destination Catalogue** | **SIMULATED** | `app/recommender.py` | 16 curated destinations with sample metadata (not live GDS/travel API). |
| **Live Telemetry & Feeds** | **SIMULATED** | `app/modules/ranking.py` | Offline placeholder (0.5 score); no real-time weather/transit API feeds. |
| **Evaluation Environment** | **SIMULATED** | `scripts/evaluate.py` | Synthetic user personas with sigmoid acceptance probability functions. |
| **Churn Prediction** | **FUTURE WORK** | — | Not implemented; proposed as post-submission extension. |
| **Real User Study** | **FUTURE WORK** | — | Real-world A/B testing with live human interaction logs. |

---

## Academic Disclosure & Authorship

Please refer to [ATTRIBUTION.md](ATTRIBUTION.md) for full authorship details, third-party libraries, and file-by-file AI assistance disclosures.
