# Reinforcement Learning Evaluation & Benchmark
# Owner: Person C
# Benchmarks Contextual LinUCB against Fair Baselines, Legacy Cycling Baseline, Random, and Oracle.
# Evaluates both Accurate Profile and Mismatched/Noisy Profile scenarios with Paired t-tests.
# Generates docs/eval_results.csv and docs/eval_curve.png.

import os
import sys
import math
import csv
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import matplotlib.pyplot as plt

# Ensure repository root is in python path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.rl_planner import LinUCBPolicy, extract_context_vector, CANONICAL_ARMS
from app.activity_data import CURATED_ACTIVITIES

# Evaluation Personas with Ground-Truth Latent Preferences
PERSONAS: Dict[str, Dict[str, Any]] = {
    "nature_enthusiast": {
        "true_preferences": {
            "nature_outdoors": 1.0,
            "adventure": 0.8,
            "relaxation": 0.6,
            "culture_history": 0.2,
            "shopping_local": -0.6,
            "food_dining": 0.4
        },
        "profile_dict": {
            "interests": ["nature_outdoors", "adventure"],
            "pace": 0.7,
            "crowd_tolerance": 0.2,
            "walking_tolerance": "high",
            "budget_tier": "balanced"
        }
    },
    "culture_buff": {
        "true_preferences": {
            "culture_history": 1.0,
            "shopping_local": 0.7,
            "food_dining": 0.8,
            "relaxation": 0.3,
            "adventure": -0.5,
            "nature_outdoors": 0.1
        },
        "profile_dict": {
            "interests": ["culture_history", "local_experiences"],
            "pace": 0.4,
            "crowd_tolerance": 0.6,
            "walking_tolerance": "medium",
            "budget_tier": "luxury"
        }
    },
    "balanced": {
        "true_preferences": {
            "culture_history": 0.6,
            "food_dining": 0.7,
            "nature_outdoors": 0.5,
            "adventure": 0.4,
            "relaxation": 0.5,
            "shopping_local": 0.3
        },
        "profile_dict": {
            "interests": ["culture_history", "food_dining"],
            "pace": 0.5,
            "crowd_tolerance": 0.5,
            "walking_tolerance": "medium",
            "budget_tier": "balanced"
        }
    }
}

TRIP_CONFIG = {
    "duration_days": 5,
    "total_budget": 1200.0,
    "travel_pace": "balanced"
}


# ---------------------------------------------------------------------------
# Statistical Helpers: Paired t-test and Student-t p-value (Pure Python)
# ---------------------------------------------------------------------------

def _betainc(a: float, b: float, x: float, max_iter: int = 200) -> float:
    """Regularized incomplete beta function via Lentz continued fraction."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    factor = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    )
    tiny = 1e-30
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1.0)
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    f = d
    for m in range(1, max_iter):
        # 2m step
        num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + num * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + num / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        f *= (c * d)
        # 2m + 1 step
        num = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + num / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = c * d
        f *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return factor * f / a


def student_t_pvalue(t: float, df: int) -> float:
    """Two-tailed p-value for Student's t distribution with df degrees of freedom."""
    if df <= 0:
        return 1.0
    x = df / (df + t * t)
    return _betainc(df / 2.0, 0.5, x)


def paired_t_test(samples_a: List[float], samples_b: List[float]) -> Tuple[float, float]:
    """Computes paired t-statistic and two-tailed p-value between two paired samples."""
    diffs = [a - b for a, b in zip(samples_a, samples_b)]
    n = len(diffs)
    if n < 2:
        return 0.0, 1.0
    mean_d = sum(diffs) / n
    var_d = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)
    std_d = math.sqrt(var_d)
    if std_d == 0.0:
        return (0.0, 1.0) if mean_d == 0.0 else (float("inf"), 0.0)
    t_stat = mean_d / (std_d / math.sqrt(n))
    p_val = student_t_pvalue(t_stat, n - 1)
    return round(t_stat, 4), p_val


# ---------------------------------------------------------------------------
# Simulation Engine
# ---------------------------------------------------------------------------

def compute_acceptance(cat: str, true_preferences: Dict[str, float], rng: np.random.Generator) -> Tuple[bool, float]:
    """Synthetic user acceptance model: sigmoid(2 * latent_preference)."""
    latent = true_preferences.get(cat, 0.0)
    p_accept = 1.0 / (1.0 + math.exp(-2.0 * latent))
    accepted = bool(rng.random() < p_accept)
    reward = 1.0 if accepted else -1.0
    return accepted, reward


def run_single_simulation(
    persona_name: str,
    policy_name: str,
    alpha: float,
    seed: int,
    rounds: int = 150,
    scenario: str = "accurate"
) -> Dict[str, Any]:
    """Runs a single simulation run with an isolated dedicated RNG."""
    persona_info = PERSONAS[persona_name]
    true_prefs = persona_info["true_preferences"]
    profile_dict = dict(persona_info["profile_dict"])

    # If testing mismatched / noisy profile scenario:
    # Set stated interests to the persona's least-liked category
    if scenario == "mismatched":
        least_liked_cat = min(true_prefs.keys(), key=lambda c: true_prefs[c])
        profile_dict["interests"] = [least_liked_cat]

    # Dedicated random generator per run to avoid stream interleaving
    rng = np.random.default_rng(seed)

    activities = CURATED_ACTIVITIES.copy()

    # Pre-determine oracle's best category
    best_cat = max(true_prefs.keys(), key=lambda c: true_prefs[c])
    oracle_activities = [a for a in activities if a.get("category") == best_cat]
    if not oracle_activities:
        oracle_activities = activities

    # Matching activities for fair baselines
    matching_activities = [
        a for a in activities if a.get("category") in profile_dict.get("interests", [])
    ]
    if not matching_activities:
        matching_activities = activities

    # Initialize policy if LinUCB
    linucb = None
    if policy_name == "LinUCB":
        linucb = LinUCBPolicy(user_id=f"eval_{persona_name}_{alpha}_{seed}_{scenario}", alpha=alpha)

    accept_history: List[int] = []
    reward_history: List[float] = []

    for t in range(1, rounds + 1):
        slot = "morning" if t % 2 == 1 else "afternoon"

        # 1. Action Selection
        if policy_name == "LinUCB":
            scored = []
            for act in activities:
                arm_id = act["category"] if act["category"] in CANONICAL_ARMS else "culture_history"
                ctx = extract_context_vector(profile_dict, TRIP_CONFIG, t, rounds, slot, act)
                score, _, _ = linucb.predict_score(arm_id, ctx)
                scored.append((score, act, arm_id, ctx))
            scored.sort(key=lambda item: item[0], reverse=True)
            chosen_score, chosen_act, chosen_arm, chosen_ctx = scored[0]

        elif policy_name == "Oracle":
            idx = int(rng.integers(0, len(oracle_activities)))
            chosen_act = oracle_activities[idx]

        elif policy_name == "Greedy Top-Match":
            # Always select from top matching category (deterministic / consistent)
            chosen_act = matching_activities[(t - 1) % len(matching_activities)]

        elif policy_name == "Random-within-Match":
            # Uniformly pick among interest-matching activities
            idx = int(rng.integers(0, len(matching_activities)))
            chosen_act = matching_activities[idx]

        elif policy_name == "Cycling Baseline":
            # Legacy baseline: ranks all activities and cycles through all 30
            def b_score(act):
                score = 0.0
                if act.get("category", "") in profile_dict.get("interests", []):
                    score += 1.5
                return score + float(rng.normal(0, 0.1))

            b_ranked = sorted(activities, key=b_score, reverse=True)
            chosen_act = b_ranked[(t - 1) % len(b_ranked)]

        elif policy_name == "Random":
            idx = int(rng.integers(0, len(activities)))
            chosen_act = activities[idx]

        else:
            raise ValueError(f"Unknown policy: {policy_name}")

        # 2. Simulate User Response
        act_cat = chosen_act.get("category", "")
        accepted, reward = compute_acceptance(act_cat, true_prefs, rng)

        accept_history.append(1 if accepted else 0)
        reward_history.append(reward)

        # 3. Update Policy
        if policy_name == "LinUCB":
            linucb.update(chosen_arm, chosen_ctx, reward)

    total_accepts = sum(accept_history)
    acceptance_rate = total_accepts / rounds
    cumulative_reward = sum(reward_history)

    # Compute acceptance per 10-round non-overlapping window
    window_size = 10
    num_windows = rounds // window_size
    window_acc = []
    for w in range(num_windows):
        sub = accept_history[w * window_size : (w + 1) * window_size]
        window_acc.append(sum(sub) / len(sub))

    return {
        "persona": persona_name,
        "policy": policy_name,
        "scenario": scenario,
        "alpha": alpha if policy_name == "LinUCB" else None,
        "seed": seed,
        "rounds": rounds,
        "accepts": total_accepts,
        "acceptance_rate": round(acceptance_rate, 4),
        "cumulative_reward": round(cumulative_reward, 2),
        "window_acceptance": window_acc
    }


def run_experiment(
    personas: Optional[List[str]] = None,
    seeds: Optional[List[int]] = None,
    alphas: Optional[List[float]] = None,
    rounds: int = 150,
    include_mismatched: bool = True
) -> List[Dict[str, Any]]:
    """Runs the full evaluation benchmark across personas, seeds, policies, and alphas."""
    if personas is None:
        personas = list(PERSONAS.keys())
    if seeds is None:
        seeds = [42, 43, 44, 45, 46, 47, 48, 49, 50, 51]  # 10 seeds
    if alphas is None:
        alphas = [0.1, 0.3, 0.5, 1.0]

    all_results: List[Dict[str, Any]] = []

    scenarios = ["accurate"]
    if include_mismatched:
        scenarios.append("mismatched")

    for scen in scenarios:
        print(f"Running Scenario '{scen}': {len(personas)} personas x {len(seeds)} seeds x {rounds} rounds...")
        for persona in personas:
            for seed in seeds:
                # 1. Oracle (ceiling)
                all_results.append(run_single_simulation(persona, "Oracle", 0.0, seed, rounds, scenario=scen))

                # 2. Fair Baselines
                all_results.append(run_single_simulation(persona, "Greedy Top-Match", 0.0, seed, rounds, scenario=scen))
                all_results.append(run_single_simulation(persona, "Random-within-Match", 0.0, seed, rounds, scenario=scen))

                # 3. Legacy Cycling Baseline
                all_results.append(run_single_simulation(persona, "Cycling Baseline", 0.0, seed, rounds, scenario=scen))

                # 4. Uniform Random
                all_results.append(run_single_simulation(persona, "Random", 0.0, seed, rounds, scenario=scen))

                # 5. Contextual LinUCB sweeps
                for alpha in alphas:
                    all_results.append(run_single_simulation(persona, "LinUCB", alpha, seed, rounds, scenario=scen))

    return all_results


def save_results_csv(results: List[Dict[str, Any]], filepath: Path):
    """Saves per-run experimental results to CSV."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "scenario", "persona", "policy", "alpha", "seed", "rounds",
            "accepts", "acceptance_rate", "cumulative_reward"
        ])
        for r in results:
            writer.writerow([
                r["scenario"],
                r["persona"],
                r["policy"],
                r["alpha"] if r["alpha"] is not None else "",
                r["seed"],
                r["rounds"],
                r["accepts"],
                r["acceptance_rate"],
                r["cumulative_reward"]
            ])
    print(f"Saved evaluation results to {filepath}")


def generate_learning_curve_plot(results: List[Dict[str, Any]], filepath: Path, rounds: int = 150):
    """Generates a 2-panel plot comparing learning curves under accurate vs. mismatched profiles."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    window_size = 10
    num_windows = rounds // window_size
    window_x = [(w * window_size + window_size // 2) for w in range(num_windows)]

    colors = {
        "Oracle": "#10b981",              # Emerald
        "Greedy Top-Match": "#0284c7",    # Sky Blue
        "Random-within-Match": "#06b6d4", # Cyan
        "LinUCB (alpha=0.1)": "#6366f1",  # Indigo
        "Cycling Baseline": "#f59e0b",    # Amber
        "Random": "#94a3b8",              # Slate
    }
    linestyles = {
        "Oracle": "--",
        "Greedy Top-Match": "-",
        "Random-within-Match": "-.",
        "LinUCB (alpha=0.1)": "-",
        "Cycling Baseline": ":",
        "Random": "-."
    }

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=150, sharey=True)

    for ax, scen, title in zip(
        axes,
        ["accurate", "mismatched"],
        ["Scenario A: Accurate Stated Profile", "Scenario B: Mismatched/Noisy Stated Profile"]
    ):
        scen_results = [r for r in results if r["scenario"] == scen]

        # Group by policy label
        groups: Dict[str, List[List[float]]] = {}
        for r in scen_results:
            if r["policy"] == "LinUCB":
                if r["alpha"] == 0.1:  # Highlight best alpha
                    label = f"LinUCB (alpha={r['alpha']})"
                else:
                    continue  # Keep plot readable
            else:
                label = r["policy"]

            if label not in groups:
                groups[label] = []
            groups[label].append(r["window_acceptance"])

        for label in ["Oracle", "Greedy Top-Match", "Random-within-Match", "LinUCB (alpha=0.1)", "Cycling Baseline", "Random"]:
            if label not in groups:
                continue
            arr = np.array(groups[label])
            mean_curve = np.mean(arr, axis=0) * 100.0
            std_curve = np.std(arr, axis=0) * 100.0

            c = colors.get(label, "#333333")
            ls = linestyles.get(label, "-")
            lw = 2.4 if "LinUCB" in label else 1.8

            ax.plot(window_x, mean_curve, label=label, color=c, linestyle=ls, linewidth=lw)
            if "LinUCB" in label or label == "Greedy Top-Match":
                ax.fill_between(window_x, mean_curve - std_curve, mean_curve + std_curve, color=c, alpha=0.12)

        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
        ax.set_xlabel("Interaction Round", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.set_xlim(0, rounds)
        ax.set_ylim(25, 95)

    axes[0].set_ylabel("Acceptance Rate (% in 10-Round Window)", fontsize=10)
    axes[0].legend(loc="lower right", frameon=True, fontsize=8)
    axes[1].legend(loc="lower right", frameon=True, fontsize=8)

    plt.suptitle("Comparative Evaluation: Contextual LinUCB vs. Baselines (150 Rounds, 30 Runs/Policy)", fontsize=12, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(filepath, bbox_inches="tight")
    plt.close()
    print(f"Saved evaluation plot to {filepath}")


def compute_summary_table(results: List[Dict[str, Any]], scenario: str = "accurate") -> Dict[str, Dict[str, Any]]:
    """Computes mean +- std and paired t-tests relative to LinUCB (alpha=0.1)."""
    scen_results = [r for r in results if r["scenario"] == scenario]
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in scen_results:
        key = f"LinUCB (alpha={r['alpha']})" if r["policy"] == "LinUCB" else r["policy"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r)

    # Reference sample for paired tests: LinUCB (alpha=0.1)
    linucb_key = "LinUCB (alpha=0.1)"
    linucb_accs = [it["acceptance_rate"] for it in grouped.get(linucb_key, [])]

    summary = {}
    for key, items in grouped.items():
        accs = [it["acceptance_rate"] for it in items]
        rews = [it["cumulative_reward"] for it in items]

        if key != linucb_key and len(accs) == len(linucb_accs):
            t_stat, p_val = paired_t_test(linucb_accs, accs)
        else:
            t_stat, p_val = 0.0, 1.0

        summary[key] = {
            "acc_mean": round(float(np.mean(accs)), 4),
            "acc_std": round(float(np.std(accs)), 4),
            "rew_mean": round(float(np.mean(rews)), 2),
            "rew_std": round(float(np.std(rews)), 2),
            "t_stat": t_stat,
            "p_val": p_val
        }
    return summary


def main():
    csv_path = REPO_ROOT / "docs" / "eval_results.csv"
    png_path = REPO_ROOT / "docs" / "eval_curve.png"

    results = run_experiment(rounds=150, include_mismatched=True)
    save_results_csv(results, csv_path)
    generate_learning_curve_plot(results, png_path, rounds=150)

    # Print Summary for Scenario A (Accurate Profile)
    summary_a = compute_summary_table(results, scenario="accurate")
    print("\n=== SCENARIO A: ACCURATE STATED PROFILE (150 Rounds, 30 Runs/Policy) ===")
    print(f"{'Policy':<25} | {'Acceptance (Mean ± Std)':<25} | {'Reward (Mean ± Std)':<22} | {'Paired t (vs UCB)':<18} | {'p-value'}")
    print("-" * 105)
    for pol, m in summary_a.items():
        acc_str = f"{m['acc_mean']*100:.1f}% ± {m['acc_std']*100:.1f}%"
        rew_str = f"{m['rew_mean']:.1f} ± {m['rew_std']:.1f}"
        t_str = f"t = {m['t_stat']:+.2f}" if pol != "LinUCB (alpha=0.1)" else "reference"
        p_str = f"p = {m['p_val']:.4f}" if pol != "LinUCB (alpha=0.1)" else "—"
        if m['p_val'] < 0.001 and pol != "LinUCB (alpha=0.1)":
            p_str = "p < 0.001"
        print(f"{pol:<25} | {acc_str:<25} | {rew_str:<22} | {t_str:<18} | {p_str}")

    # Print Summary for Scenario B (Mismatched / Noisy Profile)
    summary_b = compute_summary_table(results, scenario="mismatched")
    print("\n=== SCENARIO B: MISMATCHED / NOISY STATED PROFILE (Robustness Test) ===")
    print(f"{'Policy':<25} | {'Acceptance (Mean ± Std)':<25} | {'Reward (Mean ± Std)':<22} | {'Paired t (vs UCB)':<18} | {'p-value'}")
    print("-" * 105)
    for pol, m in summary_b.items():
        acc_str = f"{m['acc_mean']*100:.1f}% ± {m['acc_std']*100:.1f}%"
        rew_str = f"{m['rew_mean']:.1f} ± {m['rew_std']:.1f}"
        t_str = f"t = {m['t_stat']:+.2f}" if pol != "LinUCB (alpha=0.1)" else "reference"
        p_str = f"p = {m['p_val']:.4f}" if pol != "LinUCB (alpha=0.1)" else "—"
        if m['p_val'] < 0.001 and pol != "LinUCB (alpha=0.1)":
            p_str = "p < 0.001"
        print(f"{pol:<25} | {acc_str:<25} | {rew_str:<22} | {t_str:<18} | {p_str}")


if __name__ == "__main__":
    main()
