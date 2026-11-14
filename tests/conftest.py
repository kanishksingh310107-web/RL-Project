"""Shared pytest fixtures. Every test runs against a fresh temporary SQLite DB (never touches travel_guide.db)."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def prevent_unmocked_provider_network(monkeypatch):
    """Keep tests deterministic; each live-provider test supplies its own mock.

    Patch outbound transports, not TestClient's in-process ASGI transport.
    This also prevents real Geoapify credit consumption during the test suite.
    """
    import requests
    import httpx

    def requests_offline(*args, **kwargs):
        raise requests.ConnectionError('Unmocked provider network disabled in tests')

    def urllib_offline(*args, **kwargs):
        raise OSError('Unmocked provider network disabled in tests')

    def httpx_offline(*args, **kwargs):
        raise httpx.ConnectError('Unmocked provider network disabled in tests')

    monkeypatch.setattr(requests.Session, 'request', requests_offline)
    monkeypatch.setattr('urllib.request.urlopen', urllib_offline)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', httpx_offline)

@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    import app.database as database
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)
    database.init_db()

@pytest.fixture()
def client():
    from main import app
    from app.db_migrations_a import migrate_a
    from app.db_migrations_b import run_b_migration
    from app.db_migrations_c import migrate_c
    from app.modules import init_module_tables
    # TestClient without a context manager does not trigger FastAPI startup.
    # Apply the same idempotent schema setup that main.startup performs.
    migrate_a()
    run_b_migration()
    init_module_tables()
    migrate_c()
    return TestClient(app)

@pytest.fixture()
def demo_user(client):
    r = client.post("/api/auth", json={"provider": "email", "identifier": "demo@test.com",
                                       "password": "pass1234", "display_name": "Demo"})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]
    client.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    p = client.post(f"/api/profile/{uid}", json={
        "travel_goals": ["nature", "culture"], "place_interests": ["mountains", "historic"],
        "preferred_climate": "cool", "budget_tier": "mid_range", "companions": "partner"})
    assert p.status_code == 200, p.text
    history = client.post("/api/profile/history/choice", json={"choice": "none"})
    assert history.status_code == 200, history.text
    return uid


def complete_deep_profile(client, user_id):
    """Answer the applicable Level 3 questions for tests that exercise trip plans."""
    questions = client.get("/api/config/precision-questionnaire").json()["questions"]
    answers = {}
    for qid, question in questions.items():
        kind = question.get("type")
        options = question.get("options") or []
        if kind == "single" and options:
            answers[qid] = options[0]["id"]
        elif kind == "multi":
            answers[qid] = ([item["id"] for item in options]
                            if qid == "d27_privacy_saving" else [options[0]["id"]] if options else [])
        elif kind == "scale":
            answers[qid] = 3
        elif kind == "number":
            answers[qid] = question.get("min", 1)
    response = client.post(f"/api/profile/precision/{user_id}", json={"answers": answers})
    assert response.status_code == 200, response.text
    status = client.get(f"/api/profile/{user_id}/status")
    assert status.status_code == 200 and status.json()["complete"], status.text


@pytest.fixture()
def deep_user(client, demo_user):
    complete_deep_profile(client, demo_user)
    return demo_user

@pytest.fixture()
def demo_trip(client, deep_user):
    """Kyoto, 5 days, itinerary already generated. Returns (user_id, trip_id)."""
    demo_user = deep_user
    t = client.post(f"/api/trips/{demo_user}", json={
        "destination_id": "kyoto_japan", "destination_name": "Kyoto",
        "start_date": "2026-11-10", "end_date": "2026-11-14", "travellers_count": 2,
        "total_budget": 1200, "specific_interests": ["culture_history", "food_dining"]})
    assert t.status_code == 200, t.text
    trip_id = t.json()["id"]
    g = client.post(f"/api/itinerary/generate/{trip_id}?user_id={demo_user}")
    assert g.status_code == 200, g.text
    return demo_user, trip_id
