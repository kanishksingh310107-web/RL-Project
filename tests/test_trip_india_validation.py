import pytest
from fastapi.testclient import TestClient

def test_indian_trip_creation_success(client, demo_user):
    """Test creating a trip for an Indian destination succeeds."""
    r = client.post(f"/api/trips/{demo_user}", json={
        "destination_id": "manali_spiti_india",
        "destination_name": "Manali & Spiti Valley",
        "start_date": "2026-11-20",
        "end_date": "2026-11-25",
        "travellers_count": 2,
        "total_budget": 25000,
        "currency": "INR",
        "accommodation_tier": "boutique",
        "travel_pace": "balanced",
        "transit_pref": "rental_car"
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["destination_id"] == "manali_spiti_india"
    assert data["destination_name"] == "Manali & Spiti Valley"
    assert data["duration_days"] == 6
    assert data["currency"] == "INR"

def test_trip_creation_invalid_dates(client, demo_user):
    """Test creating a trip where return date is before departure date."""
    r = client.post(f"/api/trips/{demo_user}", json={
        "destination_id": "manali_spiti_india",
        "start_date": "2026-11-25",
        "end_date": "2026-11-20",
        "travellers_count": 2,
        "total_budget": 20000
    })
    assert r.status_code == 422

def test_trip_creation_invalid_travellers_or_budget(client, demo_user):
    """Test validation of travellers count and budget."""
    r1 = client.post(f"/api/trips/{demo_user}", json={
        "destination_id": "manali_spiti_india",
        "start_date": "2026-11-20",
        "end_date": "2026-11-25",
        "travellers_count": 0,
        "total_budget": 20000
    })
    assert r1.status_code == 422

    r2 = client.post(f"/api/trips/{demo_user}", json={
        "destination_id": "manali_spiti_india",
        "start_date": "2026-11-20",
        "end_date": "2026-11-25",
        "travellers_count": 2,
        "total_budget": -500
    })
    assert r2.status_code == 422

def test_international_destination_rejection():
    """Verify backend rejection of international destinations when not in test db."""
    import app.database as database
    from app.api import create_trip
    from app.models import TripCreate
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    orig_path = database.DB_PATH
    try:
        # Simulate live production DB path
        database.DB_PATH = type(orig_path)("travel_guide.db")
        with pytest.raises(HTTPException) as exc_info:
            create_trip(
                user_id="any_user",
                payload=TripCreate(
                    destination_id="kyoto_japan",
                    start_date="2026-11-20",
                    end_date="2026-11-25"
                )
            )
        assert exc_info.value.status_code == 400
        assert "Only Indian destinations are supported" in exc_info.value.detail
    finally:
        database.DB_PATH = orig_path
