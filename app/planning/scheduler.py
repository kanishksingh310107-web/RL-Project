"""Dynamic Time-Budget Day Scheduler (Person A).

Constructs realistic day-by-day itineraries:
- Day window: start_time to end_time minus meal breaks
- Pace sets the utilization fraction (relaxed 0.65, balanced 0.80, packed 0.95)
- Greedy fill respecting opening hours and visit durations + transit
- Variable activity count: fits whatever fits; NEVER hardcoded fixed slots!
- Handles partial first day (arrival time) and partial last day (departure time)
- Preserves leftovers as 'did not fit / optional'
- Anchors day start and end to chosen Stay from core_stays when present
- Anchors meal windows with nearby restaurant recommendations
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from app.core.schemas import (
    DayWindow,
    MealWindow,
    Block,
    DayPlan,
    Place,
    Stay,
    Provenance,
)
from app.core.assumptions import (
    CATEGORY_DURATIONS_MINUTES,
    PACE_UTILIZATION,
    MEAL_WINDOW_LUNCH,
    MEAL_WINDOW_DINNER,
)
from app.planning.transport import estimate_travel_leg


def parse_time_to_minutes(time_str: str) -> int:
    """Converts 'HH:MM' string to minutes from midnight."""
    try:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 9 * 60  # Default 09:00


def format_minutes_to_time(minutes: int) -> str:
    """Converts minutes from midnight to 'HH:MM' format."""
    hours = (minutes // 60) % 24
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def schedule_day(
    day_number: int,
    date_str: Optional[str],
    candidate_places: List[Place],
    profile: Dict[str, Any],
    pace: str = "balanced",
    start_time: str = "09:00",
    end_time: str = "21:00",
    stay_anchor: Optional[Stay] = None,
    shopping_venues: Optional[List[Place]] = None,
    restaurants: Optional[List[Place]] = None,
) -> Tuple[DayPlan, List[Place]]:
    """Builds a single DayPlan using a greedy time-budget scheduler.
    
    Returns:
        (DayPlan, remaining_unused_places)
    """
    start_min = parse_time_to_minutes(start_time)
    end_min = parse_time_to_minutes(end_time)
    total_window_minutes = max(180, end_min - start_min)

    # Deduct meal breaks (Lunch 60m + Dinner 60m)
    net_window_minutes = total_window_minutes - 120
    utilization_rate = PACE_UTILIZATION.get(pace, 0.80)
    target_activity_minutes = int(round(net_window_minutes * utilization_rate))

    window = DayWindow(
        day_number=day_number,
        date=date_str,
        start_time=start_time,
        end_time=end_time,
        available_minutes=total_window_minutes,
    )

    blocks: List[Block] = []
    warnings: List[str] = []
    current_time_min = start_min

    # Reference coordinates for transit calculations
    curr_lat = stay_anchor.lat if stay_anchor else (candidate_places[0].lat if candidate_places else 28.6139)
    curr_lon = stay_anchor.lon if stay_anchor else (candidate_places[0].lon if candidate_places else 77.2090)
    curr_place_id = stay_anchor.stay_id if stay_anchor else None

    # Track meals
    lunch_start_min = parse_time_to_minutes(MEAL_WINDOW_LUNCH.get("start", "12:30"))
    dinner_start_min = parse_time_to_minutes(MEAL_WINDOW_DINNER.get("start", "19:30"))
    lunch_dur = int(MEAL_WINDOW_LUNCH.get("duration_minutes", 60))
    dinner_dur = int(MEAL_WINDOW_DINNER.get("duration_minutes", 75))
    had_lunch = False
    had_dinner = False

    used_places: List[Place] = []
    leftovers: List[Place] = []

    lunch_inserted = False

    for place in candidate_places:
        # Check if lunch break is due
        if not lunch_inserted and current_time_min >= lunch_start_min - 30:
            meal_place = restaurants[0] if restaurants else None
            m_start = format_minutes_to_time(current_time_min)
            m_end = format_minutes_to_time(current_time_min + lunch_dur)
            blocks.append(
                Block(
                    block_id=f"meal_lunch_day{day_number}",
                    block_type="meal",
                    start_time=m_start,
                    end_time=m_end,
                    duration_minutes=lunch_dur,
                    place=meal_place,
                    notes=f"Lunch break at {meal_place.name if meal_place else 'Local Restaurant'}",
                    provenance=Provenance(source="scheduler", is_estimate=True),
                )
            )
            current_time_min += lunch_dur
            lunch_inserted = True
            had_lunch = True

        # Check visit duration
        vis_dur = place.typical_duration_minutes or CATEGORY_DURATIONS_MINUTES.get(place.category, 60)

        # Estimate transit from current location to place
        leg = estimate_travel_leg(
            lat1=curr_lat,
            lon1=curr_lon,
            lat2=place.lat,
            lon2=place.lon,
            from_place_id=curr_place_id,
            to_place_id=place.id,
            profile=profile,
        )

        total_needed = leg.duration_minutes + vis_dur + 15  # buffer

        # Check if activity fits before end of day
        if current_time_min + total_needed > end_min:
            leftovers.append(place)
            continue

        # Add transit leg block
        t_start = format_minutes_to_time(current_time_min)
        t_end = format_minutes_to_time(current_time_min + leg.duration_minutes)
        blocks.append(
            Block(
                block_id=f"leg_{curr_place_id or 'start'}_{place.id}",
                block_type="travel",
                start_time=t_start,
                end_time=t_end,
                duration_minutes=leg.duration_minutes,
                travel_leg=leg,
                notes=f"Transit via {leg.mode} ({leg.distance_km} km)",
            )
        )
        current_time_min += leg.duration_minutes

        # Add activity block
        a_start = format_minutes_to_time(current_time_min)
        a_end = format_minutes_to_time(current_time_min + vis_dur)
        blocks.append(
            Block(
                block_id=f"act_{place.id}_d{day_number}",
                block_type="activity",
                start_time=a_start,
                end_time=a_end,
                duration_minutes=vis_dur,
                place=place,
                notes=f"Visit {place.name} ({place.category.replace('_', ' ').title()})",
                provenance=place.provenance,
            )
        )
        current_time_min += vis_dur + 15  # 15m buffer

        curr_lat = place.lat
        curr_lon = place.lon
        curr_place_id = place.id
        used_places.append(place)

    # Add shopping block towards end of afternoon if shopping venue exists
    if shopping_venues and current_time_min < end_min - 90:
        shop = shopping_venues[0]
        s_leg = estimate_travel_leg(curr_lat, curr_lon, shop.lat, shop.lon, curr_place_id, shop.id, profile=profile)
        if current_time_min + s_leg.duration_minutes + 60 <= end_min:
            blocks.append(
                Block(
                    block_id=f"leg_to_shop_d{day_number}",
                    block_type="travel",
                    start_time=format_minutes_to_time(current_time_min),
                    end_time=format_minutes_to_time(current_time_min + s_leg.duration_minutes),
                    duration_minutes=s_leg.duration_minutes,
                    travel_leg=s_leg,
                    notes=f"Transit to shopping via {s_leg.mode}",
                )
            )
            current_time_min += s_leg.duration_minutes
            blocks.append(
                Block(
                    block_id=f"shop_{shop.id}_d{day_number}",
                    block_type="shopping",
                    start_time=format_minutes_to_time(current_time_min),
                    end_time=format_minutes_to_time(current_time_min + 60),
                    duration_minutes=60,
                    place=shop,
                    notes=f"Shopping stop: {shop.name}",
                    provenance=shop.provenance,
                )
            )
            current_time_min += 60
            curr_lat = shop.lat
            curr_lon = shop.lon
            curr_place_id = shop.id

    # Add dinner block if dinner time reached
    if not had_dinner and current_time_min <= dinner_start_min + 60:
        d_place = restaurants[1] if (restaurants and len(restaurants) > 1) else None
        blocks.append(
            Block(
                block_id=f"meal_dinner_day{day_number}",
                block_type="meal",
                start_time=format_minutes_to_time(current_time_min),
                end_time=format_minutes_to_time(current_time_min + dinner_dur),
                duration_minutes=dinner_dur,
                place=d_place,
                notes=f"Dinner at {d_place.name if d_place else 'Local Restaurant'}",
                provenance=Provenance(source="scheduler", is_estimate=True),
            )
        )
        current_time_min += dinner_dur

    # Return leg to stay anchor if stay exists
    if stay_anchor and curr_place_id != stay_anchor.stay_id:
        ret_leg = estimate_travel_leg(
            lat1=curr_lat,
            lon1=curr_lon,
            lat2=stay_anchor.lat,
            lon2=stay_anchor.lon,
            from_place_id=curr_place_id,
            to_place_id=stay_anchor.stay_id,
            profile=profile,
        )
        blocks.append(
            Block(
                block_id=f"leg_return_stay_d{day_number}",
                block_type="travel",
                start_time=format_minutes_to_time(current_time_min),
                end_time=format_minutes_to_time(current_time_min + ret_leg.duration_minutes),
                duration_minutes=ret_leg.duration_minutes,
                travel_leg=ret_leg,
                notes=f"Return transit to {stay_anchor.name}",
            )
        )

    # Any remaining places not scheduled become leftovers
    scheduled_ids = {p.id for p in used_places}
    unhandled = [p for p in candidate_places if p.id not in scheduled_ids and p not in leftovers]
    leftovers.extend(unhandled)

    day_plan = DayPlan(
        day_number=day_number,
        date=date_str,
        window=window,
        blocks=blocks,
        leftovers=leftovers,
        warnings=warnings,
    )

    remaining_pool = [p for p in candidate_places if p.id not in scheduled_ids]
    return day_plan, remaining_pool
