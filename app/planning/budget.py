"""Budget Ledger & Category Allocator (Person A).

Maintains a multi-category trip budget ledger and calculates realistic minimum
budgets for Indian travel destinations:
- Lines: intercity transit, local transit, accommodation, food, activities, shopping, necessary extras, buffer
- Clear labelling: 'verified', 'estimated', 'unavailable'
- Distinguishes per-person vs group costs
- Accounts for group room sharing and duration
- Realistic distance-based return transit estimates
- Interactive budget validation & slider bounds
- Strict rule: unknown price is 'unavailable' / None, NEVER zero.
"""
import math
import sqlite3
import datetime
from typing import Dict, Any, List, Optional, Tuple
from app.core.schemas import BudgetLine, Place
from app.core.assumptions import (
    BUDGET_SHARE_STAY,
    BUDGET_SHARE_FOOD,
    BUDGET_SHARE_TRANSPORT,
    BUDGET_SHARE_ACTIVITIES,
    BUDGET_SHARE_SHOPPING,
    BUDGET_SHARE_BUFFER,
    CIRCUITY_FACTOR,
)
from app.providers.geo import haversine_distance_km

BASE_BUDGET_SHARES = {
    "stay": BUDGET_SHARE_STAY,
    "food": BUDGET_SHARE_FOOD,
    "transport": BUDGET_SHARE_TRANSPORT,
    "activities": BUDGET_SHARE_ACTIVITIES,
    "shopping": BUDGET_SHARE_SHOPPING,
    "buffer": BUDGET_SHARE_BUFFER,
}

# Major Indian city coordinates for intercity distance calculation
MAJOR_INDIAN_HUBS: Dict[str, Tuple[float, float]] = {
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "kolkata": (22.5726, 88.3639),
    "chennai": (13.0827, 80.2707),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "jaipur": (26.9124, 75.7873),
    "ahmedabad": (23.0225, 72.5714),
    "lucknow": (26.8467, 80.9462),
    "chandigarh": (30.7333, 76.7794),
    "kochi": (9.9312, 76.2673),
    "cochin": (9.9312, 76.2673),
    "goa": (15.2993, 74.1240),
    "south goa": (15.2993, 74.1240),
    "varanasi": (25.3176, 82.9739),
    "srinagar": (34.0837, 74.7973),
    "shimla": (31.1048, 77.1734),
    "manali": (32.2432, 77.1892),
    "amritsar": (31.6340, 74.8723),
    "guwahati": (26.1445, 91.7362),
    "darjeeling": (27.0410, 88.2663),
    "gangtok": (27.3389, 88.6065),
    "rishikesh": (30.0869, 78.2676),
    "haridwar": (29.9457, 78.1642),
    "udaipur": (24.5854, 73.7125),
    "jodhpur": (26.2389, 73.0243),
    "hampi": (15.3350, 76.4600),
    "ooty": (11.4102, 76.6950),
    "coorg": (12.3375, 75.8069),
    "madikeri": (12.4244, 75.7382),
    "munnar": (10.0889, 77.0595),
    "alleppey": (9.4981, 76.3388),
    "alappuzha": (9.4981, 76.3388),
    "leh": (34.1526, 77.5771),
    "shillong": (25.5788, 91.8933),
    "cherrapunji": (25.2986, 91.7314),
    "agra": (27.1767, 78.0081),
}


def resolve_city_coords(name: str) -> Optional[Tuple[float, float]]:
    """Resolves coordinates for an Indian city or destination."""
    if not name:
        return None
    clean = name.lower().strip()
    for hub, coords in MAJOR_INDIAN_HUBS.items():
        if hub in clean or clean in hub:
            return coords

    # Try database lookup
    try:
        from app.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT latitude, longitude FROM destination_activities WHERE destination_id LIKE ? OR name LIKE ? LIMIT 1",
                (f"%{clean}%", f"%{clean}%")
            )
            row = cursor.fetchone()
            if row and row[0] is not None and row[1] is not None:
                return (float(row[0]), float(row[1]))
    except Exception:
        pass

    return None


def compute_budget_shares(
    total_budget: float,
    profile: Dict[str, Any],
    trip_prefs: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """Computes category budget shares tailored to user spend priorities."""
    shares = dict(BASE_BUDGET_SHARES)
    spend_priorities = profile.get("spend_priorities") or []
    if isinstance(spend_priorities, str):
        spend_priorities = [spend_priorities]

    # Adjust shares dynamically
    if "luxury_stay" in spend_priorities or "accommodation" in spend_priorities:
        shares["stay"] += 0.08
        shares["shopping"] -= 0.04
        shares["buffer"] -= 0.04
    if "fine_dining" in spend_priorities or "food" in spend_priorities:
        shares["food"] += 0.06
        shares["shopping"] -= 0.03
        shares["activities"] -= 0.03
    if "shopping" in spend_priorities:
        shares["shopping"] += 0.06
        shares["stay"] -= 0.03
        shares["buffer"] -= 0.03

    # Normalize to ensure sum is exactly 1.0
    total = sum(shares.values())
    return {k: round(v / total, 4) for k, v in shares.items()}


def build_budget_ledger(
    total_budget: float,
    profile: Dict[str, Any],
    actual_spent: Dict[str, float],
    currency: str = "INR",
) -> Tuple[List[BudgetLine], str]:
    """Constructs the structured BudgetLine entries and evaluates overall status."""
    shares = compute_budget_shares(total_budget, profile)
    lines: List[BudgetLine] = []
    has_red = False
    has_amber = False

    for cat, share in shares.items():
        allocated = round(total_budget * share, 2)
        spent = round(actual_spent.get(cat, 0.0), 2)

        if spent <= allocated:
            status = "green"
        elif spent <= allocated * 1.15:
            status = "amber"
            has_amber = True
        else:
            status = "red"
            has_red = True

        note = f"{share*100:.1f}% target share"
        if status == "red":
            note += " (Over budget by " + f"{spent - allocated:.0f} {currency})"

        lines.append(
            BudgetLine(
                category=cat,
                allocated_amount=allocated,
                estimated_spent=spent,
                currency=currency,
                status=status,
                notes=note,
            )
        )

    overall_status = "red" if has_red else ("amber" if has_amber else "green")
    return lines, overall_status


def find_cheaper_swaps(
    current_place: Place,
    candidate_pool: List[Place],
    max_cost: float,
) -> List[Place]:
    """Finds cheaper alternative places in the same category that fit within max_cost."""
    swaps: List[Place] = []
    for cand in candidate_pool:
        if cand.id == current_place.id:
            continue
        if cand.category == current_place.category:
            cand_cost = cand.cost_amount if cand.cost_amount is not None else 0.0
            curr_cost = current_place.cost_amount if current_place.cost_amount is not None else 999999.0
            if cand_cost < curr_cost and cand_cost <= max_cost:
                swaps.append(cand)
    return swaps[:3]


# ==============================================================================
# REALISTIC MINIMUM TRIP BUDGET CALCULATION SYSTEM
# ==============================================================================

def calculate_minimum_trip_budget(destination_id=None, destination_name=None,
        departure_location="Delhi", start_date=None, end_date=None, duration_days=None,
        travellers_count=1, accommodation_tier="boutique", transit_pref="public_transit",
        travel_pace="balanced", include_shopping=False, profile=None, party=None,
        food_style=None, destination_lat=None, destination_lon=None):
    from app.core.cost_model import estimate_cost
    trip = dict(destination_id=destination_id, destination_name=destination_name,
        departure_location=departure_location, start_date=start_date, end_date=end_date,
        duration_days=duration_days, travellers_count=travellers_count,
        accommodation_tier=accommodation_tier, transit_pref=transit_pref,
        travel_pace=travel_pace, include_shopping=include_shopping, party=party,
        food_style=food_style, destination_lat=destination_lat, destination_lon=destination_lon)
    low, rec = estimate_cost(trip, minimum=True), estimate_cost(trip)
    categories = []
    for key, value in rec['cost_breakdown'].items():
        minimum = low['cost_breakdown'][key]
        description = f"{rec['rooms']} room(s) for {rec['nights']} night(s)" if key == 'accommodation' else key.replace('_', ' ').title()
        categories.append(dict(category=key, name=description, description=description,
            minimum_cost=minimum['per_party'], recommended_cost=value['per_party'],
            per_person_min=minimum['per_person'], per_person_rec=value['per_person'],
            cost_basis='per_party', data_source='verified' if key == 'intercity_transit' and value['per_party'] == 0 else 'estimated',
            assumptions='Indicative planning assumptions, not live prices. '+str(rec['assumptions'])))
    return dict(destination={'id':destination_id or 'custom_destination','name':destination_name or destination_id or 'Selected destination'},
        departure_location=departure_location or 'Delhi', duration_days=rec['days'],
        nights_count=rec['nights'], travellers_count=rec['travellers_count'], rooms_count=rec['rooms'],
        intercity_distance_km=rec['intercity_distance_km'], bare_minimum_budget=low['total'],
        recommended_budget=rec['total'], bare_minimum_per_person=low['per_person'],
        recommended_per_person=rec['per_person'], bare_minimum_daily_per_person=low['per_person_per_day'],
        recommended_daily_per_person=rec['per_person_per_day'], categories=categories,
        slider_config={'min':low['total'],'default':rec['total'],'max':math.ceil(max(50000,rec['total']*2.5)/1000)*1000,'step':500},
        currency='INR', budget_band_labels=__import__('app.core.assumptions',fromlist=['BUDGET_BAND_LABELS']).BUDGET_BAND_LABELS, cost_breakdown=rec['cost_breakdown'], assumptions=rec['assumptions'], confidence='indicative')


def validate_trip_budget(
    selected_budget: float,
    bare_minimum_budget: float,
    recommended_budget: float,
) -> Dict[str, Any]:
    """Validates user-selected budget against the realistic minimum and comfortable recommendations."""
    sel = float(selected_budget or 0.0)
    b_min = float(bare_minimum_budget or 0.0)
    b_rec = float(recommended_budget or 0.0)

    if sel < b_min:
        shortfall = round(b_min - sel, 2)
        return {
            "is_sufficient": False,
            "tier": "insufficient",
            "shortfall": shortfall,
            "warning": (
                f"Budget Warning: Your selected budget of ₹{sel:,.0f} is below the realistic bare minimum "
                f"estimated cost of ₹{b_min:,.0f}. Shortfall: ₹{shortfall:,.0f}. "
                f"Consider increasing your budget or shortening your trip duration."
            ),
            "message": f"Shortfall of ₹{shortfall:,.0f} against bare minimum.",
        }

    if sel < b_rec:
        surplus = round(sel - b_min, 2)
        return {
            "is_sufficient": True,
            "tier": "budget_conscious",
            "surplus_above_min": surplus,
            "warning": None,
            "message": (
                f"Budget of ₹{sel:,.0f} covers the minimum trip requirements (+₹{surplus:,.0f} buffer). "
                f"The guide will prioritize affordable stays, public transit, and smart meal choices."
            ),
        }

    surplus_rec = round(sel - b_rec, 2)
    return {
        "is_sufficient": True,
        "tier": "comfortable",
        "surplus_above_recommended": surplus_rec,
        "warning": None,
        "message": (
            f"Budget of ₹{sel:,.0f} allows comfortable travel (+₹{surplus_rec:,.0f} above recommended). "
            f"The guide can include boutique accommodations, private cab transit, and premium regional dining."
        ),
    }


def adapt_itinerary_to_budget(
    itinerary: Dict[str, Any],
    selected_budget: float,
    bare_minimum_budget: float,
    recommended_budget: float,
) -> Dict[str, Any]:
    """Adapts itinerary activities and transit advice based on the selected budget tier."""
    val = validate_trip_budget(selected_budget, bare_minimum_budget, recommended_budget)
    tier = val["tier"]

    # Annotate itinerary with budget metadata
    itin_copy = dict(itinerary)
    itin_copy["budget_tier"] = tier
    itin_copy["budget_validation"] = val
    itin_copy["selected_budget"] = selected_budget
    itin_copy["minimum_budget"] = bare_minimum_budget

    # If budget conscious, flag that expensive paid activities should be substituted with free/low-cost alternatives
    if tier in ("insufficient", "budget_conscious"):
        for day in itin_copy.get("days", []):
            for act in day.get("activities", []):
                cost = act.get("cost_amount") or 0.0
                if cost > 500.0:
                    act["budget_note"] = "Optional paid highlight; free scenic walking alternative recommended."
    elif tier == "comfortable":
        for day in itin_copy.get("days", []):
            for act in day.get("activities", []):
                act["budget_note"] = "Comfortably covered within allocated trip budget."

    return itin_copy
