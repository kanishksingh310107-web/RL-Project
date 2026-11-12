"""Targeted tests for Task 4 (Hotel Selection in Trip Planning) and Task 5 (Explore Details).
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from app.core.stores import load_stay, load_trip_plan


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def setup_user_and_trip(client, demo_user):
    """Takes demo_user and completes their precision/detailed profile so trip planning is unlocked."""
    client.post(
        f"/api/profile/precision/{demo_user}",
        json={
            "b01_age_group": "25_34",
            "b02_travel_experience": "frequent",
            "b03_companions": "couple",
            "b04_planning_approach": "plan_essentials",
            "b05_travel_goals": ["culture_immersion", "relaxation"],
            "b06_place_interests": ["heritage_monuments", "artisan_markets"],
            "b14_preferred_environment": ["historic_old_quarters"],
            "b15_weather_sensitivity": "comfortable_any",
            "b20_food_adventurousness": "high",
            "b26_climate_preference": "mild",
            "b32_budget_tier": "mid_range",
            "b36_preferred_transport": ["metro", "cabs"],
            "b41_assistance_autonomy": "balanced",
        },
    )
    return demo_user


# ============================================================================
# TASK 4: HOTEL SELECTION (OPTION A & OPTION B)
# ============================================================================

def test_option_a_stay_search(client):
    """Tests pre-trip hotel search near destination with real properties and budget band."""
    res = client.get("/api/stay/search?destination_id=jaipur_india&budget=24000&duration_days=4")
    assert res.status_code == 200
    data = res.json()
    assert "options" in data
    assert data["estimated_nightly_budget_inr"] > 0
    assert "Jaipur" in data["destination"]
    assert len(data["options"]) > 0

    first = data["options"][0]
    assert "name" in first
    assert "lat" in first
    assert "lon" in first
    assert "external_search_url" in first


def test_option_a_create_trip_with_hotel_anchor(client, setup_user_and_trip):
    """Tests Option A: Creating a trip with pre-selected hotel anchors in core_stays."""
    user_id = setup_user_and_trip

    trip_payload = {
        "destination_id": "jaipur_india",
        "destination_name": "Jaipur, Rajasthan",
        "start_date": "2026-11-20",
        "end_date": "2026-11-23",
        "duration_days": 4,
        "travellers_count": 2,
        "companions": "couple",
        "has_children": False,
        "has_elderly": False,
        "departure_location": "Delhi",
        "total_budget": 30000.0,
        "currency": "INR",
        "accommodation_tier": "boutique",
        "transit_pref": "cab_rental",
        "travel_pace": "balanced",
        "specific_interests": ["history"],
        "stay_id": "stay_jaipur_heritage_haveli",
        "stay_name": "Alsisar Haveli Heritage Hotel",
        "stay_lat": 26.9242,
        "stay_lon": 75.8014,
        "stay_address": "Sansar Chandra Road, Jaipur, Rajasthan",
        "stay_type": "hotel",
    }

    res = client.post(f"/api/trips/{user_id}", json=trip_payload)
    assert res.status_code == 200
    trip_data = res.json()
    assert trip_data["stay_name"] == "Alsisar Haveli Heritage Hotel"
    assert trip_data["stay_id"] == "stay_jaipur_heritage_haveli"

    # Verify stay was persisted in core_stays
    saved_stay = load_stay(trip_data["id"])
    assert saved_stay is not None
    assert saved_stay.name == "Alsisar Haveli Heritage Hotel"
    assert saved_stay.lat == 26.9242
    assert saved_stay.lon == 75.8014


def test_option_b_hotel_replan(client, setup_user_and_trip):
    """Tests Option B: Generating itinerary first, then selecting hotel and replanning."""
    user_id = setup_user_and_trip

    # 1. Create trip without hotel
    trip_payload = {
        "destination_id": "jaipur_india",
        "destination_name": "Jaipur, Rajasthan",
        "start_date": "2026-11-20",
        "end_date": "2026-11-22",
        "duration_days": 3,
        "travellers_count": 1,
        "total_budget": 20000.0,
        "currency": "INR",
        "departure_location": "Delhi",
    }
    trip_res = client.post(f"/api/trips/{user_id}", json=trip_payload)
    assert trip_res.status_code == 200
    trip_id = trip_res.json()["id"]

    # 2. Generate initial plan
    plan_gen = client.post(f"/api/plan/generate/{trip_id}")
    assert plan_gen.status_code == 200

    # 3. Explore recommended stay areas (commute sum optimization)
    areas_res = client.get(f"/api/stay/{trip_id}/areas")
    assert areas_res.status_code == 200
    areas_data = areas_res.json()
    assert len(areas_data["recommended_areas"]) <= 3
    top_area = areas_data["recommended_areas"][0]
    assert "area_name" in top_area
    assert "estimated_daily_commute_minutes" in top_area

    # 4. Select hotel in that area
    select_payload = {
        "stay_id": "stay_opt_b_1",
        "trip_id": trip_id,
        "name": "Diggi Palace Heritage Hotel",
        "stay_type": "hotel",
        "lat": top_area["lat"],
        "lon": top_area["lon"],
        "address": f"Near {top_area['area_name']}, Jaipur",
        "provenance": {
            "source": "post_plan_selection",
            "is_live": False,
            "is_estimate": True,
        },
    }
    sel_res = client.post(f"/api/stay/{trip_id}/select", json=select_payload)
    assert sel_res.status_code == 200

    # 5. Replan itinerary anchored to the hotel
    replan_res = client.post(f"/api/stay/{trip_id}/replan")
    assert replan_res.status_code == 200
    replan_data = replan_res.json()
    assert replan_data["status"] == "success"
    assert replan_data["stay"]["name"] == "Diggi Palace Heritage Hotel"

    # Verify plan was regenerated with hotel anchor
    reloaded_plan = load_trip_plan(trip_id)
    assert reloaded_plan is not None
    # Check that day commute is anchored to hotel
    first_block = reloaded_plan.days[0].blocks[0]
    assert first_block.block_type in ("travel", "activity")


# ============================================================================
# TASK 5: EXPLORE DESTINATION DETAILS
# ============================================================================

def test_explore_destination_details_comprehensive(client, setup_user_and_trip):
    """Tests GET /api/destination/{dest_id}/explore with all 11 required elements."""
    user_id = setup_user_and_trip
    res = client.get(f"/api/destination/jaipur_india/explore?user_id={user_id}&duration_days=3&departure_location=Delhi")
    assert res.status_code == 200
    data = res.json()

    # 1. Overview
    assert "name" in data
    assert "overview" in data
    assert "image_url" in data
    assert "tags" in data

    # 2. Personalized "Why Recommended For You"
    assert "why_recommended_for_you" in data
    assert len(data["why_recommended_for_you"]) >= 2

    # 3. Main Attractions with Descriptions & Cost Labels
    assert "main_attractions" in data
    assert len(data["main_attractions"]) >= 3
    first_att = data["main_attractions"][0]
    assert "name" in first_att
    assert "category" in first_att
    assert "cost_label" in first_att
    assert "description" in first_att
    assert "opening_hours" in first_att

    # 4. Recommended Duration
    assert data["recommended_duration_days"] >= 3

    # 5. Suggested Day-Wise Itinerary (Morning, Afternoon, Evening)
    assert "suggested_itinerary" in data
    assert len(data["suggested_itinerary"]) == 3
    day1 = data["suggested_itinerary"][0]
    assert "slots" in day1
    slot_names = [s.get("slot") for s in day1["slots"]]
    assert any("Morning" in s for s in slot_names)
    assert any("Midday" in s or "Lunch" in s for s in slot_names)
    assert any("Afternoon" in s for s in slot_names)
    assert any("Evening" in s for s in slot_names)

    # 6. Culinary & Dining Experiences
    assert "food_experiences" in data
    assert len(data["food_experiences"]) >= 2
    assert "cost_est" in data["food_experiences"][0]

    # 7. Shopping Recommendations
    assert "shopping_recommendations" in data
    assert len(data["shopping_recommendations"]) >= 1

    # 8. Realistic Budget Summary
    assert "budget_summary" in data
    bs = data["budget_summary"]
    assert bs["bare_minimum_budget"] > 0
    assert bs["recommended_budget"] >= bs["bare_minimum_budget"]
    assert len(bs["categories"]) == 8

    # 9. Practical Tips
    assert "practical_tips" in data
    assert len(data["practical_tips"]) >= 3
