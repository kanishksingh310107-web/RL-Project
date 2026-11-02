"""Tests for Person B's Timed Day-by-Day Itinerary Engine & RL Alternative Suggestions."""
import pytest
import sqlite3
from app.database import get_connection
import app.services.timed_itinerary
import app.services.suggestion_engine


def time_to_mins(t_str: str) -> int:
    parts = t_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def test_timed_itinerary_generation_balanced(client, demo_trip):
    """
    Verifies that a balanced timed itinerary is generated from 09:00 to 21:00,
    containing exactly 3 activities per day plus transit, meals, and rest blocks
    without any overlapping times.
    """
    uid, trip_id = demo_trip

    res = client.post(f"/api/itinerary/timed/generate/{trip_id}?pace=balanced&user_id={uid}")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["status"] == "success"
    assert data["trip_id"] == trip_id
    assert data["pace"] == "balanced"
    assert len(data["days"]) > 0

    # Verify every day's schedule
    for day in data["days"]:
        slots = day["slots"]
        assert len(slots) >= 6

        # Count activities
        activities = [s for s in slots if s["slot_type"] == "activity"]
        transits = [s for s in slots if s["slot_type"] == "transit"]
        meals = [s for s in slots if s["slot_type"] == "meal"]
        rests = [s for s in slots if s["slot_type"] == "rest"]

        assert len(activities) == 3, f"Balanced pace must have exactly 3 activities, got {len(activities)}"
        assert len(transits) >= 2, "Must include travel/transit time buffers"
        assert len(meals) == 2, "Must include lunch and dinner"
        assert len(rests) >= 1, "Must include explicitly scheduled rest time / hotel leisure"

        # Check required fields on every slot
        for s in slots:
            assert s["slot_type"] in {"activity", "transit", "meal", "rest"}
            assert "start_time" in s and "end_time" in s
            assert "duration_mins" in s
            assert "title" in s and len(s["title"]) > 0
            assert "location" in s
            assert "estimated_cost" in s
            assert s["estimated_cost"] >= 0.0

        # Non-overlapping, contiguous time validation (09:00 to 21:00)
        assert slots[0]["start_time"] == "09:00"
        assert slots[-1]["end_time"] == "21:00"

        for i in range(len(slots)):
            curr = slots[i]
            start_m = time_to_mins(curr["start_time"])
            end_m = time_to_mins(curr["end_time"])

            # Slot duration matches difference
            assert end_m > start_m, f"Slot {curr['title']} end_time must be after start_time"
            assert (end_m - start_m) == curr["duration_mins"], f"Duration mismatch for {curr['title']}"

            # Contiguous without gaps or overlaps
            if i < len(slots) - 1:
                next_slot = slots[i + 1]
                assert curr["end_time"] == next_slot["start_time"], (
                    f"Schedule overlap or gap between '{curr['title']}' ({curr['end_time']}) "
                    f"and '{next_slot['title']}' ({next_slot['start_time']})"
                )


def test_timed_itinerary_pace_relaxed(client, demo_trip):
    """
    Verifies that relaxed pace schedules exactly 2 activities per day,
    with transit, lunch, afternoon activity, rest time, and dinner without overlaps.
    """
    uid, trip_id = demo_trip

    res = client.post(f"/api/itinerary/timed/generate/{trip_id}?pace=relaxed&user_id={uid}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["pace"] == "relaxed"

    for day in data["days"]:
        slots = day["slots"]
        activities = [s for s in slots if s["slot_type"] == "activity"]
        rests = [s for s in slots if s["slot_type"] == "rest"]
        meals = [s for s in slots if s["slot_type"] == "meal"]

        assert len(activities) == 2, f"Relaxed pace must have exactly 2 activities, got {len(activities)}"
        assert len(rests) >= 1
        assert len(meals) == 2

        # Check contiguous from 09:00 to 21:00
        assert slots[0]["start_time"] == "09:00"
        assert slots[-1]["end_time"] == "21:00"

        for i in range(len(slots) - 1):
            assert slots[i]["end_time"] == slots[i + 1]["start_time"]


def test_timed_itinerary_pace_active(client, demo_trip):
    """
    Verifies that active pace schedules exactly 4 activities per day,
    with transit, meals, and rest blocks without overlaps.
    """
    uid, trip_id = demo_trip

    res = client.post(f"/api/itinerary/timed/generate/{trip_id}?pace=active&user_id={uid}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["pace"] == "active"

    for day in data["days"]:
        slots = day["slots"]
        activities = [s for s in slots if s["slot_type"] == "activity"]
        assert len(activities) == 4, f"Active pace must have exactly 4 activities, got {len(activities)}"

        assert slots[0]["start_time"] == "09:00"
        assert slots[-1]["end_time"] == "21:00"

        for i in range(len(slots) - 1):
            assert slots[i]["end_time"] == slots[i + 1]["start_time"]


def test_database_persistence_of_timed_itinerary(client, demo_trip):
    """Verifies that generated schedules are persisted to SQLite tables timed_itineraries and timed_itinerary_slots."""
    uid, trip_id = demo_trip

    res = client.post(f"/api/itinerary/timed/generate/{trip_id}?pace=balanced&user_id={uid}")
    assert res.status_code == 200

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM timed_itineraries WHERE trip_id = ?", (trip_id,))
        itin_row = cursor.fetchone()
        assert itin_row is not None
        itin_dict = dict(itin_row)
        assert itin_dict["pace"] == "balanced"
        assert itin_dict["total_cost"] > 0

        cursor.execute("SELECT * FROM timed_itinerary_slots WHERE trip_id = ? ORDER BY day_number, order_index", (trip_id,))
        slots = cursor.fetchall()
        assert len(slots) > 0

        # Check types in database
        slot_types = {dict(s)["slot_type"] for s in slots}
        assert "activity" in slot_types
        assert "transit" in slot_types
        assert "meal" in slot_types
        assert "rest" in slot_types


def test_linucb_alternative_suggestions(client, demo_trip):
    """
    Verifies that GET /api/itinerary/timed/{trip_id}/alternatives/{activity_id}
    queries Contextual LinUCB and returns 3 alternative activities with scores and explanations.
    """
    uid, trip_id = demo_trip

    # Generate timed schedule first
    gen_res = client.post(f"/api/itinerary/timed/generate/{trip_id}?pace=balanced&user_id={uid}")
    assert gen_res.status_code == 200
    first_day = gen_res.json()["days"][0]
    first_act = next(s for s in first_day["slots"] if s["slot_type"] == "activity")
    target_act_id = first_act["activity_id"]

    # Request alternatives for that slot
    alt_res = client.get(f"/api/itinerary/timed/{trip_id}/alternatives/{target_act_id}?user_id={uid}")
    assert alt_res.status_code == 200, alt_res.text
    data = alt_res.json()

    assert data["status"] == "success"
    assert data["activity_id"] == target_act_id
    alternatives = data["alternatives"]
    assert len(alternatives) == 3, f"Must return 3 alternatives, got {len(alternatives)}"

    for alt in alternatives:
        assert alt["id"] != target_act_id, "Alternative must not be the activity being replaced"
        assert "title" in alt or "name" in alt
        assert "category" in alt
        assert "score" in alt
        assert "reason" in alt
        assert "LinUCB" in alt["reason"] or "Alternative" in alt["reason"]


def test_manali_destination_schedule(client, demo_user):
    """
    Verifies Manali destination schedule specifically:
    09:00 morning activity (e.g. Hadimba Temple), travel/transit buffer,
    lunch at local eatery (e.g. Cafe 1947), afternoon activity (e.g. Solang Valley),
    rest time, and dinner/night walk.
    """
    # Create Manali trip
    t_res = client.post(f"/api/trips/{demo_user}", json={
        "destination_id": "manali_spiti_india",
        "destination_name": "Manali & Spiti Valley",
        "start_date": "2026-11-15",
        "end_date": "2026-11-17",
        "travellers_count": 2,
        "total_budget": 800,
        "travel_pace": "relaxed",
        "specific_interests": ["nature_outdoors", "food_dining"]
    })
    assert t_res.status_code == 200, t_res.text
    manali_trip_id = t_res.json()["id"]

    res = client.post(f"/api/itinerary/timed/generate/{manali_trip_id}?pace=relaxed&user_id={demo_user}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["destination_id"] == "manali_spiti_india"

    day1_slots = data["days"][0]["slots"]

    # Morning activity (Hadimba Temple or cultural site)
    morning = day1_slots[0]
    assert morning["slot_type"] == "activity"
    assert morning["start_time"] == "09:00"
    assert morning["end_time"] == "11:30"
    assert "Hadimba" in morning["title"] or "Temple" in morning["title"] or "Monastery" in morning["title"]

    # Transit buffer
    transit1 = day1_slots[1]
    assert transit1["slot_type"] == "transit"
    assert transit1["start_time"] == "11:30"
    assert transit1["end_time"] == "12:15"

    # Lunch
    lunch = day1_slots[2]
    assert lunch["slot_type"] == "meal"
    assert lunch["start_time"] == "12:15"
    assert lunch["end_time"] == "13:45"
    assert "Cafe 1947" in lunch["title"] or "Lunch" in lunch["title"]

    # Afternoon activity (e.g. Solang Valley or scenic nature)
    afternoon = day1_slots[4]
    assert afternoon["slot_type"] == "activity"
    assert afternoon["start_time"] == "14:15"
    assert afternoon["end_time"] == "16:45" or afternoon["end_time"] == "17:00"

    # Rest Time / Hotel Leisure explicitly scheduled
    rest_slot = next(s for s in day1_slots if s["slot_type"] == "rest")
    assert "Rest Time" in rest_slot["title"] or "Leisure" in rest_slot["title"]
    assert rest_slot["estimated_cost"] == 0.0

    # Dinner & Night walk
    dinner = day1_slots[-1]
    assert dinner["slot_type"] == "meal"
    assert dinner["end_time"] == "21:00"
    assert "Dinner" in dinner["title"]


def test_invalid_trip_handling(client):
    """Verifies that non-existent trip IDs return 404."""
    res = client.post("/api/itinerary/timed/generate/non_existent_trip_id")
    assert res.status_code == 404

    alt_res = client.get("/api/itinerary/timed/non_existent_trip_id/alternatives/some_act")
    assert alt_res.status_code == 404
