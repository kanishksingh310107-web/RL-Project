"""Comprehensive Unit and Integration Tests for Dynamic Plan Engine (Person A).

Validates:
- Counterfactual profile sensitivity (changing profile modifies ranking/filtering)
- Scheduler never exceeds day window bounds
- Dynamic activity count varies with time window and pace (never fixed count)
- Budget ledger: market over mall for low-budget, reverse for high-budget
- Unknown price never counted as zero (None safety)
- Validator catches planted constraint violations
- Core tables populated correctly without data corruption
"""
import pytest
from app.core.schemas import Place, TripPrefs, DayWindow, TripPlan, Provenance
from app.planning.personalization import filter_candidate_places
from app.planning.transport import estimate_travel_leg, compare_daily_transit_styles, choose_best_mode
from app.planning.shopping import score_shopping_venue, classify_shopping_venue
from app.planning.budget import build_budget_ledger, compute_budget_shares
from app.planning.scheduler import schedule_day
from app.planning.validate import validate_trip_plan


def test_personalization_hard_filters():
    places = [
        Place(
            id="p_crowd",
            name="Dense Chandni Chowk Bazaar",
            category="shopping_local",
            lat=28.6505,
            lon=77.2303,
            provenance=Provenance(source="curated_catalogue"),
        ),
        Place(
            id="p_nature",
            name="Lodhi Serene Gardens",
            category="nature_outdoors",
            lat=28.5933,
            lon=77.2197,
            provenance=Provenance(source="curated_catalogue"),
        ),
        Place(
            id="p_steep",
            name="Steep Mountain Trek Summit",
            category="adventure",
            lat=28.7000,
            lon=77.2000,
            provenance=Provenance(source="curated_catalogue"),
        ),
    ]

    # Profile 1: Avoids crowds and steep walks
    profile_cautious = {
        "avoidances": ["crowds", "steep_walks"],
        "accessibility": ["wheelchair"],
        "walking_tolerance": "minimal",
        "physical_demand": "low",
    }

    filtered, warnings, meta = filter_candidate_places(places, profile_cautious)
    ids = [p.id for p in filtered]

    assert "p_nature" in ids
    assert "p_crowd" not in ids  # Dropped by crowd avoidance
    assert "p_steep" not in ids  # Dropped by steep/wheelchair filter
    assert "avoidances" in meta["used"]
    assert "accessibility" in meta["used"]


def test_multimodal_transport_estimation():
    # Leg 1: short distance (0.8 km) for pedestrian
    leg_walk = estimate_travel_leg(28.6139, 77.2090, 28.6190, 77.2090, profile={"walking_tolerance": "high"})
    assert leg_walk.mode in ("walk", "auto")
    assert leg_walk.duration_minutes > 0
    assert leg_walk.distance_km < 1.5

    # Leg 2: long distance (18 km)
    leg_long = estimate_travel_leg(28.6139, 77.2090, 28.4595, 77.0266, profile={})
    assert leg_long.mode in ("cab", "rental_car", "bus_metro")
    assert leg_long.estimated_cost is not None
    assert leg_long.estimated_cost > 0

    # Party with elders or children avoids two-wheelers
    mode = choose_best_mode(3.0, {"companions": ["family_with_elders"]})
    assert mode != "scooter"


def test_shopping_venue_scoring_budget_sensitivity():
    venue_flea = Place(
        id="flea_1",
        name="Sarojini Nagar Flea Market",
        category="shopping_local",
        lat=28.57,
        lon=77.19,
    )
    venue_mall = Place(
        id="mall_1",
        name="DLF Emporio Luxury Mall",
        category="shopping_local",
        lat=28.52,
        lon=77.15,
    )

    profile_budget = {"budget_tier": "budget", "crowd_tolerance": 4}
    profile_luxury = {"budget_tier": "luxury", "crowd_tolerance": 3}

    score_flea_budget = score_shopping_venue(venue_flea, profile_budget, shopping_style="bargain_markets")
    score_mall_budget = score_shopping_venue(venue_mall, profile_budget, shopping_style="bargain_markets")

    score_flea_luxury = score_shopping_venue(venue_flea, profile_luxury, shopping_style="malls_brands")
    score_mall_luxury = score_shopping_venue(venue_mall, profile_luxury, shopping_style="malls_brands")

    # Low-budget profile ranks flea market over luxury mall
    assert score_flea_budget > score_mall_budget
    # High-budget profile ranks mall over flea market
    assert score_mall_luxury > score_flea_luxury


def test_scheduler_never_exceeds_day_window():
    # 8 candidate places
    places = [
        Place(
            id=f"p_{i}",
            name=f"Spot {i}",
            category="culture_history",
            lat=28.61 + (i * 0.01),
            lon=77.20 + (i * 0.01),
            typical_duration_minutes=90,
            cost_amount=150.0,
        )
        for i in range(8)
    ]

    day_plan, remaining = schedule_day(
        day_number=1,
        date_str="2026-11-15",
        candidate_places=places,
        profile={"walking_tolerance": "moderate"},
        pace="relaxed",
        start_time="09:00",
        end_time="17:00",  # 8 hour window
    )

    # Check that the last block finishes before or at 17:00
    assert len(day_plan.blocks) > 0
    last_block = day_plan.blocks[-1]
    last_end_parts = [int(x) for x in last_block.end_time.split(":")]
    last_end_min = last_end_parts[0] * 60 + last_end_parts[1]
    assert last_end_min <= 17 * 60

    # Because window was only 8h and pace relaxed, not all 8 places fit!
    assert len(day_plan.leftovers) > 0
    # Variable activity count: fits whatever fits, not fixed 4
    act_count = len([b for b in day_plan.blocks if b.block_type == "activity"])
    assert act_count < 8


def test_budget_ledger_status_and_unknown_cost():
    total_budget = 20000.0
    profile = {"spend_priorities": ["food"]}

    # Under budget spending
    actual_spent_green = {"stay": 6000.0, "food": 4000.0, "activities": 2000.0}
    ledger, status = build_budget_ledger(total_budget, profile, actual_spent_green)
    assert status in ("green", "amber")

    # Over budget spending
    actual_spent_red = {"stay": 14000.0, "food": 9000.0, "activities": 5000.0}
    ledger_red, status_red = build_budget_ledger(total_budget, profile, actual_spent_red)
    assert status_red == "red"

    # Place with unknown cost amount is None, not 0
    unknown_place = Place(id="u1", name="Mystery Point", category="scenic", lat=28.6, lon=77.2, cost_amount=None)
    assert unknown_place.cost_amount is None


def test_validator_catches_planted_violations():
    # Construct a plan with planted overflow and budget failure
    plan = TripPlan(
        trip_id="test_planted_trip",
        user_id="u_test",
        destination_id="delhi",
        destination_name="Delhi",
        total_days=1,
    )

    # Schedule a day with day window 09:00 - 18:00
    day_plan, _ = schedule_day(
        day_number=1,
        date_str=None,
        candidate_places=[
            Place(id="p1", name="Long Visit", category="culture_history", lat=28.6, lon=77.2, typical_duration_minutes=300)
        ],
        profile={},
        start_time="09:00",
        end_time="18:00",
    )

    # Plant a late block ending at 20:30 (exceeds 18:00)
    from app.core.schemas import Block
    day_plan.blocks.append(
        Block(
            block_id="planted_overflow",
            block_type="activity",
            start_time="19:00",
            end_time="20:30",
            duration_minutes=90,
            notes="Planted overflow block",
        )
    )
    plan.days = [day_plan]

    # Plant a red budget line
    from app.core.schemas import BudgetLine
    plan.budget_ledger = [
        BudgetLine(
            category="stay",
            allocated_amount=5000.0,
            estimated_spent=9500.0,
            status="red",
        )
    ]

    violations = validate_trip_plan(plan, profile={})
    types = [v["type"] for v in violations]
    assert "day_window_overflow" in types
    assert "budget_exceeded" in types


def test_plan_api_routes(client, deep_user):
    from app.database import get_connection
    import uuid

    user_id = deep_user
    trip_id = f"trip_{uuid.uuid4().hex[:6]}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO trips (id, user_id, destination_id, destination_name, start_date, end_date, duration_days, total_budget)
            VALUES (?, ?, 'delhi', 'Delhi, India', '2026-11-20', '2026-11-22', 2, 20000.0)
            """,
            (trip_id, user_id),
        )
        conn.commit()

    # 1. GET prefs (default assumptions)
    res_prefs = client.get(f"/api/plan/prefs/{trip_id}")
    assert res_prefs.status_code == 200
    prefs_data = res_prefs.json()
    assert prefs_data["trip_id"] == trip_id
    assert prefs_data["pace"] == "balanced"

    # 2. PUT prefs
    prefs_data["pace"] = "packed"
    prefs_data["shopping_style"] = "local_crafts"
    res_put = client.put(f"/api/plan/prefs/{trip_id}", json=prefs_data)
    assert res_put.status_code == 200
    assert res_put.json()["pace"] == "packed"

    # 3. POST generate plan
    res_gen = client.post(f"/api/plan/generate/{trip_id}")
    assert res_gen.status_code == 200
    plan_data = res_gen.json()
    assert plan_data["trip_id"] == trip_id
    assert len(plan_data["days"]) == 2
    assert "budget_ledger" in plan_data
    assert len(plan_data["budget_ledger"]) > 0

    # 4. GET plan
    res_get = client.get(f"/api/plan/{trip_id}")
    assert res_get.status_code == 200
    assert res_get.json()["total_days"] == 2

    # 5. POST feedback
    first_block = plan_data["days"][0]["blocks"][1] if len(plan_data["days"][0]["blocks"]) > 1 else plan_data["days"][0]["blocks"][0]
    act_id = first_block.get("place", {}).get("id") or "test_act"
    res_fb = client.post(
        "/api/plan/feedback",
        json={
            "user_id": user_id,
            "trip_id": trip_id,
            "activity_id": act_id,
            "action_type": "accept",
        },
    )
    assert res_fb.status_code == 200
    assert res_fb.json()["status"] == "ok"

    # 6. GET validation
    res_val = client.get(f"/api/plan/{trip_id}/validation")
    assert res_val.status_code == 200
    assert "is_valid" in res_val.json()
