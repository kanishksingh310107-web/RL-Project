# Evaluation & Comparative Benchmark
# Compares Contextual LinUCB Adaptive Policy against Static Baseline Recommender.
# Measures acceptance rate, rejection rate, cumulative reward, and policy weight divergence.

import json
import math
import numpy as np
from typing import Dict, Any, List, Tuple
from app.rl_planner import LinUCBPolicy, extract_context_vector, CANONICAL_ARMS
from app.activity_data import CURATED_ACTIVITIES

def run_comparative_simulation(
    user_persona: str = "nature_enthusiast",
    rounds: int = 20,
    seed: int = 42
) -> Dict[str, Any]:
    """
    Simulates user interactions to evaluate LinUCB adaptation vs. static baseline.
    Does NOT assume convergence; records step-by-step empirical trajectories.
    """
    np.random.seed(seed)

    # Define true latent preference profile for the synthetic evaluation persona
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
    else: # general balanced
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

    # 1. Initialize Adaptive Policy
    adaptive_policy = LinUCBPolicy(user_id="sim_user", alpha=0.5)
    initial_theta_norm = 0.0

    # 2. Track metrics over rounds
    baseline_rewards = []
    adaptive_rewards = []
    baseline_accepts = 0
    adaptive_accepts = 0
    theta_divergences = []

    activities = CURATED_ACTIVITIES.copy()
    trip_config = {"duration_days": 5, "total_budget": 1200.0, "travel_pace": "balanced"}

    for t in range(1, rounds + 1):
        slot = "morning" if t % 2 == 1 else "afternoon"

        # --- A. Baseline Decision (Static Ranking) ---
        # Baseline ranks based on static interest keyword matching
        def baseline_score(act):
            score = 0.0
            act_cat = act.get("category", "")
            if act_cat in profile_dict.get("interests", []):
                score += 1.5
            return score + np.random.normal(0, 0.1)

        b_ranked = sorted(activities, key=baseline_score, reverse=True)
        b_chosen = b_ranked[(t - 1) % len(b_ranked)]

        # True user response to baseline recommendation
        b_cat = b_chosen.get("category", "")
        b_latent_val = true_preferences.get(b_cat, 0.0)
        # Probabilistic accept based on latent preference
        p_b_accept = 1.0 / (1.0 + math.exp(-2.0 * b_latent_val))
        b_accepted = (np.random.rand() < p_b_accept)
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

        # True user response to adaptive recommendation
        a_cat = a_chosen.get("category", "")
        a_latent_val = true_preferences.get(a_cat, 0.0)
        p_a_accept = 1.0 / (1.0 + math.exp(-2.0 * a_latent_val))
        a_accepted = (np.random.rand() < p_a_accept)
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
        "persona": user_persona,
        "rounds": rounds,
        "baseline": {
            "acceptance_rate": round(baseline_accepts / rounds, 3),
            "rejection_rate": round(1.0 - (baseline_accepts / rounds), 3),
            "cumulative_reward": sum(baseline_rewards),
            "reward_trajectory": [sum(baseline_rewards[:i+1]) for i in range(rounds)]
        },
        "adaptive_linucb": {
            "acceptance_rate": round(adaptive_accepts / rounds, 3),
            "rejection_rate": round(1.0 - (adaptive_accepts / rounds), 3),
            "cumulative_reward": sum(adaptive_rewards),
            "reward_trajectory": [sum(adaptive_rewards[:i+1]) for i in range(rounds)],
            "policy_adaptation_divergence": theta_divergences
        },
        "relative_improvement_pct": round(
            ((adaptive_accepts - baseline_accepts) / max(1, baseline_accepts)) * 100.0, 1
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
