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
        rounds=20,
        include_mismatched=False
    )
    # Expected policies per seed: Oracle, Greedy Top-Match, Random-within-Match, Cycling Baseline, Random, LinUCB -> 6 * 2 seeds = 12 runs
    assert len(results) == 12
    for r in results:
        assert 0.0 <= r["acceptance_rate"] <= 1.0
        assert r["rounds"] == 20
        assert -20.0 <= r["cumulative_reward"] <= 20.0
        assert len(r["window_acceptance"]) == 2  # 20 rounds / 10-round window = 2 windows


def test_india_search_success(client, monkeypatch):
    """GET /api/ranking/india/search returns live coordinates, climate score, and density proxy."""
    monkeypatch.setattr(
        "app.providers.geo.geocode_india",
        lambda q: {"name": "Jaipur", "lat": 26.9124, "lon": 75.7873, "formatted": "Jaipur, Rajasthan, India"}
    )
    monkeypatch.setattr(
        "app.providers.weather.get_seasonality_score",
        lambda lat, lon, month: 0.88
    )
    monkeypatch.setattr(
        "app.providers.weather.get_historical_climate",
        lambda lat, lon, month: {"mean_temp_c": 21.5, "rainfall_mm": 5.0, "comfort_category": "pleasant"}
    )
    from app.core.schemas import Place, Provenance
    dummy_place = Place(
        id="p1", name="Hawa Mahal", category="culture_history", lat=26.92, lon=75.82,
        provenance=Provenance(source="geoapify", is_live=True)
    )
    monkeypatch.setattr(
        "app.providers.geo.get_places_by_category",
        lambda lat, lon, cat, limit=5: [dummy_place]
    )

    r = client.get("/api/ranking/india/search?q=Jaipur&month=11")
    assert r.status_code == 200
    data = r.json()
    assert data["query"] == "Jaipur"
    assert data["geocoding"]["lat"] == 26.9124
    assert data["season_score"] == 0.88
    assert data["climate_summary"]["mean_temp_c"] == 21.5
    assert data["climate_summary"]["rainfall_mm"] == 5.0
    assert "is_comfortable" in data["climate_summary"]
    assert "density_score" in data["popularity_proxy"]
    assert "Geoapify" in data["provenance"]["geocoding"]
    assert "Open-Meteo" in data["provenance"]["climate"]


def test_india_search_validation_and_404(client, monkeypatch):
    """Validation errors: empty query returns 400; unresolvable location returns 404."""
    r_empty = client.get("/api/ranking/india/search?q=")
    assert r_empty.status_code == 400

    monkeypatch.setattr("app.providers.geo.geocode_india", lambda q: None)
    r_not_found = client.get("/api/ranking/india/search?q=NonExistentTown12345")
    assert r_not_found.status_code == 404


def test_inr_cost_parsing():
    """Verify parse_cost_range handles Indian Rupee (₹) ranges with commas."""
    low, high = parse_cost_range("₹2,500 - ₹4,500 / day · Budget")
    assert low is not None and high is not None
    # 2500 * 0.012 = 30 USD, 4500 * 0.012 = 54 USD
    assert low == 30
    assert high == 54

    # Standard USD range still works
    low_usd, high_usd = parse_cost_range("$100 - $200")
    assert low_usd == 100
    assert high_usd == 200


def test_avoidance_filter_excludes_destination(client, demo_user, monkeypatch):
    """User profile avoidance of a specific place must place it in the excluded list with a reason."""
    from app.core.profile import load_profile
    base_profile = load_profile(demo_user)
    base_profile["avoidances"] = ["swiss_alps"]
    monkeypatch.setattr("app.modules.ranking.load_profile", lambda uid: base_profile)

    r = client.get(f"/api/ranking/{demo_user}")
    assert r.status_code == 200
    data = r.json()
    excluded_ids = {x["id"]: x["reason"] for x in data["excluded"]}
    assert "swiss_alps" in excluded_ids
    assert "avoidances" in excluded_ids["swiss_alps"].lower()


def test_avoid_crowds_penalizes_high_crowd_destination(client, demo_user, monkeypatch):
    """User avoidance 'avoid_crowds' must add a crowd penalty note on high-crowd destinations."""
    from app.core.profile import load_profile
    base_profile = load_profile(demo_user)
    base_profile["avoidances"] = ["avoid_crowds"]
    monkeypatch.setattr("app.modules.ranking.load_profile", lambda uid: base_profile)

    r = client.get(f"/api/ranking/{demo_user}")
    assert r.status_code == 200
    data = r.json()
    high_crowd_items = [x for x in data["overall_ranking"] if x["crowd_level"] == "high"]
    if high_crowd_items:
        assert "avoidance_warning" in high_crowd_items[0]
        assert "crowd" in high_crowd_items[0]["avoidance_warning"].lower()


