import pytest
import json
from app.database import get_connection

def test_unified_trip_creation_and_persistence(client):
    # 1. Create a user
    auth_resp = client.post("/api/auth", json={
        "provider": "email",
        "identifier": "companion_tester@example.com",
        "password": "pass1234",
        "display_name": "Companion Tester"
    })
    assert auth_resp.status_code == 200
    user_id = auth_resp.json()["user_id"]
    client.headers.update({"Authorization": f"Bearer {auth_resp.json()['token']}"})

    # 2. Create basic profile
    profile_payload = {
        "age_group": "25_34",
        "travel_experience": "occasional",
        "companions": "family",
        "planning_approach": "balanced",
        "travel_goals": ["culture", "relaxation"],
        "place_interests": ["historical_sites", "nature_spots"],
        "experience_preference": "balanced",
        "dietary": ["vegetarian"],
        "preferred_climate": "moderate",
        "budget_tier": "mid_range",
        "assistance_autonomy": "balanced",
        "interests": ["heritage", "sightseeing"]
    }
    p_resp = client.post(f"/api/profile/{user_id}", json=profile_payload)
    assert p_resp.status_code == 200
    history_resp = client.post("/api/profile/history/choice", json={"choice": "none"})
    assert history_resp.status_code == 200, history_resp.text

    # 3. Create a trip with companion specs, children, elderly, departure, and trip-specific preferences
    trip_payload = {
        "destination_id": "manali_spiti_india",
        "destination_name": "Manali & Spiti Valley",
        "start_date": "2026-11-20",
        "end_date": "2026-11-24",
        "travellers_count": 4,
        "total_budget": 45000.0,
        "currency": "INR",
        "accommodation_tier": "resort",
        "transit_pref": "cab_rental",
        "travel_pace": "relaxed",
        "departure_location": "Bengaluru",
        "companions": "family",
        "has_children": True,
        "has_elderly": True,
        "trip_preferences": {
            "dietary": "vegetarian",
            "notes": "Need elevator and wheelchair accessible ground floors"
        }
    }

    t_resp = client.post(f"/api/trips/{user_id}", json=trip_payload)
    assert t_resp.status_code == 200, t_resp.text
    trip_data = t_resp.json()

    assert trip_data["departure_location"] == "Bengaluru"
    assert trip_data["companions"] == "family"
    assert trip_data["has_children"] is True
    assert trip_data["has_elderly"] is True
    assert trip_data["trip_preferences"]["dietary"] == "vegetarian"
    assert "elevator" in trip_data["trip_preferences"]["notes"]

    trip_id = trip_data["id"]

    # 4. Check GET /api/trips/{user_id}
    list_resp = client.get(f"/api/trips/{user_id}")
    assert list_resp.status_code == 200
    trips = list_resp.json()
    assert any(t["id"] == trip_id and t["departure_location"] == "Bengaluru" for t in trips)

    # 5. Check GET /api/trips/detail/{trip_id}
    detail_resp = client.get(f"/api/trips/detail/{trip_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["departure_location"] == "Bengaluru"
    assert detail["companions"] == "family"
    assert detail["has_children"] is True
    assert detail["has_elderly"] is True

    # 6. Verify directly in sqlite database
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT departure_location, companions, has_children, has_elderly, trip_preferences_json FROM trips WHERE id = ?", (trip_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "Bengaluru"
        assert row[1] == "family"
        assert row[2] == 1
        assert row[3] == 1
        prefs = json.loads(row[4])
        assert prefs["dietary"] == "vegetarian"


def test_companion_filtering_logic():
    from app.planning.personalization import filter_candidate_places

    sample_places = [
        {
            "id": "extreme_trek_1",
            "name": "Rohtang Extreme High-Altitude Ridge Trek",
            "category": "adventure",
            "tags": ["extreme_trek", "rocky_climb", "steep_incline", "strenuous"],
            "difficulty": "challenging"
        },
        {
            "id": "nightclub_1",
            "name": "Spiti Valley Underground Late Night Lounge & Pub",
            "category": "nightlife",
            "tags": ["bar", "club", "party", "adult"],
            "difficulty": "easy"
        },
        {
            "id": "peaceful_monastery",
            "name": "Key Gompa Heritage Monastery & Scenic Viewpoint",
            "category": "culture",
            "tags": ["peaceful", "heritage", "monastery", "scenic"],
            "difficulty": "easy"
        }
    ]

    # Test with elderly traveler: extreme rocky trek should be filtered out
    filtered_elderly, _, _ = filter_candidate_places(sample_places, {"has_elderly": True})
    ids_elderly = [p["id"] for p in filtered_elderly]
    assert "extreme_trek_1" not in ids_elderly
    assert "peaceful_monastery" in ids_elderly

    # Test with children: nightclub/pub should be filtered out
    filtered_kids, _, _ = filter_candidate_places(sample_places, {"has_children": True})
    ids_kids = [p["id"] for p in filtered_kids]
    assert "nightclub_1" not in ids_kids
    assert "peaceful_monastery" in ids_kids


def test_dynamic_trip_planning_with_companions(client):
    # Test dynamic trip planning with companion parameters
    auth_resp = client.post("/api/auth", json={
        "provider": "email",
        "identifier": "dynamic_comp@example.com",
        "password": "pass1234",
        "display_name": "Dynamic Tester"
    })
    user_id = auth_resp.json()["user_id"]

    plan_payload = {
        "user_id": user_id,
        "city": "Jaipur",
        "state": "Rajasthan",
        "lat": 26.9124,
        "lon": 75.7873,
        "start_date": "2026-12-01",
        "end_date": "2026-12-04",
        "travellers_count": 3,
        "total_budget": 35000,
        "accommodation_tier": "boutique",
        "transit_pref": "cab_rental",
        "travel_pace": "balanced",
        "radius_meters": 15000,
        "departure_location": "Delhi",
        "companions": "family",
        "has_children": True,
        "has_elderly": False,
        "trip_preferences": {"dietary": "vegetarian", "notes": "Prefer heritage sites"}
    }

    resp = client.post("/api/places/plan-dynamic", json=plan_payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "itinerary" in data
    assert "trip" in data
    assert data["trip"]["departure_location"] == "Delhi"
    assert data["trip"]["companions"] == "family"
    assert data["trip"]["has_children"] is True
