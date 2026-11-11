"""Unit tests for app.core.profile (loader & vocabulary normalizer) and app.core.stores."""
import json
import sqlite3
from app.core.profile import load_profile, map_interests, normalize_vocabulary
from app.core.stores import (
    save_trip_prefs, load_trip_prefs,
    save_trip_plan, load_trip_plan,
    save_stay, load_stay,
    save_trip_feedback, load_trip_feedback,
    ensure_core_tables
)
from app.core.schemas import (
    TripPrefs, TripPlan, DayPlan, DayWindow, Stay, Provenance
)
from app.database import get_connection


def test_map_interests_nature_culture():
    mapped = map_interests(["nature", "culture"], ["historical_sites"])
    assert "nature_outdoors" in mapped
    assert "culture_history" in mapped
    assert len(mapped) >= 2


def test_normalize_vocabulary_synonyms():
    assert normalize_vocabulary("companions", "solo") == "alone"
    assert normalize_vocabulary("companions", "SOLO") == "alone"
    assert normalize_vocabulary("budget_tier", "mid_range") == "balanced"
    assert normalize_vocabulary("budget_tier", "budget_backpacker") == "budget"
    assert normalize_vocabulary("pace", "slow") == "relaxed"
    assert normalize_vocabulary("pace", "fast") == "packed"


def test_missing_profile_returns_safe_defaults():
    profile = load_profile("non_existent_user_id_9999")
    assert profile["has_profile"] is False
    assert profile["interests"] == ["culture_history", "nature_outdoors", "food_dining"]
    assert profile["companions"] == "alone"
    assert profile["budget_tier"] == "balanced"
    assert profile["pace"] == "balanced"
    assert profile["avoidances"] == []


def test_load_profile_with_raw_answers(client, demo_user):
    # Insert profile with raw answers containing travel_goals and place_interests
    with get_connection() as conn:
        cursor = conn.cursor()
        raw_json = json.dumps({
            "companions": "solo",
            "budget_tier": "mid_range",
            "travel_goals": ["nature", "food"],
            "place_interests": ["mountains_nature", "cafes_restaurants"]
        })
        cursor.execute("""
            INSERT OR REPLACE INTO traveller_profiles (
                user_id, profile_type, interests, pace, crowd_tolerance,
                structure, companions, has_children, budget_tier, preferred_climate,
                planning_experience, raw_answers_json
            ) VALUES (?, 'basic', '[]', 0.5, 0.5, 0.5, 'solo', 0, 'mid_range', 'mild', 'intermediate', ?)
        """, (demo_user, raw_json))
        conn.commit()

    loaded = load_profile(demo_user)
    assert loaded["has_profile"] is True
    assert loaded["companions"] == "alone"
    assert loaded["budget_tier"] == "balanced"
    assert "nature_outdoors" in loaded["interests"]
    assert "food_dining" in loaded["interests"]


def test_stores_trip_prefs_roundtrip():
    prefs = TripPrefs(
        trip_id="test_trip_123",
        user_id="user_abc",
        pace="packed",
        shopping_style="local_crafts"
    )
    save_trip_prefs(prefs)
    loaded = load_trip_prefs("test_trip_123")
    assert loaded is not None
    assert loaded.trip_id == "test_trip_123"
    assert loaded.pace == "packed"
    assert loaded.shopping_style == "local_crafts"


def test_stores_trip_plan_roundtrip():
    plan = TripPlan(
        trip_id="plan_trip_999",
        user_id="user_abc",
        destination_id="udaipur_india",
        destination_name="Udaipur",
        total_days=1,
        days=[DayPlan(day_number=1, window=DayWindow(day_number=1))]
    )
    save_trip_plan(plan)
    loaded = load_trip_plan("plan_trip_999")
    assert loaded is not None
    assert loaded.destination_name == "Udaipur"
    assert loaded.total_days == 1
    assert len(loaded.days) == 1


def test_stores_stay_roundtrip():
    stay = Stay(
        stay_id="stay_hotel_456",
        trip_id="trip_stay_123",
        name="Lake Palace",
        lat=24.5760,
        lon=73.6800,
        estimated_nightly_budget=6000.0
    )
    save_stay(stay)
    loaded = load_stay("trip_stay_123")
    assert loaded is not None
    assert loaded.name == "Lake Palace"
    assert loaded.estimated_nightly_budget == 6000.0


def test_stores_trip_feedback_roundtrip():
    f_id = save_trip_feedback("trip_fb_1", "user_1", {"rating": 5, "comment": "Excellent"})
    assert f_id is not None
    feedbacks = load_trip_feedback("trip_fb_1")
    assert len(feedbacks) == 1
    assert feedbacks[0]["rating"] == 5


def test_password_hashing_pbkdf2_and_legacy_compatibility():
    import hashlib
    from app.auth import hash_password, verify_password, AUTH_SECRET_KEY

    # 1. PBKDF2 hash verification
    pwd = "Secr3tPassword!2026"
    stored_hash, salt = hash_password(pwd)
    assert stored_hash.startswith("pbkdf2:sha256:100000$")
    assert verify_password(pwd, stored_hash) is True
    assert verify_password("WrongPassword!", stored_hash) is False

    # 2. Backward compatibility with legacy SHA-256 hashes
    legacy_salt = "ab12cd34ef56"
    legacy_salted = f"{legacy_salt}${pwd}${AUTH_SECRET_KEY}"
    legacy_hash = f"{legacy_salt}${hashlib.sha256(legacy_salted.encode('utf-8')).hexdigest()}"
    assert verify_password(pwd, legacy_hash) is True
    assert verify_password("WrongPassword!", legacy_hash) is False
