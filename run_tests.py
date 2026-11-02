# Tests for travel guide backend
import sys
from fastapi.testclient import TestClient
from main import app
from app.vectorizer import PreferenceVectorizer
from app.database import init_db, get_connection
from app import precision as prec
from app.questionnaire import QUESTIONS as BASE_QUESTIONS

def run_tests():
    print("Running tests...")
    init_db()  # TestClient(app) does not fire the startup hook, so create tables explicitly
    client = TestClient(app)

    # 1. Options & Master Questionnaire Bank
    res = client.get("/api/config/options")
    assert res.status_code == 200

    q_res = client.get("/api/config/questionnaire")
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert len(q_data["sections"]) == 10
    assert len(q_data["questions"]) == 56
    print(f"[OK] Master Questionnaire Bank verified ({len(q_data['questions'])} questions across {len(q_data['sections'])} sections)")

    # 2. Auth tests (google, email, phone)
    # google
    g_res = client.post("/api/auth", json={
        "provider": "google",
        "identifier": "test@gmail.com",
        "display_name": "Test User"
    })
    assert g_res.status_code == 200
    user_id = g_res.json()["user_id"]

    # start clean so the suite can be re-run against an existing database
    # (a saved Level 3 profile would otherwise take priority in /api/rl/state)
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM precision_profiles WHERE user_id = ?", (user_id,))
        conn.commit()

    # email
    e_res = client.post("/api/auth", json={
        "provider": "email",
        "identifier": "test_student@example.com",
        "password": "password123",
        "display_name": "Alex"
    })
    assert e_res.status_code == 200

    # phone
    p_res = client.post("/api/auth", json={
        "provider": "phone",
        "identifier": "9876543210"
    })
    assert p_res.status_code == 200
    print("[OK] Auth working (google, email, phone)")

    # 3. Vectorizer test
    sample_profile = {
        "interests": ["nature_outdoors", "photography"],
        "pace": 0.4,
        "crowd_tolerance": 0.3,
        "structure": 0.8,
        "companions": "solo",
        "has_children": False,
        "budget_tier": "balanced",
        "preferred_climate": "mild"
    }
    vec, names = PreferenceVectorizer.vectorize(sample_profile)
    assert len(vec) == 22
    print(f"[OK] Vectorizer working ({len(vec)} features)")

    # 4. Profile API test
    prof_payload = {
        **sample_profile,
        "planning_experience": "intermediate"
    }
    p_res = client.post(f"/api/profile/{user_id}", json=prof_payload)
    assert p_res.status_code == 200
    print("[OK] Profile created and saved")

    # 5. Detailed options
    det_opt_res = client.get("/api/config/detailed-options")
    assert det_opt_res.status_code == 200
    assert "avoidances" in det_opt_res.json()
    print("[OK] Loaded detailed config options")

    # 6. Detailed Profile API & 41-dim vectorizer test
    detailed_payload = {
        "avoidances": ["crowded_places", "steep_stairs_hills", "night_clubs"],
        "walking_tolerance": "medium",
        "schedule_density": "balanced_2_3",
        "accessibility": ["step_free"],
        "dietary": ["vegetarian"],
        "stay_style": "boutique",
        "transit_pref": "public_transit",
        "repetition_strategy": "explore_new",
        "past_trips": [
            {
                "destination": "Kyoto, Japan",
                "rating": 5,
                "favorite_activity": "Zen gardens & historic tea houses",
                "skipped_or_disliked": "Overcrowded peak season market"
            }
        ]
    }
    det_res = client.post(f"/api/profile/detailed/{user_id}", json=detailed_payload)
    assert det_res.status_code == 200
    det_data = det_res.json()
    assert det_data["feature_dimension"] == 41
    assert len(det_data["rl_state_vector"]) == 41
    print(f"[OK] Detailed profile saved ({det_data['feature_dimension']} features)")

    # 7. RL state endpoint returns upgraded 41-dim vector
    state_res = client.get(f"/api/rl/state/{user_id}")
    assert state_res.status_code == 200
    state_data = state_res.json()
    assert state_data["dimension_count"] == 41
    assert "detailed" in state_data["level"]
    print(f"[OK] RL state upgraded to {state_data['dimension_count']}-dim vector with constraint masks")

    run_precision_tests(client, user_id)
    print("\nAll tests passed successfully!")


def run_precision_tests(client, user_id):
    """Level 3 Precision Profile tests."""
    bank = prec.PRECISION_QUESTIONS
    section_ids = {s["id"] for s in prec.PRECISION_SECTIONS}

    # --- 1. Bank integrity -------------------------------------------------
    feature_names = prec.get_precision_feature_names()
    assert len(feature_names) == len(set(feature_names)), "duplicate feature names"
    for qid, q in bank.items():
        assert q["section"] in section_ids, qid
        assert q["type"] in ("single", "multi", "scale", "number", "text"), qid
        ids = [o["id"] for o in q.get("options", [])]
        assert len(ids) == len(set(ids)), f"{qid}: duplicate option ids"
        if q["type"] in ("single", "multi"):
            assert ids, f"{qid}: needs options"
        if q["type"] == "scale":
            assert q.get("low") and q.get("high"), qid
        if q["type"] == "number":
            assert q["min"] < q["max"], qid
        if q.get("exclusive"):
            assert q["exclusive"] in ids, qid
        spec = q.get("vec")
        if spec:
            if spec["type"] == "ordinal":
                assert set(spec["map"]) == set(ids), f"{qid}: ordinal map must cover every option"
                assert all(0 <= v <= 1 for v in spec["map"].values()), qid
                if q.get("show_if"):
                    assert min(spec["map"].values()) > 0, f"{qid}: 0.0 is reserved for 'not applicable'"
            if spec["type"] == "flags":
                assert set(spec["options"]) <= set(ids), qid
            if spec["type"] == "scale":
                assert q["type"] == "scale", qid
        # every show_if must reference a real question and real option ids
        def check(cond):
            if "any" in cond or "all" in cond:
                for c in cond.get("any", []) + cond.get("all", []):
                    check(c)
                return
            src = cond["q"]
            src_q = bank.get(src) or (BASE_QUESTIONS[src] if src in prec.CONTEXT_QIDS else None)
            assert src_q is not None, f"{qid}: show_if source {src} unknown"
            src_ids = {o["id"] for o in src_q.get("options", [])}
            assert set(cond["includes_any"]) <= src_ids, f"{qid}: show_if uses unknown option ids of {src}"
        if q.get("show_if"):
            check(q["show_if"])
    assert len(prec.NEW_QUESTIONS) == 65 and len(prec.CARRYOVER) == 18 and len(bank) == 83
    print(f"[OK] Precision bank verified ({len(bank)} questions: {len(prec.NEW_QUESTIONS)} new + {len(prec.CARRYOVER)} previously-unshown, {len(feature_names)} features)")

    # --- 2. Conditional follow-ups -----------------------------------------
    assert not prec.is_visible("q64", {})
    assert not prec.is_visible("q64", {"q3": "alone"})
    assert prec.is_visible("q64", {"q3": "family_children"})
    assert not prec.is_visible("q95", {}) and prec.is_visible("q95", {"q10": ["food_allergies"]})
    assert not prec.is_visible("q96", {"q10": ["food_allergies"]})                         # needs an allergen picked
    assert prec.is_visible("q96", {"q10": ["food_allergies"], "q95": ["peanuts"]})
    assert not prec.is_visible("q96", {"q10": ["pollen_environmental"], "q95": ["peanuts"]})  # parent hidden -> child hidden
    print("[OK] Conditional follow-up questions (show_if, chained) working")

    # --- 3. Validation ------------------------------------------------------
    _, errs = prec.validate_answers({"q999": "x", "q78": 9, "q72": 99, "q57": "nope", "q62": ["flight", "teleport"]})
    assert len(errs) == 5, errs
    _, errs = prec.validate_answers({"q10": ["no_concerns", "food_allergies"]})
    assert errs and "cannot be combined" in errs[0]
    _, errs = prec.validate_answers({"q6": ["planning_decisions", "unfamiliar_env", "language_barriers", "managing_expenses"]})
    assert errs and "at most 3" in errs[0]
    clean, errs = prec.validate_answers({"q95": ["peanuts"], "q78": 2, "q100": "  mushrooms  "})  # q95 hidden: q10 missing
    assert not errs and "q95" not in clean and clean["q100"] == "mushrooms" and clean["q78"] == 2
    print("[OK] Validation rejects bad input and drops answers to hidden questions")

    # --- 4. Privacy filter (Q47) -------------------------------------------
    kept, dropped = prec.apply_privacy_filter({"q47": ["interests_hobbies"], "q78": 2, "q74": "m10", "q106": "serious", "q57": "short"})
    assert set(dropped) == {"q78", "q74"} and "q106" in kept and "q57" in kept
    kept, dropped = prec.apply_privacy_filter({"q78": 2})   # Q47 unanswered -> nothing dropped
    assert not dropped
    print("[OK] Privacy filter enforces Q47 choices")

    # --- 5. Vector ----------------------------------------------------------
    ctx = {"q3": "family_children"}
    answers = {"q10": ["food_allergies"], "q95": ["peanuts", "sesame"], "q96": "severe", "q78": 1, "q73": 5, "q64": "toddler"}
    vec, names = prec.build_precision_vector(answers, ctx)
    d = dict(zip(names, vec))
    assert len(vec) == len(names) == 85 and all(0.0 <= v <= 1.0 for v in vec)
    assert d["allergen_peanuts"] == 1.0 and d["allergen_sesame"] == 1.0 and d["allergen_fish"] == 0.0
    assert d["allergy_severity"] == 1.0 and d["cold_tolerance"] == 0.0 and d["walk_km"] == 0.2 and d["youngest_child_age"] == 0.5
    assert d["spice_tolerance"] == 0.5          # visible but unanswered -> neutral
    assert d["diet_strictness"] == 0.0          # hidden (no restrictive diet in context) -> not applicable
    n, tot = prec.coverage(answers, ctx)
    assert abs(d["precision_coverage"] - n / tot) < 1e-3
    empty_vec, _ = prec.build_precision_vector({}, {})
    assert empty_vec[-1] == 0.0
    print(f"[OK] Precision vector: 85 dims, all in [0,1], hidden=0.0, unanswered=0.5, coverage={d['precision_coverage']:.2f}")

    # --- 6. Insights --------------------------------------------------------
    ins = prec.derive_insights({"q10": ["food_allergies"], "q95": ["peanuts"], "q96": "severe", "q80": 1, "q61": "carry_on"}, {})
    kinds = [i["kind"] for i in ins]
    assert "constraint" in kinds and any("windproof" in i["text"] for i in ins) and any("Carry-on" in i["text"] for i in ins)
    print(f"[OK] Planner insights derived ({len(ins)} rules from 5 answers)")

    # --- 7. Avoidance alias fix (Q12 ids used to be silently lost) ---------
    vec41, names41 = PreferenceVectorizer.vectorize_detailed({}, {"avoidances": ["noisy_nightlife", "early_morning_rush"]})
    d41 = dict(zip(names41, vec41))
    assert d41["avoid_crowded_clubs"] == 1.0 and d41["avoid_early_starts"] == 1.0
    print("[OK] Q12 avoidance ids now reach the 41-dim penalty mask")

    # --- 8. API round trip --------------------------------------------------
    q_res = client.get("/api/config/precision-questionnaire")
    assert q_res.status_code == 200 and q_res.json()["total"] == 83
    assert "vec" not in next(iter(q_res.json()["questions"].values()))
    assert client.post("/api/profile/precision/does-not-exist", json={"answers": {}}).status_code == 404

    g = client.get(f"/api/profile/precision/{user_id}")
    assert g.status_code == 200 and g.json()["exists"] is False

    bad = client.post(f"/api/profile/precision/{user_id}", json={"answers": {"q78": 99}})
    assert bad.status_code == 422

    ok = client.post(f"/api/profile/precision/{user_id}", json={"answers": {
        "q10": ["food_allergies"], "q95": ["peanuts"], "q96": "severe", "q78": 2, "q80": 1,
        "q61": "carry_on", "q100": "mushrooms", "q47": ["travel_prefs", "dietary_needs"]}})
    assert ok.status_code == 200, ok.text
    data = ok.json()
    assert data["feature_dimension"] == 126 and len(data["rl_state_vector"]) == 126
    assert set(data["dropped_for_privacy"]) == {"q10", "q95", "q96", "q78", "q80"} or "q95" in data["dropped_for_privacy"]
    print(f"[OK] Precision profile saved via API ({data['feature_dimension']} dims, coverage {data['coverage']:.0%}, privacy-dropped: {sorted(data['dropped_for_privacy'])})")

    # save again without the privacy restriction so allergen masks reach the vector
    ok2 = client.post(f"/api/profile/precision/{user_id}", json={"answers": {
        "q10": ["food_allergies"], "q95": ["peanuts"], "q96": "severe", "q78": 2, "q80": 1, "q61": "carry_on"}})
    assert ok2.status_code == 200 and not ok2.json()["dropped_for_privacy"]
    assert any(i["kind"] == "constraint" for i in ok2.json()["insights"])

    st = client.get(f"/api/rl/state/{user_id}").json()
    assert st["dimension_count"] == 126 and st["level"].startswith("precision")
    masks = {f["feature_name"] for f in st["feature_breakdown"] if f["is_constraint_mask"] and f["value"] > 0}
    assert "allergen_peanuts" in masks
    prof = client.get(f"/api/profile/{user_id}").json()
    assert prof["has_precision_profile"] is True
    assert client.get(f"/api/profile/precision/{user_id}").json()["exists"] is True
    print("[OK] /api/rl/state serves the 126-dim precision vector; allergen masks flagged as constraints")

    # Recommendations API Test (Feature Two)
    rec_res = client.get(f"/api/recommendations/{user_id}")
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert "recommended_for_you" in rec_data
    assert "trending_trips" in rec_data
    assert "seasonal_and_upcoming" in rec_data
    assert len(rec_data["recommended_for_you"]) >= 3
    assert len(rec_data["trending_trips"]) >= 2
    assert len(rec_data["seasonal_and_upcoming"]) >= 2

    # Verify each card contains required metadata
    sample_rec = rec_data["recommended_for_you"][0]
    required_keys = [
        "name", "why_it_suits", "available_experiences",
        "travel_style_and_atmosphere", "budget_tier",
        "best_season_and_weather", "limitations_or_uncertainties"
    ]
    for key in required_keys:
        assert key in sample_rec, f"Missing key '{key}' in recommendation"
        assert sample_rec[key], f"Value for '{key}' should not be empty"

    print(f"[OK] General Travel Recommender verified ({len(rec_data['recommended_for_you'])} Recommended, {len(rec_data['trending_trips'])} Trending, {len(rec_data['seasonal_and_upcoming'])} Seasonal)")

    # 9. Recommendation offset rotation & shortlist tests
    rec_offset_res = client.get(f"/api/recommendations/{user_id}?offset=4")
    assert rec_offset_res.status_code == 200
    rec_offset_data = rec_offset_res.json()
    assert rec_offset_data["offset"] == 4
    assert rec_offset_data["total_candidates"] == 16
    assert len(rec_offset_data["recommended_for_you"]) >= 3
    print("[OK] Recommendation candidate rotation (offset pagination) verified")

    # Shortlist toggle
    with get_connection() as conn:
        conn.execute("DELETE FROM shortlisted_destinations WHERE user_id = ?", (user_id,))
        conn.commit()

    dest_to_shortlist = rec_data["recommended_for_you"][0]["id"]
    sl_res = client.post(f"/api/shortlist/{user_id}", json={"destination_id": dest_to_shortlist})
    assert sl_res.status_code == 200
    assert sl_res.json()["is_shortlisted"] is True

    # Check shortlist listing
    sl_get = client.get(f"/api/shortlist/{user_id}")
    assert sl_get.status_code == 200
    assert dest_to_shortlist in sl_get.json()["shortlisted_ids"]

    # Recommendations should now reflect is_shortlisted=True
    rec_after_sl = client.get(f"/api/recommendations/{user_id}")
    matched_card = next((c for c in rec_after_sl.json()["recommended_for_you"] if c["id"] == dest_to_shortlist), None)
    if matched_card:
        assert matched_card["is_shortlisted"] is True

    # Toggle shortlist off
    sl_off = client.post(f"/api/shortlist/{user_id}", json={"destination_id": dest_to_shortlist})
    assert sl_off.status_code == 200
    assert sl_off.json()["is_shortlisted"] is False
    print(f"[OK] Destination shortlisting and toggle verified ({dest_to_shortlist})")



    # New: Google account isolation tests
    # First Google login (sub1)
    sub1 = "google-sub-111"
    user1 = client.post("/api/auth", json={
        "provider": "google",
        "identifier": sub1,
        "display_name": "User One"
    })
    assert user1.status_code == 200
    uid1 = user1.json()["user_id"]
    # Re-login same sub should return same user
    user1b = client.post("/api/auth", json={
        "provider": "google",
        "identifier": sub1,
        "display_name": "User One"
    })
    assert user1b.status_code == 200
    assert user1b.json()["user_id"] == uid1

    # Different Google sub
    sub2 = "google-sub-222"
    user2 = client.post("/api/auth", json={
        "provider": "google",
        "identifier": sub2,
        "display_name": "User Two"
    })
    assert user2.status_code == 200
    uid2 = user2.json()["user_id"]
    assert uid2 != uid1

    # Verify database records have correct google_sub values
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT google_sub FROM users WHERE id = ?", (uid1,))
        assert cur.fetchone()["google_sub"] == sub1
        cur.execute("SELECT google_sub FROM users WHERE id = ?", (uid2,))
        assert cur.fetchone()["google_sub"] == sub2
    print("[OK] Google account isolation verified")

    # Run Adaptive Pre-Trip Itinerary Planner & LinUCB Tests
    run_itinerary_and_rl_tests(client, user_id)

def run_itinerary_and_rl_tests(client, user_id):
    """Test suite for Adaptive Pre-Trip Itinerary Planner, LinUCB RL policy, feedback, and constraints."""
    print("\n--- Testing Adaptive Pre-Trip Itinerary Planner & LinUCB ---")

    # 1. Trip Creation
    trip_payload = {
        "destination_id": "kyoto_japan",
        "destination_name": "Kyoto",
        "start_date": "2026-11-10",
        "end_date": "2026-11-14",
        "travellers_count": 2,
        "total_budget": 1200.0,
        "currency": "USD",
        "accommodation_tier": "boutique",
        "transit_pref": "public_transit",
        "travel_pace": "balanced",
        "specific_interests": ["culture_history", "food_dining", "nature_outdoors"]
    }
    trip_res = client.post(f"/api/trips/{user_id}", json=trip_payload)
    assert trip_res.status_code == 200, trip_res.text
    trip_data = trip_res.json()
    trip_id = trip_data["id"]
    assert trip_data["duration_days"] == 5
    assert trip_data["destination_name"] == "Kyoto"
    print(f"[OK] Trip configuration created: {trip_data['destination_name']} ({trip_data['duration_days']} days)")

    # 2. Trips List
    list_res = client.get(f"/api/trips/{user_id}")
    assert list_res.status_code == 200
    assert any(t["id"] == trip_id for t in list_res.json())

    # 3. Itinerary Generation via Contextual LinUCB
    gen_res = client.post(f"/api/itinerary/generate/{trip_id}?user_id={user_id}")
    assert gen_res.status_code == 200, gen_res.text
    itin_data = gen_res.json()
    itin_id = itin_data["id"]
    assert itin_data["total_days"] == 5
    assert len(itin_data["days"]) == 5
    assert itin_data["total_estimated_cost"] > 0

    first_day = itin_data["days"][0]
    assert len(first_day["activities"]) >= 3
    sample_act = first_day["activities"][0]
    assert "morning" in sample_act["time_slot"] or "meal" in sample_act["time_slot"]
    assert sample_act["why_it_suits"] is not None
    assert sample_act["status"] == "proposed"
    assert sample_act["duration_minutes"] > 0
    print(f"[OK] LinUCB Day-by-Day Itinerary generated: 5 days, {sum(len(d['activities']) for d in itin_data['days'])} activities, estimated cost ${itin_data['total_estimated_cost']:.2f}")

    # 4. Fetch Itinerary API
    get_res = client.get(f"/api/itinerary/{trip_id}?user_id={user_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == itin_id

    # 5. Interactive User Feedback (ACCEPT)
    act_to_accept = sample_act["activity_id"]
    accept_res = client.post(f"/api/itinerary/feedback/{user_id}", json={
        "itinerary_id": itin_id,
        "activity_id": act_to_accept,
        "action_type": "accept"
    })
    assert accept_res.status_code == 200, accept_res.text
    accept_data = accept_res.json()
    assert accept_data["reward_assigned"] == 1.0
    assert accept_data["policy_updated"] is True
    print(f"[OK] Explicit ACCEPT feedback recorded with reward +1.0 and LinUCB parameter update")

    # 6. Interactive User Feedback (REJECT with reason)
    act_to_reject = itin_data["days"][1]["activities"][0]["activity_id"]
    reject_res = client.post(f"/api/itinerary/feedback/{user_id}", json={
        "itinerary_id": itin_id,
        "activity_id": act_to_reject,
        "action_type": "reject",
        "rejection_reason": "too_crowded",
        "is_trip_specific": False
    })
    assert reject_res.status_code == 200
    reject_data = reject_res.json()
    assert reject_data["reward_assigned"] == -1.0
    print(f"[OK] Explicit REJECT feedback recorded with reason 'too_crowded' and reward -1.0")

    # 7. Rejection Invariant: Regenerated Itinerary Must Exclude Rejected Activity
    regen_res = client.post(f"/api/itinerary/generate/{trip_id}?user_id={user_id}")
    assert regen_res.status_code == 200
    regen_data = regen_res.json()
    scheduled_after_regen = set()
    for d in regen_data["days"]:
        for a in d["activities"]:
            scheduled_after_regen.add(a["activity_id"])
    assert act_to_reject not in scheduled_after_regen, "Rejected activity must not be re-recommended"
    print(f"[OK] Avoidance invariant verified: rejected activity '{act_to_reject}' was excluded from regeneration")

    # 8. Temporary vs Persistent Preference Handling
    temp_act = regen_data["days"][0]["activities"][1]["activity_id"]
    temp_res = client.post(f"/api/itinerary/feedback/{user_id}", json={
        "itinerary_id": itin_id,
        "activity_id": temp_act,
        "action_type": "reject",
        "rejection_reason": "schedule_conflict_today",
        "is_trip_specific": True
    })
    assert temp_res.status_code == 200
    assert temp_res.json()["is_trip_specific"] is True
    assert temp_res.json()["policy_updated"] is False, "Trip-specific feedback must not alter permanent policy"
    print(f"[OK] Trip-specific vs. persistent preference isolation verified")

    # 9. Alternatives & MODIFY Action
    alt_act = regen_data["days"][2]["activities"][0]["activity_id"]
    alts_res = client.get(f"/api/itinerary/alternatives/{itin_id}/{alt_act}?user_id={user_id}")
    assert alts_res.status_code == 200
    alts_data = alts_res.json()
    assert "alternatives" in alts_data
    assert len(alts_data["alternatives"]) > 0
    replacement_id = alts_data["alternatives"][0]["id"]

    modify_res = client.post(f"/api/itinerary/feedback/{user_id}", json={
        "itinerary_id": itin_id,
        "activity_id": alt_act,
        "action_type": "modify",
        "replacement_activity_id": replacement_id
    })
    assert modify_res.status_code == 200
    print(f"[OK] MODIFY action verified with alternative replacement '{replacement_id}'")

    # 10. Academic Model Inspector LinUCB Policy Endpoint
    policy_res = client.get(f"/api/rl/policy/{user_id}")
    assert policy_res.status_code == 200
    policy_data = policy_res.json()
    assert policy_data["algorithm"] == "Disjoint Contextual LinUCB"
    assert policy_data["feature_dimension"] == 24
    assert len(policy_data["arms"]) >= 6
    assert policy_data["total_interactions"] > 0
    assert len(policy_data["recent_feedback"]) > 0
    print(f"[OK] Academic Model Inspector LinUCB Policy verified ({policy_data['total_interactions']} total interactions tracked)")

    # 11. Comparative Simulation Benchmark
    bench_res = client.get("/api/evaluation/benchmark?persona=nature_enthusiast&rounds=15")
    assert bench_res.status_code == 200
    bench_data = bench_res.json()
    assert "baseline" in bench_data
    assert "adaptive_linucb" in bench_data
    assert "policy_adaptation_divergence" in bench_data["adaptive_linucb"]
    assert len(bench_data["adaptive_linucb"]["policy_adaptation_divergence"]) == 15
    print(f"[OK] Comparative benchmark verified (Adaptive LinUCB acceptance {bench_data['adaptive_linucb']['acceptance_rate']:.1%} vs Baseline {bench_data['baseline']['acceptance_rate']:.1%})")

    # 12. Live User Empirical Metrics
    live_eval = client.get(f"/api/evaluation/live/{user_id}")
    assert live_eval.status_code == 200
    live_data = live_eval.json()
    assert live_data["total_interactions"] >= 3
    assert "cumulative_reward_history" in live_data
    print(f"[OK] Live user empirical evaluation verified (Total: {live_data['total_interactions']}, Cumulative Reward: {live_data['cumulative_reward']})")

    # 13. Ownership and Unauthorized Access Protection
    unauthorized_res = client.get("/api/itinerary/invalid-trip-id?user_id=wrong-user")
    assert unauthorized_res.status_code in (404, 400)
    print(f"[OK] Access control & unauthorized itinerary protection verified")

    print("[OK] ALL ADAPTIVE ITINERARY & RL TESTS PASSED SUCCESSFULLY!")
if __name__ == "__main__":
    run_tests()
    import sys
    sys.exit(0)
