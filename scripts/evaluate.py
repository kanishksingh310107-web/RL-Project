# Reinforcement Learning Evaluation & Benchmark
# Owner: Person C
# Benchmarks Contextual LinUCB against Static Baseline, Random, and Oracle policies.
# Generates docs/eval_results.csv and docs/eval_curve.png.

import os
import sys
import math
import csv
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import matplotlib.pyplot as plt

# Ensure repository root is in python path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.rl_planner import LinUCBPolicy, extract_context_vector, CANONICAL_ARMS
from app.activity_data import CURATED_ACTIVITIES

# Evaluation Personas with Ground-Truth Latent Preferences
# (Copied faithfully from app/evaluation.py to keep the evaluation harness independent)
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
    rounds: int = 150
) -> Dict[str, Any]:
    """Runs a single simulation run with an isolated dedicated RNG."""
    persona_info = PERSONAS[persona_name]
    true_prefs = persona_info["true_preferences"]
    profile_dict = persona_info["profile_dict"]

    # Dedicated random generator per run to avoid stream interleaving
    rng = np.random.default_rng(seed)

    activities = CURATED_ACTIVITIES.copy()

    # Pre-determine oracle's best category
    best_cat = max(true_prefs.keys(), key=lambda c: true_prefs[c])
    oracle_activities = [a for a in activities if a.get("category") == best_cat]
    if not oracle_activities:
        oracle_activities = activities

    # Initialize policy if LinUCB
    linucb = None
    if policy_name == "LinUCB":
        linucb = LinUCBPolicy(user_id=f"eval_{persona_name}_{alpha}_{seed}", alpha=alpha)

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

        elif policy_name == "Static Baseline":
            # Static keyword scoring + ranking from app/evaluation.py
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

        elif policy_name == "Oracle":
            idx = int(rng.integers(0, len(oracle_activities)))
            chosen_act = oracle_activities[idx]

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
        "alpha": alpha if policy_name == "LinUCB" else None,
        "seed": seed,
        "rounds": rounds,
        "accepts": total_accepts,
        "acceptance_rate": round(acceptance_rate, 4),
        "cumulative_reward": round(cumulative_reward, 2),
        "window_acceptance": window_acc
    }


def run_experiment(
    personas: List[str] = None,
    seeds: List[int] = None,
    alphas: List[float] = None,
    rounds: int = 150
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Runs the full evaluation benchmark across personas, seeds, policies, and alphas."""
    if personas is None:
        personas = list(PERSONAS.keys())
    if seeds is None:
        seeds = [42, 43, 44, 45, 46, 47, 48, 49, 50, 51]  # 10 seeds
    if alphas is None:
        alphas = [0.1, 0.3, 0.5, 1.0]

    all_results: List[Dict[str, Any]] = []

    print(f"Running RL evaluation: {len(personas)} personas x {len(seeds)} seeds x {rounds} rounds...")

    for persona in personas:
        for seed in seeds:
            # 1. Oracle
            res_oracle = run_single_simulation(persona, "Oracle", 0.0, seed, rounds)
            all_results.append(res_oracle)

            # 2. Static Baseline
            res_base = run_single_simulation(persona, "Static Baseline", 0.0, seed, rounds)
            all_results.append(res_base)

            # 3. Random
            res_rand = run_single_simulation(persona, "Random", 0.0, seed, rounds)
            all_results.append(res_rand)

            # 4. LinUCB sweeps
            for alpha in alphas:
                res_ucb = run_single_simulation(persona, "LinUCB", alpha, seed, rounds)
                all_results.append(res_ucb)

    return all_results


def save_results_csv(results: List[Dict[str, Any]], filepath: Path):
    """Saves per-run experimental results to CSV."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "persona", "policy", "alpha", "seed", "rounds",
            "accepts", "acceptance_rate", "cumulative_reward"
        ])
        for r in results:
            writer.writerow([
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
    """Generates and saves the learning curve plot comparing policies over 10-round windows."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    window_size = 10
    num_windows = rounds // window_size
    window_x = [(w * window_size + window_size // 2) for w in range(num_windows)]

    # Group runs by policy label
    groups: Dict[str, List[List[float]]] = {}
    for r in results:
        if r["policy"] == "LinUCB":
            label = f"LinUCB (alpha={r['alpha']})"
        else:
            label = r["policy"]
        if label not in groups:
            groups[label] = []
        groups[label].append(r["window_acceptance"])

    plt.figure(figsize=(10, 6), dpi=150)

    # Plot styling
    colors = {
        "Oracle": "#10b981",          # Emerald
        "Static Baseline": "#f59e0b", # Amber
        "Random": "#94a3b8",          # Slate
        "LinUCB (alpha=0.1)": "#6366f1", # Indigo
        "LinUCB (alpha=0.3)": "#3b82f6", # Blue
        "LinUCB (alpha=0.5)": "#8b5cf6", # Purple
        "LinUCB (alpha=1.0)": "#ec4899"  # Pink
    }
    linestyles = {
        "Oracle": "--",
        "Static Baseline": ":",
        "Random": "-.",
        "LinUCB (alpha=0.1)": "-",
        "LinUCB (alpha=0.3)": "-",
        "LinUCB (alpha=0.5)": "-",
        "LinUCB (alpha=1.0)": "-"
    }

    for label, histories in groups.items():
        arr = np.array(histories)  # shape: (n_runs, num_windows)
        mean_curve = np.mean(arr, axis=0) * 100.0
        std_curve = np.std(arr, axis=0) * 100.0

        c = colors.get(label, "#333333")
        ls = linestyles.get(label, "-")
        lw = 2.2 if "LinUCB" in label else 1.8

        plt.plot(window_x, mean_curve, label=label, color=c, linestyle=ls, linewidth=lw)
        if "LinUCB" in label or label == "Static Baseline":
            plt.fill_between(window_x, mean_curve - std_curve, mean_curve + std_curve, color=c, alpha=0.12)

    plt.title("Comparative Learning Curves: Acceptance Rate Over Time (150 Rounds)", fontsize=13, fontweight="bold", pad=12)
    plt.xlabel("Interaction Round", fontsize=11)
    plt.ylabel("Acceptance Rate (% in 10-Round Window)", fontsize=11)
    plt.ylim(30, 95)
    plt.xlim(0, rounds)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(loc="lower right", frameon=True, fontsize=9)
    plt.tight_layout()

    plt.savefig(filepath)
    plt.close()
    print(f"Saved evaluation plot to {filepath}")


def compute_summary_table(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Computes mean +- std of acceptance rate and cumulative reward per policy."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        if r["policy"] == "LinUCB":
            key = f"LinUCB (alpha={r['alpha']})"
        else:
            key = r["policy"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r)

    summary = {}
    for key, items in grouped.items():
        accs = [it["acceptance_rate"] for it in items]
        rews = [it["cumulative_reward"] for it in items]
        summary[key] = {
            "acc_mean": round(float(np.mean(accs)), 4),
            "acc_std": round(float(np.std(accs)), 4),
            "rew_mean": round(float(np.mean(rews)), 2),
            "rew_std": round(float(np.std(rews)), 2)
        }
    return summary


def main():
    csv_path = REPO_ROOT / "docs" / "eval_results.csv"
    png_path = REPO_ROOT / "docs" / "eval_curve.png"

    results = run_experiment(rounds=150)
    save_results_csv(results, csv_path)
    generate_learning_curve_plot(results, png_path, rounds=150)

    summary = compute_summary_table(results)
    print("\n=== EVALUATION SUMMARY (150 Rounds, 3 Personas x 10 Seeds = 30 runs per policy) ===")
    print(f"{'Policy':<25} | {'Acceptance Rate (Mean +- Std)':<30} | {'Cumulative Reward (Mean +- Std)':<30}")
    print("-" * 90)
    for pol, metrics in summary.items():
        acc_str = f"{metrics['acc_mean']*100:.1f}% ± {metrics['acc_std']*100:.1f}%"
        rew_str = f"{metrics['rew_mean']:.1f} ± {metrics['rew_std']:.1f}"
        print(f"{pol:<25} | {acc_str:<30} | {rew_str:<30}")


if __name__ == "__main__":
    main()
