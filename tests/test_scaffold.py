def test_modules_endpoint(client):
    assert client.get("/api/modules").status_code == 200

def test_fixtures_work(client, demo_trip):
    uid, trip_id = demo_trip
    from app.modules.common import get_itinerary, get_trip, get_user_context
    assert get_trip(trip_id)["destination_name"] == "Kyoto"
    assert len(get_itinerary(trip_id)["activities"]) > 0
    assert get_user_context(uid)["basic"] is not None
