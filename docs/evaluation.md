# Honest Reinforcement Learning Evaluation & Benchmark

**Module / Task:** Deliverable 2 – Honest RL Evaluation  
**Owner:** Person C (Integrator)  
**Script:** `scripts/evaluate.py`  
**Data Artifact:** `docs/eval_results.csv`  
**Plot Artifact:** `docs/eval_curve.png`  
**Reproduction Command:** `python scripts/evaluate.py`  

---

## 1. Problem Statement & Diagnostic

In the initial project prototype (`app/evaluation.py`), a toy simulation reported:
- **Contextual LinUCB:** **73.3%** acceptance rate
- **Static Baseline:** **80.0%** acceptance rate

Before claiming that Reinforcement Learning improves recommendation quality over a heuristic baseline, we conducted an empirical diagnosis to understand **why** this occurred:

1. **Short Horizon ($T = 20$):**
   With 7 canonical arms (activity categories) and a 24-dimensional context vector per arm, the agent had $7 \times 24 = 168$ parameters to learn. In 20 rounds, each arm was pulled fewer than 3 times on average. LinUCB was in its cold-start exploration phase and paid an exploration penalty.
2. **Exploration Parameter $\alpha = 0.5$:**
   The exploration bonus $\alpha \sqrt{x^T A_a^{-1} x}$ was initially large ($\sim 1.0 - 1.5$), forcing LinUCB to pull uncertain arms rather than exploit early positive rewards.
3. **The Baseline Handicap & Question of Fairness:**
   The legacy static baseline in `app/evaluation.py` cycled through its entire ranked catalog using `(t - 1) % len(b_ranked)`. Over long horizons ($T=150$), this forced it to recommend categories the user disliked (resulting in 68.8% acceptance). However, if we test a **fair, sensible baseline** that always selects from the user's top stated interest matches (`Greedy Top-Match`), it achieves **84.7%**, virtually matching LinUCB (**83.3%**).
4. **The Real Value of LinUCB: Robustness to Inaccurate Profiles:**
   If a user's stated questionnaire answers are 100% accurate, complete, and static, a simple rule-based matcher performs well and does not strictly require a bandit. However, when user preferences are noisy, incomplete, or mismatched (e.g., stated interests contradict actual behavior), rule-based matchers collapse to **39.4%**, while **Contextual LinUCB autonomously adapts to user feedback and maintains 82.2% acceptance**.

---

## 2. Rigorous Experiment Design

To provide an honest, reproducible benchmark, `scripts/evaluate.py` evaluates:
- **3 Diverse Personas:** `nature_enthusiast`, `culture_buff`, and `balanced` with ground-truth latent utility vectors.
- **10 Independent Random Seeds:** `[42, 43, 44, 45, 46, 47, 48, 49, 50, 51]`.
- **150 Interaction Rounds:** Sufficient for linear bandits to transition from exploration to asymptotic exploitation.
- **Dedicated Independent RNGs:** Each policy on each seed uses its own `np.random.default_rng(seed)`.
- **Paired Statistical Testing:** Paired Student's t-test computed across matching seeds ($N = 30$ runs per policy).
- **Two Scenarios:**
  1. **Scenario A (Accurate Profile):** Stated interests match the user's true latent preferences.
  2. **Scenario B (Mismatched / Noisy Profile):** Stated interests represent the user's least-preferred category (simulating cold start or inaccurate questionnaire responses).

---

## 3. Empirical Results

All numbers below are produced directly by running `python scripts/evaluate.py`:

### Scenario A: Accurate Stated Profile (Standard Case)

| Policy | $\alpha$ | Acceptance Rate (Mean $\pm$ Std) | Cumulative Reward (Mean $\pm$ Std) | Paired $t$ (vs LinUCB $\alpha=0.1$) | $p$-value |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Oracle** (Ceiling) | — | **86.3% $\pm$ 4.1%** | **+108.8 $\pm$ 12.2** | $t = -4.01$ | $p < 0.001$ |
| **Random-within-Match** | — | **85.0% $\pm$ 4.6%** | **+104.9 $\pm$ 13.8** | $t = -2.25$ | $p = 0.032$ |
| **Greedy Top-Match** | — | **84.7% $\pm$ 5.5%** | **+104.1 $\pm$ 16.6** | $t = -3.22$ | $p = 0.003$ |
| **LinUCB** | 0.1 | **83.3% $\pm$ 5.9%** | **+99.9 $\pm$ 17.7** | *Reference* | — |
| **LinUCB** | 0.3 | **79.6% $\pm$ 4.9%** | **+88.8 $\pm$ 14.8** | $t = +6.66$ | $p < 0.001$ |
| **LinUCB** | 0.5 | **79.4% $\pm$ 5.6%** | **+88.1 $\pm$ 16.8** | $t = +6.17$ | $p < 0.001$ |
| **LinUCB** | 1.0 | **78.5% $\pm$ 4.6%** | **+85.5 $\pm$ 13.9** | $t = +7.62$ | $p < 0.001$ |
| **Random Policy** | — | **70.8% $\pm$ 5.0%** | **+62.3 $\pm$ 15.0** | $t = +8.64$ | $p < 0.001$ |
| **Cycling Baseline** | — | **68.8% $\pm$ 4.0%** | **+56.3 $\pm$ 12.0** | $t = +10.04$ | $p < 0.001$ |

### Scenario B: Mismatched / Noisy Profile (Robustness Benchmark)

| Policy | $\alpha$ | Acceptance Rate (Mean $\pm$ Std) | Cumulative Reward (Mean $\pm$ Std) | Paired $t$ (vs LinUCB $\alpha=0.1$) | $p$-value |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Oracle** (Ceiling) | — | **86.3% $\pm$ 4.1%** | **+108.8 $\pm$ 12.2** | $t = -4.63$ | $p < 0.001$ |
| **LinUCB** | 0.1 | **82.2% $\pm$ 6.1%** | **+96.7 $\pm$ 18.4** | *Reference* | — |
| **LinUCB** | 0.3 | **81.1% $\pm$ 5.4%** | **+93.2 $\pm$ 16.3** | $t = +1.71$ | $p = 0.098$ |
| **LinUCB** | 0.5 | **79.3% $\pm$ 5.7%** | **+87.8 $\pm$ 17.0** | $t = +3.83$ | $p < 0.001$ |
| **LinUCB** | 1.0 | **78.3% $\pm$ 5.3%** | **+84.9 $\pm$ 16.0** | $t = +5.58$ | $p < 0.001$ |
| **Random Policy** | — | **70.8% $\pm$ 5.0%** | **+62.3 $\pm$ 15.0** | $t = +8.17$ | $p < 0.001$ |
| **Cycling Baseline** | — | **67.7% $\pm$ 4.4%** | **+53.2 $\pm$ 13.3** | $t = +11.01$ | $p < 0.001$ |
| **Random-within-Match** | — | **40.0% $\pm$ 19.2%** | **-30.1 $\pm$ 57.6** | $t = +9.79$ | $p < 0.001$ |
| **Greedy Top-Match** | — | **39.4% $\pm$ 19.5%** | **-31.9 $\pm$ 58.5** | $t = +9.85$ | $p < 0.001$ |

---

## 4. Learning Curve Analysis (`docs/eval_curve.png`)

The evaluation generates a 2-panel comparative plot across both scenarios:
- **Panel A (Accurate Profile):** The Greedy Top-Match baseline and Random-within-Match baseline maintain a stable high acceptance (~84–85%). LinUCB ($\alpha=0.1$) starts lower due to exploration in rounds 1–20 (~70%), then steadily climbs and reaches ~84–85% after round 40.
- **Panel B (Mismatched Profile):** The static matchers instantly collapse to ~38–40% and stay trapped there because they have no feedback mechanism to escape bad initial data. LinUCB ($\alpha=0.1$) rapidly pivots away from rejected arms and reaches **>82%** acceptance by round 30.

---

## 5. Honest Academic Takeaways for the Viva

1. **When Profiles are Accurate:**
   A simple heuristic keyword matcher is competitive with LinUCB (84.7% vs. 83.3%). If user profiles are fully accurate and static, reinforcement learning provides minimal marginal benefit over clean heuristics.
2. **When Profiles are Inaccurate or Evolving:**
   Static heuristics fail catastrophically (dropping to 39.4%). LinUCB exhibits remarkable **robustness**, maintaining **82.2%** acceptance ($p < 0.001$) by learning directly from user feedback $(A_a, b_a)$.
3. **Exploration Costs in Small Action Spaces:**
   In small action spaces (7 categories), a low exploration rate ($\alpha = 0.1$) achieves the best trade-off, avoiding over-exploration while preserving rapid adaptation.

---

## 6. Limitations
- **Simulated Environment:** All users and accept/reject trials are generated from synthetic latent preference distributions; no live human behavioral dataset was available.
- **Stationary Preferences:** Latent preferences are assumed stationary over the 150 rounds; non-stationary preference drift is reserved for future research.

## AI assistance and external libraries/APIs used
- Script authored by Person C under SHARED guidelines
- Libraries: `numpy`, `matplotlib` (zero external statistics packages; paired t-test computed in pure Python)
