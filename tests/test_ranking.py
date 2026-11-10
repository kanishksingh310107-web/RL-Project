# Tests for Ranking Module
# Owner: Person C
# Verifies scoring components, filters, normalization, edge cases, and API responses.

import pytest
from app.recommender import DESTINATIONS
from app.modules.ranking import (
    DEFAULT_WEIGHTS,
    parse_cost_range,
    parse_season_months,
    calculate_season_score,
    calculate_popularity_score,
)


def test_module_registered(client, demo_user):
    """Ranking module must be auto-discovered in the module registry and its routes must respond."""
    from app.modules import discover
    mods = [m.MODULE for m in discover()]
    ranking_mod = next((m for m in mods if m["id"] == "ranking"), None)
    assert ranking_mod is not None
    assert ranking_mod["owner"] == "C"
    assert ranking_mod["title"] == "Ranking"
    r = client.get(f"/api/ranking/{demo_user}")
    assert r.status_code == 200


def test_default_weights_sum_to_one():
    """Default assumed weights must sum to 1.0."""
    total = sum(DEFAULT_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6


def test_overridden_weights_rescale(client, demo_user):
    """Overriding weights must re-normalize them to sum to 1.0."""
    r = client.get(
        f"/api/ranking/{demo_user}?w_interest=2.0&w_season=2.0&w_popularity=0&w_feasibility=0&w_live=0&w_feedback=0"
    )
    assert r.status_code == 200
    data = r.json()
    weights = data["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-4
    assert abs(weights["interest"] - 0.5) < 1e-4
    assert abs(weights["season"] - 0.5) < 1e-4


def test_every_best_seasons_string_parses():
    """All 16 destinations in the catalogue must yield at least one valid active month."""
    for dest in DESTINATIONS:
        seasons = dest.get("best_seasons", [])
        months = parse_season_months(seasons)
        assert len(months) > 0, f"Failed to parse seasons for {dest['id']}: {seasons}"
        assert all(1 <= m <= 12 for m in months)


def test_season_wrap_around():
    """Ranges that cross the new year (e.g., Nov to Feb, Dec to Feb) must include Dec, Jan, Feb."""
    sample = ["Winter (Dec - Feb) for snow"]
    months = parse_season_months(sample)
    assert {12, 1, 2}.issubset(months)

    # Cape Town "November to March"
    sample2 = ["November to March (warm summer)"]
    months2 = parse_season_months(sample2)
    assert {11, 12, 1, 2, 3}.issubset(months2)


def test_date_changes_season_and_total(client, demo_user):
    """Changing date from November (Kyoto peak) to July must lower Kyoto's season and total score."""
    # November: Autumn foliage
    r_nov = client.get(f"/api/ranking/{demo_user}?date=2026-11-15")
    assert r_nov.status_code == 200
    kyoto_nov = next(x for x in r_nov.json()["overall_ranking"] if x["id"] == "kyoto_japan")

    # July: Off-peak summer
    r_jul = client.get(f"/api/ranking/{demo_user}?date=2026-07-15")
    assert r_jul.status_code == 200
    kyoto_jul = next(x for x in r_jul.json()["overall_ranking"] if x["id"] == "kyoto_japan")

    assert kyoto_nov["breakdown"]["season"]["value"] > kyoto_jul["breakdown"]["season"]["value"]
    assert kyoto_nov["total_score"] > kyoto_jul["total_score"]


def test_budget_cap_excludes_and_gives_reason(client, demo_user):
    """A low budget cap must exclude expensive destinations with clear reason, appearing in no list."""
    cap = 50.0  # Swiss Alps ($210 - $360) and Santorini ($180 - $320) exceed $50 low end
    r = client.get(f"/api/ranking/{demo_user}?budget={cap}")
    assert r.status_code == 200
    data = r.json()

    excluded = data["excluded"]
    excluded_ids = {item["id"] for item in excluded}
    assert "swiss_alps" in excluded_ids
    assert "santorini_greece" in excluded_ids

    # Excluded reason check
    swiss = next(item for item in excluded if item["id"] == "swiss_alps")
    assert "exceeds budget cap" in swiss["reason"]

    # Verify excluded items appear in NO ranked list
    all_included_ids = set()
    for list_key in ["overall_ranking", "trending_now", "best_this_season", "best_for_you", "best_feasible"]:
        all_included_ids.update(x["id"] for x in data[list_key])

    for exc_id in excluded_ids:
        assert exc_id not in all_included_ids


def test_closed_and_advisory_flags_exclude(client, demo_user):
    """Manual closed and advisory query parameters must filter out destinations."""
    r = client.get(f"/api/ranking/{demo_user}?closed=kyoto_japan&advisory=tokyo_japan")
    assert r.status_code == 200
    data = r.json()

    excluded_ids = {x["id"]: x["reason"] for x in data["excluded"]}
    assert "kyoto_japan" in excluded_ids
    assert "closed" in excluded_ids["kyoto_japan"].lower()

    assert "tokyo_japan" in excluded_ids
    assert "advisory" in excluded_ids["tokyo_japan"].lower()


def test_missing_profile_works(client):
    """Ranking request for an unknown user must succeed with has_profile=False and neutral values."""
    r = client.get("/api/ranking/non_existent_user_999")
    assert r.status_code == 200
    data = r.json()
    assert data["has_profile"] is False
    assert len(data["overall_ranking"]) > 0

    first = data["overall_ranking"][0]
    assert first["breakdown"]["interest"]["value"] == 0.5
    assert first["breakdown"]["live"]["value"] == 0.5


def test_profile_interests_change_best_for_you(client):
    """User questionnaire answers in raw_answers_json must match destination tags and affect ranking."""
    # User A: nature lover
    u_nature = client.post(
        "/api/auth",
        json={"provider": "email", "identifier": "nature@test.com", "password": "pass1234", "display_name": "Nature"}
    ).json()["user_id"]
    client.post(
        f"/api/profile/{u_nature}",
        json={"travel_goals": ["nature", "adventure"], "place_interests": ["mountains"]}
    )

    r_nature = client.get(f"/api/ranking/{u_nature}")
    assert r_nature.status_code == 200
    top_nature = r_nature.json()["best_for_you"][0]

    # Manali / Spiti is mountain and nature heavy
    assert top_nature["id"] in ["manali_spiti_india", "swiss_alps", "banff_canada", "patagonia_chile"]


def test_questionnaire_bug_fix_kyoto_nature_culture(client, demo_user):
    """Verifies that reading interests from raw_answers_json gives Kyoto non-zero interest score."""
    # demo_user fixture sets travel_goals: ["nature", "culture"], place_interests: ["mountains", "historic"]
    r = client.get(f"/api/ranking/{demo_user}")
    assert r.status_code == 200
    items = r.json()["overall_ranking"]
    kyoto = next(x for x in items if x["id"] == "kyoto_japan")

    interest_val = kyoto["breakdown"]["interest"]["value"]
    assert interest_val > 0.0, "Interest score for Kyoto must be non-zero after fixing questionnaire reader"


def test_shortlisted_gives_feedback_one(client, demo_user):
    """Shortlisting a destination must give it a feedback score of 1.0."""
    # Shortlist Kyoto
    client.post(f"/api/shortlist/{demo_user}", json={"destination_id": "kyoto_japan"})

    r = client.get(f"/api/ranking/{demo_user}")
    assert r.status_code == 200
    kyoto = next(x for x in r.json()["overall_ranking"] if x["id"] == "kyoto_japan")
    assert kyoto["breakdown"]["feedback"]["value"] == 1.0
    assert "Shortlisted" in kyoto["breakdown"]["feedback"]["note"]


def test_breakdown_contributions_sum_to_total(client, demo_user):
    """The sum of individual component contributions must equal the item's total score."""
    r = client.get(f"/api/ranking/{demo_user}")
    assert r.status_code == 200
    for item in r.json()["overall_ranking"]:
        contributions_sum = sum(comp["contribution"] for comp in item["breakdown"].values())
        assert abs(contributions_sum - item["total_score"]) < 0.05


def test_four_lists_and_limit(client, demo_user):
    """Endpoint must return four separate specialized lists bounded by the limit parameter."""
    limit = 3
    r = client.get(f"/api/ranking/{demo_user}?limit={limit}")
    assert r.status_code == 200
    data = r.json()

    for key in ["trending_now", "best_this_season", "best_for_you", "best_feasible"]:
        assert key in data
        assert len(data[key]) <= limit

    # Check trending_now only contains is_trending items
    for item in data["trending_now"]:
        assert item["is_trending"] is True


def test_bad_date_or_negative_weight_returns_400(client, demo_user):
    """Bad date format or negative weight override must return HTTP 400."""
    r_bad_date = client.get(f"/api/ranking/{demo_user}?date=2026/11/02")
    assert r_bad_date.status_code == 400

    r_bad_weight = client.get(f"/api/ranking/{demo_user}?w_interest=-0.5")
    assert r_bad_weight.status_code == 400

    r_all_zero = client.get(
        f"/api/ranking/{demo_user}?w_interest=0&w_season=0&w_popularity=0&w_feasibility=0&w_live=0&w_feedback=0"
    )
    assert r_all_zero.status_code == 400


def test_evaluation_experiment_output_shape():
    """Verifies scripts/evaluate.py run_experiment generates valid metrics and rates in [0, 1]."""
    from scripts.evaluate import run_experiment
    results = run_experiment(
        personas=["nature_enthusiast"],
        seeds=[42, 43],
        alphas=[0.5],
        rounds=20
    )
    # Expected policies per seed: Oracle, Static Baseline, Random, LinUCB (alpha=0.5) -> 4 * 2 seeds = 8 runs
    assert len(results) == 8
    for r in results:
        assert 0.0 <= r["acceptance_rate"] <= 1.0
        assert r["rounds"] == 20
        assert -20.0 <= r["cumulative_reward"] <= 20.0
        assert len(r["window_acceptance"]) == 2  # 20 rounds / 10-round window = 2 windows

