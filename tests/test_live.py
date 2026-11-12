"""Tests for Person B's During-Trip Support and Post-Trip Learning module."""
import json
import pytest
import numpy as np
from app.database import get_connection
from app.modules.common import get_itinerary
from app.rl_planner import load_user_policy


def test_live_module_registration(client):
    """Verifies that the live module is registered and exposed in /api/modules, and static file is accessible."""
    res = client.get("/api/modules")
    assert res.status_code == 200
    modules = res.json()
    live_mod = next((m for m in modules if m.get("id") == "live"), None)
    assert live_mod is not None
    assert live_mod["title"] == "During & Post Trip"
    assert live_mod["owner"] == "B"
    assert "icon" in live_mod

    # Static JS file test
    static_res = client.get("/static/modules/live.js")
    assert static_res.status_code == 200
    assert 'TravelModules.register("live"' in static_res.text


def test_live_tables_initialized(client):
    """Verifies that all 7 live_* tables are created with proper schemas."""
    expected_tables = {
        "live_trip_state",
        "live_activity_status",
        "live_conditions",
        "live_alerts",
        "live_postrip",
        "live_activity_feedback",
        "live_activity_contexts"
    }
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        missing = expected_tables - tables
        assert not missing, f"Missing live tables: {missing}"


def test_module_info_and_trip_state(client, demo_trip):
    """Verifies module metadata endpoint and default trip state retrieval."""
    uid, trip_id = demo_trip

    res = client.get("/api/live/module-info")
    assert res.status_code == 200
    assert res.json()["status"] == "active"

    res = client.get(f"/api/live/{trip_id}/state?user_id={uid}")
    assert res.status_code == 200
    data = res.json()
    assert data["trip_id"] == trip_id
    assert data["user_id"] == uid
    assert data["is_started"] == 0
    assert data["is_completed"] == 0
    assert data["current_day"] == 1

    # Unauthorized access check
    res = client.get(f"/api/live/{trip_id}/state?user_id=other_user")
    assert res.status_code == 403


def test_get_today_itinerary(client, demo_trip):
    """Verifies retrieving today's itinerary enriched with live statuses."""
    uid, trip_id = demo_trip

    res = client.get(f"/api/live/{trip_id}/today?day=1&user_id={uid}")
    assert res.status_code == 200
    data = res.json()
    assert data["trip_id"] == trip_id
    assert data["day_number"] == 1
    assert data["destination_name"] == "Kyoto"
    assert len(data["activities"]) > 0
    assert data["is_simulated_environment"] is True

    first_act = data["activities"][0]
    assert "activity_id" in first_act
    assert "title" in first_act
    assert "status" in first_act
    assert first_act["status"] == "upcoming"
    assert "alerts" in first_act


def test_activity_status_updates(client, demo_trip):
    """Verifies updating activity statuses: upcoming, in_progress, completed, skipped, delayed."""
    uid, trip_id = demo_trip

    today_res = client.get(f"/api/live/{trip_id}/today?day=1&user_id={uid}")
    act = today_res.json()["activities"][0]
    act_id = act["activity_id"]

    for valid_status in ["in_progress", "completed", "skipped", "delayed", "upcoming"]:
        res = client.post(
            f"/api/live/{trip_id}/activity/{act_id}/status",
            json={"status": valid_status, "notes": f"Testing {valid_status}", "user_id": uid}
        )
        assert res.status_code == 200
        assert res.json()["new_status"] == valid_status

    # Verify updated status reflects in today's view
    today_res2 = client.get(f"/api/live/{trip_id}/today?day=1&user_id={uid}")
    updated_act = next(a for a in today_res2.json()["activities"] if a["activity_id"] == act_id)
    assert updated_act["status"] == "upcoming"

    # Rejects invalid status
    bad_res = client.post(
        f"/api/live/{trip_id}/activity/{act_id}/status",
        json={"status": "invalid_random_status", "user_id": uid}
    )
    assert bad_res.status_code == 400

    # Rejects unauthorized user
    unauth_res = client.post(
        f"/api/live/{trip_id}/activity/{act_id}/status",
        json={"status": "completed", "user_id": "other_intruder"}
    )
    assert unauth_res.status_code == 403


def test_simulate_condition_and_alerts(client, demo_trip):
    """Verifies condition simulation (explicitly 'simulated') and contextual alert generation."""
    uid, trip_id = demo_trip

    res = client.post(
        f"/api/live/{trip_id}/simulate",
        json={"condition_type": "heavy_rain", "day_number": 1, "severity": "warning", "user_id": uid}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "simulated"
    assert data["condition_type"] == "heavy_rain"

    alerts_res = client.get(f"/api/live/{trip_id}/alerts?day=1&user_id={uid}")
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()["alerts"]
    assert len(alerts) > 0
    assert any("Rain" in a["title"] or a["severity"] == "warning" for a in alerts)

    # Duplicate prevention
    alerts_count_before = len(alerts)
    res_repeat = client.post(
        f"/api/live/{trip_id}/simulate",
        json={"condition_type": "heavy_rain", "day_number": 1, "severity": "warning", "user_id": uid}
    )
    assert res_repeat.status_code == 200
    alerts_res_after = client.get(f"/api/live/{trip_id}/alerts?day=1&user_id={uid}")
    assert len(alerts_res_after.json()["alerts"]) == alerts_count_before

    # Dismiss alert
    alert_to_dismiss = alerts[0]
    dismiss_res = client.post(f"/api/live/{trip_id}/alerts/{alert_to_dismiss['id']}/dismiss?user_id={uid}")
    assert dismiss_res.status_code == 200
    assert dismiss_res.json()["dismissed"] is True

    active_alerts = client.get(f"/api/live/{trip_id}/alerts?day=1&user_id={uid}").json()["alerts"]
    assert all(a["id"] != alert_to_dismiss["id"] for a in active_alerts)


def test_alert_budget_limit(client, demo_trip):
    """Verifies that alert generation respects the daily budget (max 3 alerts/day)."""
    uid, trip_id = demo_trip

    for c_type in ["closure", "extreme_heat", "traffic_delay", "fatigue"]:
        client.post(
            f"/api/live/{trip_id}/simulate",
            json={"condition_type": c_type, "day_number": 2, "user_id": uid}
        )

    alerts = client.get(f"/api/live/{trip_id}/alerts?day=2&user_id={uid}").json()["alerts"]
    assert len(alerts) <= 3


def test_targeted_activity_replanning(client, demo_trip):
    """
    Verifies targeted replanning:
    - Obtains alternatives filtered by condition.
    - Swaps only the targeted activity.
    - Preserves remaining activities untouched.
    - Preserves permanent LinUCB policy (trip-specific modification).
    """
    uid, trip_id = demo_trip

    today_res = client.get(f"/api/live/{trip_id}/today?day=1&user_id={uid}")
    acts_before = today_res.json()["activities"]
    assert len(acts_before) >= 2
    act_to_replace = acts_before[0]
    act_to_keep = acts_before[1]
    old_act_id = act_to_replace["activity_id"]

    alts_res = client.get(f"/api/live/{trip_id}/replan?activity_id={old_act_id}&condition=heavy_rain&user_id={uid}")
    assert alts_res.status_code == 200
    alts = alts_res.json()["alternatives"]
    assert len(alts) > 0
    replacement = alts[0]
    rep_id = replacement["id"]

    with get_connection() as conn:
        policy_before = load_user_policy(conn, uid)
        arm_id = act_to_replace["category"] if act_to_replace["category"] in policy_before.arms else "culture_history"
        pulls_before = policy_before.arms[arm_id]["pull_count"]

    replan_res = client.post(
        f"/api/live/{trip_id}/replan",
        json={
            "activity_id": old_act_id,
            "replacement_activity_id": rep_id,
            "reason": "Simulated heavy rain disruption",
            "is_trip_specific": True,
            "user_id": uid
        }
    )
    assert replan_res.status_code == 200
    acts_after = replan_res.json()["activities"]

    replaced_act = acts_after[0]
    assert replaced_act["activity_id"] == rep_id
    assert replaced_act["activity_id"] != old_act_id

    kept_act = acts_after[1]
    assert kept_act["activity_id"] == act_to_keep["activity_id"]
    assert kept_act["title"] == act_to_keep["title"]
    assert kept_act["time_slot"] == act_to_keep["time_slot"]

    with get_connection() as conn:
        policy_after = load_user_policy(conn, uid)
        pulls_after = policy_after.arms[arm_id]["pull_count"]
        assert pulls_after == pulls_before, "Permanent LinUCB policy must not change for trip-specific replanning"


# ---------------------------------------------------------------------------
# Post-Trip Feedback & Genuine LinUCB Learning Tests
# ---------------------------------------------------------------------------

def test_trip_completion_and_incomplete_trip_rejection(client, demo_trip):
    """Verifies trip completion endpoint and rejection of feedback for incomplete trips."""
    uid, trip_id = demo_trip

    # 1. Attempting post-trip feedback on incomplete trip must fail with 400
    fb_payload = {
        "user_id": uid,
        "overall_satisfaction": 4.5,
        "pace_rating": "just_right",
        "budget_accuracy": "accurate",
        "itinerary_realistic": "realistic",
        "activity_ratings": []
    }
    res_premature = client.post(f"/api/live/{trip_id}/postrip", json=fb_payload)
    assert res_premature.status_code == 400
    assert "not completed" in res_premature.json()["detail"].lower()

    # 2. Mark trip completed
    res_complete = client.post(f"/api/live/{trip_id}/complete", json={"user_id": uid})
    assert res_complete.status_code == 200
    assert res_complete.json()["is_completed"] == 1

    # Idempotent re-completion
    res_recomplete = client.post(f"/api/live/{trip_id}/complete", json={"user_id": uid})
    assert res_recomplete.status_code == 200
    assert res_recomplete.json()["is_completed"] == 1


def test_post_trip_feedback_and_genuine_linucb_learning(client, demo_trip):
    """
    Verifies:
    - Post-trip feedback acceptance and duplicate submission protection.
    - Genuine LinUCB parameter updates (pull_count, total_reward, weights) using historical 24-dim context.
    - Policy persistence across database reloads.
    """
    uid, trip_id = demo_trip

    # Mark trip completed
    client.post(f"/api/live/{trip_id}/complete", json={"user_id": uid})

    # Retrieve itinerary activities to rate
    today_res = client.get(f"/api/live/{trip_id}/today?day=1&user_id={uid}")
    acts = today_res.json()["activities"]
    assert len(acts) >= 2
    act_positive = acts[0]
    act_negative = acts[1]

    pos_arm = act_positive["category"] if act_positive["category"] in ["culture_history", "food_dining", "nature_outdoors"] else "culture_history"
    neg_arm = act_negative["category"] if act_negative["category"] in ["culture_history", "food_dining", "nature_outdoors"] else "culture_history"

    with get_connection() as conn:
        policy_before = load_user_policy(conn, uid)
        pos_pulls_before = policy_before.arms[pos_arm]["pull_count"]
        pos_reward_before = policy_before.arms[pos_arm]["total_reward"]
        pos_weight_before = float(np.linalg.norm(policy_before.get_arm_weights(pos_arm)))

    fb_payload = {
        "user_id": uid,
        "overall_satisfaction": 4.5,
        "pace_rating": "just_right",
        "budget_accuracy": "accurate",
        "itinerary_realistic": "realistic",
        "enjoyed_most": act_positive["title"],
        "disliked": act_negative["title"],
        "comments": "Great cultural trip overall!",
        "activity_ratings": [
            {
                "activity_id": act_positive["activity_id"],
                "rating": 5, # Reward +1.0
                "remember_preference": True,
                "comments": "Loved it!"
            },
            {
                "activity_id": act_negative["activity_id"],
                "rating": 1, # Reward -1.0
                "remember_preference": True,
                "comments": "Too noisy"
            }
        ]
    }

    # 1. Submit valid post-trip feedback
    fb_res = client.post(f"/api/live/{trip_id}/postrip", json=fb_payload)
    assert fb_res.status_code == 200
    fb_data = fb_res.json()
    assert fb_data["status"] == "success"
    assert fb_data["activities_evaluated"] == 2
    assert fb_data["policy_updates_applied"] == 2

    # 2. Duplicate submission protection (submitting again fails with 409)
    res_duplicate = client.post(f"/api/live/{trip_id}/postrip", json=fb_payload)
    assert res_duplicate.status_code == 409
    assert "already been submitted" in res_duplicate.json()["detail"].lower()

    # 3. Verify genuine LinUCB policy parameter updates and persistence
    with get_connection() as conn:
        policy_after = load_user_policy(conn, uid)
        pos_pulls_after = policy_after.arms[pos_arm]["pull_count"]
        pos_reward_after = policy_after.arms[pos_arm]["total_reward"]
        pos_weight_after = float(np.linalg.norm(policy_after.get_arm_weights(pos_arm)))

        # Pull count must increase
        assert pos_pulls_after == pos_pulls_before + 1
        # Reward must increase by +1.0
        assert pos_reward_after == pytest.approx(pos_reward_before + 1.0, 0.01)
        # Weight vector norm must shift
        assert pos_weight_after != pos_weight_before

        # Check historical context vector preservation: 24 dims
        cursor = conn.cursor()
        cursor.execute("SELECT context_vector_json FROM live_activity_feedback WHERE trip_id = ? AND activity_id = ?",
                       (trip_id, act_positive["activity_id"]))
        vec_row = cursor.fetchone()
        assert vec_row is not None
        vec = json.loads(vec_row[0])
        assert len(vec) == 24
        assert isinstance(vec[0], float)


def test_dont_remember_preference_isolation(client, demo_trip):
    """
    Verifies that when a user flags 'remember_preference=False' (trip-specific anomaly / don't remember),
    the feedback is recorded but does NOT update the permanent LinUCB policy parameters.
    """
    uid, trip_id = demo_trip

    client.post(f"/api/live/{trip_id}/complete", json={"user_id": uid})
    today_res = client.get(f"/api/live/{trip_id}/today?day=1&user_id={uid}")
    act = today_res.json()["activities"][0]
    arm_id = act["category"] if act["category"] in ["culture_history", "food_dining", "nature_outdoors"] else "culture_history"

    with get_connection() as conn:
        policy_before = load_user_policy(conn, uid)
        pulls_before = policy_before.arms[arm_id]["pull_count"]
        reward_before = policy_before.arms[arm_id]["total_reward"]

    fb_payload = {
        "user_id": uid,
        "overall_satisfaction": 3.0,
        "activity_ratings": [
            {
                "activity_id": act["activity_id"],
                "rating": 1, # -1.0 reward normally
                "remember_preference": False, # DO NOT LEARN
                "comments": "Bad day, but generally love this type"
            }
        ]
    }
    res = client.post(f"/api/live/{trip_id}/postrip", json=fb_payload)
    assert res.status_code == 200
    assert res.json()["policy_updates_applied"] == 0

    with get_connection() as conn:
        policy_after = load_user_policy(conn, uid)
        assert policy_after.arms[arm_id]["pull_count"] == pulls_before
        assert policy_after.arms[arm_id]["total_reward"] == reward_before


def test_user_isolation_and_unauthorized_feedback(client, demo_trip):
    """Verifies that User B cannot submit feedback for User A's trip, and policies remain strictly isolated."""
    uid, trip_id = demo_trip

    client.post(f"/api/live/{trip_id}/complete", json={"user_id": uid})

    # Unauthorized submit
    res = client.post(f"/api/live/{trip_id}/postrip", json={
        "user_id": "intruder_user_id",
        "overall_satisfaction": 5.0,
        "activity_ratings": []
    })
    assert res.status_code == 403


def test_learning_summary_endpoint(client, demo_trip):
    """Verifies that the /learning-summary endpoint returns arm stats, norms, and transparent explanations, and enforces ownership."""
    uid, trip_id = demo_trip

    # Authorized request
    res = client.get(f"/api/live/{uid}/learning-summary?caller_user_id={uid}")
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == uid
    assert "arms_summary" in data
    assert len(data["arms_summary"]) == 7 # 7 canonical arms
    assert "explanation" in data

    # Unauthorized request
    res_unauth = client.get(f"/api/live/{uid}/learning-summary?caller_user_id=intruder_user")
    assert res_unauth.status_code == 403

    # Verify arm structure
    first_arm = data["arms_summary"][0]
    assert "arm_id" in first_arm
    assert "pull_count" in first_arm
    assert "weight_norm" in first_arm



def test_weather_alerts_and_core_trip_feedback_bridge():
    from fastapi.testclient import TestClient
    from main import app
    from app.database import get_connection
    from app.core.stores import load_trip_feedback, ensure_core_tables
    from app.modules.live import init_tables as init_live_tables
    import uuid

    client = TestClient(app)
    user_id = f"user_live_{uuid.uuid4().hex[:6]}"
    trip_id = f"trip_live_{uuid.uuid4().hex[:6]}"

    with get_connection() as conn:
        init_live_tables(conn)
        ensure_core_tables(conn)
        conn.execute(
            """
            INSERT INTO users (id, auth_provider, identifier, display_name)
            VALUES (?, 'email', ?, 'Live Tester')
            """,
            (user_id, f"{user_id}@test.com"),
        )
        conn.execute(
            """
            INSERT INTO trips (id, user_id, destination_id, destination_name, start_date, end_date, duration_days, total_budget)
            VALUES (?, ?, 'delhi', 'Delhi, India', '2026-11-20', '2026-11-23', 3, 25000.0)
            """,
            (trip_id, user_id),
        )
        conn.execute(
            """
            INSERT INTO itineraries (id, trip_id, user_id, title, total_days, status)
            VALUES (?, ?, ?, 'Test Itin', 3, 'completed')
            """,
            (f"itin_{trip_id}", trip_id, user_id),
        )
        conn.execute(
            """
            INSERT INTO live_trip_state (trip_id, user_id, is_completed, completed_at)
            VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            """,
            (trip_id, user_id),
        )
        conn.commit()

    # 1. Weather alerts endpoint (Task B9)
    res_w = client.get(f"/api/live/{trip_id}/weather-alerts")
    assert res_w.status_code == 200
    w_data = res_w.json()
    assert "sunrise" in w_data
    assert "sunset" in w_data
    assert "forecast" in w_data

    # 2. Post-trip feedback bridges to core_trip_feedback (Task B11)
    res_post = client.post(
        f"/api/live/{trip_id}/postrip",
        json={
            "user_id": user_id,
            "overall_satisfaction": 5.0,
            "pace_rating": "just_right",
            "budget_accuracy": "accurate",
            "itinerary_realistic": "realistic",
            "enjoyed_most": "Cultural monuments",
            "disliked": "None",
            "comments": "Great trip!",
            "activity_ratings": [],
        },
    )
    assert res_post.status_code == 200

    # Verify that core_trip_feedback received the feedback!
    fb_list = load_trip_feedback(trip_id)
    assert len(fb_list) > 0
    assert fb_list[0]["overall_satisfaction"] == 5
