"""
Tests for Realistic Trip Budget System (Task 3)
Validates:
1. Minimum estimated budget calculation across 8 specific categories:
   - Intercity travel (to destination and return)
   - Local transportation
   - Accommodation (group room sharing and duration nights)
   - Food & meals (per person per day)
   - Attraction entry fees & activities (database verified or realistic estimates)
   - Shopping allowance (selected vs unselected)
   - Necessary incidental expenses
   - Contingency buffer (5% bare min vs 10% recommended)
2. Transparent price provenance: verified, estimated, unavailable.
3. Slider configuration (min, max, step).
4. Budget validation endpoint (shortfall, surplus, feasibility, and tier).
5. Itinerary adaptation to budget tier.
"""
import pytest
from app.planning.budget import (
    calculate_minimum_trip_budget,
    validate_trip_budget,
    adapt_itinerary_to_budget,
    MAJOR_INDIAN_HUBS,
)


def test_estimate_minimum_trip_budget_solo_short_trip():
    # 3 days in Jaipur from Delhi (approx 260 km)
    budget_data = calculate_minimum_trip_budget(
        destination_name="Jaipur, Rajasthan",
        departure_location="Delhi",
        duration_days=3,
        travellers_count=1,
        accommodation_tier="budget_hotel",
        transit_pref="public_transit",
        travel_pace="balanced",
        include_shopping=False,
    )

    assert budget_data["duration_days"] == 3
    assert budget_data["travellers_count"] == 1
    assert budget_data["bare_minimum_budget"] > 0
    assert budget_data["recommended_budget"] > budget_data["bare_minimum_budget"]

    # Verify 8 categories
    categories = {c["category"]: c for c in budget_data["categories"]}
    expected_categories = [
        "intercity_transit",
        "local_transit",
        "accommodation",
        "food",
        "activities",
        "shopping",
        "necessary_extras",
        "contingency_buffer",
    ]
    for cat_id in expected_categories:
        assert cat_id in categories, f"Missing category: {cat_id}"
        cat = categories[cat_id]
        assert cat["data_source"] in ("verified", "estimated", "unavailable")
        assert cat["minimum_cost"] >= 0
        assert cat["recommended_cost"] >= cat["minimum_cost"]

    # Shopping was False -> should be 0
    assert categories["shopping"]["minimum_cost"] == 0
    assert categories["shopping"]["recommended_cost"] == 0

    # Slider bounds
    slider = budget_data["slider_config"]
    assert slider["min"] == budget_data["bare_minimum_budget"]
    assert slider["max"] >= budget_data["recommended_budget"]
    assert slider["step"] == 500


def test_estimate_minimum_trip_budget_group_room_sharing_and_shopping():
    # 5 travellers in Goa for 5 days with shopping included
    budget_data = calculate_minimum_trip_budget(
        destination_name="Goa",
        departure_location="Mumbai",
        duration_days=5,
        travellers_count=5,
        accommodation_tier="budget_hotel",
        transit_pref="public_transit",
        travel_pace="relaxed",
        include_shopping=True,
    )

    categories = {c["category"]: c for c in budget_data["categories"]}

    # 5 travellers -> ceil(5/2) = 3 rooms, 4 nights (5-1)
    # Total room nights = 3 * 4 = 12 room-nights
    accom = categories["accommodation"]
    assert "3 room" in accom["description"]
    assert "4 night" in accom["description"]
    assert accom["minimum_cost"] > 0

    # Shopping was True -> non-zero amount
    assert categories["shopping"]["minimum_cost"] > 0
    assert categories["shopping"]["recommended_cost"] > categories["shopping"]["minimum_cost"]


def test_same_city_intercity_is_zero():
    # Departure is Delhi, Destination is Delhi -> Intercity travel should be 0 and verified
    budget_data = calculate_minimum_trip_budget(
        destination_name="Delhi",
        departure_location="Delhi",
        duration_days=2,
        travellers_count=2,
        accommodation_tier="budget_hotel",
        transit_pref="public_transit",
        travel_pace="balanced",
    )
    categories = {c["category"]: c for c in budget_data["categories"]}
    intercity = categories["intercity_transit"]
    assert intercity["minimum_cost"] == 0
    assert intercity["recommended_cost"] == 0
    assert intercity["data_source"] == "verified"


def test_budget_api_estimate_minimum_endpoint(client):
    res = client.post(
        "/api/budget/estimate-minimum",
        json={
            "destination_name": "Varanasi, Uttar Pradesh",
            "departure_location": "Delhi",
            "duration_days": 4,
            "travellers_count": 2,
            "accommodation_tier": "budget_hotel",
            "transit_pref": "public_transit",
            "travel_pace": "balanced",
            "include_shopping": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "Varanasi" in data["destination"]["name"]
    assert data["bare_minimum_budget"] > 0
    assert len(data["categories"]) == 8
    assert data["bare_minimum_per_person"] == round(data["bare_minimum_budget"] / 2, 2)


def test_budget_api_validate_endpoint_insufficient_vs_sufficient(client):
    # Calculate minimum first
    calc_res = client.post(
        "/api/budget/estimate-minimum",
        json={
            "destination_name": "Agra, Uttar Pradesh",
            "departure_location": "Delhi",
            "duration_days": 2,
            "travellers_count": 1,
            "accommodation_tier": "budget_hotel",
            "transit_pref": "public_transit",
            "travel_pace": "balanced",
        },
    )
    bare_min = calc_res.json()["bare_minimum_budget"]
    rec = calc_res.json()["recommended_budget"]

    # 1. Test insufficient budget (e.g. 500 rupees)
    val_res = client.post(
        "/api/budget/validate",
        json={
            "selected_budget": 500,
            "bare_minimum_budget": bare_min,
            "recommended_budget": rec,
        },
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_sufficient"] is False
    assert val_data["shortfall"] > 0
    assert val_data["tier"] == "insufficient"
    assert val_data["warning"] is not None

    # 2. Test sufficient budget
    val_res_ok = client.post(
        "/api/budget/validate",
        json={
            "selected_budget": bare_min + 5000,
            "bare_minimum_budget": bare_min,
            "recommended_budget": rec,
        },
    )
    assert val_res_ok.status_code == 200
    ok_data = val_res_ok.json()
    assert ok_data["is_sufficient"] is True
    assert not ok_data.get("shortfall")
    assert ok_data["tier"] in ("budget_conscious", "comfortable")


def test_itinerary_adaptation_to_budget():
    dummy_itinerary = {
        "destination_name": "Jaipur",
        "total_estimated_cost": 6000,
        "daily_plans": [
            {
                "day_number": 1,
                "activities": [
                    {"name": "Walking Tour", "cost": 0, "tier": "budget"},
                    {"name": "Palace Visit", "cost": 300, "tier": "standard"},
                    {"name": "Private Royal Chariot", "cost": 3500, "tier": "luxury"},
                ]
            }
        ]
    }

    # Lower budget
    adapted_low = adapt_itinerary_to_budget(
        itinerary=dummy_itinerary,
        selected_budget=4500,
        bare_minimum_budget=4500,
        recommended_budget=10000,
    )
    assert adapted_low["budget_tier"] == "budget_conscious"
    assert adapted_low["budget_validation"]["is_sufficient"] is True

    # Comfortable budget
    adapted_high = adapt_itinerary_to_budget(
        itinerary=dummy_itinerary,
        selected_budget=15000,
        bare_minimum_budget=4500,
        recommended_budget=10000,
    )
    assert adapted_high["budget_tier"] == "comfortable"
    assert adapted_high["budget_validation"]["is_sufficient"] is True
