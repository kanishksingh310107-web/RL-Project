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

### Q6: Does LinUCB beat a static baseline when user profiles are accurate?
**Answer (Honest Viva Answer):**
**No, when user profiles are accurate, a simple static matcher is as good as LinUCB — the honest result is a statistical tie.**
- When compared against a realistic, fair baseline (Greedy Top-Match) over 150 rounds:
  - **Greedy Top-Match:** $84.7\% \pm 5.5\%$ acceptance rate.
  - **Random within Match:** $85.3\% \pm 5.1\%$ acceptance rate.
  - **LinUCB ($\alpha = 0.1$):** $83.3\% \pm 5.9\%$ acceptance rate.
  - **Theoretical Oracle Ceiling:** $86.3\% \pm 4.2\%$.
- The reason is intuitive: if the profile accurately lists the user's top categories and catalogue items match them well, a static keyword matcher greedily serves what the user likes with zero cold-start exploration cost. LinUCB pays an initial exploration dividend ($\alpha \sqrt{x^T A^{-1} x}$) to discover what the static rule already hardcoded.
- *Caveat on Handicapped Baselines:* The legacy prototype baseline achieved only 68.8% because it cycled unconditionally through an entire ranked list `(t-1) % len`, which forced it to recommend categories the user disliked. We corrected this to compare against competitive, fair baselines.

---

### Q7: If a static matcher ties LinUCB on accurate profiles, what is the core justification for using RL / Bandits?
**Answer:**
The definitive real-world advantage of Contextual LinUCB is **robustness against noisy, incomplete, outdated, or misstated user profiles**.
In practical travel planning, users frequently misstate preferences (e.g., saying they want "intense trekking" when they fatigue quickly, or checking "museums" because they feel they should, while actually enjoying street food and cafes).
- **Scenario B (Mismatched Profile Benchmark):** When we simulated a profile where the stated interest was inverted (matching the persona's least-preferred category):
  - **Greedy Top-Match collapsed completely to $39.4\% \pm 19.5\%$** acceptance.
  - **LinUCB maintained $82.2\% \pm 6.1\%$** acceptance.
  - Paired Student's $t$-test confirmed statistical superiority: $t = +9.85, p < 0.001$.
- Because LinUCB learns online from actual feedback (`+1.0` accept, `-1.0` reject), it rapidly detects that the stated profile was misleading, dampens the unrewarded arm, and shifts recommendations toward categories the user truly accepts. A rule-based matcher has no learning mechanism and remains trapped recommending unwanted activities.

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

---

### Q11: How is the Interest Match score mathematically computed?
**Answer:**
The interest score in `app/modules/ranking.py` is calculated as a **normalized tag overlap count**, bounded between 0.0 and 1.0:
$$\text{Score}_{\text{interest}} = \min\left(1.0, \frac{|U_{\text{tags}} \cap D_{\text{tags}}|}{3.0}\right)$$
where $U_{\text{tags}}$ is the set of user interests derived from `basic['interests']` and questionnaire answers, and $D_{\text{tags}}$ is the destination's tag set.
- It is **not** a Jaccard index ($|U \cap D| / |U \cup D|$) because penalizing a destination for having additional diverse tags (a large denominator $|U \cup D|$) would unfairly disadvantage rich destinations like Kyoto or Jaipur that offer many varied experiences.
- Matching 3 relevant user tags achieves the full 1.0 interest match score.

---

### Q12: How are statistical tests computed in the evaluation without relying on heavy external libraries like SciPy?
**Answer:**
In `scripts/evaluate.py`, we implement a pure-Python paired Student's $t$-test using standard library `math`:
1. Calculate differences $d_i = x_{A, i} - x_{B, i}$ across paired runs ($N = 30$).
2. Compute sample mean $\bar{d}$ and sample variance $s_d^2 = \frac{1}{N-1} \sum (d_i - \bar{d})^2$.
3. Compute $t$-statistic: $t = \frac{\bar{d}}{s_d / \sqrt{N}}$ with degrees of freedom $\nu = N - 1$.
4. Evaluate two-tailed $p$-value using the regularized incomplete beta function $I_x(a, b)$:
   $$p = I_{\frac{\nu}{\nu + t^2}}\left(\frac{\nu}{2}, \frac{1}{2}\right)$$
   approximated using Lentz's continued fraction method. This allows rigorous, zero-dependency statistical verification that runs instantly in any Python 3 environment.

---

### Q13: How does the system handle security, password hashing, and API error handling?
**Answer:**
- **Password Security:** Passwords are hashed using Python's standard `hashlib.pbkdf2_hmac("sha256", password, salt, 100_000)` with a 16-byte cryptographically secure random salt (`secrets.token_hex(16)`), formatted as `pbkdf2:sha256:100000${salt}${hash}`. Verification uses `secrets.compare_digest` to prevent timing attacks, with transparent backward compatibility for legacy hashes.
- **Production Secret Validation:** In production environments (`APP_ENV=production`), missing `AUTH_SECRET_KEY` halts startup with a `RuntimeError` rather than silently defaulting to a development fallback key.
- **Geocoding Validation:** If an Indian destination cannot be located during dynamic planning (`/api/places/plan-trip`), the API returns HTTP 404 with an explicit diagnostic message rather than silently defaulting to India's geographical centroid coordinates.
