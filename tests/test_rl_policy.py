# Unit Tests for LinUCB Policy & Sherman-Morrison Rank-1 Inversion Updates
# Author: Atharva Sokhal (RL Evaluation & Modules)

import numpy as np
import pytest
from app.rl_planner import LinUCBPolicy, FEATURE_DIMENSION, CANONICAL_ARMS


def test_sherman_morrison_rank1_update_matches_matrix_inversion():
    """
    Verifies that maintaining A_inv incrementally via the Sherman-Morrison rank-1 update:
        A_inv <- A_inv - (A_inv @ x @ x^T @ A_inv) / (1 + x^T @ A_inv @ x)
    produces identical results to direct np.linalg.inv(A) over multiple sequential updates.
    """
    rng = np.random.default_rng(1337)
    policy = LinUCBPolicy(user_id="test_sm_user", alpha=0.5)
    arm = "nature_outdoors"

    for step in range(50):
        # Generate random continuous context vector
        context = rng.normal(loc=0.0, scale=1.0, size=FEATURE_DIMENSION)
        reward = float(rng.choice([1.0, -1.0, 0.2, -0.4]))

        policy.update(arm, context, reward)

        arm_data = policy.arms[arm]
        A = arm_data["A"]
        A_inv_sm = arm_data["A_inv"]
        A_inv_direct = np.linalg.inv(A)

        # Numerical equivalence assertion
        assert np.allclose(A_inv_sm, A_inv_direct, atol=1e-7), (
            f"Step {step}: Sherman-Morrison A_inv diverged from np.linalg.inv(A). "
            f"Max absolute diff: {np.max(np.abs(A_inv_sm - A_inv_direct))}"
        )


def test_predict_score_numerical_equivalence():
    """
    Verifies that predict_score produces identical exploitation and exploration terms
    whether using maintained A_inv or freshly inverted np.linalg.inv(A).
    """
    rng = np.random.default_rng(2026)
    policy = LinUCBPolicy(user_id="test_pred_user", alpha=0.7)
    arm = "adventure"

    # Seed the policy with several updates
    for _ in range(15):
        ctx = rng.uniform(0.0, 1.0, size=FEATURE_DIMENSION)
        policy.update(arm, ctx, reward=1.0)

    test_context = rng.uniform(0.0, 1.0, size=FEATURE_DIMENSION)
    total_score, exploitation, exploration = policy.predict_score(arm, test_context)

    # Reference computation using direct inverse
    arm_data = policy.arms[arm]
    A_inv_direct = np.linalg.inv(arm_data["A"])
    theta_direct = A_inv_direct.dot(arm_data["b"])
    ref_exploit = float(np.dot(theta_direct, test_context))
    ref_variance = float(np.dot(test_context, A_inv_direct.dot(test_context)))
    ref_explore = 0.7 * np.sqrt(max(0.0, ref_variance))
    ref_total = ref_exploit + ref_explore

    assert abs(total_score - ref_total) < 1e-7
    assert abs(exploitation - ref_exploit) < 1e-7
    assert abs(exploration - ref_explore) < 1e-7


def test_get_arm_weights_equivalence():
    """Verifies get_arm_weights returns A_inv @ b matching direct inverse."""
    rng = np.random.default_rng(999)
    policy = LinUCBPolicy(user_id="test_weights_user", alpha=0.5)
    arm = "culture_history"

    for _ in range(10):
        ctx = rng.normal(0, 1, size=FEATURE_DIMENSION)
        policy.update(arm, ctx, reward=1.0)

    weights = policy.get_arm_weights(arm)
    direct_weights = np.linalg.inv(policy.arms[arm]["A"]).dot(policy.arms[arm]["b"])
    assert np.allclose(weights, direct_weights, atol=1e-7)
