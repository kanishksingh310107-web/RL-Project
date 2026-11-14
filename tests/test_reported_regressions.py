from app.profile_gate import AccountInput
from app.recommender import DESTINATIONS


def test_india_recommendation_catalogue_covers_100_destinations():
    destinations = [item for item in DESTINATIONS if item.get("country") == "India"]
    assert len(destinations) == 100
    assert len({item["id"] for item in destinations}) == 100


def test_email_signup_password_accepts_8_to_16_characters_only():
    base = {"email": "traveller@example.com", "mode": "signup", "username": "traveller",
            "confirm_password": "SafePas1"}
    assert AccountInput(**{**base, "password": "SafePas1"}).password == "SafePas1"
    for password in ("Short1A", "LongPassword123456A"):
        try:
            AccountInput(**{**base, "password": password, "confirm_password": password})
        except Exception:
            continue
        raise AssertionError("Expected signup password length validation to reject the value")
