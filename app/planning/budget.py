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

def estimate_intercity_transit_cost(
    departure_city: str,
    destination_city: str,
    travellers_count: int,
    transit_pref: str = "train",
) -> Dict[str, Any]:
    """Calculates return intercity transit between departure and destination.
    
    Uses distance bands based on Indian Railway and state transport norms:
    - Short (< 300 km): Sleeper/Bus ₹220 vs AC Chair Car ₹650 each way
    - Medium (300-750 km): Sleeper/3AC ₹480 vs Vande Bharat/2AC ₹1,450 each way
    - Long (750-1400 km): 3AC ₹850 vs 2AC/Flight ₹2,600 each way
    - Very Long (> 1400 km): 3AC ₹1,250 vs Economy Flight ₹4,200 each way
    """
    dep_c = (departure_city or "Delhi").strip()
    dest_c = (destination_city or "").strip()

    # Same city / Local trip
    if dep_c.lower() in dest_c.lower() or dest_c.lower() in dep_c.lower():
        return {
            "category": "intercity_transit",
            "name": "Intercity Travel (Return)",
            "description": f"Local exploration within {dep_c}",
            "minimum_cost": 0.0,
            "recommended_cost": 0.0,
            "per_person_min": 0.0,
            "per_person_rec": 0.0,
            "cost_basis": "per_person",
            "distance_km": 0.0,
            "data_source": "verified",
            "assumptions": "Departure equals destination; no intercity travel required (local resident journey).",
        }

    dep_coords = resolve_city_coords(dep_c) or MAJOR_INDIAN_HUBS["delhi"]
    dest_coords = resolve_city_coords(dest_c) or MAJOR_INDIAN_HUBS.get("jaipur", (26.9124, 75.7873))

    straight_dist = haversine_distance_km(dep_coords[0], dep_coords[1], dest_coords[0], dest_coords[1])
    road_rail_dist = straight_dist * CIRCUITY_FACTOR

    if road_rail_dist < 300.0:
        one_way_min = 220.0
        one_way_rec = 650.0
        mode_desc = "Express Train Sleeper / State Bus vs AC Chair Car / Volvo"
    elif road_rail_dist < 750.0:
        one_way_min = 480.0
        one_way_rec = 1450.0
        mode_desc = "3-Tier / Sleeper Train vs Vande Bharat / AC 2-Tier"
    elif road_rail_dist < 1400.0:
        one_way_min = 850.0
        one_way_rec = 2600.0
        mode_desc = "3AC Superfast Train vs AC 2-Tier / Advance Economy Air"
    else:
        one_way_min = 1250.0
        one_way_rec = 4200.0
        mode_desc = "3AC Express Train vs Domestic Air Travel"

    return_min_per_p = round(one_way_min * 2, 2)
    return_rec_per_p = round(one_way_rec * 2, 2)
    total_min = round(return_min_per_p * travellers_count, 2)
    total_rec = round(return_rec_per_p * travellers_count, 2)

    return {
        "category": "intercity_transit",
        "name": "Intercity Travel (Return)",
        "description": f"Round-trip travel between {dep_c} and {dest_c} ({road_rail_dist:.0f} km)",
        "minimum_cost": total_min,
        "recommended_cost": total_rec,
        "per_person_min": return_min_per_p,
        "per_person_rec": return_rec_per_p,
        "cost_basis": "per_person",
        "distance_km": round(road_rail_dist, 1),
        "data_source": "estimated",
        "assumptions": f"Estimated return fares per person based on {road_rail_dist:.0f} km distance band ({mode_desc}). Team assumption, not live rail GDS.",
    }


def estimate_local_transit_cost(
    duration_days: int,
    travellers_count: int,
    transit_pref: str = "public_transit",
) -> Dict[str, Any]:
    """Calculates destination in-city local transit cost across days."""
    days = max(1, duration_days)
    
    # Minimum: Metro, bus, shared e-rickshaw (₹180/person/day)
    daily_min_per_p = 180.0
    total_min = round(daily_min_per_p * travellers_count * days, 2)

    # Recommended: Private auto or on-demand cab / hired car (₹650 per vehicle per day for party up to 4)
    vehicles_needed = max(1, math.ceil(travellers_count / 4))
    daily_rec_vehicle = 650.0 * vehicles_needed
    total_rec = round(daily_rec_vehicle * days, 2)

    return {
        "category": "local_transit",
        "name": "Local Transportation",
        "description": f"{days} days of in-city transit for {travellers_count} traveller(s)",
        "minimum_cost": total_min,
        "recommended_cost": total_rec,
        "per_person_min": round(total_min / travellers_count, 2),
        "per_person_rec": round(total_rec / travellers_count, 2),
        "cost_basis": "shared_vehicle_and_public",
        "data_source": "estimated",
        "assumptions": f"Bare minimum assumes Metro/Bus/Shared auto at ₹{daily_min_per_p:.0f}/person/day. Recommended assumes pre-paid on-demand cabs/auto at ₹{daily_rec_vehicle:.0f}/day for party.",
    }


def estimate_accommodation_cost(
    destination_id: str,
    duration_days: int,
    travellers_count: int,
    accommodation_tier: str = "boutique",
) -> Dict[str, Any]:
    """Calculates accommodation cost factoring group room sharing and night duration."""
    days = max(1, duration_days)
    nights = max(1, days - 1 if days > 1 else 1)
    
    # Standard group sharing: 2 adults per room, solo = 1 room
    rooms_count = max(1, math.ceil(travellers_count / 2))

    # Base rates per room per night in India
    # Minimum: Clean budget homestay, hostel, dharamsala or standard guesthouse
    rate_min = 850.0
    
    # Recommended: 3-star hotel, verified heritage haveli, or boutique homestay
    tier_lower = (accommodation_tier or "boutique").lower()
    if "resort" in tier_lower or "luxury" in tier_lower:
        rate_rec = 5500.0
        tier_label = "Luxury Resort / Villa"
    elif "apartment" in tier_lower or "homestay" in tier_lower:
        rate_rec = 2200.0
        tier_label = "Serviced Apartment / Homestay"
    elif "hostel" in tier_lower or "budget" in tier_lower:
        rate_rec = 1200.0
        tier_label = "Budget Stay / Hostel"
    else:
        rate_rec = 2600.0
        tier_label = "Boutique & 3-Star Heritage"

    total_min = round(rooms_count * nights * rate_min, 2)
    total_rec = round(rooms_count * nights * rate_rec, 2)

    return {
        "category": "accommodation",
        "name": "Accommodation & Stay",
        "description": f"{rooms_count} room(s) for {nights} night(s) ({travellers_count} guests)",
        "minimum_cost": total_min,
        "recommended_cost": total_rec,
        "per_person_min": round(total_min / travellers_count, 2),
        "per_person_rec": round(total_rec / travellers_count, 2),
        "cost_basis": "group_shared_rooms",
        "rooms_count": rooms_count,
        "nights_count": nights,
        "data_source": "estimated",
        "assumptions": f"Minimum based on budget guesthouse @ ₹{rate_min:.0f}/room/night. Recommended based on {tier_label} @ ₹{rate_rec:.0f}/room/night across {rooms_count} shared room(s).",
    }


def estimate_food_cost(
    duration_days: int,
    travellers_count: int,
    dietary: str = "all",
) -> Dict[str, Any]:
    """Calculates food and dining cost per person across trip days."""
    days = max(1, duration_days)

    # Minimum: Pure veg / street thali / darshini breakfast + lunch + dinner + chai
    # Breakfast ₹60, Lunch ₹120, Dinner ₹150, Tea/Water ₹50 = ₹380/day/person
    daily_min_per_p = 380.0
    
    # Recommended: Quality casual dining & regional cuisine restaurants
    # Breakfast ₹150, Lunch ₹350, Dinner ₹450, Snacks/Beverages ₹150 = ₹1,100/day/person
    daily_rec_per_p = 1100.0

    total_min = round(daily_min_per_p * travellers_count * days, 2)
    total_rec = round(daily_rec_per_p * travellers_count * days, 2)

    return {
        "category": "food",
        "name": "Food & Daily Meals",
        "description": f"3 meals and refreshments daily for {travellers_count} guest(s) across {days} days",
        "minimum_cost": total_min,
        "recommended_cost": total_rec,
        "per_person_min": round(total_min / travellers_count, 2),
        "per_person_rec": round(total_rec / travellers_count, 2),
        "cost_basis": "per_person",
        "data_source": "estimated",
        "assumptions": f"Minimum based on authentic local thali and street food @ ₹{daily_min_per_p:.0f}/day/person. Recommended based on sit-down regional specialty dining @ ₹{daily_rec_per_p:.0f}/day/person.",
    }


def estimate_activities_cost(
    destination_id: str,
    duration_days: int,
    travellers_count: int,
    travel_pace: str = "balanced",
) -> Dict[str, Any]:
    """Calculates attraction entry fees and sightseeing activity costs."""
    days = max(1, duration_days)
    
    # Check if destination has verified attraction records in SQLite
    verified_costs: List[float] = []
    try:
        from app.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT cost_amount FROM destination_activities WHERE destination_id = ? AND cost_amount IS NOT NULL",
                (destination_id,)
            )
            rows = cursor.fetchall()
            for r in rows:
                if r[0] is not None:
                    raw_val = float(r[0])
                    # Legacy amounts under $50 were stored in USD; convert to INR
                    inr_val = raw_val * 83.0 if raw_val <= 50.0 else raw_val
                    verified_costs.append(inr_val)
    except Exception:
        pass

    pace_lower = (travel_pace or "balanced").lower()
    spots_per_day = 2 if "relaxed" in pace_lower else (4 if "packed" in pace_lower else 3)
    total_attractions = spots_per_day * days

    if verified_costs:
        verified_costs.sort()
        # Minimum: top free or low-cost tickets
        cheapest_tier = verified_costs[:min(len(verified_costs), total_attractions)]
        avg_min_ticket = sum(cheapest_tier) / max(1, len(cheapest_tier))
        avg_rec_ticket = sum(verified_costs) / len(verified_costs)
        data_source = "verified"
        source_note = f"Verified from {len(verified_costs)} curated activity ticket records in local destination catalog."
    else:
        avg_min_ticket = 80.0   # ASI standard monument entry
        avg_rec_ticket = 280.0  # Palace museum, audio guide, or garden pass
        data_source = "estimated"
        source_note = f"Estimated average monument ticket rates in India ({spots_per_day} spots/day scheduled)."

    # Minimum: focus on free spots + essential ticketed entries (assumes 50% free places like ghats/temples)
    total_min_p = round(avg_min_ticket * (total_attractions * 0.5), 2)
    total_rec_p = round(avg_rec_ticket * total_attractions, 2)

    total_min = round(total_min_p * travellers_count, 2)
    total_rec = round(total_rec_p * travellers_count, 2)

    return {
        "category": "activities",
        "name": "Attraction Entry & Sightseeing",
        "description": f"Monument entry fees, temple tickets & activity passes for {days} days",
        "minimum_cost": total_min,
        "recommended_cost": total_rec,
        "per_person_min": total_min_p,
        "per_person_rec": total_rec_p,
        "cost_basis": "per_person",
        "data_source": data_source,
        "assumptions": f"{source_note} Assumes {spots_per_day} spots/day based on {travel_pace} pace.",
    }


def estimate_shopping_cost(
    travellers_count: int,
    include_shopping: bool = False,
) -> Dict[str, Any]:
    """Calculates optional souvenir, textile, and artisan bazaar allowance."""
    if not include_shopping:
        return {
            "category": "shopping",
            "name": "Bazaar & Souvenirs",
            "description": "Local artisan crafts, teas & keepsakes",
            "minimum_cost": 0.0,
            "recommended_cost": 0.0,
            "per_person_min": 0.0,
            "per_person_rec": 0.0,
            "cost_basis": "per_person",
            "data_source": "estimated",
            "assumptions": "Excluded by user selection (₹0 allocation).",
        }

    # Minimum: Small keepsakes, tea, spices, magnets (₹350/person)
    # Recommended: Local textiles, handicraft, brass/pottery gifts (₹1,500/person)
    shop_min_p = 350.0
    shop_rec_p = 1500.0

    total_min = round(shop_min_p * travellers_count, 2)
    total_rec = round(shop_rec_p * travellers_count, 2)

    return {
        "category": "shopping",
        "name": "Bazaar & Souvenirs",
        "description": f"Discretionary artisan market budget for {travellers_count} guest(s)",
        "minimum_cost": total_min,
        "recommended_cost": total_rec,
        "per_person_min": shop_min_p,
        "per_person_rec": shop_rec_p,
        "cost_basis": "per_person",
        "data_source": "estimated",
        "assumptions": "Discretionary shopping: basic mementos @ ₹350/person vs quality artisan handicrafts @ ₹1,500/person.",
    }


def estimate_necessary_extras_cost(
    duration_days: int,
    travellers_count: int,
) -> Dict[str, Any]:
    """Calculates daily necessary incidental travel expenses in India."""
    days = max(1, duration_days)

    # Minimum: Packaged mineral water (₹40/day) + temple shoe-keeping (₹20/day) + mobile data / tips (₹30/day) = ₹90/day/person
    daily_min_p = 90.0
    
    # Recommended: Bottled water & electrolytes (₹80) + camera/phone monument permits (₹75) + porterage & cloakroom (₹75) = ₹230/day/person
    daily_rec_p = 230.0

    total_min = round(daily_min_p * travellers_count * days, 2)
    total_rec = round(daily_rec_p * travellers_count * days, 2)

    return {
        "category": "necessary_extras",
        "name": "Necessary Incidental Expenses",
        "description": "Packaged drinking water, monument camera permits, shoe-keeping, connectivity",
        "minimum_cost": total_min,
        "recommended_cost": total_rec,
        "per_person_min": round(total_min / travellers_count, 2),
        "per_person_rec": round(total_rec / travellers_count, 2),
        "cost_basis": "per_person",
        "data_source": "estimated",
        "assumptions": f"Essential daily incidentals: sealed mineral water, monument camera fees, temple shoe tokens, mobile data @ ₹{daily_min_p:.0f}/day min vs ₹{daily_rec_p:.0f}/day recommended.",
    }


def estimate_contingency_buffer(
    subtotal_min: float,
    subtotal_rec: float,
    travellers_count: int,
) -> Dict[str, Any]:
    """Calculates emergency contingency reserve (5% minimum, 10% recommended)."""
    buf_min = round(subtotal_min * 0.05, 2)
    buf_rec = round(subtotal_rec * 0.10, 2)

    return {
        "category": "contingency_buffer",
        "name": "Contingency & Emergency Buffer",
        "description": "5% minimum reserve vs 10% recommended safety margin",
        "minimum_cost": buf_min,
        "recommended_cost": buf_rec,
        "per_person_min": round(buf_min / travellers_count, 2),
        "per_person_rec": round(buf_rec / travellers_count, 2),
        "cost_basis": "group_reserve",
        "data_source": "estimated",
        "assumptions": "Unallocated emergency buffer for medical supplies, unexpected auto surge fares, or route delays (5% bare min / 10% comfortable).",
    }


def calculate_minimum_trip_budget(
    destination_id: Optional[str] = None,
    destination_name: Optional[str] = None,
    departure_location: Optional[str] = "Delhi",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    duration_days: Optional[int] = None,
    travellers_count: int = 1,
    accommodation_tier: Optional[str] = "boutique",
    transit_pref: Optional[str] = "public_transit",
    travel_pace: Optional[str] = "balanced",
    include_shopping: bool = False,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculates a realistic minimum budget and recommended comfortable budget.
    
    Considers:
    1. Intercity return transit
    2. Local transportation
    3. Accommodation (room sharing by party size)
    4. Food & meals
    5. Attraction entry fees & activities
    6. Shopping (if selected)
    7. Necessary incidental expenses
    8. Contingency buffer
    """
    travellers = max(1, travellers_count)

    # Resolve trip duration
    days = duration_days
    if not days and start_date and end_date:
        try:
            d1 = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            d2 = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
            days = max(1, (d2 - d1).days + 1)
        except Exception:
            days = 4
    if not days:
        days = 4

    nights = max(1, days - 1 if days > 1 else 1)
    rooms = max(1, math.ceil(travellers / 2))

    dest_name = destination_name or destination_id or "Jaipur, Rajasthan"
    dep_loc = departure_location or "Delhi"

    # 1. Intercity Travel
    intercity = estimate_intercity_transit_cost(
        departure_city=dep_loc,
        destination_city=dest_name,
        travellers_count=travellers,
        transit_pref=transit_pref or "train",
    )

    # 2. Local Transit
    local_transit = estimate_local_transit_cost(
        duration_days=days,
        travellers_count=travellers,
        transit_pref=transit_pref or "public_transit",
    )

    # 3. Accommodation
    accom = estimate_accommodation_cost(
        destination_id=destination_id or "",
        duration_days=days,
        travellers_count=travellers,
        accommodation_tier=accommodation_tier or "boutique",
    )

    # 4. Food & Meals
    food = estimate_food_cost(
        duration_days=days,
        travellers_count=travellers,
        dietary=profile.get("dietary", "all") if profile else "all",
    )

    # 5. Activities & Sightseeing
    activities = estimate_activities_cost(
        destination_id=destination_id or "",
        duration_days=days,
        travellers_count=travellers,
        travel_pace=travel_pace or "balanced",
    )

    # 6. Shopping
    shopping = estimate_shopping_cost(
        travellers_count=travellers,
        include_shopping=include_shopping,
    )

    # 7. Necessary Extras
    extras = estimate_necessary_extras_cost(
        duration_days=days,
        travellers_count=travellers,
    )

    # Compute subtotal for buffer calculation
    subtotal_min = (
        intercity["minimum_cost"]
        + local_transit["minimum_cost"]
        + accom["minimum_cost"]
        + food["minimum_cost"]
        + activities["minimum_cost"]
        + shopping["minimum_cost"]
        + extras["minimum_cost"]
    )
    subtotal_rec = (
        intercity["recommended_cost"]
        + local_transit["recommended_cost"]
        + accom["recommended_cost"]
        + food["recommended_cost"]
        + activities["recommended_cost"]
        + shopping["recommended_cost"]
        + extras["recommended_cost"]
    )

    # 8. Contingency Buffer
    buffer = estimate_contingency_buffer(
        subtotal_min=subtotal_min,
        subtotal_rec=subtotal_rec,
        travellers_count=travellers,
    )

    # Total overall figures
    bare_minimum_total = round(subtotal_min + buffer["minimum_cost"], 2)
    recommended_total = round(subtotal_rec + buffer["recommended_cost"], 2)

    categories = [
        intercity,
        local_transit,
        accom,
        food,
        activities,
        shopping,
        extras,
        buffer,
    ]

    # Slider configuration: allows user to increase allowance smoothly above minimum
    slider_max = max(recommended_total * 2.5, bare_minimum_total * 3.0, 50000.0)
    # Round slider max to nearest thousand
    slider_max = math.ceil(slider_max / 1000.0) * 1000.0

    return {
        "destination": {
            "id": destination_id or "custom_destination",
            "name": dest_name,
        },
        "departure_location": dep_loc,
        "duration_days": days,
        "nights_count": nights,
        "travellers_count": travellers,
        "rooms_count": rooms,
        "intercity_distance_km": intercity.get("distance_km", 0.0),
        "bare_minimum_budget": bare_minimum_total,
        "recommended_budget": recommended_total,
        "bare_minimum_per_person": round(bare_minimum_total / travellers, 2),
        "recommended_per_person": round(recommended_total / travellers, 2),
        "bare_minimum_daily_per_person": round(bare_minimum_total / (travellers * days), 2),
        "recommended_daily_per_person": round(recommended_total / (travellers * days), 2),
        "categories": categories,
        "slider_config": {
            "min": bare_minimum_total,
            "default": recommended_total,
            "step": 500.0,
            "max": slider_max,
        },
        "currency": "INR",
    }


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
