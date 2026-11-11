"""Unit tests for app.core.assumptions consistency and constraints."""
import math
from app.core.assumptions import (
    BUDGET_SHARES,
    RANKING_DEFAULT_WEIGHTS,
    MODE_SPEEDS_KMH,
    CATEGORY_DURATIONS_MINUTES,
    CIRCUITY_FACTOR,
    GEOAPIFY_DAILY_CREDIT_LIMIT,
    GEOAPIFY_MAX_CALLS_PER_REQUEST,
)


def test_budget_shares_sum_to_one():
    total = sum(BUDGET_SHARES.values())
    assert math.isclose(total, 1.0, abs_tol=1e-5), f"Budget shares sum to {total}, expected 1.0"


def test_ranking_weights_sum_to_one():
    total = sum(RANKING_DEFAULT_WEIGHTS.values())
    assert math.isclose(total, 1.0, abs_tol=1e-5), f"Ranking weights sum to {total}, expected 1.0"


def test_transport_speeds_positive():
    for mode, speed in MODE_SPEEDS_KMH.items():
        assert speed > 0.0, f"Speed for {mode} must be positive"


def test_category_durations_positive():
    for cat, duration in CATEGORY_DURATIONS_MINUTES.items():
        assert duration >= 15, f"Duration for {cat} must be at least 15 mins"


def test_circuity_factor_valid():
    assert CIRCUITY_FACTOR >= 1.0, "Circuity factor must be at least 1.0"


def test_credit_limits_positive():
    assert GEOAPIFY_DAILY_CREDIT_LIMIT > 0
    assert GEOAPIFY_MAX_CALLS_PER_REQUEST > 0
