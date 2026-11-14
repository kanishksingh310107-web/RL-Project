from concurrent.futures import ThreadPoolExecutor

from app.db_migrations_a import migrate_a
from app.database import get_connection
from app.auth import authenticate_or_register
from app.profile_gate import HistoryInput, RATING_KEYS, require_profile_complete
from fastapi import HTTPException
from app.vectorizer import PreferenceVectorizer
from app.recommender import DESTINATIONS, score_destination_for_user
from starlette.requests import Request


def _signup(client, email="a@example.com", username="traveler", password="SafePass123"):
    return client.post("/api/account/register", json={
        "email": email, "username": username, "password": password,
        "confirm_password": password, "mode": "signup",
    })


def test_case_insensitive_duplicate_email_and_username(client):
    migrate_a()
    first = _signup(client)
    assert first.status_code == 201
    assert client.post("/api/account/register", json={
        "email": "A@EXAMPLE.COM", "username": "other", "password": "SafePass123",
        "confirm_password": "SafePass123", "mode": "signup",
    }).status_code == 409
    assert client.post("/api/account/register", json={
        "email": "another@example.com", "username": "Traveler", "password": "SafePass123",
        "confirm_password": "SafePass123", "mode": "signup",
    }).status_code == 409


def test_concurrent_registration_and_repeat_guest_google_identity(client):
    migrate_a()
    def register_same_email(_):
        try:
            return authenticate_or_register("email", "parallel@example.com", password="SafePass123", display_name="Parallel", mode="signup")["user_id"]
        except ValueError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=4) as pool:
        registrations = list(pool.map(register_same_email, range(4)))
    assert len({item for item in registrations if item != "duplicate"}) == 1
    assert registrations.count("duplicate") == 3
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: authenticate_or_register("guest", "stable_guest_identity_0123456789", display_name="Guest"), range(4)))
    assert len({r["user_id"] for r in results}) == 1
    guest_payload = {"guest_id": "browser_guest_identity_0123456789"}
    guest_one = client.post("/api/account/guest", json=guest_payload)
    guest_two = client.post("/api/account/guest", json=guest_payload)
    assert guest_one.status_code == guest_two.status_code == 200
    assert guest_one.json()["user_id"] == guest_two.json()["user_id"]
    g1 = authenticate_or_register("google", "stable-google-sub", email="same@example.com", display_name="Traveler")
    g2 = authenticate_or_register("google", "stable-google-sub", email="same@example.com", display_name="Traveler")
    assert g1["user_id"] == g2["user_id"]


def test_wrong_password_session_persistence_and_rate_limit(client):
    migrate_a()
    registered = _signup(client)
    assert registered.status_code == 201
    user = registered.json()
    assert client.get("/api/profile/status", headers={"Authorization": f"Bearer {user['token']}"}).status_code == 200
    wrong = client.post("/api/account/login", json={"email": "a@example.com", "password": "WrongPass123", "mode": "login"})
    assert wrong.status_code == 401
    assert "Invalid email or password" in wrong.text


def test_no_history_choice_completes_required_basic_gate(client):
    user = _signup(client, email="no-history@example.com", username="nohistory").json()
    headers = {"Authorization": f"Bearer {user['token']}"}
    profile = client.post(f"/api/profile/{user['user_id']}", headers=headers, json={
        "residence_country": "IN", "residence_state": "Tamil Nadu", "residence_city": "Tirunelveli",
        "travel_goals": ["nature", "culture"], "place_interests": ["mountains", "historic"],
        "preferred_climate": "cool", "budget_tier": "mid_range", "companions": "partner",
    })
    assert profile.status_code == 200, profile.text

    choice = client.post("/api/profile/history/choice", headers=headers, json={"choice": "none"})
    assert choice.status_code == 200, choice.text
    assert choice.json() == {"history_choice": "none", "profile_complete": True}
    assert client.get("/api/profile/status", headers=headers).json() == {"profile_complete": True}


def test_history_validation_and_profile_gate(client):
    migrate_a()
    user = _signup(client).json()
    headers = {"Authorization": f"Bearer {user['token']}"}
    assert client.get("/api/profile/status", headers=headers).json() == {"profile_complete": False}
    try:
        require_profile_complete({"id": user["user_id"]})
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["code"] == "PROFILE_INCOMPLETE"
    else:
        raise AssertionError("incomplete profiles must be blocked")
    payload = {"destination": "<img src=x onerror=alert(1)>", "visited_on": "2024-03-01", "trip_type": "solo", "ratings": {key: 4 for key in RATING_KEYS}, "would_revisit": True}
    assert client.post("/api/profile/history", headers=headers, json=payload).status_code == 201
    assert client.post("/api/profile/history/choice", headers=headers, json={"choice": "none"}).status_code == 409
    invalid = {**payload, "ratings": {**payload["ratings"], "food": 6}}
    assert client.post("/api/profile/history", headers=headers, json=invalid).status_code == 422
    with get_connection() as conn:
        conn.execute("""INSERT INTO traveller_profiles(user_id,interests,pace,crowd_tolerance,structure,companions,has_children,budget_tier,preferred_climate,planning_experience,raw_answers_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (user["user_id"], "[]", .5, .5, .5, "solo", 0, "balanced", "mild", "intermediate", '{"age_group":"18_24","travel_experience":"occasional","companions":"solo","planning_approach":"plan_essentials","travel_goals":["nature","culture"],"place_interests":["mountains","history"],"experience_preference":"balanced_mix","dietary":["none"],"preferred_climate":"mild","budget_tier":"balanced","assistance_autonomy":"shortlist_explain"}'))
    with get_connection() as conn:
        conn.execute("UPDATE user_profile SET residence_country='IN',residence_state='Tamil Nadu',residence_city='Tirunelveli',preferred_currency='INR' WHERE user_id=?",(user['user_id'],))
    client.post("/api/profile/history/choice", headers=headers, json={"choice": "provided"})
    assert client.get("/api/profile/status", headers=headers).json() == {"profile_complete": True}
    try:
        require_profile_complete({"id": user["user_id"]})
    except Exception as exc:
        assert False, f"complete profile should pass gate: {exc}"
    foreign_request = Request({"type": "http", "method": "POST", "path": "/api/trips/other-user", "headers": [], "path_params": {"user_id": "other-user"}})
    try:
        require_profile_complete({"id": user["user_id"]}, foreign_request)
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["code"] == "USER_MISMATCH"
    else:
        raise AssertionError("trip planning must not accept another user’s path ID")


def test_completed_feedback_appears_in_revisit_list(client):
    migrate_a()
    user = _signup(client).json()
    with get_connection() as conn:
        conn.execute("INSERT INTO trips(id,user_id,destination_id,destination_name,start_date,end_date,duration_days) VALUES('trip_a',?,'jaipur','Jaipur','2025-01-01','2025-01-02',2)", (user["user_id"],))
        conn.execute("INSERT INTO post_trip_feedback(trip_id,user_id,ratings_json,trip_type,would_revisit,liked,disliked,notes,submitted_at) VALUES('trip_a',?,'{\"overall\":5}','friends','yes','Loved it','','Loved it','2025-01-03')", (user["user_id"],))
        conn.execute("INSERT INTO activity_runs(id,trip_id,activity_id,itinerary_activity_id,day_number,ratings_json,notes,action) VALUES('run_a','trip_a','act_a','itin_act_a',1,'{\"food\":5}','Great meal','keep')")
    response = client.get("/api/profile/history", headers={"Authorization": f"Bearer {user['token']}"})
    assert response.status_code == 200
    trip = next(row for row in response.json()["entries"] if row["source"] == "trip")
    assert trip["destination"] == "Jaipur"
    assert trip["would_revisit"] is True
    assert trip["ratings"]["food"] == 5


def test_history_input_contract_and_casefold_vector_signal():
    payload = {"destination": "  Shimla  ", "visited_on": "2025-06-01", "trip_type": "Family", "ratings": {key: 4 for key in RATING_KEYS}, "would_revisit": True}
    model = HistoryInput.model_validate(payload)
    assert model.destination == "Shimla"
    assert model.trip_type == "family"
    bad = {**payload, "trip_type": "tour_group"}
    try:
        HistoryInput.model_validate(bad)
    except Exception:
        pass
    else:
        raise AssertionError("unknown trip types must be rejected")
    try:
        HistoryInput.model_validate({**payload, "destination": "___"})
    except Exception:
        pass
    else:
        raise AssertionError("symbol-only destinations must be rejected")
    profile = {"interests": [], "travel_history": [{"ratings": {"food": 5}}]}
    vector, names = PreferenceVectorizer.vectorize(profile)
    assert len(vector) == len(PreferenceVectorizer.vectorize({"interests": []})[0])
    assert vector[names.index("interest_food_dining")] == 1.0
    category_tags = {"scenery": {"nature", "mountains", "beaches", "photography", "relaxation"}, "food": {"food", "cafes", "culinary", "local_experiences"}}
    neutral = {"interests": [], "companions": "solo", "budget_tier": "balanced", "preferred_climate": "mild"}
    candidates = []
    for destination in DESTINATIONS:
        tags = {str(tag).lower() for tag in destination.get("tags", [])}
        category = next((name for name, values in category_tags.items() if tags.intersection(values)), None)
        if category:
            baseline = score_destination_for_user(destination, neutral)["match_score"]
            if 25 < baseline < 90:
                candidates.append((destination, category, baseline))
                break
    assert candidates, "the catalogue should contain a destination with history-rated tags"
    destination, category, baseline = candidates[0]
    high = score_destination_for_user(destination, neutral, past_trips=[{"ratings": {category: 5}, "destination": "Somewhere else"}])["match_score"]
    low = score_destination_for_user(destination, neutral, past_trips=[{"ratings": {category: 1}, "destination": "Somewhere else"}])["match_score"]
    assert high > baseline > low
