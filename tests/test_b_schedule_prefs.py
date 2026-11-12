import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db_migrations_b import migrate_b
from app.schedule_preferences import normalize_schedule_preferences


def _memory_trip(pace="balanced", trip_id="trip-b"):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE trips (id TEXT PRIMARY KEY, user_id TEXT, destination_id TEXT, destination_name TEXT, duration_days INTEGER, travel_pace TEXT, start_date TEXT, end_date TEXT)")
    conn.execute("CREATE TABLE destination_activities (id TEXT, destination_id TEXT, name TEXT, category TEXT, neighborhood TEXT, estimated_cost REAL, cost_amount REAL, description TEXT)")
    conn.execute("INSERT INTO trips VALUES (?,?,?,?,?,?,?,?)", (trip_id,"user-b","test_destination","Test",3,pace,"2027-02-01","2027-02-03"))
    conn.executemany("INSERT INTO destination_activities VALUES (?,?,?,?,?,?,?,?)", [
        (f"act-{i}","test_destination",f"Activity {i}","culture","Center",10,10,"Description") for i in range(12)
    ])
    conn.commit()
    return conn


def test_schedule_preferences_reject_invalid_times_overlap_and_outside_window():
    with pytest.raises(ValidationError):
        normalize_schedule_preferences({"activity_start_time": "25:99"}, 2)
    with pytest.raises(ValidationError):
        normalize_schedule_preferences({"activity_start_time": "10:00", "bed_time": "09:00"}, 2)
    with pytest.raises(ValidationError):
        normalize_schedule_preferences({"free_blocks": [
            {"day": 1, "start": "10:00", "end": "12:00", "label": "Break"},
            {"day": 1, "start": "11:00", "end": "13:00", "label": "Another"},
        ]}, 2)
    with pytest.raises(ValidationError, match="inside the daily activity window"):
        normalize_schedule_preferences({"free_blocks": [
            {"day": 1, "start": "20:30", "end": "21:30", "label": "Late"},
        ]}, 2)


def test_free_blocks_on_different_days_may_share_times():
    prefs = normalize_schedule_preferences({"free_blocks": [
        {"day": 1, "start": "12:00", "end": "13:00", "label": "Lunch"},
        {"day": 2, "start": "12:00", "end": "13:00", "label": "Lunch"},
    ]}, 2)
    assert len(prefs["free_blocks"]) == 2


def test_b_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE trips (id TEXT PRIMARY KEY)")
    migrate_b(conn)
    migrate_b(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(trip_schedule_prefs)")}
    assert {"trip_id", "hotel_arrival_time", "hotel_departure_time", "wake_time", "bed_time", "activity_start_time", "free_blocks_json"} <= cols


@pytest.mark.parametrize("pace", ["relaxed", "balanced", "active"])
def test_custom_timed_schedule_respects_free_blocks_and_hotel_buffers(pace):
    from app.services.timed_itinerary import regenerate_timed_itinerary_for_trip
    trip_id = f"trip-{pace}"
    conn = _memory_trip(pace, trip_id)
    prefs = normalize_schedule_preferences({
        "hotel_arrival_time": "14:00", "hotel_departure_time": "11:00",
        "wake_time": "07:00", "activity_start_time": "09:00", "bed_time": "21:00",
        "free_blocks": [{"day": None, "start": "12:00", "end": "13:00", "label": "Lunch with family"}],
    }, 3)
    migrate_b(conn)
    conn.execute("INSERT INTO trip_schedule_prefs VALUES (?,?,?,?,?,?,?)",
        (trip_id,prefs["hotel_arrival_time"],prefs["hotel_departure_time"],prefs["wake_time"],prefs["bed_time"],
         prefs["activity_start_time"],json.dumps(prefs["free_blocks"])))
    conn.commit()
    schedule = regenerate_timed_itinerary_for_trip(conn, trip_id, "user-b", pace)
    assert schedule["days"][0]["arrival_marker"] == "14:00"
    assert schedule["days"][-1]["departure_marker"] == "11:00"
    regenerated = regenerate_timed_itinerary_for_trip(conn, trip_id, "user-b", pace)
    assert regenerated["days"][0]["arrival_marker"] == "14:00"
    assert regenerated["days"][-1]["departure_marker"] == "11:00"
    for day in schedule["days"]:
        for slot in day["slots"]:
            start = int(slot["start_time"][:2]) * 60 + int(slot["start_time"][3:])
            end = int(slot["end_time"][:2]) * 60 + int(slot["end_time"][3:])
            if slot["slot_type"] == "activity":
                assert start >= 9 * 60
                assert end <= 21 * 60
                if day["day_number"] == 1:
                    assert start >= 15 * 60
                if day["day_number"] == 3:
                    assert end <= 10 * 60
            if slot["slot_type"] == "free_time":
                assert slot["start_time"] == "12:00"
                assert slot["end_time"] == "13:00"
            assert not (slot["slot_type"] == "activity" and start < 13 * 60 and end > 12 * 60)
    assert any(day["note"] for day in schedule["days"] if day["day_number"] == 3)


def test_api_returns_readable_422_for_invalid_schedule_preferences():
    from app.api import create_trip
    from app.models import TripCreate
    response = create_trip("unlooked-up-user", TripCreate.model_validate({
        "destination_id": "jaipur_india", "start_date": "2027-03-01", "end_date": "2027-03-03",
        "schedule_prefs": {"activity_start_time": "abc"},
    }))
    assert response.status_code == 422
    body = json.loads(response.body)
    assert body["code"] == "INVALID_SCHEDULE_PREFS"
    assert body["field"] == "schedule_prefs"
    assert "valid 24-hour time" in body["detail"]


def test_edit_trip_updates_stored_schedule_preferences():
    from app.database import get_connection
    from app.api import edit_trip
    from app.modules import init_module_tables
    init_module_tables()
    user_id, trip_id = "b-user", "b-edit-trip"
    with get_connection() as conn:
        conn.execute("INSERT INTO users (id,auth_provider,identifier) VALUES (?,?,?)", (user_id,"email","b@test.invalid"))
        conn.execute("""INSERT INTO trips (id,user_id,destination_id,destination_name,start_date,end_date,duration_days,
            travellers_count,total_budget) VALUES (?,?,?,?,?,?,?,?,?)""",
            (trip_id,user_id,"jaipur_india","Jaipur","2027-03-01","2027-03-03",3,1,25000))
        migrate_b(conn)
        conn.commit()
    response = edit_trip(trip_id, {"schedule_prefs": {
        "hotel_arrival_time": "15:00", "hotel_departure_time": "12:00", "wake_time": "06:30",
        "activity_start_time": "08:30", "bed_time": "22:30",
        "free_blocks": [{"day": 2, "start": "13:00", "end": "14:00", "label": "Rest"}],
    }, "regeneration_mode": "everything"}, user_id)
    assert response.schedule_prefs["hotel_arrival_time"] == "15:00"
    assert response.schedule_prefs["activity_start_time"] == "08:30"
    assert response.schedule_prefs["free_blocks"][0]["day"] == 2


def test_schedule_form_blocks_invalid_submit_and_keeps_readable_field_errors():
    source = (Path(__file__).parents[1] / "static" / "modules" / "schedule_prefs.js").read_text(encoding="utf-8")
    assert 'role="alert"' in source
    assert 'event.preventDefault(); event.stopImmediatePropagation();' in source
    assert 'show("bedTime"' in source
    assert 'body.schedule_prefs = readPrefs()' in source


def test_legacy_trip_without_preferences_keeps_0900_to_2100_window():
    from app.services.timed_itinerary import regenerate_timed_itinerary_for_trip
    conn = _memory_trip()
    schedule = regenerate_timed_itinerary_for_trip(conn, "trip-b", "user-b")
    activities = [slot for day in schedule["days"] for slot in day["slots"] if slot["slot_type"] == "activity"]
    assert activities[0]["start_time"] == "09:00"
    assert max(int(a["end_time"][:2]) * 60 + int(a["end_time"][3:]) for a in activities) <= 21 * 60
