"""
Tests for Redesigned India-Specific, Deduplicated Questionnaire Schema & Endpoints
Validates:
1. Schema integrity (Schema 2.0.0, 12 basic + 27 deep, zero duplicated concepts).
2. India travel realities (Indian regions, satvik/Jain/halal diets, Vande Bharat/AC trains, Himalayan acclimatization, INR budgets).
3. Prefill and refinement logic.
4. Model-agnostic feature extraction (named, vector, onehot).
5. New API endpoints:
   - GET /api/config/questionnaire-schema
   - GET /api/profile/{user_id}/features
   - GET /api/profile/{user_id}/export
   - GET /api/profile/{user_id}/summary
6. Backwards-compatibility adapters.
"""
import json
import pytest
from pathlib import Path
from app.vectorizer import SchemaAdapter, PreferenceVectorizer
from app import precision as prec
from app import questionnaire as quest

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "app" / "data" / "questionnaire_schema.json"


def test_schema_json_integrity():
    assert SCHEMA_FILE.exists(), "Schema file app/data/questionnaire_schema.json missing"
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema = json.load(f)

    assert schema["schema_version"] == "2.0.0"
    assert schema["country_scope"] in ("IN", "India")
    assert schema["currency"] == "INR"

    basic_qs = [q for q in schema["questions"] if q["tier"] == "basic"]
    deep_qs = [q for q in schema["questions"] if q["tier"] == "deep"]

    assert len(basic_qs) == 12, f"Expected 12 basic questions, found {len(basic_qs)}"
    assert len(deep_qs) == 27, f"Expected 27 deep questions, found {len(deep_qs)}"
    assert len(schema["questions"]) == 39

    # Verify sections exist and link properly
    sec_ids = {s["id"] for s in schema["basic_sections"] + schema["deep_sections"]}
    for q in schema["questions"]:
        assert q["section"] in sec_ids, f"Question {q['id']} references unknown section {q['section']}"
        assert q.get("text") or q.get("question"), f"Question {q['id']} has no text"
        assert q.get("concept"), f"Question {q['id']} has no concept defined"


def test_concept_uniqueness_and_zero_cross_tier_duplication():
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema = json.load(f)

    concepts = [q["concept"] for q in schema["questions"]]
    assert len(concepts) == len(set(concepts)), f"Found duplicate concepts: {[c for c in concepts if concepts.count(c) > 1]}"

    # Check refines relations: any deep question refining must point to a basic concept
    basic_concepts = {q["concept"] for q in schema["questions"] if q["tier"] == "basic"}
    basic_ids = {q["id"] for q in schema["questions"] if q["tier"] == "basic"}

    for q in schema["questions"]:
        if q.get("refines"):
            assert q["refines"] in basic_concepts, f"{q['id']} refines unknown basic concept {q['refines']}"
        if q.get("prefill_from"):
            assert q["prefill_from"] in basic_ids, f"{q['id']} prefill_from unknown basic question {q['prefill_from']}"


def test_india_specific_travel_realities():
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema = json.load(f)

    q_map = {q["id"]: q for q in schema["questions"]}

    # 1. Indian Origin Regions
    origin_opts = [o["id"] for o in q_map["b02_home_region"]["options"]]
    assert "north_india" in origin_opts and "south_india" in origin_opts and "northeast_india" in origin_opts

    # 2. Indian Dietary Traditions
    diet_opts = [o["id"] for o in q_map["b09_dietary"]["options"]]
    assert "pure_veg" in diet_opts and "jain" in diet_opts and "halal" in diet_opts and "eggetarian" in diet_opts

    # 3. Indian Railways Classes
    train_opts = [o["id"] for o in q_map["d13_train_class"]["options"]]
    assert any("vande_bharat" in t for t in train_opts)
    assert any("first" in t or "1a" in t for t in train_opts)
    assert any("2" in t for t in train_opts)

    # 4. Indian Daily Spend Bands in INR (<2.5k, 2.5k-6k, >6k)
    budget_opts = [o["id"] for o in q_map["b10_budget"]["options"]]
    assert "budget_backpacker" in budget_opts and "mid_range_comfortable" in budget_opts and "premium_luxury" in budget_opts

    # 5. High-Altitude Himalayan Acclimatization & Monsoon Rain
    assert "d06_high_altitude" in q_map
    assert "d05_monsoon_rain" in q_map

    # 6. Solo Safety & Senior Accessibility
    assert "d01_solo_safety" in q_map
    assert "d03_senior_accessibility" in q_map


def test_model_agnostic_feature_extraction():
    test_answers = {
        "b01_age": "25_34",
        "b02_home_region": "west_india",
        "b03_companions": "solo",
        "b05_travel_goals": ["heritage_architecture", "spiritual_pilgrimage"],
        "b06_place_interests": ["temple_towns_spiritual", "heritage_forts_palaces"],
        "b09_dietary": ["pure_veg", "jain"],
        "b10_budget": "mid_range_comfortable",
        "d05_monsoon_rain": 2,
        "d06_high_altitude": 2,
        "d08_winter_cold": 1,
        "d11_food_allergens": ["allergen_peanuts"],
        "d13_train_class": "vande_bharat_executive",
    }

    # Named features format
    named = SchemaAdapter.extract_features(test_answers, format_type="named")
    assert isinstance(named, dict)
    assert len(named) > 30
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in named.values())

    # Vector format
    vec_data = SchemaAdapter.extract_features(test_answers, format_type="vector")
    assert "vector" in vec_data and "feature_names" in vec_data
    assert len(vec_data["vector"]) == len(vec_data["feature_names"])

    # Onehot format
    onehot = SchemaAdapter.extract_features(test_answers, format_type="onehot")
    assert all(v in (0.0, 1.0) for v in onehot.values())


def test_questionnaire_schema_endpoint(client):
    res = client.get("/api/config/questionnaire-schema")
    assert res.status_code == 200
    data = res.json()
    assert data["schema_version"] == "2.0.0"
    assert data["country_scope"] in ("IN", "India")
    assert len(data["questions"]) == 39


def test_profile_features_export_and_summary_endpoints(client, demo_user):
    user_id = demo_user

    # Save a profile first
    save_res = client.post(
        f"/api/profile/{user_id}",
        json={
            "age_group": "25_34",
            "travel_experience": "occasional",
            "companions": "solo",
            "planning_approach": "plan_essentials",
            "travel_goals": ["heritage_architecture", "culinary_exploration"],
            "place_interests": ["heritage_forts_palaces", "culinary_food_trails"],
            "dietary": ["pure_veg"],
            "budget_tier": "mid_range",
            "preferred_climate": "mild",
            "raw_answers": {
                "b01_age": "25_34",
                "b03_companions": "solo",
                "b05_travel_goals": ["heritage_architecture", "culinary_exploration"],
                "b06_place_interests": ["heritage_forts_palaces", "culinary_food_trails"],
                "b09_dietary": ["pure_veg"],
                "d08_winter_cold": 2,
                "d11_food_allergens": ["allergen_peanuts"],
            }
        }
    )
    assert save_res.status_code == 200

    # 1. Test /api/profile/{user_id}/features
    f_res = client.get(f"/api/profile/{user_id}/features?format=named")
    assert f_res.status_code == 200
    features = f_res.json()
    assert isinstance(features, dict)
    assert len(features) > 20

    # 2. Test /api/profile/{user_id}/export
    exp_res = client.get(f"/api/profile/{user_id}/export")
    assert exp_res.status_code == 200
    export_data = exp_res.json()
    assert export_data["schema_version"] == "2.0.0"
    assert export_data["user_id"] == user_id
    assert "llm_system_context" in export_data
    assert "User Profile" in export_data["llm_system_context"]

    # 3. Test /api/profile/{user_id}/summary
    sum_res = client.get(f"/api/profile/{user_id}/summary")
    assert sum_res.status_code == 200
    summary_data = sum_res.json()
    assert "overview" in summary_data
    assert "travel_party" in summary_data
    assert "food_and_diet" in summary_data
    assert "transit_and_stay" in summary_data


def test_backward_compatibility_adapters():
    # Legacy question IDs (q1, q78, q95, etc.) should map smoothly
    legacy_answers = {
        "q1": "25_34",
        "q3": "alone",
        "q78": 1,                     # winter cold
        "q95": ["peanuts", "sesame"],  # allergens
        "q61": "carry_on",            # luggage
    }

    migrated = SchemaAdapter.migrate_answers(legacy_answers)
    assert migrated["b01_age"] == "25_34"
    assert migrated["d08_winter_cold"] == 1
    assert migrated["d11_food_allergens"] == ["peanuts", "sesame"]

    # Insights derive hard constraints from legacy keys
    insights = prec.derive_insights(legacy_answers)
    assert any(i["kind"] == "constraint" for i in insights)
    assert any("peanuts" in i["text"].lower() for i in insights)
    assert any("windproof" in i["text"].lower() for i in insights)
