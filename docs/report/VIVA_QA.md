# Viva Voce Preparation & Technical Q&A

**Subject:** B.Tech CSE (AI/ML) Project Defense  
**Project:** RL-Based Proactive Travel Guide  
**Integrator / Person C Reference**  

---

### Q1: What is Contextual LinUCB, and how does it work mathematically?
**Answer:**
Contextual LinUCB (Linear Upper Confidence Bound; Li et al., WWW 2010) is a multi-armed bandit algorithm for sequential decision problems where context vectors guide reward prediction. It assumes the expected payoff for pulling arm $a$ given context vector $x \in \mathbb{R}^d$ is linear:
$$\mathbb{E}[r \mid x, a] = x^T \theta_a^*$$
For each arm $a$, the agent maintains an inverted covariance matrix $A_a^{-1}$ where $A_a = D_a^T D_a + I_d$ (initialized to $I_d$), and bias vector $b_a = D_a^T c_a$ (initialized to $\mathbf{0}$). The ridge-regression estimator is $\hat{\theta}_a = A_a^{-1} b_a$.

To balance exploration and exploitation, it selects the arm that maximizes the upper confidence bound:
$$a_t = \arg\max_{a \in \mathcal{A}} \left( x^T \hat{\theta}_a + \alpha \sqrt{x^T A_a^{-1} x} \right)$$
The first term ($x^T \hat{\theta}_a$) represents exploitation (predicted reward), while the second term ($\alpha \sqrt{x^T A_a^{-1} x}$) represents the standard deviation of the estimate, acting as an exploration bonus for under-explored regions of the feature space.

---

### Q2: Why is the bandit "disjoint" rather than "shared" or "hybrid"?
**Answer:**
In Disjoint LinUCB, each canonical arm maintains its own independent parameters $(A_a, b_a, \hat{\theta}_a)$, sharing no weights across arms. This architecture was chosen because user preferences across distinct travel categories are heterogeneous: a traveller's reaction to cultural temple visits (e.g., highly influenced by interest in history and walking tolerance) has entirely different feature correlations than their reaction to an extreme adventure sport or nightlife dining. A shared parameter space would force unnatural weight coupling across fundamentally different experiences.

---

### Q3: What is the exact distinction between an "arm" and an "action" in your system?
**Answer:**
- **Arm:** A discrete behavioral category in the bandit policy. We define 7 canonical arms: `culture_history`, `nature_outdoors`, `food_dining`, `adventure`, `relaxation`, `shopping_local`, and `scenic`. The bandit policy maintains mathematical weights for these 7 arms.
- **Action:** The concrete activity recommended to the traveller (e.g. *"Sunrise walking tour through Arashiyama Bamboo Grove"*). The recommender maps candidate activities to their respective category arms, computes LinUCB scores for each candidate activity, and serves the top-scoring concrete activity.

---

### Q4: How is the reward function structured, and why do we distinguish explicit from implicit feedback?
**Answer:**
The reward function in `/api/itinerary/feedback` maps real user interactions to numerical scalar rewards:
- **Explicit Accept ($+1.0$):** Strong positive reinforcement when the user taps "Keep" or approves an activity.
- **Explicit Reject ($-1.0$):** Strong negative penalty when the user deletes or rejects an activity. The rejected activity is blacklisted for that specific trip.
- **Modify / Replace ($-0.4$ on old, $+1.0$ on new):** Replacing an activity signals moderate dissatisfaction with the replaced item ($-0.4$) and strong positive intent for the alternative ($+1.0$).
- **Implicit Accept ($+0.2$):** Passive retention when a user exports or saves an itinerary without modifying a suggested activity signals weak positive satisfaction.

Explicit feedback reflects conscious evaluation, whereas implicit feedback provides high-volume, low-friction weak supervision.

---

### Q5: Why are the evaluation results based on simulated users rather than real users?
**Answer:**
In offline reinforcement learning, evaluating an adaptive policy against live humans requires either an active deployment with high traffic or counterfactual off-policy evaluation (OPE) on randomized exploration logs (such as inverse propensity scoring on the Open Bandit Dataset). Because this is an undergraduate prototype without live user traffic, we follow the established literature (e.g., Chapelle & Li, 2011) by simulating personas with ground-truth latent preferences. We explicitly declare this limitation in the UI, code, and documentation: *"SIMULATED / STATIC DATA"*.

---

### Q6: Why did the static baseline beat LinUCB in the initial 20-round prototype (80.0% vs 73.3%)?
**Answer:**
Through empirical diagnosis, we identified four structural reasons:
1. **Short Horizon ($T = 20$):** With 7 arms and 24 dimensions, LinUCB must learn 168 parameters. In 20 rounds, each arm receives $< 3$ pulls. LinUCB was still in its cold-start exploration phase and paid an exploration penalty.
2. **Hard-Coded $\alpha = 0.5$:** A high exploration parameter forced LinUCB to pull uncertain, suboptimal arms rather than exploit early positive rewards.
3. **Unfair Baseline Advantage:** The static baseline was given the user's ground-truth stated interests and cycled through activities via `b_ranked[(t-1) % len(b_ranked)]`. Over 20 rounds, it almost exclusively sampled from the 8 curated activities matching the user's top interests, giving it an artificial head-start without needing to learn anything.
4. **Interleaved RNG Streams:** Both algorithms shared a single global `np.random` stream, creating artifactual coupling.

---

### Q7: Under what conditions does LinUCB actually outperform the static baseline?
**Answer:**
When we extended the benchmark to **150 rounds** across **10 independent seeds** and **3 personas** using separate RNGs:
- **LinUCB ($\alpha = 0.1$) achieved an 83.0% $\pm$ 6.2% acceptance rate** and **+99.1 cumulative reward**, approaching within 3.3% of the theoretical Oracle upper bound (86.3%).
- **Static Baseline dropped to 69.9% $\pm$ 5.0%** (cumulative reward: +59.8).
- **Reason:** Once interaction rounds exceed ~30–35, the static baseline's cycling exhausts the matching activities and is forced to recommend low-preference activities. LinUCB, by contrast, converges on the user's latent preferences and continuously exploits high-reward categories.

---

### Q8: Why are the ranking weights described as "assumptions" in the API and UI?
**Answer:**
The 6 scoring weights (Interest 0.25, Season 0.20, Popularity 0.15, Feasibility 0.15, Live 0.10, Feedback 0.15) are human-designed heuristic defaults, not learned econometric parameters. Presenting fixed weights as "optimal AI scores" would be intellectually dishonest. We explicitly label them as `ASSUMPTIONS` in the API response and UI banner, and allow users to override them dynamically via query parameters (`w_interest`, `w_season`, etc.), which the backend re-normalizes to sum to 1.0.

---

### Q9: What was the questionnaire interest bug, and how did it affect ranking?
**Answer:**
`get_user_context(user_id)["basic"]` stores legacy slider values in `basic["interests"]`, whereas questionnaire answers like `travel_goals: ["nature", "culture"]` are stored in `basic["raw_answers_json"]`. Additionally, user vocabulary (`"historic"`, `"trying_new_foods"`) differed from catalogue tags (`"history"`, `"food"`).
A naive reader retrieved 0 interests for Kyoto. Consequently, Tokyo (0 shared tags with a nature lover) topped the ranking because Season (20%) + Popularity (15%) + Feasibility (15%) = 50% outweighed the zero interest score.
We resolved this in `extract_user_interests()` by aggregating across all raw answer fields and mapping synonyms via `GOAL_MAPPING`. Following the fix, Kyoto receives 25.0 interest points and ranks #1 overall (83.00 pts), while Tokyo ranks #6 (70.83 pts).

---

### Q10: How does the system handle hard constraints versus soft preferences?
**Answer:**
- **Hard Constraints (Filters):** Hard constraints represent absolute boundaries that must never be violated (e.g. daily budget cap exceeded, manual destination closure, active travel advisory, or physical mobility avoidances). Hard constraints are implemented as deterministic filters: candidate items that violate a constraint are immediately excluded and added to an `excluded` list with an explicit reason. They are never scored by the model.
- **Soft Preferences (Scores):** Soft preferences represent trade-offs (e.g. degree of interest match, climate proximity, popularity, past ratings). These are scored continuously ($0.0 \dots 1.0$) and weighted to produce a ranking among feasible candidates.
