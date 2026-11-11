# Project Sources, Attribution & AI Disclosure

## 1. Project Overview

**Project Title:** RL-Based Proactive Travel Guide  
**Course:** B.Tech Computer Science & Engineering (AI/ML)  
**Submission Date:** 3 November 2026  
**Core Machine Learning Architecture:** Contextual Linear Bandit — **Disjoint LinUCB** (Li, Chu, Langford, & Schapire, *World Wide Web Conference (WWW)*, 2010), **NOT Q-learning**.

---

## 2. Theoretical Clarification: Why Contextual LinUCB (Not Q-Learning)?

Previous draft documentation incorrectly referred to the learning algorithm as "Q-learning". This is technically inaccurate and has been corrected throughout the project:

- **What is implemented:** Disjoint Contextual Multi-Armed Bandit using **LinUCB**. Each discrete activity category represents a bandit arm $a \in \mathcal{A}$ ($|\mathcal{A}| = 7$). For each arm, the agent maintains an independent covariance matrix $A_a \in \mathbb{R}^{24 \times 24}$ and bias vector $b_a \in \mathbb{R}^{24}$. The ridge-regression parameter $\hat{\theta}_a = A_a^{-1} b_a$ is updated in closed form using Sherman-Morrison matrix updates.
- **Why not Q-learning?** Q-learning is a Temporal Difference (TD) reinforcement learning algorithm for sequential Markov Decision Processes (MDPs) where actions alter the state transition dynamics $P(s' | s, a)$ across multi-step delayed-reward horizons. In pre-trip itinerary recommendation, recommending an attraction in one time slot does not alter the underlying stochastic environmental dynamics, and user feedback (accept/reject) is immediate for each item. LinUCB directly balances exploration (upper confidence bound bonus) and exploitation in contextual settings without the instability and high sample-complexity of deep Q-learning.

---

## 3. External Libraries & Tools Used

All dependencies are defined in `requirements.txt` and `requirements-dev.txt`:

| Library / Tool | Version | Purpose in Project | Source / Reference |
| :--- | :--- | :--- | :--- |
| **FastAPI** | $\ge 0.110.0$ | Asynchronous REST API routing, query parameter validation, and OpenAPI documentation | https://fastapi.tiangolo.com/ |
| **Uvicorn** | $\ge 0.28.0$ | ASGI server implementation running the local application | https://www.uvicorn.org/ |
| **Pydantic** | $\ge 2.6.0$ | Data validation and schema enforcement for API payloads | https://docs.pydantic.dev/ |
| **NumPy** | $\ge 1.26.0$ | Linear algebra for LinUCB ($A^{-1} b$, matrix outer products), random number generation, vectorization | https://numpy.org/ |
| **Matplotlib** | $\ge 3.8.0$ | Empirical learning curves and evaluation trajectory visualization | https://matplotlib.org/ |
| **Requests / HTTPX** | $\ge 2.31 / \ge 0.27$ | HTTP clients for test execution via Starlette TestClient | https://www.python-httpx.org/ |
| **Pytest** | $\ge 8.0.0$ | Automated test runner and test fixture isolation | https://pytest.org/ |
| **SQLite3** | Standard Library | Embedded ACID relational persistence (`travel_guide.db`) | Python Standard Library |
| **Tailwind CSS** | CDN v3 | Responsive styling for UI views and Companion modals | https://tailwindcss.com/ |
| **Font Awesome** | CDN v6 | UI typography and category iconography | https://fontawesome.com/ |

---

## 4. Work Breakdown & Honest File-by-File AI Assistance Disclosure

In accordance with academic integrity guidelines, the table below documents the authorship and specific nature of AI assistance for each file in the repository:

| File / Component | Primary Author | AI Assistance Used? | Description of Human vs. AI Contributions |
| :--- | :--- | :--- | :--- |
| `app/questionnaire.py` | Teammate | Yes | Questionnaire structure authored with LLM brainstorming; question bank finalized by team. |
| `app/auth.py` | Teammate | Yes | Salted SHA-256 hashing and token flows; Google auth token verification scaffold assisted by LLM. |
| `app/vectorizer.py` | Teammate | Yes | Linear mapping from questionnaire answers to 22-dim and 41-dim normalized feature representations. |
| `app/precision.py` | Teammate | Yes (Claude) | Level 3 precision profile, conditional `show_if` rules, and privacy filters developed with Claude assistance. |
| `app/recommender.py` | Teammate | Yes | Static destination catalogue (16 destinations) and baseline heuristic scoring function. |
| `app/itinerary_generator.py` | Teammate | Yes | Heuristic day-by-day scheduler applying opening hours, cost, and geographic proximity rules. |
| `app/rl_planner.py` | Teammate | Yes | Contextual LinUCB matrix updates and 24-dimensional feature extraction code assisted by LLM. |
| `app/evaluation.py` | Teammate | Yes | Initial 20-round prototype benchmark comparing LinUCB vs static keyword ranking. |
| `app/modules/ranking.py` | Person C | Yes (Claude / Gemini) | Designed 6-component scoring system, strict regex month parser, hard constraint filters, and bug fixes for questionnaire answer extraction. |
| `app/core/*` | Person C | Yes (Gemini / Antigravity) | Centralized configuration, Pydantic shared schemas (`Place`, `TripPlan`, etc.), centralized assumptions (`assumptions.py`), SQLite persistence (`stores.py`), and unified profile loader fixing the interest bug. |
| `app/providers/*` | Person C | Yes (Gemini / Antigravity) | Geoapify geocoding & places provider with 7-day TTL caching, 2500 calls/day credit guard, and Open-Meteo historical climate & forecast provider. |
| `static/modules/ranking.js` | Person C | Yes (Claude / Gemini) | Frontend Companion tab featuring stacked 6-color breakdown bars, input controls, and sample data disclosure banners. |
| `tests/test_ranking.py` | Person C | Yes (Claude / Gemini) | Unit tests (16 tests) covering weight normalization, circular season distance, budget filtering, and evaluation metrics. |
| `scripts/evaluate.py` | Person C | Yes (Claude / Gemini) | Engineered multi-persona (3), multi-seed (10), 150-round benchmark with separate RNGs and alpha sweeps. |
| `docs/ranking.md` | Person C | Yes (Claude / Gemini) | Technical specification, verified test results table, and limitation documentation. |
| `docs/evaluation.md` | Person C | Yes (Claude / Gemini) | Detailed diagnostic report, empirical data table, and honest interpretation of bandit dynamics. |
| `docs/report/*` | Person C | Yes (Claude / Gemini) | Academic report, 10-slide presentation deck outline, and comprehensive viva preparation sheet. |
| `ATTRIBUTION.md` & `README.md` | Atharva / Person C | Yes (Claude / Gemini) | Comprehensive attribution cleanup, Q-learning correction, verified capability matrix, and execution instructions. |
| `tests/test_rl_policy.py` | Atharva | Yes (Claude / Gemini) | Unit tests verifying Sherman-Morrison rank-1 inverse updates match direct matrix inversion within machine precision. |
| `docs/evaluation_results.md` | Atharva | Yes (Claude / Gemini) | Pre-registered 100-seed empirical LinUCB vs. static baseline benchmark reporting means, standard deviations, and 95% confidence intervals. |
| `docs/bugs/atharva.md` | Atharva | Yes | Click-through verification bug log capturing external UI and lifecycle issues for teammates. |

---

## 5. Verification Statement

No synthetic benchmark results, mock APIs, or invented performance metrics have been claimed. All quantitative figures reported in documentation and presentation slides are derived directly from code executed in this repository (`pytest tests -v` and `python scripts/evaluate.py`).
