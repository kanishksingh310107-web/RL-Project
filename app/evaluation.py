# Evaluation & Comparative Benchmark
# Compares Contextual LinUCB Adaptive Policy against Static Baseline Recommender.
# Measures acceptance rate, rejection rate, cumulative reward, 95% confidence intervals, and policy weight divergence.

import json
import math
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from app.rl_planner import LinUCBPolicy, extract_context_vector, CANONICAL_ARMS
from app.activity_data import CURATED_ACTIVITIES


def _get_persona_config(user_persona: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Returns (true_preferences, profile_dict) for a synthetic evaluation persona."""
    if user_persona == "nature_enthusiast":
        true_preferences = {
            "nature_outdoors": 1.0,
            "adventure": 0.8,
            "relaxation": 0.6,
            "culture_history": 0.2,
            "shopping_local": -0.6,
            "food_dining": 0.4
        }
        profile_dict = {
            "interests": ["nature_outdoors", "adventure"],
            "pace": 0.7,
            "crowd_tolerance": 0.2,
            "walking_tolerance": "high",
            "budget_tier": "balanced"
        }
    elif user_persona == "culture_buff":
        true_preferences = {
            "culture_history": 1.0,
            "shopping_local": 0.7,
            "food_dining": 0.8,
            "relaxation": 0.3,
            "adventure": -0.5,
            "nature_outdoors": 0.1
        }
        profile_dict = {
            "interests": ["culture_history", "local_experiences"],
            "pace": 0.4,
            "crowd_tolerance": 0.6,
            "walking_tolerance": "medium",
            "budget_tier": "luxury"
        }
    else:  # general balanced
        true_preferences = {
            "culture_history": 0.6,
            "food_dining": 0.7,
            "nature_outdoors": 0.5,
            "adventure": 0.4,
            "relaxation": 0.5,
            "shopping_local": 0.3
        }
        profile_dict = {
            "interests": ["culture_history", "food_dining"],
            "pace": 0.5,
            "crowd_tolerance": 0.5,
            "walking_tolerance": "medium",
            "budget_tier": "balanced"
        }
    return true_preferences, profile_dict


def _run_single_seed_simulation(
    user_persona: str,
    rounds: int,
    seed: int,
    warm_start: bool = False
) -> Dict[str, Any]:
    """
    Simulates a single run with an isolated dedicated RNG to prevent global seed pollution.
    """
    rng = np.random.default_rng(seed)
    true_preferences, profile_dict = _get_persona_config(user_persona)

    # 1. Initialize Adaptive Policy
    adaptive_policy = LinUCBPolicy(user_id=f"sim_user_{seed}", alpha=0.5)

    if warm_start:
        for interest_arm in profile_dict.get("interests", []):
            if interest_arm in adaptive_policy.arms:
                adaptive_policy.arms[interest_arm]["b"][19] = 1.0

    baseline_rewards: List[float] = []
    adaptive_rewards: List[float] = []
    baseline_accepts = 0
    adaptive_accepts = 0
    theta_divergences: List[float] = []

    activities = CURATED_ACTIVITIES.copy()
    trip_config = {"duration_days": 5, "total_budget": 1200.0, "travel_pace": "balanced"}

    for t in range(1, rounds + 1):
        slot = "morning" if t % 2 == 1 else "afternoon"

        # --- A. Baseline Decision (Static Interest Ranking) ---
        def baseline_score(act):
            score = 0.0
            act_cat = act.get("category", "")
            if act_cat in profile_dict.get("interests", []):
                score += 1.5
            return score + float(rng.normal(0, 0.1))

        b_ranked = sorted(activities, key=baseline_score, reverse=True)
        b_chosen = b_ranked[(t - 1) % len(b_ranked)]

        # Latent user response to baseline recommendation
        b_cat = b_chosen.get("category", "")
        b_latent_val = true_preferences.get(b_cat, 0.0)
        p_b_accept = 1.0 / (1.0 + math.exp(-2.0 * b_latent_val))
        b_accepted = bool(rng.random() < p_b_accept)
        b_reward = 1.0 if b_accepted else -1.0
        baseline_rewards.append(b_reward)
        if b_accepted:
            baseline_accepts += 1

        # --- B. Adaptive LinUCB Decision ---
        scored_adaptive = []
        for act in activities:
            arm_id = act["category"] if act["category"] in CANONICAL_ARMS else "culture_history"
            ctx = extract_context_vector(profile_dict, trip_config, t, rounds, slot, act)
            score, _, _ = adaptive_policy.predict_score(arm_id, ctx)
            scored_adaptive.append((score, act, arm_id, ctx))

        scored_adaptive.sort(key=lambda item: item[0], reverse=True)
        a_score, a_chosen, a_arm, a_ctx = scored_adaptive[0]

        # Latent user response to adaptive recommendation
        a_cat = a_chosen.get("category", "")
        a_latent_val = true_preferences.get(a_cat, 0.0)
        p_a_accept = 1.0 / (1.0 + math.exp(-2.0 * a_latent_val))
        a_accepted = bool(rng.random() < p_a_accept)
        a_reward = 1.0 if a_accepted else -1.0
        adaptive_rewards.append(a_reward)
        if a_accepted:
            adaptive_accepts += 1

        # Policy update
        adaptive_policy.update(a_arm, a_ctx, a_reward)

        # Track weight adaptation (Frobenius norm of theta change across arms)
        total_theta_norm = sum(np.linalg.norm(adaptive_policy.get_arm_weights(arm)) for arm in CANONICAL_ARMS)
        theta_divergences.append(round(float(total_theta_norm), 4))

    return {
        "baseline_cumulative_reward": sum(baseline_rewards),
        "baseline_acceptance_rate": baseline_accepts / rounds,
        "baseline_reward_trajectory": [sum(baseline_rewards[:i+1]) for i in range(rounds)],
        "adaptive_cumulative_reward": sum(adaptive_rewards),
        "adaptive_acceptance_rate": adaptive_accepts / rounds,
        "adaptive_reward_trajectory": [sum(adaptive_rewards[:i+1]) for i in range(rounds)],
        "theta_divergences": theta_divergences
    }


def run_comparative_simulation(
    user_persona: str = "nature_enthusiast",
    rounds: int = 20,
    seed: int = 42,
    num_seeds: int = 100,
    warm_start: bool = False
) -> Dict[str, Any]:
    """
    Simulates user interactions to evaluate LinUCB adaptation vs. static baseline.
    Executes an empirical multi-seed Monte Carlo evaluation (default N=100 independent seeds),
    reporting sample means and 95% confidence intervals without global RNG pollution.
    Preserves all response keys required by the frontend and test suites.
    """
    if num_seeds <= 1:
        seeds = [seed]
    else:
        seeds = list(range(num_seeds))

    all_results = [
        _run_single_seed_simulation(
            user_persona=user_persona,
            rounds=rounds,
            seed=s,
            warm_start=warm_start
        )
        for s in seeds
    ]

    n = len(all_results)
    b_rewards = [r["baseline_cumulative_reward"] for r in all_results]
    b_accs = [r["baseline_acceptance_rate"] for r in all_results]
    a_rewards = [r["adaptive_cumulative_reward"] for r in all_results]
    a_accs = [r["adaptive_acceptance_rate"] for r in all_results]

    mean_b_reward = float(np.mean(b_rewards))
    mean_b_acc = float(np.mean(b_accs))
    mean_a_reward = float(np.mean(a_rewards))
    mean_a_acc = float(np.mean(a_accs))

    # Standard deviations and 95% confidence intervals (1.96 * s / sqrt(N))
    std_b_reward = float(np.std(b_rewards, ddof=1)) if n > 1 else 0.0
    std_b_acc = float(np.std(b_accs, ddof=1)) if n > 1 else 0.0
    std_a_reward = float(np.std(a_rewards, ddof=1)) if n > 1 else 0.0
    std_a_acc = float(np.std(a_accs, ddof=1)) if n > 1 else 0.0

    ci_b_reward_hw = round(1.96 * std_b_reward / math.sqrt(n), 4) if n > 1 else 0.0
    ci_b_acc_hw = round(1.96 * std_b_acc / math.sqrt(n), 4) if n > 1 else 0.0
    ci_a_reward_hw = round(1.96 * std_a_reward / math.sqrt(n), 4) if n > 1 else 0.0
    ci_a_acc_hw = round(1.96 * std_a_acc / math.sqrt(n), 4) if n > 1 else 0.0

    # Mean trajectories across seeds
    b_traj_matrix = np.array([r["baseline_reward_trajectory"] for r in all_results])
    a_traj_matrix = np.array([r["adaptive_reward_trajectory"] for r in all_results])
    theta_matrix = np.array([r["theta_divergences"] for r in all_results])

    mean_b_traj = [round(float(val), 2) for val in np.mean(b_traj_matrix, axis=0)]
    mean_a_traj = [round(float(val), 2) for val in np.mean(a_traj_matrix, axis=0)]
    mean_theta_div = [round(float(val), 4) for val in np.mean(theta_matrix, axis=0)]

    rel_improvement = (
        ((mean_a_acc - mean_b_acc) / max(0.001, mean_b_acc)) * 100.0
    )

    return {
        "persona": user_persona,
        "rounds": rounds,
        "seeds_evaluated": n,
        "baseline": {
            "acceptance_rate": round(mean_b_acc, 3),
            "rejection_rate": round(1.0 - mean_b_acc, 3),
            "cumulative_reward": round(mean_b_reward, 2),
            "reward_trajectory": mean_b_traj,
            "confidence_interval_95": {
                "cumulative_reward": [
                    round(mean_b_reward - ci_b_reward_hw, 2),
                    round(mean_b_reward + ci_b_reward_hw, 2)
                ],
                "cumulative_reward_ci_half_width": ci_b_reward_hw,
                "acceptance_rate": [
                    round(mean_b_acc - ci_b_acc_hw, 3),
                    round(mean_b_acc + ci_b_acc_hw, 3)
                ],
                "acceptance_rate_ci_half_width": ci_b_acc_hw
            }
        },
        "adaptive_linucb": {
            "acceptance_rate": round(mean_a_acc, 3),
            "rejection_rate": round(1.0 - mean_a_acc, 3),
            "cumulative_reward": round(mean_a_reward, 2),
            "reward_trajectory": mean_a_traj,
            "policy_adaptation_divergence": mean_theta_div,
            "confidence_interval_95": {
                "cumulative_reward": [
                    round(mean_a_reward - ci_a_reward_hw, 2),
                    round(mean_a_reward + ci_a_reward_hw, 2)
                ],
                "cumulative_reward_ci_half_width": ci_a_reward_hw,
                "acceptance_rate": [
                    round(mean_a_acc - ci_a_acc_hw, 3),
                    round(mean_a_acc + ci_a_acc_hw, 3)
                ],
                "acceptance_rate_ci_half_width": ci_a_acc_hw
            }
        },
        "relative_improvement_pct": round(rel_improvement, 1),
        "evaluation_summary": (
            f"Over {rounds} rounds across {n} seeds (95% CI): "
            f"Static Baseline achieves {mean_b_acc:.1%} acceptance (reward {mean_b_reward:.2f} ± {ci_b_reward_hw:.2f}), "
            f"Adaptive LinUCB achieves {mean_a_acc:.1%} acceptance (reward {mean_a_reward:.2f} ± {ci_a_reward_hw:.2f}). "
            + (
                "Static baseline outperforms LinUCB on short horizons due to 0-exploration-cost keyword prior."
                if mean_b_reward > mean_a_reward
                else "Adaptive LinUCB outperforms static baseline as exploration pays off over extended interactions."
            )
        )
    }


def get_user_live_evaluation(conn, user_id: str) -> Dict[str, Any]:
    """Retrieves empirical acceptance, rejection, and reward metrics for an actual user from SQLite."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT action_type, reward, is_trip_specific, is_implicit, created_at
        FROM rl_feedback_log
        WHERE user_id = ?
        ORDER BY created_at ASC
    """, (user_id,))
    rows = cursor.fetchall()

    total = len(rows)
    if total == 0:
        return {
            "user_id": user_id,
            "total_interactions": 0,
            "acceptance_rate": 0.0,
            "rejection_rate": 0.0,
            "modification_rate": 0.0,
            "cumulative_reward": 0.0,
            "explicit_interactions": 0,
            "implicit_interactions": 0,
            "cumulative_reward_history": []
        }

    accepts = sum(1 for r in rows if r[0] == "accept")
    rejects = sum(1 for r in rows if r[0] == "reject")
    modifies = sum(1 for r in rows if r[0] == "modify")
    implicit = sum(1 for r in rows if r[3] == 1)
    explicit = total - implicit

    cum_rewards = []
    run_sum = 0.0
    for r in rows:
        run_sum += r[1]
        cum_rewards.append(round(run_sum, 2))

    return {
        "user_id": user_id,
        "total_interactions": total,
        "acceptance_rate": round(accepts / total, 3),
        "rejection_rate": round(rejects / total, 3),
        "modification_rate": round(modifies / total, 3),
        "cumulative_reward": round(run_sum, 2),
        "explicit_interactions": explicit,
        "implicit_interactions": implicit,
        "cumulative_reward_history": cum_rewards
    }
