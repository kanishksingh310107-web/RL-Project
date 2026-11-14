"""Central profile loader and normalizer for RL Travel Guide.

Resolves the vocabulary mismatch and interest extraction bug by synthesizing:
1. traveller_profiles (basic onboarding)
2. raw_answers_json (original survey selections)
3. detailed_profiles (comfort, physical constraints, avoidances)
4. precision_profiles (deep personalized answers, filtered for privacy)

Ensures consistent canonical vocabulary across the entire codebase.
"""
import json
from typing import Dict, Any, List, Optional

from app.database import get_connection

# Canonical mapping from questionnaire selections to the 7 LinUCB arms
GOAL_TO_CANONICAL: Dict[str, str] = {
    "culture": "culture_history",
    "culture_history": "culture_history",
    "history": "culture_history",
    "historic": "culture_history",
    "heritage": "culture_history",
    "nature": "nature_outdoors",
    "nature_outdoors": "nature_outdoors",
    "food": "food_dining",
    "food_dining": "food_dining",
    "culinary": "food_dining",
    "adventure": "adventure",
    "relaxation": "relaxation",
    "wellness": "relaxation",
    "growth": "relaxation",
    "shopping": "shopping_local",
    "shopping_local": "shopping_local",
    "scenic": "scenic",
    "photography": "scenic",
    "quality_time": "relaxation",
    "socializing": "food_dining",
    "work_study": "culture_history",
}

PLACE_INTEREST_TO_CANONICAL: Dict[str, str] = {
    "mountains_nature": "nature_outdoors",
    "beaches_coastal": "relaxation",
    "forests_wildlife": "nature_outdoors",
    "historical_sites": "culture_history",
    "museums_art": "culture_history",
    "local_markets": "shopping_local",
    "cafes_restaurants": "food_dining",
    "religious_spiritual": "culture_history",
    "theme_parks": "adventure",
    "nightlife_music": "food_dining",
    "villages_communities": "culture_history",
    "architecture_photo": "scenic",
}


def normalize_vocabulary(field: str, value: Any) -> Any:
    """Map legacy synonyms to canonical terms."""
    if not isinstance(value, str):
        return value

    val_lower = value.lower().strip()
    if field == "companions":
        if val_lower in ("solo", "single", "myself"):
            return "alone"
        return val_lower

    if field == "budget_tier":
        if val_lower in ("mid_range", "mid", "moderate", "medium"):
            return "balanced"
        if val_lower in ("budget_backpacker", "hostel", "low"):
            return "budget"
        if val_lower in ("luxury_premium", "high", "upscale"):
            return "luxury"
        return val_lower

    if field == "pace":
        if val_lower in ("slow", "relaxed"):
            return "relaxed"
        if val_lower in ("fast", "packed", "intense"):
            return "packed"
        return "balanced"

    return value


def map_interests(raw_goals: List[str], raw_places: List[str]) -> List[str]:
    """Map raw goal and place selection tags to canonical LinUCB categories."""
    canonical_set: Dict[str, None] = {}
    for g in raw_goals:
        c = GOAL_TO_CANONICAL.get(g.lower().strip())
        if c:
            canonical_set[c] = None

    for p in raw_places:
        c = PLACE_INTEREST_TO_CANONICAL.get(p.lower().strip())
        if c:
            canonical_set[c] = None

    return list(canonical_set.keys())


def load_profile(user_id: str) -> Dict[str, Any]:
    """Load unified traveller profile for user_id.
    
    Merges basic onboarding, raw answers, detailed profile, and precision profile.
    If the user has not completed onboarding, returns safe defaults.
    Never raises an uncaught exception or returns None for mandatory fields.
    """
    safe_defaults: Dict[str, Any] = {
        "user_id": user_id,
        "has_profile": False,
        "interests": ["culture_history", "nature_outdoors", "food_dining"],
        "pace": "balanced",
        "crowd_tolerance": 0.5,
        "structure": 0.5,
        "companions": "alone",
        "has_children": False,
        "budget_tier": "balanced",
        "preferred_climate": "mild",
        "planning_experience": "intermediate",
        "avoidances": [],
        "dietary": ["none"],
        "walking_tolerance": "medium",
        "schedule_density": "balanced_2_3",
        "stay_style": "boutique",
        "transit_pref": "public_transit",
        "repetition_strategy": "similar_vibes",
        "travel_goals": ["culture_history", "nature_outdoors", "food_dining"],
        "place_interests": ["historical_sites", "mountains_nature", "local_markets"],
        "precision_answers": {},
        "raw_answers": {}
    }

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # 1. Fetch Basic Profile
            cursor.execute("SELECT * FROM traveller_profiles WHERE user_id = ?", (user_id,))
            base_row = cursor.fetchone()
            if not base_row:
                return safe_defaults

            profile: Dict[str, Any] = dict(safe_defaults)
            profile["has_profile"] = True

            # Extract basic columns
            raw_answers_json = base_row["raw_answers_json"] if "raw_answers_json" in base_row.keys() else None
            raw_answers: Dict[str, Any] = json.loads(raw_answers_json) if raw_answers_json else {}
            profile["raw_answers"] = raw_answers
            home = conn.execute('SELECT * FROM user_profile WHERE user_id=?',(user_id,)).fetchone()
            if home:
                profile.update({key:home[key] for key in ('residence_country','residence_state','residence_city','preferred_currency')})

            # Companions
            comp = base_row["companions"] or raw_answers.get("companions", "alone")
            profile["companions"] = normalize_vocabulary("companions", comp)

            # Budget tier
            bt = base_row["budget_tier"] or raw_answers.get("budget_tier", "balanced")
            profile["budget_tier"] = normalize_vocabulary("budget_tier", bt)

            # Pace
            raw_pace = base_row["pace"]
            if isinstance(raw_pace, (int, float)):
                if raw_pace < 0.35:
                    profile["pace"] = "relaxed"
                elif raw_pace > 0.65:
                    profile["pace"] = "packed"
                else:
                    profile["pace"] = "balanced"
            elif isinstance(raw_pace, str):
                profile["pace"] = normalize_vocabulary("pace", raw_pace)

            # Crowd tolerance
            try:
                profile["crowd_tolerance"] = float(base_row["crowd_tolerance"])
            except (ValueError, TypeError):
                profile["crowd_tolerance"] = 0.5

            profile["structure"] = float(base_row["structure"]) if base_row["structure"] is not None else 0.5
            profile["has_children"] = bool(base_row["has_children"])
            profile["preferred_climate"] = base_row["preferred_climate"] or "mild"
            profile["planning_experience"] = base_row["planning_experience"] or "intermediate"

            # 2. Fix the Interest Extraction Bug
            # Parse travel_goals and place_interests from raw survey answers
            travel_goals: List[str] = raw_answers.get("travel_goals") or []
            if not travel_goals and "interests" in base_row.keys() and base_row["interests"]:
                try:
                    loaded = json.loads(base_row["interests"])
                    if isinstance(loaded, list):
                        travel_goals = loaded
                except Exception:
                    pass

            place_interests: List[str] = raw_answers.get("place_interests") or []

            profile["travel_goals"] = travel_goals
            profile["place_interests"] = place_interests

            mapped_interests = map_interests(travel_goals, place_interests)
            if mapped_interests:
                profile["interests"] = mapped_interests
            else:
                profile["interests"] = safe_defaults["interests"]

            # Dietary preferences
            raw_diet = raw_answers.get("dietary") or []
            if isinstance(raw_diet, list) and raw_diet:
                profile["dietary"] = raw_diet

            # 3. Fetch Detailed Profile (if any)
            cursor.execute("SELECT * FROM detailed_profiles WHERE user_id = ?", (user_id,))
            det_row = cursor.fetchone()
            if det_row:
                try:
                    detailed_answers = json.loads(det_row["raw_answers_json"] or "{}")
                    profile["custom_travel_context"] = str(detailed_answers.get("custom_travel_context") or "") if isinstance(detailed_answers, dict) else ""
                except (TypeError, ValueError):
                    profile["custom_travel_context"] = ""
                try:
                    profile["avoidances"] = json.loads(det_row["avoidances"]) if det_row["avoidances"] else []
                except Exception:
                    profile["avoidances"] = []

                if det_row["walking_tolerance"]:
                    profile["walking_tolerance"] = det_row["walking_tolerance"]
                if det_row["schedule_density"]:
                    profile["schedule_density"] = det_row["schedule_density"]
                if det_row["stay_style"]:
                    profile["stay_style"] = det_row["stay_style"]
                if det_row["transit_pref"]:
                    profile["transit_pref"] = det_row["transit_pref"]
                if det_row["repetition_strategy"]:
                    profile["repetition_strategy"] = det_row["repetition_strategy"]

                try:
                    det_diet = json.loads(det_row["dietary"]) if det_row["dietary"] else []
                    if det_diet:
                        profile["dietary"] = list(set(profile["dietary"] + det_diet))
                except Exception:
                    pass

            # 4. Fetch Precision Profile (respect privacy filter)
            cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
            prec_row = cursor.fetchone()
            if prec_row and prec_row["answers_json"]:
                try:
                    from app.precision import apply_privacy_filter
                    prec_raw = json.loads(prec_row["answers_json"])
                    clean_answers, _ = apply_privacy_filter(prec_raw)
                    profile["precision_answers"] = clean_answers

                    # Incorporate precision avoidances
                    prec_avoid = clean_answers.get("d01_avoidances") or clean_answers.get("q12") or []
                    if isinstance(prec_avoid, list) and prec_avoid:
                        profile["avoidances"] = list(set(profile["avoidances"] + prec_avoid))
                except Exception:
                    pass

            return profile

    except Exception:
        return safe_defaults
