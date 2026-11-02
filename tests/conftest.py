"""Shared pytest fixtures. Every test runs against a fresh temporary SQLite DB (never touches travel_guide.db)."""
import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.database as database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    from main import app
    from app.modules import init_module_tables
    database.init_db()
    init_module_tables()
    return TestClient(app)

@pytest.fixture()
def demo_user(client):
    r = client.post("/api/auth", json={"provider": "email", "identifier": "demo@test.com",
                                       "password": "pass1234", "display_name": "Demo"})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]
    p = client.post(f"/api/profile/{uid}", json={
        "travel_goals": ["nature", "culture"], "place_interests": ["mountains", "historic"],
        "preferred_climate": "cool", "budget_tier": "mid_range", "companions": "partner"})
    assert p.status_code == 200, p.text
    return uid

@pytest.fixture()
def demo_trip(client, demo_user):
    """Kyoto, 5 days, itinerary already generated. Returns (user_id, trip_id)."""
    t = client.post(f"/api/trips/{demo_user}", json={
        "destination_id": "kyoto_japan", "destination_name": "Kyoto",
        "start_date": "2026-11-10", "end_date": "2026-11-14", "travellers_count": 2,
        "total_budget": 1200, "specific_interests": ["culture_history", "food_dining"]})
    assert t.status_code == 200, t.text
    trip_id = t.json()["id"]
    g = client.post(f"/api/itinerary/generate/{trip_id}?user_id={demo_user}")
    assert g.status_code == 200, g.text
    return demo_user, trip_id
