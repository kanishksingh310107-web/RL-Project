# Presentation Deck Outline: RL-Based Proactive Travel Guide

**Target Presentation Length:** 8–10 Slides (10–12 minutes + 5 minutes Q&A)  
**Academic Target:** B.Tech CSE (AI/ML) Viva & Project Defense  
**Theme:** Contextual LinUCB Bandit, Transparent Explainability, and Honest Empirical Benchmarking.

---

### Slide 1: Title & Overview
- **Title:** RL-Based Proactive Travel Guide
- **Subtitle:** Contextual Linear Multi-Armed Bandits for Dynamic Itinerary Personalization
- **Team / Authors:** B.Tech CSE (AI/ML) Project Team (Person A: Pre-trip prep, Person B: Live trip, Person C: Ranking, Evaluation & Report)
- **Key Callout:** Live demonstration of an interactive FastAPI + SQLite + Tailwind web application utilizing Disjoint Contextual LinUCB (Li et al., WWW 2010).

---

### Slide 2: Motivation & Problem Statement
- **The Travel Dilemma:**
  - High-dimensional, subjective preferences (budget, pace, mobility, companions).
  - Questionnaire fatigue: users abandon long 50+ question forms.
  - Contextual sensitivity: morning vs afternoon preferences, pacing fatigue.
- **The Solution:**
  - Progressive Profiling (1-minute onboarding with deep optional layers).
  - Online Reinforcement Learning: Learn real-time preferences via immediate explicit and implicit feedback loops without cold-start failure.

---

### Slide 3: Architecture & Honest Implementation Matrix
- **Three-Tier Architecture:**
  - Frontend: Vanilla JS + Tailwind CSS + FontAwesome (Modular Companion tabs).
  - Backend: Asynchronous FastAPI REST services + auto-loading plugin system.
  - Database: Local SQLite relational storage (`travel_guide.db`).
- **Honest Status Table:**
  - **IMPLEMENTED:** LinUCB Bandit, Progressive Profiling (L1–L3), Seasonal Ranking, Feedback Loop, Evaluation Benchmark.
  - **SIMULATED:** 16-destination catalogue metadata, offline live-conditions placeholder (0.5), synthetic user evaluation environment.
  - **FUTURE WORK:** Churn prediction, real-time live flight/weather API feeds, human-subject user study.

---

### Slide 4: Progressive User Profiling
- **Level 1 (Basic Onboarding):** 3-step setup collecting goals, pace, companions, and budget $\to$ 22-dimensional state vector $s \in [0, 1]^{22}$.
- **Level 2 (Deep Personalisation):** Mobility tolerances, dietary constraints, schedule density, avoidance masks $\to$ 41-dimensional vector.
- **Level 3 (Precision Profile):** Adaptive conditional branching (83 questions, `show_if`), server-side validation, privacy filters $\to$ 126-dimensional state.
- **Key Viva Point:** Avoidance constraints act as negative masks, guaranteeing that unsafe activities (e.g. steep stairs for mobility-impaired travellers) are strictly filtered out before policy scoring.

---

### Slide 5: Seasonal & Multi-Criteria Destination Ranking
- **6-Component Transparent Scoring Formula ($0 \dots 100$ pts):**
  $$\text{Score} = 100 \times [0.25 V_{\text{interest}} + 0.20 V_{\text{season}} + 0.15 V_{\text{popularity}} + 0.15 V_{\text{feasibility}} + 0.10 V_{\text{live}} + 0.15 V_{\text{feedback}}]$$
- **Strict Month Regex & Circular Season Distance:**
  - Robust regex parsing handles date ranges crossing the new year (e.g. `"Nov to Mar"`).
  - Circular clock distance: In-season = 1.0, 1 mo away = 0.6, 2 mo away = 0.3, 3+ mo away = 0.0.
- **Hard Constraints as Absolute Filters:**
  - Daily budget cap exceedance, temporary closures, travel advisories immediately exclude items to an "Excluded" list with explicit rationales.
- **Four Specialized Views:** *Trending Now*, *Best This Season*, *Best For You*, *Best Feasible*.

---

### Slide 6: Reinforcement Learning Formulation (Contextual LinUCB)
- **Why LinUCB?** Disjoint linear multi-armed bandit (Li et al., 2010); avoids the sample inefficiency and instability of deep Q-learning in single-turn contextual recommendation.
- **State Space ($x \in \mathbb{R}^{24}$):**
  - Profile interests (8), Pacing/Comfort (4), Trip duration/budget (3), Slot progression (4), Activity attributes (5).
- **Action Space ($|\mathcal{A}| = 7$):**
  - Canonical Category Arms: `culture_history`, `nature_outdoors`, `food_dining`, `adventure`, `relaxation`, `shopping_local`, `scenic`.
- **Policy:**
  $$a_t = \arg\max_a \left( x_{t, a}^T \hat{\theta}_a + \alpha \sqrt{x_{t, a}^T A_a^{-1} x_{t, a}} \right)$$
- **Reward Loop:** Accept (+1.0), Reject (-1.0), Replace (-0.4 & +1.0), Implicit (+0.2). Updates $A_a \leftarrow A_a + x x^T$ and $b_a \leftarrow b_a + r x$ in real time.

---

### Slide 7: Diagnostic: Why Did LinUCB Lose in the Initial 20-Round Test?
- **The Teammate's Paradox:** Initial prototype showed LinUCB at 73.3% vs Static Baseline at 80.0%.
- **Four Critical Flaws Identified:**
  1. *Horizon Too Short:* 168 parameters cannot converge in 20 rounds (exploration penalty dominated).
  2. *Excessive Exploration:* $\alpha = 0.5$ forced random sampling over known good arms.
  3. *Unfair Baseline Advantage:* Baseline was handed ground-truth interests upfront and only cycled through the top 8 matching activities in short runs.
  4. *Coupled RNG Streams:* Single random seed interleaved decision probabilities.

---

### Slide 8: Rigorous RL Benchmark Results (150 Rounds, 30 Runs/Policy)
- **Empirical Results Table:**
  - **Oracle Upper Bound:** **86.3% $\pm$ 4.1%** (Theoretical ceiling from sigmoid reward model)
  - **LinUCB ($\alpha = 0.1$):** **83.0% $\pm$ 6.2%** (Cumulative reward: $+99.1$)
  - **LinUCB ($\alpha = 0.5$):** **80.2% $\pm$ 5.3%** (Cumulative reward: $+90.6$)
  - **Random:** **71.6% $\pm$ 4.4%** (Cumulative reward: $+64.9$)
  - **Static Baseline:** **69.9% $\pm$ 5.0%** (Cumulative reward: $+59.8$)
- **Learning Curve Trajectory:**
  - LinUCB crosses the static baseline at round ~30.
  - Asymptotic exploitation approaches within 3.3% of the Oracle ceiling.

---

### Slide 9: User Experience & Explainable UI
- **Stacked Color Breakdown Bars:**
  - Visual display of the 6 components per destination (Indigo: Interest, Emerald: Season, Amber: Popularity, Blue: Feasibility, Slate: Live, Rose: Feedback).
- **Interactive Controls:**
  - Dynamic travel date picker and daily budget cap input.
  - Transparent disclosure badge: "SIMULATED / STATIC DATA - catalogue is sample data".
- **Excluded Panel:** Clear explanation for filtered destinations.

---

### Slide 10: Limitations, Viva Takeaways & Future Work
- **Limitations:**
  - Synthetic sigmoid acceptance model; no real human user clickstream data.
  - Absence of real-world live APIs (weather/flight feeds).
  - Item repetition in converged policy (requires diversity penalty).
- **Key Viva Takeaway:**
  - "We do not claim RL magically beats a static heuristic in every scenario; we proved empirically that LinUCB pays an initial exploration cost but outperforms static heuristics once the horizon exceeds 30 rounds."
- **Future Directions:** Live GDS integration, post-trip feedback loops, and churn prediction modeling.
