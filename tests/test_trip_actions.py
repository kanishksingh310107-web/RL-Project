# Tests for Trip Actions & Timed Itinerary Module
# Owner: Person C
# Verifies timed timeline view (activities, transit, meals, rest),
# activity swapping & removal, finalization, and the 'Start Trip' activation.

import pytest


def test_timed_itinerary_view(client, demo_trip):
    """Verifies timed day-by-day view includes activities, transit, lunch, and rest breaks."""
    user_id, trip_id = demo_trip
    r = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    assert r.status_code == 200
    data = r.json()

    assert data["has_itinerary"] is True
    assert data["trip_status"] in ["planning", "finalized", "active_trip"]
    assert len(data["days"]) > 0

    # Inspect first day
    day1 = data["days"][0]
    assert day1["day_number"] == 1
    blocks = day1["timeline"]
    assert len(blocks) >= 3

    # Check block types
    types = [b["type"] for b in blocks]
    assert "activity" in types
    assert "meal" in types  # Eating time scheduled
    assert "rest" in types  # Rest time scheduled


def test_finalize_trip_lifecycle(client, demo_trip):
    """Verifies that finalizing locks the trip and sets status to 'finalized'."""
    user_id, trip_id = demo_trip

    r = client.post(f"/api/trip-actions/{trip_id}/finalize?user_id={user_id}")
    assert r.status_code == 200
    res = r.json()
    assert res["status"] == "finalized"
    assert "finalized_at" in res

    # Verify timed-view reflects finalized state
    r_view = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    assert r_view.status_code == 200
    assert r_view.json()["trip_status"] == "finalized"


def test_start_trip_activation(client, demo_trip):
    """Verifies that starting a trip transitions status to 'active_trip' with timestamp."""
    user_id, trip_id = demo_trip

    # 1. Finalize first
    client.post(f"/api/trip-actions/{trip_id}/finalize?user_id={user_id}")

    # 2. Start trip
    r = client.post(f"/api/trip-actions/{trip_id}/start?user_id={user_id}")
    assert r.status_code == 200
    res = r.json()
    assert res["status"] == "active_trip"
    assert "started_at" in res
    assert "Trip started" in res["message"]

    # Verify timed-view reflects active_trip state
    r_view = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    assert r_view.status_code == 200
    assert r_view.json()["trip_status"] == "active_trip"


def test_activity_swap(client, demo_trip):
    """Verifies swapping an activity with an alternative updates the itinerary."""
    user_id, trip_id = demo_trip

    # Fetch initial activity
    r_view = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    day1 = r_view.json()["days"][0]
    act_block = next(b for b in day1["timeline"] if b["type"] == "activity")
    old_act_id = act_block["activity_id"]

    # Get alternatives
    r_alts = client.get(f"/api/itinerary/alternatives/{r_view.json()['itinerary']['id']}/{old_act_id}?user_id={user_id}")
    assert r_alts.status_code == 200
    alts = r_alts.json()["alternatives"]
    assert len(alts) > 0
    replacement_id = alts[0]["id"]

    # Swap
    r_swap = client.post(
        f"/api/trip-actions/{trip_id}/activity/{old_act_id}/swap",
        json={"user_id": user_id, "replacement_activity_id": replacement_id}
    )
    assert r_swap.status_code == 200
    assert r_swap.json()["status"] == "swapped"

    # Verify updated activity in timed view
    r_view2 = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    day1_updated = r_view2.json()["days"][0]
    act_ids = [b.get("activity_id") for b in day1_updated["timeline"] if b["type"] == "activity"]
    assert replacement_id in act_ids


def test_activity_remove(client, demo_trip):
    """Verifies removing an activity deletes it from the itinerary."""
    user_id, trip_id = demo_trip

    r_view = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    day1 = r_view.json()["days"][0]
    act_block = next(b for b in day1["timeline"] if b["type"] == "activity")
    target_id = act_block["activity_id"]

    # Remove
    r_del = client.delete(f"/api/trip-actions/{trip_id}/activity/{target_id}?user_id={user_id}")
    assert r_del.status_code == 200
    assert r_del.json()["status"] == "removed"

    # Verify deletion
    r_view2 = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    day1_after = r_view2.json()["days"][0]
    act_ids_after = [b.get("activity_id") for b in day1_after["timeline"] if b["type"] == "activity"]
    assert target_id not in act_ids_after
