"""Unit tests for budget forecasts, contingency and residual shopping."""
import json
import sqlite3

from app.recommendation_budget import _allocation_summary


def summary_for(allocations, expenses=(), total=30000):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE trip_budget_allocations(
        trip_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,total_budget_inr INTEGER NOT NULL,
        allocations_json TEXT NOT NULL,updated_at TEXT NOT NULL)""")
    conn.execute(
        "INSERT INTO trip_budget_allocations VALUES(?,?,?,?,?)",
        ("trip-1", "owner", total, json.dumps(allocations), "2026-11-15T00:00:00+00:00"),
    )
    trip = {
        "id": "trip-1", "user_id": "owner", "total_budget": total,
        "travellers_count": 2, "start_date": "2026-12-01", "end_date": "2026-12-03",
    }
    return _allocation_summary(conn, trip, list(expenses))


def allocations():
    return {
        "accommodation": {"planned_inr": 8000, "basis": "total", "status": "booked"},
        "intercity_travel": {"planned_inr": 4000, "basis": "total", "status": "booked"},
        "local_transport": {"planned_inr": 2000, "basis": "total", "status": "estimated"},
        "activities": {"planned_inr": 3000, "basis": "total", "status": "estimated"},
        "food": {"planned_inr": 6000, "basis": "total", "status": "estimated"},
        "other": {"planned_inr": 0, "basis": "total", "status": "estimated"},
        "shopping": {"planned_inr": 0, "basis": "residual_allowance", "status": "estimated"},
        "emergency_reserve": {"planned_inr": 0, "basis": "automatic", "status": "estimated"},
    }


def test_one_reserve_and_residual_shopping_allowance():
    result = summary_for(allocations())
    assert result["emergency_reserve_inr"] == 1100
    assert result["shopping_allowance_inr"] == 5900
    assert result["shopping_remaining_inr"] == 5900
    assert result["forecast_final_cost_inr"] == 23000
    assert result["forecast_with_reserve_inr"] == 24100
    assert result["budget_shortfall_inr"] == 0
    assert result["forecast_complete"] is True


def test_deposit_final_payment_and_shopping_replace_estimates_without_double_count():
    expenses = [
        {"category": "stay", "amount_inr": 2000, "planned_cost_key": "accommodation",
         "is_final_for_planned_cost": 0},
        {"category": "stay", "amount_inr": 6000, "planned_cost_key": "accommodation",
         "is_final_for_planned_cost": 1},
        {"category": "shopping", "amount_inr": 1500, "planned_cost_key": None,
         "is_final_for_planned_cost": 0},
    ]
    result = summary_for(allocations(), expenses)
    assert result["actual_by_category_inr"]["stay"] == 8000
    assert result["estimated_remaining_by_category_inr"]["accommodation"] == 0
    assert result["forecast_final_cost_inr"] == 24500
    assert result["shopping_spent_inr"] == 1500
    assert result["shopping_remaining_inr"] == 4400
    assert result["forecast_with_reserve_inr"] == 25600


def test_confirmed_costs_can_exhaust_budget_and_show_shortfall():
    amounts = allocations()
    amounts["accommodation"]["planned_inr"] = 25000
    amounts["intercity_travel"]["planned_inr"] = 10000
    result = summary_for(amounts)
    assert result["budget_shortfall_inr"] > 0
    assert result["shopping_remaining_inr"] == 0


def test_local_transport_estimate_uses_itinerary_legs_when_coordinates_exist(monkeypatch):
    from app.core.assumptions import CIRCUITY_FACTOR
    from app.core.cost_model import estimate_cost, leg_cost_inr
    from app.providers.geo import haversine_distance_km
    import app.providers.geo as geo

    anchor = (12.97, 77.59)
    stops = [(12.98, 77.60), (12.99, 77.62)]
    monkeypatch.setattr(geo, "resolve_trip_location", lambda **kwargs: {"lat": anchor[0], "lon": anchor[1]})
    trip = {
        "destination_id": "test", "destination_name": "Test India", "destination_lat": anchor[0],
        "destination_lon": anchor[1], "departure_location": "Bengaluru", "duration_days": 1,
        "travellers_count": 2, "party": {"adults": 2, "children": 0, "seniors": 0},
        "trip_type": "couple", "total_budget": 30000, "start_date": "2026-12-01",
        "end_date": "2026-12-01", "transit_pref": "taxi", "stay_lat": anchor[0], "stay_lon": anchor[1],
    }
    activities = [
        {"id": "a", "day_number": 1, "order_index": 0, "category": "culture_history",
         "latitude": stops[0][0], "longitude": stops[0][1], "cost_estimate": 100},
        {"id": "b", "day_number": 1, "order_index": 1, "category": "nature_outdoors",
         "latitude": stops[1][0], "longitude": stops[1][1], "cost_estimate": 100},
    ]
    result = estimate_cost(trip, activities)
    distances = [haversine_distance_km(*anchor, *stops[0]),
                 haversine_distance_km(*stops[0], *stops[1]),
                 haversine_distance_km(*stops[1], *anchor)]
    expected = sum(leg_cost_inr(distance*CIRCUITY_FACTOR, "cab") for distance in distances)
    assert result["cost_breakdown"]["local_transit"]["per_party"] == expected
    assert result["assumptions"]["local_transit_basis"] == "estimated itinerary legs from the stay location"
