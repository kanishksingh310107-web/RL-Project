# B.Tech Project Report: RL-Based Proactive Travel Guide

**Course:** B.Tech Computer Science & Engineering (Artificial Intelligence & Machine Learning)  
**Academic Submission:** 3 November 2026  
**Project Role:** Person C (Seasonal Ranking, Honest Evaluation, Report/PPT Content, Integration)  

---

## 1. Executive Summary

Traditional travel recommendation engines rely on static filtering or collaborative filtering algorithms that suffer from severe cold-start challenges, cannot handle time-sensitive contextual shifts (such as trip pacing or morning vs. afternoon slots), and fail to adapt interactively to user feedback.

This project implements an end-to-end travel personalization system combining:
1. **Multi-Tier Progressive Profiling:** Eliciting user preferences across 3 progressive tiers ($s \in \mathbb{R}^{22} \to \mathbb{R}^{41} \to \mathbb{R}^{126}$) with server-enforced privacy filtering.
2. **Seasonal & Multi-Criteria Destination Ranking:** A 6-component explainable scoring engine evaluating destinations across Interest Match, Season Suitability, Popularity, Feasibility, Live Conditions, and User Feedback, combined with strict hard constraint filtering.
3. **Contextual Linear Multi-Armed Bandit (Disjoint LinUCB):** Online reinforcement learning at the itinerary level that balances exploration and exploitation across 7 canonical activity categories using a 24-dimensional continuous context vector.
4. **Honest Empirical Evaluation:** A rigorous, reproducible benchmark across 3 user personas, 10 random seeds, and 150 interaction rounds diagnosing earlier short-horizon anomalies and establishing that LinUCB achieves an **83.0% acceptance rate**, operating within 3.3% of the theoretical Oracle upper bound.

---

## 2. Problem Statement & Motivation

Travel planning is inherently high-dimensional, subjective, and dynamic:
- **Cold-Start & Preference Ambiguity:** Travellers rarely know all exact attractions they want to visit in advance, and full questionnaires induce user fatigue.
- **Dynamic Context Dependency:** An attraction ideal for an energetic morning slot is inappropriate for an exhausted evening slot; pacing, budget, and walking tolerances must constrain recommendations.
- **Explainability Requirement:** Black-box recommendations diminish user trust. Travellers need to know *why* an activity or destination was recommended.
- **The RL Opportunity:** Multi-Armed Bandits offer a principled framework to learn individual traveller preferences in real time from minimal explicit and implicit feedback signals.

---

## 3. System Architecture & Component Status

The application is structured as a modular FastAPI backend with embedded SQLite persistence and a responsive vanilla-JavaScript frontend.

### Component Implementation Status Matrix

| Component | Status | Implementation File | Verification & Notes |
| :--- | :--- | :--- | :--- |
| **User Authentication** | **IMPLEMENTED** | `app/auth.py` | Google Identity, salted email/password, phone, guest demo paths. |
| **Progressive Profiles (L1–L3)** | **IMPLEMENTED** | `app/vectorizer.py`, `app/precision.py` | Validated by unit tests; privacy filter masks sensitive items. |
| **Destination Recommender** | **IMPLEMENTED** | `app/recommender.py` | 16 curated destinations with tag matching and baseline scores. |
| **Seasonal Ranking Engine** | **IMPLEMENTED** | `app/modules/ranking.py` | 6 components, regex month parser, 4 specialized views, bug fix. |
| **Ranking Companion Tab** | **IMPLEMENTED** | `static/modules/ranking.js` | Stacked breakdown bars, date/budget controls, disclosure banner. |
| **Contextual LinUCB Agent** | **IMPLEMENTED** | `app/rl_planner.py` | Disjoint LinUCB with closed-form Sherman-Morrison matrix updates. |
| **Interactive Feedback Loop** | **IMPLEMENTED** | `app/api.py` | Accept (+1.0), Reject (-1.0), Modify (-0.4/+1.0), Implicit (+0.2). |
| **Honest Evaluation Suite** | **IMPLEMENTED** | `scripts/evaluate.py` | Multi-seed benchmark generating CSV results and learning curve plot. |
| **Catalogue Metadata** | **SIMULATED** | `app/recommender.py` | Curated sample dataset of 16 destinations and 30 activities. |
| **Live Telemetry & Feeds** | **SIMULATED** | `app/modules/ranking.py` | Neutral placeholder (0.5 score); no external live API feed exists. |
| **Simulation Environment** | **SIMULATED** | `scripts/evaluate.py` | Synthetic user personas with sigmoid acceptance probability functions. |
| **Churn Prediction** | **FUTURE WORK** | — | Predictive retention modeling; out of current project scope. |
| **Live User Field Study** | **FUTURE WORK** | — | Real-world human subject trial with observational clickstream data. |

---

## 4. Reinforcement Learning Mathematical Formulation

### 4.1 Algorithm: Disjoint Contextual LinUCB (Li et al., 2010)

The core recommendation engine models itinerary activity selection as a **Contextual Linear Multi-Armed Bandit**. Rather than treating recommendation as an unguided heuristic, LinUCB assumes the expected reward $r_{t, a}$ of an arm $a$ is linear in its $d$-dimensional context vector $x_{t, a}$:
$$\mathbb{E}[r_{t, a} \mid x_{t, a}] = x_{t, a}^T \theta_a^*$$
where $\theta_a^*$ is an unknown coefficient vector specific to arm $a$.

For each arm $a \in \mathcal{A}$, the policy maintains:
- $A_a \in \mathbb{R}^{d \times d}$: Regularized design matrix, initialized to the identity matrix $I_d$.
- $b_a \in \mathbb{R}^d$: Accumulated reward-weighted context vector, initialized to $\mathbf{0}_d$.

At step $t$, the ridge-regression weight vector is estimated via:
$$\hat{\theta}_a = A_a^{-1} b_a$$
The action is selected by maximizing the upper confidence bound:
$$a_t = \arg\max_{a \in \mathcal{A}} \left( x_{t, a}^T \hat{\theta}_a + \alpha \sqrt{x_{t, a}^T A_a^{-1} x_{t, a}} \right)$$
where $\alpha > 0$ controls the exploration-exploitation trade-off. Upon observing reward $r_t$, the parameters are updated in closed form:
$$A_{a_t} \leftarrow A_{a_t} + x_{t, a_t} x_{t, a_t}^T, \quad b_{a_t} \leftarrow b_{a_t} + r_t x_{t, a_t}$$

### 4.2 State Space: 24-Dimensional Context Vector ($x \in \mathbb{R}^{24}$)

Extracted by `extract_context_vector()` in `app/rl_planner.py`:
1. **User Profile Interests (Indices 0..7):** Binary indicators for Culture/History, Nature/Outdoors, Food/Dining, Adventure, Relaxation, Shopping, Photography, Architecture.
2. **User Comfort & Pacing (Indices 8..11):** Continuous pace preference ($0 \dots 1$), crowd tolerance ($0 \dots 1$), budget tier normalized ($0.1 \dots 1.0$), and walking tolerance ($0.2 \dots 1.0$).
3. **Trip Context (Indices 12..14):** Normalized duration $\min(1.0, \text{days}/14)$, daily budget normalized, trip pace index.
4. **Slot Context (Indices 15..18):** Day progression ratio ($t / T$), and one-hot slot indicators (`slot_is_morning`, `slot_is_afternoon`, `slot_is_evening`).
5. **Candidate Activity Attributes (Indices 19..23):** Category match with stated interests, physical intensity, crowd level, normalized cost, and geographic proximity bonus.

### 4.3 Action Space: 7 Canonical Category Arms

$$\mathcal{A} = \{\text{culture\_history}, \text{nature\_outdoors}, \text{food\_dining}, \text{adventure}, \text{relaxation}, \text{shopping\_local}, \text{scenic}\}$$
Each arm corresponds to a distinct behavioral category. The policy evaluates all candidate activities from `CURATED_ACTIVITIES`, maps each to its arm, predicts the UCB score, and selects the highest-scoring activity.

### 4.4 Reward Feedback Signal

The feedback endpoint (`/api/itinerary/feedback`) captures 4 distinct user signals:
- **Explicit Accept ($+1.0$):** User approves the suggested activity.
- **Explicit Reject ($-1.0$):** User rejects the activity. The activity is blacklisted for the specific trip, and a negative penalty updates the policy arm.
- **Modify / Replace ($-0.4$ & $+1.0$):** Replacing an activity penalizes the replaced activity moderately ($-0.4$) while rewarding the incoming selection ($+1.0$).
- **Implicit Accept ($+0.2$):** Activities left unchanged in a saved or exported itinerary receive weak positive confirmation.

### 4.5 Hard Safety Constraints

Hard constraints operate as deterministic filters preceding the policy:
- **Operating Hours:** Activities closed during the targeted slot are filtered.
- **Daily Budget Limit:** Activities whose individual cost causes daily spend to exceed the budget cap are excluded.
- **Geographic Proximity:** Consecutive activities in a half-day slot must fall within reasonable transit radius.

---

## 5. Seasonal & Multi-Criteria Ranking Module

### 5.1 Formulation & Explainability
Destination ranking evaluates the 16 curated destinations across 6 transparent components:
$$\text{Score} = 100 \times \left( 0.25 V_{\text{interest}} + 0.20 V_{\text{season}} + 0.15 V_{\text{pop}} + 0.15 V_{\text{feas}} + 0.10 V_{\text{live}} + 0.15 V_{\text{feed}} \right)$$

1. **Interest Match ($V_{\text{interest}} \in [0, 1]$):** Normalized overlap of user tags against catalogue tags.
2. **Season Suitability ($V_{\text{season}} \in [0, 1]$):** Circular month distance. A strict regex parses month names from catalogue strings (e.g. `"November to March"`). Scoring: in-season = 1.0; 1 month away = 0.6; 2 months away = 0.3; 3+ months away = 0.0.
3. **Popularity ($V_{\text{pop}} \in [0, 1]$):** Static heuristic from `crowd_level` and `is_trending`. Labelled as static sample data.
4. **Feasibility ($V_{\text{feas}} \in [0, 1]$):** Average of budget cap fit and companion compatibility.
5. **Live Conditions ($V_{\text{live}} = 0.5$):** Offline neutral placeholder.
6. **Past Feedback ($V_{\text{feed}} \in [0, 1]$):** 1.0 if shortlisted, $\frac{r-1}{4}$ if past trip rated, 0.5 if neutral.

### 5.2 Critical Questionnaire Bug Resolution
- **Identified Bug:** Profile questionnaire answers (`travel_goals` like `["nature", "culture"]`) were stored in `raw_answers_json`, while `basic["interests"]` only contained legacy slider fields. A naive reader received 0 interests, causing Tokyo (a high-popularity, high-crowd spot) to outrank Kyoto for a nature lover.
- **Fix:** `extract_user_interests()` reads from all raw answer sources and normalizes synonyms via `GOAL_MAPPING`.
- **Verified Result:** Kyoto receives 25.0 interest points and ranks #1 overall (83.00 pts), while Tokyo drops to #6 (70.83 pts).

---

## 6. Honest RL Evaluation Findings

### 6.1 Diagnostic Summary of the Teammate's Benchmark
The initial benchmark showed LinUCB underperforming the static baseline (73.3% vs 80.0%). Our diagnostic proved:
1. **Horizon was too short (20 rounds):** 168 parameters cannot converge in 20 rounds.
2. **Exploration constant was excessive ($\alpha = 0.5$):** Induced needless random exploration.
3. **Baseline had an unfair heuristic advantage:** Given ground-truth interests upfront, cycling through top matches.
4. **Random draws were interleaved:** Single random stream caused artifactual coupling.

### 6.2 Rigorous Benchmark Results (150 Rounds, 3 Personas $\times$ 10 Seeds = 30 Runs)

| Policy | $\alpha$ | Acceptance Rate (Mean $\pm$ Std) | Cumulative Reward (Mean $\pm$ Std) |
|---|---|---|---|
| **Oracle** (Theoretical Ceiling) | — | **86.3% $\pm$ 4.1%** | **+108.8 $\pm$ 12.2** |
| **LinUCB** | 0.1 | **83.0% $\pm$ 6.2%** | **+99.1 $\pm$ 18.4** |
| **LinUCB** | 0.5 | **80.2% $\pm$ 5.3%** | **+90.6 $\pm$ 15.8** |
| **LinUCB** | 0.3 | **79.8% $\pm$ 5.4%** | **+89.4 $\pm$ 16.3** |
| **LinUCB** | 1.0 | **78.6% $\pm$ 4.7%** | **+85.9 $\pm$ 14.0** |
| **Random** | — | **71.6% $\pm$ 4.4%** | **+64.9 $\pm$ 13.1** |
| **Static Baseline** | — | **69.9% $\pm$ 5.0%** | **+59.8 $\pm$ 15.0** |

**Key Takeaway:** Given sufficient interaction rounds ($T \ge 35$), Contextual LinUCB with moderate exploration ($\alpha = 0.1$) decisively beats the static baseline ($83.0\%$ vs $69.9\%$, $p < 0.001$), closing 80% of the gap between random selection and the theoretical Oracle limit.

---

## 7. Limitations & Future Work

1. **Simulated User Environment:** Synthetic agents with static sigmoid acceptance probabilities cannot mirror human emotional nuance, budget fatigue, or weather disappointment.
2. **Absence of Real Telemetry:** Live transit delays, weather alerts, and flight surges are simulated via static placeholders.
3. **Item-Level Diversity Deficit:** Once LinUCB discovers that a user loves "culture_history", it repeatedly serves the highest-scoring temple without penalty. Future work must integrate a decaying repetition penalty or determinantal point process (DPP) diversity layer.
4. **Churn Prediction:** Unimplemented in the current prototype; flagged for post-submission development.

---

## 8. Conclusion

This project demonstrates the practical viability of Contextual Linear Multi-Armed Bandits for interactive travel recommendation. By coupling LinUCB with progressive profiling, multi-criteria ranking, and transparent explainability breakdowns, the system bridges the gap between theoretical reinforcement learning and user-centered decision support.
