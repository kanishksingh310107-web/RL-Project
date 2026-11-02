"""Unit and integration tests for Pre-trip Preparation Module (Person A)."""

import pytest
from app.modules import prep


def test_weather_endpoint_404_on_unknown_trip(client):
    """Unknown trip ID must return 404."""
    resp = client.get("/api/prep/non_existent_trip_id_999/weather")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip not found"


def test_weather_offline_fallback(client, demo_trip, monkeypatch):
    """When network call raises or fails, endpoint falls back to offline estimate."""
    uid, trip_id = demo_trip

    def mock_fetch_raise(lat, lon, start, end):
        raise RuntimeError("Network disconnected")

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_fetch_raise)

    resp = client.get(f"/api/prep/{trip_id}/weather")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "offline-estimate"
    assert "not a live forecast" in data["label"]
    assert "fetched_at" in data
    assert "temp_min_c" in data["summary"]
    assert "temp_max_c" in data["summary"]
    assert "wind_kmh" in data["summary"]
    assert "rain_expected" in data["summary"]


def test_weather_live_open_meteo_mock(client, demo_trip, monkeypatch):
    """When Open-Meteo succeeds, source is open-meteo with proper values."""
    uid, trip_id = demo_trip

    def mock_fetch_success(lat, lon, start, end):
        return {
            "temp_min_c": 12.0,
            "temp_max_c": 21.0,
            "wind_kmh": 22.0,
            "rain_expected": True,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_fetch_success)

    resp = client.get(f"/api/prep/{trip_id}/weather")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "open-meteo"
    assert data["label"] == "Live forecast (Open-Meteo)"
    assert data["summary"]["temp_min_c"] == 12.0
    assert data["summary"]["temp_max_c"] == 21.0
    assert data["summary"]["wind_kmh"] == 22.0
    assert data["summary"]["rain_expected"] is True


def test_packing_endpoint_404_on_unknown_trip(client):
    """Unknown trip ID must return 404 for packing endpoint."""
    resp = client.get("/api/prep/non_existent_trip_id_888/packing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip not found"


def test_packing_cold_windy_vs_hot(client, demo_trip, monkeypatch):
    """Cold and windy trip includes windproof layer; hot trip does not."""
    uid, trip_id = demo_trip

    # Case A: Cold and windy weather mock
    def mock_weather_cold_windy(lat, lon, start, end):
        return {
            "temp_min_c": 5.0,
            "temp_max_c": 12.0,
            "wind_kmh": 34.0,  # strong wind
            "rain_expected": True,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather_cold_windy)
    resp_cold = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_cold.status_code == 200
    data_cold = resp_cold.json()

    cold_item_names = [item["name"] for item in data_cold["items"]]
    assert any("Windproof" in name for name in cold_item_names), "Cold+windy must have windproof layer"
    assert any("umbrella" in name.lower() or "rain" in name.lower() for name in cold_item_names)

    # Case B: Hot weather mock
    def mock_weather_hot(lat, lon, start, end):
        return {
            "temp_min_c": 24.0,
            "temp_max_c": 33.0,
            "wind_kmh": 10.0,
            "rain_expected": False,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather_hot)
    resp_hot = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_hot.status_code == 200
    data_hot = resp_hot.json()

    hot_item_names = [item["name"] for item in data_hot["items"]]
    assert not any("Windproof" in name for name in hot_item_names), "Hot trip must NOT have windproof outer shell"
    assert not any("Thermal base" in name for name in hot_item_names), "Hot trip must NOT have thermal base layers"
    assert any("breathable" in name.lower() for name in hot_item_names), "Hot trip must suggest breathable fabrics"


def test_packing_carry_on_shorter_list_and_liquids_reminder(client, demo_trip, monkeypatch):
    """User with carry_on gets a shorter list AND a liquids reminder item."""
    uid, trip_id = demo_trip

    def mock_weather(lat, lon, start, end):
        return {
            "temp_min_c": 16.0,
            "temp_max_c": 22.0,
            "wind_kmh": 12.0,
            "rain_expected": False,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather)

    # Standard packing (no carry-on specified)
    resp_std = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_std.status_code == 200
    data_std = resp_std.json()
    std_items = data_std["items"]
    assert not any("100ml" in i["name"] for i in std_items)

    # Update precision profile with carry_on
    p_resp = client.post(
        f"/api/profile/precision/{uid}",
        json={"answers": {"q61": "carry_on"}},
    )
    assert p_resp.status_code == 200

    resp_carry = client.get(f"/api/prep/{trip_id}/packing")
    assert resp_carry.status_code == 200
    data_carry = resp_carry.json()
    carry_items = data_carry["items"]

    # Carry-on list must be strictly shorter than standard
    assert len(carry_items) < len(std_items), f"Expected carry_on ({len(carry_items)}) < standard ({len(std_items)})"

    # Carry-on must contain liquids reminder
    assert any("Liquids" in i["name"] and "100ml" in i["name"] for i in carry_items)


def test_packing_medication_and_allergy_profile(client, demo_trip, monkeypatch):
    """User with medication/allergy flagged gets neutral cabin bag reminder."""
    uid, trip_id = demo_trip

    def mock_weather(lat, lon, start, end):
        return {
            "temp_min_c": 16.0,
            "temp_max_c": 22.0,
            "wind_kmh": 12.0,
            "rain_expected": False,
            "daily_details": {},
        }

    monkeypatch.setattr(prep, "fetch_open_meteo", mock_weather)

    p_resp = client.post(
        f"/api/profile/precision/{uid}",
        json={"answers": {"q11": "personal_medication", "q10": ["food_allergies"]}},
    )
    assert p_resp.status_code == 200

    resp = client.get(f"/api/prep/{trip_id}/packing")
    assert resp.status_code == 200
    items = resp.json()["items"]

    med_item = next((i for i in items if "medication" in i["name"].lower()), None)
    assert med_item is not None
    assert "cabin" in med_item["name"].lower() or "cabin" in med_item["reason"].lower()
    assert "no medical advice" in med_item["reason"].lower()


def test_packing_without_itinerary_and_without_precision_profile(client, demo_user, monkeypatch):
    """Packing endpoint gracefully handles a new trip before itinerary generation."""
    # Create trip without generating itinerary
    t_resp = client.post(
        f"/api/trips/{demo_user}",
        json={
            "destination_id": "reykjavik_iceland",
            "destination_name": "Reykjavik",
            "start_date": "2026-12-01",
            "end_date": "2026-12-05",
            "travellers_count": 1,
            "total_budget": 800,
        },
    )
    assert t_resp.status_code == 200
    trip_id = t_resp.json()["id"]

    resp = client.get(f"/api/prep/{trip_id}/packing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["itinerary_status"] == "not_generated"
    assert len(data["items"]) > 0
    assert any("sneakers" in i["name"].lower() or "shoes" in i["name"].lower() for i in data["items"])


def test_documents_endpoint_404_on_unknown_trip(client):
    """Unknown trip ID must return 404 for documents endpoint."""
    resp = client.get("/api/prep/non_existent_trip_id_777/documents")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "trip not found"


def test_documents_checklist_never_invents_visa_rules(client, demo_trip):
    """Documents endpoint provides verified checklist and directs user to official government sites."""
    uid, trip_id = demo_trip

    resp = client.get(f"/api/prep/{trip_id}/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert "disclaimer" in data
    items = data["items"]
    assert len(items) >= 8

    # Check passport and visa items specifically
    visa_item = next((i for i in items if "visa" in i["name"].lower()), None)
    assert visa_item is not None
    assert "official" in visa_item["note"].lower()
    assert visa_item["official_check_required"] is True

    passport_item = next((i for i in items if "passport" in i["name"].lower()), None)
    assert passport_item is not None
    assert "official" in passport_item["note"].lower()
    assert passport_item["official_check_required"] is True

    power_item = next((i for i in items if "power" in i["name"].lower() or "adapter" in i["name"].lower()), None)
    assert power_item is not None
    assert "Type A / B" in power_item["note"] or "Japan" in power_item["note"]  # Kyoto trip


def test_reminders_generation_and_due_dates(client, demo_trip):
    """Reminder due dates equal start_date - N days for each template."""
    uid, trip_id = demo_trip
    # demo_trip start_date is "2026-11-10"

    gen_resp = client.post(f"/api/prep/{trip_id}/reminders/generate")
    assert gen_resp.status_code == 200
    assert gen_resp.json()["created_count"] == 6

    # Verify idempotency
    gen_again = client.post(f"/api/prep/{trip_id}/reminders/generate")
    assert gen_again.status_code == 200
    assert gen_again.json()["created_count"] == 0

    list_resp = client.get(f"/api/prep/{trip_id}/reminders")
    assert list_resp.status_code == 200
    reminders = list_resp.json()["reminders"]
    assert len(reminders) == 6

    by_cat = {r["category"]: r["due_date"] for r in reminders}
    # 2026-11-10 minus 30 days = 2026-10-11
    assert by_cat["documents"] == "2026-10-11"
    # 2026-11-10 minus 14 days = 2026-10-27
    assert by_cat["insurance"] == "2026-10-27"
    # 2026-11-10 minus 3 days = 2026-11-07
    assert by_cat["packing"] == "2026-11-07"
    # 2026-11-10 minus 2 days = 2026-11-08
    assert by_cat["weather"] == "2026-11-08"
    # 2026-11-10 minus 1 day = 2026-11-09
    assert by_cat["checkin"] == "2026-11-09"
    assert by_cat["logistics"] == "2026-11-09"


def test_reminders_alert_budget_enforcement(client, demo_trip):
    """Alert budget caps the number of active reminders returned."""
    uid, trip_id = demo_trip

    client.post(f"/api/prep/{trip_id}/reminders/generate")
    list_resp = client.get(f"/api/prep/{trip_id}/reminders")
    assert list_resp.status_code == 200
    data = list_resp.json()

    assert data["alert_budget"] == 3
    assert data["active_count"] == 3
    assert data["waiting_count"] == 3

    active_items = [r for r in data["reminders"] if r.get("is_active")]
    assert len(active_items) == 3


def test_reminders_feedback_validation_and_errors(client, demo_trip):
    """Validation checks on feedback endpoint: unknown trip, unknown reminder, invalid value."""
    uid, trip_id = demo_trip

    client.post(f"/api/prep/{trip_id}/reminders/generate")

    # 404 on unknown trip
    r404_trip = client.post(
        "/api/prep/unknown_trip/reminders/some_id/feedback",
        json={"feedback": "useful"},
    )
    assert r404_trip.status_code == 404

    # 404 on unknown reminder
    r404_rem = client.post(
        f"/api/prep/{trip_id}/reminders/non_existent_reminder/feedback",
        json={"feedback": "useful"},
    )
    assert r404_rem.status_code == 404

    # Get a real reminder ID
    rems = client.get(f"/api/prep/{trip_id}/reminders").json()["reminders"]
    rem_id = rems[0]["id"]

    # 422 on invalid feedback string
    r422 = client.post(
        f"/api/prep/{trip_id}/reminders/{rem_id}/feedback",
        json={"feedback": "super_awesome"},
    )
    assert r422.status_code == 422


def test_bandit_feedback_updates_and_shifts_preference(client, demo_trip):
    """Feedback updates Thompson Sampling Beta(alpha, beta) parameters.
    Sustained feedback changes sampled preferences under deterministic seed.
    """
    uid, trip_id = demo_trip

    client.post(f"/api/prep/{trip_id}/reminders/generate")
    initial_rems = client.get(f"/api/prep/{trip_id}/reminders?seed=42").json()["reminders"]
    packing_rem = next(r for r in initial_rems if r["category"] == "packing")
    insurance_rem = next(r for r in initial_rems if r["category"] == "insurance")

    # 1. Single positive feedback updates alpha
    fb1 = client.post(
        f"/api/prep/{trip_id}/reminders/{packing_rem['id']}/feedback",
        json={"feedback": "useful"},
    )
    assert fb1.status_code == 200
    assert fb1.json()["new_alpha"] == 2.0
    assert fb1.json()["new_beta"] == 1.0

    # 2. Single negative feedback updates beta
    fb2 = client.post(
        f"/api/prep/{trip_id}/reminders/{insurance_rem['id']}/feedback",
        json={"feedback": "not_useful"},
    )
    assert fb2.status_code == 200
    assert fb2.json()["new_alpha"] == 1.0
    assert fb2.json()["new_beta"] == 2.0

    # 3. Apply 15x negative feedback to insurance, 15x positive feedback to packing
    for _ in range(15):
        client.post(
            f"/api/prep/{trip_id}/reminders/{insurance_rem['id']}/feedback",
            json={"feedback": "not_useful"},
        )
        client.post(
            f"/api/prep/{trip_id}/reminders/{packing_rem['id']}/feedback",
            json={"feedback": "useful"},
        )

    updated_data = client.get(f"/api/prep/{trip_id}/reminders?seed=42").json()
    bandit_state = {s["category"]: s for s in updated_data["bandit_state"]}

    assert bandit_state["packing"]["alpha"] >= 16.0
    assert bandit_state["packing"]["mean"] > 0.8
    assert bandit_state["insurance"]["beta"] >= 16.0
    assert bandit_state["insurance"]["mean"] < 0.2

    # Under seed=42, packing sampled score must significantly exceed insurance score
    rems_seeded = updated_data["reminders"]
    packing_score = next(r["bandit_score"] for r in rems_seeded if r["category"] == "packing")
    insurance_score = next(r["bandit_score"] for r in rems_seeded if r["category"] == "insurance")
    assert packing_score > insurance_score
    assert packing_score > 0.6
    assert insurance_score < 0.3



