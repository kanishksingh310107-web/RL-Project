# Seasonal and Multi-Criteria Ranking Module
# Owner: Person C
# Evaluates curated destinations using 6 transparent, configurable components.

import re
import datetime
from typing import Dict, Any, List, Optional, Set
from fastapi import APIRouter, HTTPException, Query

from app.database import get_connection
from app.modules.common import get_user_context
from app.recommender import DESTINATIONS

MODULE = {
    "id": "ranking",
    "title": "Ranking",
    "icon": "fa-ranking-star",
    "owner": "C"
}

router = APIRouter(prefix="/api/ranking", tags=["ranking"])

# Default scoring weights (Assumed baseline, sum = 1.0)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "interest": 0.25,
    "season": 0.20,
    "popularity": 0.15,
    "feasibility": 0.15,
    "live": 0.10,
    "feedback": 0.15
}

# Vocabulary mapping: user answers -> catalogue destination tags
GOAL_MAPPING: Dict[str, str] = {
    "nature": "nature",
    "experiencing_nature": "nature",
    "adventure": "adventure",
    "relaxation": "relaxation",
    "history": "history",
    "historic": "history",
    "history_culture": "history",
    "culture": "culture",
    "food": "food",
    "trying_new_foods": "food",
    "food_dining": "food",
    "photography": "photography",
    "sightseeing": "photography",
    "beaches": "beaches",
    "mountains": "mountains",
    "shopping": "shopping",
    "wellness": "wellness",
    "cafes": "cafes",
    "hidden_gems": "nature",
    "nightlife": "nightlife",
    "scenic_landscapes": "nature"
}

# Month names to integers 1..12
MONTH_MAP: Dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}

STRICT_MONTH_REGEX = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE
)


def init_tables(conn):
    """Initialise module-specific tables (none required, placeholder for CONTRACT compliance)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ranking_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            requested_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def parse_cost_range(cost_str: str) -> Optional[tuple[int, int]]:
    """Extract low and high daily USD cost using regex."""
    m = re.search(r"\$(\d+)\s*-\s*\$?(\d+)", cost_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def parse_season_months(best_seasons: List[str]) -> Set[int]:
    """Parse active month numbers from catalogue best_seasons strings."""
    active_months: Set[int] = set()

    for season_text in best_seasons:
        matches = STRICT_MONTH_REGEX.findall(season_text)
        if not matches:
            continue

        month_nums = [MONTH_MAP[m.lower()] for m in matches]

        # If paired (start - end), fill range including year wrap-around
        if len(month_nums) >= 2:
            for i in range(0, len(month_nums) - 1, 2):
                start_m = month_nums[i]
                end_m = month_nums[i + 1]
                if start_m <= end_m:
                    for m in range(start_m, end_m + 1):
                        active_months.add(m)
                else:
                    # Wraps around new year (e.g., Nov to Feb)
                    for m in range(start_m, 13):
                        active_months.add(m)
                    for m in range(1, end_m + 1):
                        active_months.add(m)
        elif len(month_nums) == 1:
            active_months.add(month_nums[0])

    return active_months


def calculate_season_score(best_seasons: List[str], target_month: int) -> float:
    """Score season suitability: 1.0 (in season), 0.6 (1 month away), 0.3 (2 months), 0.0 (3+)."""
    months = parse_season_months(best_seasons)
    if not months:
        return 0.5

    if target_month in months:
        return 1.0

    # Circular distance on a 12-month clock
    min_dist = min(
        min(abs(target_month - m), 12 - abs(target_month - m))
        for m in months
    )

    if min_dist == 1:
        return 0.6
    elif min_dist == 2:
        return 0.3
    else:
        return 0.0


def calculate_popularity_score(dest: Dict[str, Any]) -> float:
    """Static popularity estimate based on crowd level and is_trending flag."""
    crowd = dest.get("crowd_level", "moderate").lower()
    base = 0.7
    if crowd == "low":
        base = 0.4
    elif crowd == "high":
        base = 0.9

    if dest.get("is_trending", False):
        return min(1.0, base + 0.1)
    return base


def calculate_feasibility_score(
    dest: Dict[str, Any],
    budget_cap: Optional[float],
    basic_profile: Optional[Dict[str, Any]]
) -> tuple[float, str]:
    """Feasibility = average of budget part and companions part."""
    # 1. Budget part
    cost_range = parse_cost_range(dest.get("estimated_cost", ""))
    if budget_cap is not None and cost_range:
        _, high = cost_range
        budget_score = 1.0 if high <= budget_cap else 0.5
        budget_reason = f"Budget cap ${budget_cap:.0f}: high end ${high} -> {budget_score}"
    elif basic_profile:
        user_tier = str(basic_profile.get("budget_tier", "balanced")).lower()
        dest_tier = str(dest.get("budget_tier", "balanced")).lower()

        tier_order = {"budget": 1, "balanced": 2, "luxury": 3}
        u_val = tier_order.get("budget" if "budget" in user_tier else "luxury" if "luxury" in user_tier else "balanced", 2)
        d_val = tier_order.get(dest_tier, 2)
        diff = abs(u_val - d_val)

        if diff == 0:
            budget_score = 1.0
        elif diff == 1:
            budget_score = 0.6
        else:
            budget_score = 0.3
        budget_reason = f"Tier match ({user_tier} vs {dest_tier}) -> {budget_score}"
    else:
        budget_score = 0.5
        budget_reason = "No budget cap or profile -> neutral 0.5"

    # 2. Companions part
    user_comp = str(basic_profile.get("companions", "")).lower() if basic_profile else ""
    if user_comp == "solo":
        user_comp = "alone"

    suitable = [str(c).lower() for c in dest.get("suitable_companions", [])]
    if user_comp:
        if user_comp in suitable:
            comp_score = 1.0
            comp_reason = f"Companion '{user_comp}' is suitable -> 1.0"
        else:
            comp_score = 0.4
            comp_reason = f"Companion '{user_comp}' not in suitable list -> 0.4"
    else:
        comp_score = 0.5
        comp_reason = "Companions unspecified -> neutral 0.5"

    score = round((budget_score + comp_score) / 2.0, 2)
    return score, f"{budget_reason}; {comp_reason}"


def get_user_feedback_score(user_id: str, dest_id: str, dest_name: str) -> tuple[float, str]:
    """Feedback: shortlisted = 1.0; past trip rating = (r-1)/4; else neutral 0.5."""
    with get_connection() as conn:
        shortlisted = conn.execute(
            "SELECT 1 FROM shortlisted_destinations WHERE user_id = ? AND destination_id = ?",
            (user_id, dest_id)
        ).fetchone()
        if shortlisted:
            return 1.0, "Shortlisted by user"

        past = conn.execute(
            "SELECT rating FROM past_trips WHERE user_id = ? AND (LOWER(destination) = ? OR LOWER(destination) = ?)",
            (user_id, dest_id.lower(), dest_name.lower())
        ).fetchone()
        if past and past["rating"] is not None:
            r = float(past["rating"])
            val = max(0.0, min(1.0, (r - 1.0) / 4.0))
            return val, f"Past trip rating {r:.1f}/5 -> {val:.2f}"

    return 0.5, "No shortlist or past trip feedback - neutral placeholder"


def extract_user_interests(basic_profile: Optional[Dict[str, Any]]) -> Set[str]:
    """Read user interests from basic['interests'], raw_answers_json['travel_goals'], and place_interests."""
    if not basic_profile:
        return set()

    interests = set()

    # 1. basic['interests']
    raw_interests = basic_profile.get("interests", [])
    if isinstance(raw_interests, list):
        for item in raw_interests:
            interests.add(str(item).lower())
    elif isinstance(raw_interests, str) and raw_interests:
        interests.add(raw_interests.lower())

    # 2. raw_answers_json
    raw_answers = basic_profile.get("raw_answers_json", {})
    if isinstance(raw_answers, dict):
        for goal in raw_answers.get("travel_goals", []):
            interests.add(str(goal).lower())
        for place in raw_answers.get("place_interests", []):
            interests.add(str(place).lower())

    # Map to normalized catalogue tags
    normalized = set()
    for item in interests:
        normalized.add(item)
        if item in GOAL_MAPPING:
            normalized.add(GOAL_MAPPING[item])

    return normalized


@router.get("/{user_id}")
def get_rankings(
    user_id: str,
    date: Optional[str] = Query(None, alias="date"),
    budget: Optional[float] = Query(None, description="Max USD per day"),
    limit: int = Query(5, ge=1, description="Max items per list"),
    w_interest: Optional[float] = Query(None),
    w_season: Optional[float] = Query(None),
    w_popularity: Optional[float] = Query(None),
    w_feasibility: Optional[float] = Query(None),
    w_live: Optional[float] = Query(None),
    w_feedback: Optional[float] = Query(None),
    closed: Optional[str] = Query(None, description="Comma-separated destination IDs that are closed"),
    advisory: Optional[str] = Query(None, description="Comma-separated destination IDs under travel advisory")
):
    """Rank destinations with 6 components and strict constraint filtering."""
    # 1. Date validation
    if date:
        try:
            target_dt = datetime.datetime.strptime(date, "%Y-%m-%d").date()
            target_month = target_dt.month
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")
    else:
        target_dt = datetime.date.today()
        target_month = target_dt.month

    # 2. Weights setup and normalization
    weights = dict(DEFAULT_WEIGHTS)
    overrides = {
        "interest": w_interest,
        "season": w_season,
        "popularity": w_popularity,
        "feasibility": w_feasibility,
        "live": w_live,
        "feedback": w_feedback
    }
    for k, val in overrides.items():
        if val is not None:
            if val < 0:
                raise HTTPException(status_code=400, detail=f"Weight for '{k}' cannot be negative")
            weights[k] = val

    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise HTTPException(status_code=400, detail="Sum of weights must be greater than zero")

    normalized_weights = {k: v / total_weight for k, v in weights.items()}

    # 3. Parse hard constraint flags
    closed_ids = {c.strip() for c in closed.split(",")} if closed else set()
    advisory_ids = {a.strip() for a in advisory.split(",")} if advisory else set()

    # 4. Fetch user context
    ctx = get_user_context(user_id)
    basic_profile = ctx.get("basic")
    has_profile = basic_profile is not None
    user_tags = extract_user_interests(basic_profile)

    # 5. Filter and score destinations
    ranked_items = []
    excluded_items = []

    for dest in DESTINATIONS:
        dest_id = dest["id"]
        dest_name = dest["name"]

        # Filter A: Closed flag
        if dest_id in closed_ids:
            excluded_items.append({
                "id": dest_id,
                "name": dest_name,
                "reason": "Destination manually marked as closed"
            })
            continue

        # Filter B: Advisory flag
        if dest_id in advisory_ids:
            excluded_items.append({
                "id": dest_id,
                "name": dest_name,
                "reason": "Travel advisory in effect"
            })
            continue

        # Filter C: Budget cap (low end of daily cost > cap)
        cost_range = parse_cost_range(dest.get("estimated_cost", ""))
        if budget is not None and cost_range:
            low_cost, high_cost = cost_range
            if low_cost > budget:
                excluded_items.append({
                    "id": dest_id,
                    "name": dest_name,
                    "reason": f"Low end of daily cost (${low_cost}) exceeds budget cap (${budget:.0f}/day)"
                })
                continue

        # --- Compute 6 Component Scores (0.0 to 1.0) ---

        # 1. Interest Match
        dest_tags = {str(t).lower() for t in dest.get("tags", [])}
        if has_profile:
            shared = user_tags.intersection(dest_tags)
            if shared:
                val_interest = min(1.0, len(shared) / 3.0)
                note_interest = f"Shared tags: {', '.join(sorted(shared))}"
            else:
                val_interest = 0.0
                note_interest = "No overlapping interest tags"
        else:
            val_interest = 0.5
            note_interest = "No profile - neutral interest placeholder"

        # 2. Season Suitability
        val_season = calculate_season_score(dest.get("best_seasons", []), target_month)
        note_season = f"Target month {target_month} vs seasons: {', '.join(dest.get('best_seasons', []))}"

        # 3. Popularity (Static catalogue estimate)
        val_popularity = calculate_popularity_score(dest)
        note_popularity = f"Static estimate (crowd: {dest.get('crowd_level')}, trending: {dest.get('is_trending')})"

        # 4. Feasibility
        val_feasibility, note_feasibility = calculate_feasibility_score(dest, budget, basic_profile)

        # 5. Live Conditions (No live feed)
        val_live = 0.5
        note_live = "no live feed - neutral placeholder"

        # 6. Past Feedback
        val_feedback, note_feedback = get_user_feedback_score(user_id, dest_id, dest_name)

        # Calculate breakdown contributions (points)
        components = {
            "interest": (val_interest, note_interest),
            "season": (val_season, note_season),
            "popularity": (val_popularity, note_popularity),
            "feasibility": (val_feasibility, note_feasibility),
            "live": (val_live, note_live),
            "feedback": (val_feedback, note_feedback)
        }

        breakdown = {}
        total_points = 0.0
        for comp_name, (comp_val, comp_note) in components.items():
            w = normalized_weights[comp_name]
            points = round(comp_val * w * 100.0, 2)
            total_points += points
            breakdown[comp_name] = {
                "value": round(comp_val, 2),
                "weight": round(w, 4),
                "contribution": points,
                "note": comp_note
            }

        total_score = round(total_points, 2)

        item_data = {
            "id": dest_id,
            "name": dest_name,
            "country": dest.get("country", ""),
            "tagline": dest.get("tagline", ""),
            "image_url": dest.get("image_url", ""),
            "estimated_cost": dest.get("estimated_cost", ""),
            "best_seasons": dest.get("best_seasons", []),
            "is_trending": dest.get("is_trending", False),
            "crowd_level": dest.get("crowd_level", "moderate"),
            "total_score": total_score,
            "breakdown": breakdown
        }
        ranked_items.append(item_data)

    # Sort items for 4 specialized lists + overall ranking
    overall_ranking = sorted(ranked_items, key=lambda x: x["total_score"], reverse=True)

    trending_now = sorted(
        [it for it in ranked_items if it["is_trending"]],
        key=lambda x: (x["breakdown"]["popularity"]["value"], x["total_score"]),
        reverse=True
    )[:limit]

    best_this_season = sorted(
        ranked_items,
        key=lambda x: (x["breakdown"]["season"]["value"], x["total_score"]),
        reverse=True
    )[:limit]

    best_for_you = sorted(
        ranked_items,
        key=lambda x: (x["breakdown"]["interest"]["value"], x["total_score"]),
        reverse=True
    )[:limit]

    best_feasible = sorted(
        ranked_items,
        key=lambda x: (x["breakdown"]["feasibility"]["value"], x["total_score"]),
        reverse=True
    )[:limit]

    return {
        "user_id": user_id,
        "has_profile": has_profile,
        "date": target_dt.isoformat(),
        "budget_cap": budget,
        "weights": {k: round(v, 4) for k, v in normalized_weights.items()},
        "weights_note": "ASSUMPTIONS - weights are subjective defaults, overrideable via query params",
        "data_freshness": {
            "popularity": "Static estimate from catalogue metadata (crowd_level + is_trending) as of 2026-11-02",
            "trending": "Static is_trending flag from catalogue, not live trend analysis",
            "season": "Calculated from best_seasons month parsing relative to requested date",
            "live_conditions": "Absent (no live feed exists, neutral 0.5 placeholder)",
            "manual_flags": "User-supplied closed and advisory query parameters",
            "label": "SIMULATED / STATIC DATA - catalogue is sample data"
        },
        "overall_ranking": overall_ranking[:limit],
        "trending_now": trending_now,
        "best_this_season": best_this_season,
        "best_for_you": best_for_you,
        "best_feasible": best_feasible,
        "excluded": excluded_items
    }
