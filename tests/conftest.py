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
    from main import startup
    startup()

@pytest.fixture()
def client():
    from main import app
    from app.modules import init_module_tables
    init_module_tables()
    return TestClient(app)

@pytest.fixture()
def demo_user(client):
    r = client.post("/api/auth", json={"provider": "email", "identifier": "demo@test.com",
                                       "password": "SafePass123", "display_name": "Demo", "mode": "signup"})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]
    client.headers['Authorization'] = 'Bearer ' + r.json()['token']
    p = client.post(f"/api/profile/{uid}", json={
        "travel_goals": ["nature", "culture"], "place_interests": ["mountains", "historic"],
        "preferred_climate": "cool", "budget_tier": "mid_range", "companions": "partner"})
    assert p.status_code == 200, p.text
    history = client.post('/api/profile/history/choice', json={'choice': 'none'})
    assert history.status_code == 200, history.text
    assert client.get('/api/profile/status').json()['profile_complete'] is True
    return uid


@pytest.fixture
def onboard_user(client):
    """Complete the real account/profile flow for tests creating their own user."""
    def onboard(auth):
        user_id = auth['user_id']
        client.headers['Authorization'] = 'Bearer ' + auth['token']
        profile = client.post('/api/profile/' + user_id, json={
            'travel_goals': ['nature', 'culture'], 'place_interests': ['mountains', 'historic']})
        assert profile.status_code == 200, profile.text
        history = client.post('/api/profile/history/choice', json={'choice': 'none'})
        assert history.status_code == 200, history.text
        assert client.get('/api/profile/status').json()['profile_complete'] is True
        return user_id
    return onboard

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
