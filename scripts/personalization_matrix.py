"""Generate Personalization Coverage Matrix for Destination Ranking & LinUCB.

Evaluates how user profile parameters (interests, climate, crowd tolerance, budget,
companions, pace, avoidances, past feedback) directly affect recommendations across
diverse simulated traveler personas.

Outputs: docs/personalization_matrix.md
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.modules.ranking import get_rankings
from app.database import get_connection, init_db


PERSONAS = [
    {
        "id": "persona_nature_hiker",
        "name": "Arjun - Nature & Adventure Solo Trekker",
        "profile": {
            "travel_goals": ["nature", "adventure"],
            "place_interests": ["mountains", "hiking"],
            "preferred_climate": "cool",
            "budget_tier": "budget",
            "companions": "alone",
            "pace": "packed",
            "crowd_tolerance": 0.2,  # Low tolerance
            "avoidances": ["avoid_crowds"]
        },
        "query_params": {"budget": 60.0, "date": "2026-11-15"}
    },
    {
        "id": "persona_heritage_family",
        "name": "Meera - Culture & History Family Traveler",
        "profile": {
            "travel_goals": ["culture", "history"],
            "place_interests": ["historic", "photography"],
            "preferred_climate": "mild",
            "budget_tier": "balanced",
            "companions": "family",
            "pace": "relaxed",
            "crowd_tolerance": 0.6,
            "avoidances": []
        },
        "query_params": {"budget": 180.0, "date": "2026-11-15"}
    },
    {
        "id": "persona_luxury_wellness",
        "name": "Kabir - Luxury Relaxation & Scenic Escapist",
        "profile": {
            "travel_goals": ["relaxation", "wellness"],
            "place_interests": ["beaches", "scenic"],
            "preferred_climate": "warm",
            "budget_tier": "luxury",
            "companions": "partner",
            "pace": "relaxed",
            "crowd_tolerance": 0.4,
            "avoidances": ["avoid_walking"]
        },
        "query_params": {"budget": 350.0, "date": "2026-11-15"}
    },
    {
        "id": "persona_budget_foodie",
        "name": "Riya - Urban Food & Market Explorer",
        "profile": {
            "travel_goals": ["food", "shopping"],
            "place_interests": ["cafes", "markets"],
            "preferred_climate": "mild",
            "budget_tier": "budget",
            "companions": "friends",
            "pace": "balanced",
            "crowd_tolerance": 0.8,  # Loves bustling spots
            "avoidances": ["avoid_heat"]
        },
        "query_params": {"budget": 50.0, "date": "2026-11-15"}
    }
]


def setup_persona_in_db(persona: Dict[str, Any]) -> str:
    """Insert persona profile into temporary or active DB."""
    uid = persona["id"]
    prof = persona["profile"]
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM traveller_profiles WHERE user_id = ?", (uid,))
        cursor.execute("DELETE FROM users WHERE id = ?", (uid,))
        cursor.execute(
            "INSERT INTO users (id, auth_provider, identifier, display_name) VALUES (?, 'email', ?, ?)",
            (uid, f"{uid}@example.com", persona["name"])
        )
        cursor.execute(
            """INSERT INTO traveller_profiles (
                user_id, interests, companions, budget_tier, pace, crowd_tolerance,
                preferred_climate, raw_answers_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid,
                json.dumps(prof.get("travel_goals", []) + prof.get("place_interests", [])),
                prof["companions"],
                prof["budget_tier"],
                0.8 if prof["pace"] == "packed" else (0.2 if prof["pace"] == "relaxed" else 0.5),
                prof["crowd_tolerance"],
                prof["preferred_climate"],
                json.dumps(prof)
            )
        )
        conn.commit()
    return uid


def generate_personalization_matrix():
    print("Generating Personalization Coverage Matrix across traveler personas...")
    init_db()

    docs_dir = root_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for p in PERSONAS:
        uid = setup_persona_in_db(p)
        qp = p["query_params"]

        ranking_res = get_rankings(
            user_id=uid,
            date=qp.get("date"),
            budget=qp.get("budget"),
            limit=3
        )

        top_1 = ranking_res["overall_ranking"][0] if ranking_res["overall_ranking"] else None
        top_best_you = ranking_res["best_for_you"][0] if ranking_res["best_for_you"] else None
        top_feasible = ranking_res["best_feasible"][0] if ranking_res["best_feasible"] else None
        excluded = [e["name"] for e in ranking_res.get("excluded", [])]

        results.append({
            "persona": p["name"],
            "preferences": p["profile"],
            "budget_cap": f"${qp.get('budget', 0)}/day",
            "top_overall": f"{top_1['name']} ({top_1['total_score']} pts)" if top_1 else "None",
            "top_for_you": f"{top_best_you['name']} ({top_best_you['breakdown']['interest']['value']} match)" if top_best_you else "None",
            "top_feasible": f"{top_feasible['name']} ({top_feasible['breakdown']['feasibility']['value']})" if top_feasible else "None",
            "excluded_count": len(excluded),
            "excluded_destinations": ", ".join(excluded[:3]) + ("..." if len(excluded) > 3 else "") if excluded else "None"
        })

    # Build Markdown Document
    md_lines = [
        "# Personalization & Constraint Coverage Matrix",
        "",
        f"*Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        "*Evaluation Target: Destination Ranking (`app/modules/ranking.py`) and LinUCB Policy Personalization*",
        "",
        "## 1. Persona Recommendations Comparison Table",
        "",
        "| Persona | Stated Profile & Budget | Top Overall Ranked | Best For You (Interest) | Best Feasible | Excluded by Hard Filter |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in results:
        p_desc = f"Goals: {', '.join(r['preferences']['travel_goals'])}, Tier: {r['preferences']['budget_tier']}, Crowd Tol: {r['preferences']['crowd_tolerance']}"
        md_lines.append(
            f"| **{r['persona']}** | {p_desc} (Cap: {r['budget_cap']}) | {r['top_overall']} | {r['top_for_you']} | {r['top_feasible']} | {r['excluded_destinations']} |"
        )

    md_lines.extend([
        "",
        "## 2. Parameter Mapping & Three-Layer Architecture",
        "",
        "| Profile Parameter | Extraction Location | Ranking Layer Impact (25% Interest, 20% Season, 15% Pop, 15% Feas, 15% Feedback) | LinUCB Bandit Impact (Arm Recommendation) | Scheduling & Plan Layer Impact |",
        "| :--- | :--- | :--- | :--- | :--- |",
        "| **Travel Goals / Interests** | `raw_answers_json['travel_goals']` & `raw_answers_json['place_interests']` | Drives **Interest Match (25%)** via normalized tag overlap count (min(1.0, count/3.0)) | Primary feature in 24-dim context vector; maps directly to 7 arm affinities | Guides POI category selection within scheduled daily slots |",
        "| **Climate Preference** | `traveller_profiles.preferred_climate` | Drives **Season Match (20%)** bonus (+0.1) when destination climate aligns | Environmental context feature in bandit | Weather forecast advisory warning in live module |",
        "| **Crowd Tolerance** | `traveller_profiles.crowd_tolerance` (0.0 to 1.0) | Modulates **Popularity (15%)**: Low tolerance flips high-crowd bonus to a penalty | Crowd level feature in context vector (0.2 / 0.5 / 0.8) | Off-peak / peak time advice in POI cards |",
        "| **Budget Tier & Cap** | `budget_tier` & API query param `budget` | Low end > cap triggers **Hard Constraint Exclusion Filter**; tier delta drives Feasibility | Activity cost tier feature (budget / balanced / luxury) | Budget tier guides category spend targets (assumptions.py defines 35/25/20/10/5/5 shares as specification) |",
        "| **Companions** | `companions` ('alone', 'partner', 'friends', 'family') | Feasibility companion compatibility scoring | Context feature influencing activity pacing | Party context passed to booking & POI recommendations |",
        "| **Pace** | `pace` ('relaxed', 'balanced', 'packed') | Feasibility style matching (active vs relaxed) | Slot density preference | Determines daily activity count template (2 relaxed, 3 balanced, 4 active in timed_itinerary.py) |",
        "| **Avoidances** | `raw_answers_json['avoidances']` | Named destination = **Hard Exclusion Filter**; 'avoid_crowds' / 'avoid_heat' = soft score penalty | Negative feature mask on conflicting arms | Filter in candidate POI pool |",
        "| **Past Feedback** | `shortlisted_destinations`, `past_trips`, `core_trip_feedback` | Drives **Feedback Match (15%)**: Shortlist = 1.0; post-trip rating = `(rating-1)/4` | Immediate LinUCB policy weight update `(A, b)` with reward `[-1.0, +1.0]` | Future itinerary rotation |",
        "| **Dietary / Allergens** | `raw_answers_json['dietary']` | Non-verifiable venue warning label: 'cannot verify dietary/allergens, check with venue' | None (never used as a fake filter on live places) | Venue check reminder |",
        "",
        "## AI assistance and external libraries/APIs used",
        "- Generated by Person C under SHARED specifications",
        "- Uses SQLite and Pydantic schemas",
    ])

    out_file = docs_dir / "personalization_matrix.md"
    out_file.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[OK] Successfully wrote personalization matrix to {out_file.name}")


if __name__ == "__main__":
    generate_personalization_matrix()
