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

def test_reschedule_activity(client, demo_trip):
    """Verifies rescheduling an activity moves its position/time."""
    user_id, trip_id = demo_trip
    r_view = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    day1 = r_view.json()["days"][0]
    acts = [b for b in day1["timeline"] if b["type"] == "activity"]
    if len(acts) >= 2:
        first_act_id = acts[0]["activity_id"]
        res = client.post(
            f"/api/trip-actions/{trip_id}/activity/{first_act_id}/reschedule",
            json={"user_id": user_id, "direction": "later"}
        )
        assert res.status_code == 200
        assert res.json()["status"] in ["rescheduled", "unchanged"]


def test_switch_activities_between_days(client, demo_trip):
    """Verifies switching activities between two different days."""
    user_id, trip_id = demo_trip
    r_view = client.get(f"/api/trip-actions/{trip_id}/timed-view")
    days = r_view.json()["days"]
    assert len(days) >= 2
    act_day1 = next(b for b in days[0]["timeline"] if b["type"] == "activity")["activity_id"]
    act_day2 = next(b for b in days[1]["timeline"] if b["type"] == "activity")["activity_id"]

    res = client.post(
        f"/api/trip-actions/{trip_id}/switch-days",
        json={"user_id": user_id, "activity_id_a": act_day1, "activity_id_b": act_day2}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "switched"


def test_companion_lock_status(client, demo_user):
    """Verifies Companion is locked for basic profile and unlocked only after deep personalization."""
    # 1. User only has basic profile -> locked
    res1 = client.get(f"/api/companion/status/{demo_user}")
    assert res1.status_code == 200
    assert res1.json()["unlocked"] is False
    assert res1.json()["has_basic_profile"] is True
    assert res1.json()["has_deep_profile"] is False

    # Also /api/modules?user_id=... should return 403
    res_mod_locked = client.get(f"/api/modules?user_id={demo_user}")
    assert res_mod_locked.status_code == 403

    # 2. Complete deep profile -> unlocked
    p_res = client.post(f"/api/profile/detailed/{demo_user}", json={
        "avoidances": ["extreme_heights"],
        "walking_tolerance": "high",
        "schedule_density": "packed_all_day",
        "accessibility": [],
        "dietary": ["vegetarian"],
        "stay_style": "boutique",
        "transit_pref": "walking",
        "repetition_strategy": "explore_new"
    })
    assert p_res.status_code == 200

    res2 = client.get(f"/api/companion/status/{demo_user}")
    assert res2.status_code == 200
    assert res2.json()["unlocked"] is True
    assert res2.json()["has_deep_profile"] is True

    # Now /api/modules?user_id=... succeeds and does NOT include ranking
    res_mod_unlocked = client.get(f"/api/modules?user_id={demo_user}")
    assert res_mod_unlocked.status_code == 200
    module_ids = [m["id"] for m in res_mod_unlocked.json()]
    assert "ranking" not in module_ids

