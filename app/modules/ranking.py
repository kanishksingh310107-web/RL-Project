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
from app.core.assumptions import (
    RANKING_DEFAULT_WEIGHTS,
    INR_TO_USD_RATE,
)
from app.core.profile import load_profile

MODULE = {
    "id": "ranking",
    "title": "Ranking",
    "icon": "fa-ranking-star",
    "owner": "C"
}

router = APIRouter(prefix="/api/ranking", tags=["ranking"])

# Default scoring weights (Assumed baseline, sum = 1.0)
DEFAULT_WEIGHTS: Dict[str, float] = dict(RANKING_DEFAULT_WEIGHTS)

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
    "scenic_landscapes": "nature",
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
    "dec": 12, "december": 12,
}

STRICT_MONTH_REGEX = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE
)


def init_tables(conn):
    """Initialise module-specific tables (ranking_audit_log for CONTRACT compliance)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ranking_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            requested_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def parse_cost_range(cost_str: str) -> Optional[tuple[int, int]]:
    """Extract low and high daily USD cost using regex, handling $, ₹, and comma separators."""
    if not cost_str:
        return None

    is_inr = "₹" in cost_str or "rs" in cost_str.lower()
    # Match range e.g. "$100 - $200" or "₹2,500 - ₹4,500"
    m = re.search(r"[\$₹Rs\.]*\s*([\d,]+)\s*-\s*[\$₹Rs\.]*\s*([\d,]+)", cost_str, re.IGNORECASE)
    if m:
        try:
            low = int(m.group(1).replace(",", ""))
            high = int(m.group(2).replace(",", ""))
            if is_inr:
                low = int(round(low * INR_TO_USD_RATE))
                high = int(round(high * INR_TO_USD_RATE))
            return low, high
        except ValueError:
            return None

    # Single number fallback
    m_single = re.search(r"[\$₹]\s*([\d,]+)", cost_str)
    if m_single:
        try:
            val = int(m_single.group(1).replace(",", ""))
            if is_inr:
                val = int(round(val * INR_TO_USD_RATE))
            return val, val
        except ValueError:
            return None

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


def calculate_popularity_score(dest: Dict[str, Any], crowd_tolerance: Any = "moderate") -> float:
    """Popularity score incorporating crowd level, trending flag, and user crowd tolerance."""
    crowd = dest.get("crowd_level", "moderate").lower()
    
    if isinstance(crowd_tolerance, (int, float)):
        if crowd_tolerance < 0.35:
            ct = "low"
        elif crowd_tolerance > 0.65:
            ct = "high"
        else:
            ct = "moderate"
    else:
        ct = str(crowd_tolerance or "moderate").lower()

    if ct == "low":
        # Dislikes crowds: low crowd is preferred
        base = 0.9 if crowd == "low" else (0.6 if crowd == "moderate" else 0.3)
    elif ct == "high":
        # Enjoys crowds / bustling destinations
        base = 0.95 if crowd == "high" else (0.7 if crowd == "moderate" else 0.4)
    else:
        # Default / moderate
        base = 0.4 if crowd == "low" else (0.7 if crowd == "moderate" else 0.9)

    if dest.get("is_trending", False):
        return min(1.0, round(base + 0.1, 2))
    return round(base, 2)


def calculate_feasibility_score(
    dest: Dict[str, Any],
    budget_cap: Optional[float],
    profile: Optional[Dict[str, Any]]
) -> tuple[float, str]:
    """Feasibility = composite of budget match, companion match, and pace match."""
    # 1. Budget part
    cost_range = parse_cost_range(dest.get("estimated_cost", ""))
    if budget_cap is not None and cost_range:
        low, high = cost_range
        if high <= budget_cap:
            budget_score = 1.0
        elif low <= budget_cap:
            budget_score = 0.65
        else:
            budget_score = 0.3
        budget_reason = f"Budget cap ${budget_cap:.0f}: est ${low}-${high} -> {budget_score}"
    elif profile:
        user_tier = str(profile.get("budget_tier", "balanced")).lower()
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
    user_comp = str(profile.get("companions", "")).lower() if profile else ""
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

    # 3. Pace / style match
    user_pace = str(profile.get("pace", "balanced")).lower() if profile else "balanced"
    dest_style = str(dest.get("style", "balanced")).lower()
    if (user_pace == "packed" and dest_style in ["active", "fast"]) or \
       (user_pace == "relaxed" and dest_style in ["relaxed", "slow"]) or \
       (user_pace == "balanced"):
        pace_score = 1.0
    else:
        pace_score = 0.6

    score = round((budget_score * 0.5) + (comp_score * 0.3) + (pace_score * 0.2), 2)
    return score, f"{budget_reason}; {comp_reason}"


def get_user_feedback_score(user_id: str, dest_id: str, dest_name: str) -> tuple[float, str]:
    """Feedback: shortlisted = 1.0; core_trip_feedback or past trip rating = (r-1)/4; else neutral 0.5."""
    # 1. Shortlist check
    with get_connection() as conn:
        shortlisted = conn.execute(
            "SELECT 1 FROM shortlisted_destinations WHERE user_id = ? AND destination_id = ?",
            (user_id, dest_id)
        ).fetchone()
        if shortlisted:
            return 1.0, "Shortlisted by user"

    # 2. Check core_trip_feedback
    try:
        from app.core.stores import load_trip_feedback
        with get_connection() as conn:
            user_trips = conn.execute(
                "SELECT id FROM trips WHERE user_id = ? AND (LOWER(destination_id) = ? OR LOWER(destination_name) = ?)",
                (user_id, dest_id.lower(), dest_name.lower())
            ).fetchall()
            for t in user_trips:
                feedbacks = load_trip_feedback(t["id"])
                if feedbacks:
                    ratings = [f.get("rating") for f in feedbacks if f.get("rating") is not None]
                    if ratings:
                        avg_r = sum(ratings) / len(ratings)
                        val = max(0.0, min(1.0, (avg_r - 1.0) / 4.0))
                        return round(val, 2), f"Post-trip feedback rating {avg_r:.1f}/5 -> {val:.2f}"
    except Exception:
        pass

    # 3. Check legacy past_trips table
    with get_connection() as conn:
        past = conn.execute(
            "SELECT rating FROM past_trips WHERE user_id = ? AND (LOWER(destination) = ? OR LOWER(destination) = ?)",
            (user_id, dest_id.lower(), dest_name.lower())
        ).fetchone()
        if past and past["rating"] is not None:
            r = float(past["rating"])
            val = max(0.0, min(1.0, (r - 1.0) / 4.0))
            return round(val, 2), f"Past trip rating {r:.1f}/5 -> {val:.2f}"

    return 0.5, "No shortlist or past trip feedback - neutral placeholder"


def extract_user_interests(profile: Optional[Dict[str, Any]]) -> Set[str]:
    """Read user interests from normalized profile interests and raw answers."""
    if not profile:
        return set()

    interests = set()

    raw_interests = profile.get("interests", [])
    if isinstance(raw_interests, list):
        for item in raw_interests:
            interests.add(str(item).lower())
    elif isinstance(raw_interests, str) and raw_interests:
        interests.add(raw_interests.lower())

    # Raw questionnaire answers if present
    raw_answers = profile.get("raw_answers", {}) or profile.get("raw_answers_json", {})
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


# Static routes MUST be registered before dynamic routes like /{user_id}
@router.get("/india/search")
def search_india_destination(
    q: str = Query(..., description="Indian city or destination query"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Target month 1-12")
):
    """Search any Indian place/city and return live climate seasonality and tourist infrastructure density."""
    from app.providers.geo import geocode_india, get_places_by_category
    from app.providers.weather import get_seasonality_score, get_historical_climate
    from app.providers.guard import reset_request_counter

    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    reset_request_counter()
    geo = geocode_india(q.strip())
    if not geo:
        raise HTTPException(status_code=404, detail=f"Could not find coordinates for Indian destination '{q}'")

    lat, lon = geo["lat"], geo["lon"]
    target_month = month or datetime.date.today().month

    # Seasonality from Open-Meteo historical climate
    season_score = get_seasonality_score(lat, lon, target_month)
    climate_data = get_historical_climate(lat, lon, target_month)

    # Tourist infrastructure & density proxy from Geoapify
    reset_request_counter()
    attractions = get_places_by_category(lat, lon, "culture_history", limit=5)
    nature = get_places_by_category(lat, lon, "nature_outdoors", limit=5)
    dining = get_places_by_category(lat, lon, "food_dining", limit=5)

    total_pois = len(attractions) + len(nature) + len(dining)
    density_score = min(1.0, round(total_pois / 12.0, 2))

    return {
        "query": q.strip(),
        "geocoding": geo,
        "target_month": target_month,
        "season_score": round(season_score, 2),
        "climate_summary": {
            "mean_temp_c": climate_data.get("mean_temp_c"),
            "rainfall_mm": climate_data.get("total_rain_mm") or climate_data.get("rainfall_mm"),
            "is_comfortable": climate_data.get("is_comfortable", True),
        },
        "popularity_proxy": {
            "density_score": density_score,
            "nearby_attractions_count": len(attractions),
            "nearby_nature_count": len(nature),
            "nearby_dining_count": len(dining),
            "total_sampled_pois": total_pois,
            "note": "Infrastructure density proxy derived from Geoapify nearby points of interest"
        },
        "provenance": {
            "geocoding": "Powered by Geoapify | © OpenStreetMap contributors",
            "climate": "Weather data by Open-Meteo.com (CC BY 4.0)",
            "is_live": True
        }
    }


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
    """Rank destinations with 6 components, deep personalization, and strict constraint filtering."""
    # 1. Date validation
    if isinstance(date, str) and date:
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
        if isinstance(val, (int, float)):
            if val < 0:
                raise HTTPException(status_code=400, detail=f"Weight for '{k}' cannot be negative")
            weights[k] = float(val)

    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise HTTPException(status_code=400, detail="Sum of weights must be greater than zero")

    normalized_weights = {k: v / total_weight for k, v in weights.items()}

    # 3. Parse hard constraint flags
    closed_ids = {c.strip() for c in closed.split(",")} if isinstance(closed, str) and closed else set()
    advisory_ids = {a.strip() for a in advisory.split(",")} if isinstance(advisory, str) and advisory else set()
    budget_val = budget if isinstance(budget, (int, float)) else None
    limit_val = limit if isinstance(limit, int) else 5

    # 4. Fetch unified user profile using core profile loader
    profile = load_profile(user_id)
    # Check if a non-empty user actually exists in the database
    with get_connection() as conn:
        user_row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        has_profile = user_row is not None and bool(profile.get("interests") or profile.get("raw_answers"))

    user_tags = extract_user_interests(profile)
    user_avoidances = profile.get("avoidances", [])
    user_crowd_tol = profile.get("crowd_tolerance", "moderate")
    user_preferred_climate = profile.get("preferred_climate", "")

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

        # Filter C: Explicit destination avoidance
        if dest_id in user_avoidances or any(a.lower() in dest_name.lower() for a in user_avoidances if len(a) > 3):
            excluded_items.append({
                "id": dest_id,
                "name": dest_name,
                "reason": "Destination in user stated avoidances"
            })
            continue

        # Filter D: Budget cap (low end of daily cost > cap)
        cost_range = parse_cost_range(dest.get("estimated_cost", ""))
        if budget_val is not None and cost_range:
            low_cost, high_cost = cost_range
            if low_cost > budget_val:
                excluded_items.append({
                    "id": dest_id,
                    "name": dest_name,
                    "reason": f"Low end of daily cost (${low_cost}) exceeds budget cap (${budget_val:.0f}/day)"
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

        # 2. Season Suitability (with optional climate preference match)
        base_season = calculate_season_score(dest.get("best_seasons", []), target_month)
        note_season = f"Target month {target_month} vs seasons: {', '.join(dest.get('best_seasons', []))}"
        dest_climates = [str(c).lower() for c in dest.get("preferred_climate", [])]
        if user_preferred_climate and user_preferred_climate.lower() in dest_climates:
            val_season = min(1.0, round(base_season + 0.1, 2))
            note_season += f" (matches preferred climate '{user_preferred_climate}')"
        else:
            val_season = base_season

        # 3. Popularity (Factoring in crowd level + user crowd tolerance)
        val_popularity = calculate_popularity_score(dest, user_crowd_tol)
        note_popularity = f"Crowd: {dest.get('crowd_level')}, user tolerance: {user_crowd_tol}"

        # 4. Feasibility
        val_feasibility, note_feasibility = calculate_feasibility_score(dest, budget_val, profile if has_profile else None)

        # 5. Live Conditions (No live weather disruption feed, neutral placeholder)
        val_live = 0.5
        note_live = "no live feed - neutral placeholder"

        # 6. Past Feedback
        val_feedback, note_feedback = get_user_feedback_score(user_id, dest_id, dest_name)

        # Apply soft avoidance penalties if applicable
        avoidance_penalty = 0.0
        avoidance_notes = []
        if "avoid_crowds" in user_avoidances and dest.get("crowd_level") == "high":
            avoidance_penalty += 0.15
            avoidance_notes.append("crowd avoidance penalty -0.15")

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

        # Deduct soft avoidance penalty if any
        if avoidance_penalty > 0:
            total_points = max(0.0, total_points - (avoidance_penalty * 100.0))

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
        if avoidance_notes:
            item_data["avoidance_warning"] = "; ".join(avoidance_notes)

        ranked_items.append(item_data)

    # Sort items for 4 specialized lists + overall ranking
    overall_ranking = sorted(ranked_items, key=lambda x: x["total_score"], reverse=True)

    trending_now = sorted(
        [it for it in ranked_items if it["is_trending"]],
        key=lambda x: (x["breakdown"]["popularity"]["value"], x["total_score"]),
        reverse=True
    )[:limit_val]

    best_this_season = sorted(
        ranked_items,
        key=lambda x: (x["breakdown"]["season"]["value"], x["total_score"]),
        reverse=True
    )[:limit_val]

    best_for_you = sorted(
        ranked_items,
        key=lambda x: (x["breakdown"]["interest"]["value"], x["total_score"]),
        reverse=True
    )[:limit_val]

    best_feasible = sorted(
        ranked_items,
        key=lambda x: (x["breakdown"]["feasibility"]["value"], x["total_score"]),
        reverse=True
    )[:limit_val]

    return {
        "user_id": user_id,
        "has_profile": has_profile,
        "date": target_dt.isoformat(),
        "budget_cap": budget_val,
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
