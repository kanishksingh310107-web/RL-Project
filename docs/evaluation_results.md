# Empirical RL Evaluation & Benchmark Results

## Pre-Registration Specification (Task F-016 Step A)

**Date Registered:** November 2026  
**Investigator:** Atharva Sokhal (RL Evaluation & Modules)  
**Evaluation Target:** Contextual LinUCB Policy vs. Static Baseline Recommender (`app/evaluation.py`)  

### 1. Evaluation Methodology & Metrics
- **Cumulative Reward:** Sum of feedback rewards across rounds, where user acceptance yields $+1.0$ and rejection yields $-1.0$.
- **Acceptance Rate:** Fraction of recommended activities accepted by the simulated user ($\frac{\text{Accepts}}{\text{Total Rounds}}$).
- **Statistical Rigor:**
  - $N = 100$ independent Monte Carlo seeds (seeds $0, 1, \dots, 99$).
  - Per-seed isolated RNG using `np.random.default_rng(seed)` (eliminating global state pollution).
  - Metrics reported as Empirical Mean $\pm$ 95% Confidence Interval:
    $$\text{CI}_{95\%} = \bar{x} \pm 1.96 \cdot \frac{s}{\sqrt{N}}$$
- **Persona:** `nature_enthusiast` (with cross-validation on `culture_buff` and `general_balanced`).

### 2. Pre-Declared Experimental Variants
Before running simulations or altering model hyperparameters, four experimental variants were formally pre-registered:

1. **Variant 1 — Cold-Start LinUCB ($T=20$ rounds, $\alpha=0.5$):**
   - Standard cold-start initialization: $A_a = I_{24}$, $b_a = \mathbf{0}_{24}$.
   - Matches the original audit benchmark setting.
   - **Pre-experimental expectation:** Static baseline is expected to outperform LinUCB over short horizon due to exploration cost and static keyword bonus (+1.5).

2. **Variant 2 — Cold-Start LinUCB with Extended Horizon ($T=50$ rounds, $\alpha=0.5$):**
   - Tests whether exploration payoff amortizes over a longer 50-round horizon once policy weights converge.
   - Standard cold-start initialization: $A_a = I_{24}$, $b_a = \mathbf{0}_{24}$.

3. **Variant 3 — Warm-Start / Informed Prior LinUCB ($T=20$ rounds, $\alpha=0.5$):**
   - Initializing vector $b_a$ using stated user profile interests prior to round 1:
     For arms matching profile interests, $b_a$ is initialized with a prior weight vector ($+1.0$).
   - Tests whether informed initialization mitigates the early exploration deficit under short horizons.

4. **Variant 4 — Warm-Start LinUCB with Extended Horizon ($T=50$ rounds, $\alpha=0.5$):**
   - Combining warm-started prior with extended interaction horizon ($T=50$).

---

## Benchmark Execution & Results Table

The following results were empirically measured across 100 independent Monte Carlo seeds ($N=100$) using dedicated `np.random.default_rng(seed)` instances:

| Variant | Rounds ($T$) | Seeds ($N$) | Metric | Static Baseline (Mean ± 95% CI) | Adaptive LinUCB (Mean ± 95% CI) | Relative Gain | Winner |
|---|---|---|---|---|---|---|---|
| **Variant 1 (Cold-Start)** | 20 | 100 | Cum. Reward<br>Accept Rate | $11.66 \pm 0.58$<br>$79.1\% \pm 1.4\%$ | $8.92 \pm 0.71$<br>$72.3\% \pm 1.8\%$ | $-23.5\%$ reward<br>$-8.7\%$ accept | **Static Baseline** |
| **Variant 2 (Extended Horizon)** | 50 | 100 | Cum. Reward<br>Accept Rate | $17.78 \pm 1.26$<br>$67.8\% \pm 1.3\%$ | $25.88 \pm 1.04$<br>$75.9\% \pm 1.0\%$ | $+45.6\%$ reward<br>$+12.0\%$ accept | **Adaptive LinUCB** |
| **Variant 3 (Warm-Start Prior)** | 20 | 100 | Cum. Reward<br>Accept Rate | $11.66 \pm 0.58$<br>$79.1\% \pm 1.4\%$ | $9.08 \pm 0.86$<br>$72.7\% \pm 2.1\%$ | $-22.1\%$ reward<br>$-8.1\%$ accept | **Static Baseline** |
| **Variant 4 (Warm-Start + Extended)** | 50 | 100 | Cum. Reward<br>Accept Rate | $17.78 \pm 1.26$<br>$67.8\% \pm 1.3\%$ | $26.48 \pm 1.02$<br>$76.5\% \pm 1.0\%$ | $+48.9\%$ reward<br>$+12.8\%$ accept | **Adaptive LinUCB** |

---

## Honest Theoretical Analysis & Findings

### Why the Static Baseline Wins on Short Horizons ($T=20$)
1. **Zero Exploration Cost:** The static baseline ranks items using hardcoded keyword matching (`if act_category in interests: score += 1.5`). For the `nature_enthusiast` persona, it immediately targets `nature_outdoors` ($p_{\text{accept}} = 88.1\%$) and `adventure` ($p_{\text{accept}} = 83.2\%$). It incurs zero exploration cost in the early rounds.
2. **Bandit Exploration Tax:** Disjoint LinUCB starts with $A_a = I_{24}$ and $b_a = \mathbf{0}_{24}$ for all 6 canonical arms. With $\alpha = 0.5$, the upper confidence bound term $\alpha \sqrt{x^T A_a^{-1} x}$ compels the agent to explore under-pulled arms, including `shopping_local` ($p_{\text{accept}} = 23.1\%$, net negative reward) and `culture_history` ($p_{\text{accept}} = 59.9\%$). Each exploratory pull of a dispreferred arm produces a $-1.0$ penalty, depressing early cumulative reward.
3. **Warm-Starting Efficacy:** Initializing $b_a$ using profile interests (Variant 3) modestly improves LinUCB reward ($9.08$ vs $8.92$), but exploration uncertainty still leads to exploration pulls over a short 20-round horizon.

### Why Adaptive LinUCB Wins on Extended Horizons ($T=50$)
1. **Convergence and Exploitation:** By round 20–25, LinUCB has estimated ridge regression coefficients $\hat{\theta}_a = A_a^{-1} b_a$ accurately across all feature dimensions. Confidence ellipses shrink ($\sqrt{x^T A_a^{-1} x} \to 0$), and the policy reliably exploits high-utility arms while suppressing dispreferred arms.
2. **Baseline Degradation:** The static baseline cycles through activities via round-robin. As it exhausts the top-tier items in `nature_outdoors`, it is forced to recommend lower-relevance activities, causing its acceptance rate to drop from $79.1\%$ to $67.8\%$.
3. **Long-Term Superiority:** Over 50 rounds, LinUCB achieves a $+45.6\%$ higher cumulative reward ($25.88 \pm 1.04$ vs $17.78 \pm 1.26$) and $+12.0\%$ higher acceptance rate ($75.9\%$ vs $67.8\%$) with non-overlapping 95% confidence intervals.

---

## Reproduction Command

To reproduce the multi-seed empirical evaluation and verify the confidence intervals reported above, execute:

```bash
python -c "
from app.evaluation import run_comparative_simulation

print('=== 100-Seed Cold-Start T=20 ===')
r20 = run_comparative_simulation(user_persona='nature_enthusiast', rounds=20, num_seeds=100, warm_start=False)
print(r20['evaluation_summary'])

print('\n=== 100-Seed Cold-Start T=50 ===')
r50 = run_comparative_simulation(user_persona='nature_enthusiast', rounds=50, num_seeds=100, warm_start=False)
print(r50['evaluation_summary'])
"
```
