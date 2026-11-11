"""Unit tests for app.core.schemas contract data types."""
import json
from app.core.schemas import (
    Provenance, Place, DayWindow, MealWindow, TripPrefs,
    TravelLeg, Block, DayPlan, TripPlan, BudgetLine, Stay
)


def test_provenance_defaults():
    prov = Provenance()
    assert prov.source == "curated_catalogue"
    assert prov.is_live is False
    assert prov.is_estimate is False
    assert prov.fetched_at is not None


def test_place_unknown_cost_is_none():
    place = Place(
        id="test_place_1",
        name="Hawa Mahal",
        category="culture_history",
        lat=26.9239,
        lon=75.8267
    )
    # Critical invariant: unknown cost/rating must be None, NEVER 0
    assert place.cost_amount is None
    assert place.rating is None
    assert place.provenance.is_live is False


def test_stay_budget_band_not_price():
    stay = Stay(
        stay_id="stay_101",
        trip_id="trip_abc",
        name="Heritage Haveli",
        lat=26.9124,
        lon=75.7873,
        estimated_nightly_budget=3500.0
    )
    assert stay.estimated_nightly_budget == 3500.0
    assert stay.stars is None


def test_trip_plan_serialization():
    window = DayWindow(day_number=1, start_time="09:00", end_time="20:00")
    day = DayPlan(day_number=1, window=window)
    budget = BudgetLine(category="food", allocated_amount=5000.0, estimated_spent=4200.0)
    plan = TripPlan(
        trip_id="trip_1",
        user_id="user_1",
        destination_id="jaipur_india",
        destination_name="Jaipur",
        total_days=1,
        days=[day],
        budget_ledger=[budget]
    )
    data = json.loads(plan.model_dump_json())
    assert data["trip_id"] == "trip_1"
    assert len(data["days"]) == 1
    assert data["budget_ledger"][0]["category"] == "food"
    assert data["days"][0]["window"]["available_minutes"] == 720
