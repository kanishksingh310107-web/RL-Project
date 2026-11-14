"""Timed itinerary engine with trip-specific activity windows and free-time blocks."""
import uuid
import json
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database import get_connection
from app.services.suggestion_engine import get_linucb_alternatives
from app.schedule_preferences import LEGACY_SCHEDULE_PREFS, minute_of_day, schedule_window

# Router for timed itinerary endpoints
timed_router = APIRouter(prefix="/itinerary/timed", tags=["timed_itinerary"])


# ---------------------------------------------------------------------------
# Database Tables for Timed Itinerary
# ---------------------------------------------------------------------------

def init_timed_tables(conn: sqlite3.Connection):
    """Initializes tables for timed itineraries and structured daily slots."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS timed_itineraries (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            destination_id TEXT NOT NULL,
            total_days INTEGER NOT NULL,
            pace TEXT NOT NULL,
            total_cost REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS timed_itinerary_slots (
            id TEXT PRIMARY KEY,
            itinerary_id TEXT NOT NULL,
            trip_id TEXT NOT NULL,
            day_number INTEGER NOT NULL,
            order_index INTEGER NOT NULL,
            slot_type TEXT NOT NULL, -- 'activity', 'transit', 'meal', 'rest'
            start_time TEXT NOT NULL, -- '09:00'
            end_time TEXT NOT NULL,   -- '11:30'
            duration_mins INTEGER NOT NULL,
            title TEXT NOT NULL,
            location TEXT,
            estimated_cost REAL DEFAULT 0.0,
            activity_id TEXT,
            category TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (itinerary_id) REFERENCES timed_itineraries(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timed_slots_trip_day ON timed_itinerary_slots(trip_id, day_number)")
    conn.commit()


# ---------------------------------------------------------------------------
# Helper Data for Destination Meals and Default Attractions
# ---------------------------------------------------------------------------

DESTINATION_MEAL_PLANS = {
    "manali_spiti_india": {
        "lunch": {
            "title": "Lunch at Cafe 1947 & Old Manali Eatery",
            "location": "Old Manali, Manali",
            "cost": 12.0,
            "description": "Riverside dining savoring Himachali trout, woodfired pizza, and artisan coffee."
        },
        "dinner": {
            "title": "Dinner & Night Walk at Mall Road / Johnson's Cafe",
            "location": "Circuit House Road, Manali",
            "cost": 22.0,
            "description": "Candlelit dinner followed by an evening night stroll along pine-scented mountain streets."
        }
    },
    "kyoto_japan": {
        "lunch": {
            "title": "Lunch at Nishiki Market / Local Soba House",
            "location": "Nakagyo Ward, Kyoto",
            "cost": 15.0,
            "description": "Authentic Kansai handmade soba noodles and regional seasonal delicacies."
        },
        "dinner": {
            "title": "Dinner & Pontocho Alley Night Walk",
            "location": "Pontocho, Kyoto",
            "cost": 30.0,
            "description": "Lantern-lit dining alongside the Kamogawa River followed by a traditional night walk."
        }
    },
    "santorini_greece": {
        "lunch": {
            "title": "Seaside Taverna Lunch in Ammoudi Bay",
            "location": "Ammoudi Bay, Oia",
            "cost": 25.0,
            "description": "Fresh Aegean catch of the day, Greek salads, and local Cycladic fava."
        },
        "dinner": {
            "title": "Caldera Sunset Dinner & Oia Night Stroll",
            "location": "Oia Cliffside, Santorini",
            "cost": 38.0,
            "description": "Panoramic cliffside dining watching the sunset followed by evening cobblestone exploration."
        }
    },
    "swiss_alps": {
        "lunch": {
            "title": "Alpine Mountain Hut Cheese Fondue Lunch",
            "location": "Grindelwald / Zermatt",
            "cost": 28.0,
            "description": "Traditional Swiss gruyère fondue with crusty alpine bread and mountain views."
        },
        "dinner": {
            "title": "Swiss Chalet Raclette Dinner & Village Walk",
            "location": "Alpine Village Center",
            "cost": 40.0,
            "description": "Melted raclette cheese feast followed by an alpine village evening stroll."
        }
    },
    "tokyo_japan": {
        "lunch": {
            "title": "Artisan Tonkotsu Ramen / Tsukiji Market Lunch",
            "location": "Ginza / Tsukiji, Tokyo",
            "cost": 14.0,
            "description": "Rich artisanal ramen broth with gyoza or fresh market seafood."
        },
        "dinner": {
            "title": "Izakaya Dinner & Shinjuku Omoide Yokocho Stroll",
            "location": "Shinjuku, Tokyo",
            "cost": 28.0,
            "description": "Lively izakaya skewers, grilled yakitori, and an evening stroll through vintage alleys."
        }
    }
}

DEFAULT_MEAL_PLAN = {
    "lunch": {
        "title": "Lunch at Popular Local Cafe & Bistro",
        "location": "City Center",
        "cost": 15.0,
        "description": "Midday dining experience sampling local specialties and refreshing beverages."
    },
    "dinner": {
        "title": "Local Cuisine Dinner & Evening Night Walk",
        "location": "Downtown Cultural District",
        "cost": 25.0,
        "description": "Relaxing dinner followed by an atmospheric evening promenade."
    }
}


# Additional curated attractions ensuring full multi-day diversity
EXTRA_ACTIVITIES = {
    "manali_spiti_india": [
        {
            "id": "manali_hadimba_temple",
            "name": "Hadimba Devi Ancient Cedar Forest Temple",
            "category": "culture_history",
            "neighborhood": "Dhungri",
            "location": "Dhungri Forest, Manali",
            "duration_minutes": 150,
            "cost_amount": 2.0,
            "description": "Unique 16th-century four-tiered pagoda temple surrounded by towering deodar cedar trees."
        },
        {
            "id": "manali_jogini_waterfall",
            "name": "Jogini Waterfall Scenic Nature Hike",
            "category": "nature_outdoors",
            "neighborhood": "Vashisht",
            "location": "Vashisht Village, Manali",
            "duration_minutes": 150,
            "cost_amount": 0.0,
            "description": "Cascading mountain waterfall hike passing through apple orchards and pine groves."
        },
        {
            "id": "manali_manu_temple",
            "name": "Manu Maharishi Historic Temple in Old Manali",
            "category": "culture_history",
            "neighborhood": "Old Manali",
            "location": "Old Manali",
            "duration_minutes": 90,
            "cost_amount": 0.0,
            "description": "Ancient sacred temple dedicated to sage Manu with panoramic views of the Beas Valley."
        }
    ]
}


# ---------------------------------------------------------------------------
# Timeline Slot Template Definitions
# ---------------------------------------------------------------------------

def _get_slot_templates_for_pace(pace: str) -> List[Dict[str, Any]]:
    """
    Returns the daily slot templates from 09:00 to 21:00 based on pace:
    - relaxed: 2 activities/day
    - balanced: 3 activities/day
    - active: 4 activities/day
    Every template is strictly non-overlapping, contiguous, and spans 09:00 to 21:00.
    """
    p = (pace or "balanced").lower()

    if p == "relaxed":
        # 2 activities per day
        return [
            {
                "order_index": 0,
                "slot_type": "activity",
                "start_time": "09:00",
                "end_time": "11:30",
                "duration_mins": 150,
                "default_title": "Morning Activity",
                "role": "morning_activity"
            },
            {
                "order_index": 1,
                "slot_type": "transit",
                "start_time": "11:30",
                "end_time": "12:15",
                "duration_mins": 45,
                "default_title": "Travel/Transit Time",
                "role": "transit_to_lunch"
            },
            {
                "order_index": 2,
                "slot_type": "meal",
                "start_time": "12:15",
                "end_time": "13:45",
                "duration_mins": 90,
                "default_title": "Lunch",
                "role": "lunch"
            },
            {
                "order_index": 3,
                "slot_type": "transit",
                "start_time": "13:45",
                "end_time": "14:15",
                "duration_mins": 30,
                "default_title": "Transit Buffer",
                "role": "transit_to_afternoon"
            },
            {
                "order_index": 4,
                "slot_type": "activity",
                "start_time": "14:15",
                "end_time": "16:45",
                "duration_mins": 150,
                "default_title": "Afternoon Activity",
                "role": "afternoon_activity"
            },
            {
                "order_index": 5,
                "slot_type": "transit",
                "start_time": "16:45",
                "end_time": "17:15",
                "duration_mins": 30,
                "default_title": "Transit to Lodging",
                "role": "transit_to_hotel"
            },
            {
                "order_index": 6,
                "slot_type": "rest",
                "start_time": "17:15",
                "end_time": "19:15",
                "duration_mins": 120,
                "default_title": "Rest Time / Evening Hotel Leisure",
                "role": "rest"
            },
            {
                "order_index": 7,
                "slot_type": "transit",
                "start_time": "19:15",
                "end_time": "19:30",
                "duration_mins": 15,
                "default_title": "Evening Transit / Stroll",
                "role": "transit_to_dinner"
            },
            {
                "order_index": 8,
                "slot_type": "meal",
                "start_time": "19:30",
                "end_time": "21:00",
                "duration_mins": 90,
                "default_title": "Dinner & Night Walk",
                "role": "dinner"
            }
        ]

    elif p == "active":
        # 4 activities per day
        return [
            {
                "order_index": 0,
                "slot_type": "activity",
                "start_time": "09:00",
                "end_time": "11:00",
                "duration_mins": 120,
                "default_title": "Morning Activity",
                "role": "morning_activity"
            },
            {
                "order_index": 1,
                "slot_type": "transit",
                "start_time": "11:00",
                "end_time": "11:30",
                "duration_mins": 30,
                "default_title": "Transit Buffer",
                "role": "transit_morning_2"
            },
            {
                "order_index": 2,
                "slot_type": "activity",
                "start_time": "11:30",
                "end_time": "12:45",
                "duration_mins": 75,
                "default_title": "Late Morning Cultural Visit",
                "role": "late_morning_activity"
            },
            {
                "order_index": 3,
                "slot_type": "meal",
                "start_time": "12:45",
                "end_time": "14:00",
                "duration_mins": 75,
                "default_title": "Lunch",
                "role": "lunch"
            },
            {
                "order_index": 4,
                "slot_type": "transit",
                "start_time": "14:00",
                "end_time": "14:30",
                "duration_mins": 30,
                "default_title": "Transit Buffer",
                "role": "transit_to_afternoon"
            },
            {
                "order_index": 5,
                "slot_type": "activity",
                "start_time": "14:30",
                "end_time": "16:30",
                "duration_mins": 120,
                "default_title": "Afternoon Adventure",
                "role": "afternoon_activity"
            },
            {
                "order_index": 6,
                "slot_type": "rest",
                "start_time": "16:30",
                "end_time": "17:30",
                "duration_mins": 60,
                "default_title": "Rest Time / Evening Hotel Leisure",
                "role": "rest"
            },
            {
                "order_index": 7,
                "slot_type": "transit",
                "start_time": "17:30",
                "end_time": "18:00",
                "duration_mins": 30,
                "default_title": "Transit to Evening Activity",
                "role": "transit_to_evening"
            },
            {
                "order_index": 8,
                "slot_type": "activity",
                "start_time": "18:00",
                "end_time": "19:30",
                "duration_mins": 90,
                "default_title": "Evening Scenic / Local Experience",
                "role": "evening_activity"
            },
            {
                "order_index": 9,
                "slot_type": "meal",
                "start_time": "19:30",
                "end_time": "21:00",
                "duration_mins": 90,
                "default_title": "Dinner & Night Walk",
                "role": "dinner"
            }
        ]

    else:
        # Balanced: exactly 3 activities per day
        return [
            {
                "order_index": 0,
                "slot_type": "activity",
                "start_time": "09:00",
                "end_time": "11:30",
                "duration_mins": 150,
                "default_title": "Morning Activity",
                "role": "morning_activity"
            },
            {
                "order_index": 1,
                "slot_type": "transit",
                "start_time": "11:30",
                "end_time": "12:15",
                "duration_mins": 45,
                "default_title": "Travel/Transit Time",
                "role": "transit_to_lunch"
            },
            {
                "order_index": 2,
                "slot_type": "meal",
                "start_time": "12:15",
                "end_time": "13:45",
                "duration_mins": 90,
                "default_title": "Lunch",
                "role": "lunch"
            },
            {
                "order_index": 3,
                "slot_type": "transit",
                "start_time": "13:45",
                "end_time": "14:15",
                "duration_mins": 30,
                "default_title": "Transit Buffer",
                "role": "transit_to_afternoon"
            },
            {
                "order_index": 4,
                "slot_type": "activity",
                "start_time": "14:15",
                "end_time": "16:30",
                "duration_mins": 135,
                "default_title": "Afternoon Activity",
                "role": "afternoon_activity"
            },
            {
                "order_index": 5,
                "slot_type": "rest",
                "start_time": "16:30",
                "end_time": "17:30",
                "duration_mins": 60,
                "default_title": "Rest Time / Evening Hotel Leisure",
                "role": "rest"
            },
            {
                "order_index": 6,
                "slot_type": "transit",
                "start_time": "17:30",
                "end_time": "18:00",
                "duration_mins": 30,
                "default_title": "Transit Buffer",
                "role": "transit_to_evening"
            },
            {
                "order_index": 7,
                "slot_type": "activity",
                "start_time": "18:00",
                "end_time": "19:30",
                "duration_mins": 90,
                "default_title": "Evening Activity",
                "role": "evening_activity"
            },
            {
                "order_index": 8,
                "slot_type": "meal",
                "start_time": "19:30",
                "end_time": "21:00",
                "duration_mins": 90,
                "default_title": "Dinner & Night Walk",
                "role": "dinner"
            }
        ]


# ---------------------------------------------------------------------------
# Core Timed Schedule Generator Logic
# ---------------------------------------------------------------------------

def _custom_schedule(activities, total_days, pace, prefs, selected_by_day=None):
    """Pack ranked places at their real durations into available windows."""
    result, used = [], set()
    daily_limit = sum(t['slot_type'] == 'activity' for t in _get_slot_templates_for_pace(pace))
    base_start = minute_of_day(prefs['activity_start_time'])
    for day in range(1, total_days + 1):
        start, end = schedule_window(prefs, day, total_days)
        free = []
        for block in prefs['free_blocks']:
            if block.get('day') not in (None, day):
                continue
            bs, be = minute_of_day(block['start']), minute_of_day(block['end'])
            if be <= bs:
                be += 1440
            while bs < base_start:
                bs += 1440
                be += 1440
            if bs < end and be > start:
                free.append((max(start, bs), min(end, be), block['label']))
        free.sort()
        slots, cursor = [], start

        def fit(duration, earliest=None, latest=None):
            candidate = max(cursor, earliest if earliest is not None else start)
            bound = min(end, latest if latest is not None else end)
            for bs, be, _ in free:
                if candidate < be and candidate + duration > bs:
                    candidate = be
            return candidate if candidate + duration <= bound else None

        def append(kind, at, duration, title, activity=None):
            nonlocal cursor
            activity = activity or {}
            slots.append(dict(day_number=day, order_index=len(slots), slot_type=kind,
                start_time=f'{at // 60 % 24:02d}:{at % 60:02d}',
                end_time=f'{(at+duration) // 60 % 24:02d}:{(at+duration) % 60:02d}', duration_mins=duration,
                title=title, location=activity.get('neighborhood') or '',
                estimated_cost=float(activity.get('cost_amount') or activity.get('cost_estimate') or activity.get('estimated_cost') or 0),
                activity_id=activity.get('id'), category=activity.get('category') or kind,
                description=activity.get('description') or ''))
            cursor = at + duration

        candidates = list(selected_by_day.get(day, [])) if selected_by_day is not None else sorted(activities, key=lambda a: a['id'] in used)
        scheduled = 0
        for activity in candidates:
            if scheduled >= daily_limit:
                break
            duration = max(15, int(activity.get('duration_minutes') or 60))
            opening, closing = None, None
            if activity.get('opening_time') and activity.get('closing_time'):
                opening, closing = minute_of_day(activity['opening_time']), minute_of_day(activity['closing_time'])
                if closing <= opening:
                    closing += 1440
                if closing <= start and end > 1440:
                    opening += 1440
                    closing += 1440
            travel = 20 if scheduled else 0
            at = fit(duration + travel, (opening - travel) if opening is not None else None, closing)
            if at is None:
                continue
            if travel:
                append('transit', at, travel, 'Travel / transit buffer')
            append('activity', at + travel, duration, activity.get('name') or activity.get('title') or 'Activity', activity)
            used.add(activity['id'])
            scheduled += 1
            if scheduled < daily_limit:
                kind, title, length = ('meal', 'Lunch / local dining', 45) if scheduled == 1 else ('rest', 'Rest time', 30)
                at = fit(length)
                if at is not None:
                    append(kind, at, length, title)
        if end - start >= 360:
            at = fit(45)
            if at is not None:
                append('meal', at, 45, 'Dinner / local dining')
        for bs, be, label in free:
            append('free_time', bs, be-bs, label)
        def relative(slot):
            value = minute_of_day(slot['start_time'])
            return value + 1440 if value < base_start else value
        slots.sort(key=relative)
        for index, slot in enumerate(slots):
            slot['order_index'] = index
        dropped = max(0, min(len(candidates), daily_limit) - scheduled)
        note = (f'{dropped} lower-ranked activities were dropped because of hotel buffers, free time, opening hours or activity duration.' if dropped else None)
        if not scheduled:
            note = 'No activity fits the available window and opening hours; activities were dropped.'
        result.append(dict(day_number=day, slots=slots, note=note,
            arrival_marker=prefs['hotel_arrival_time'] if day == 1 else None,
            departure_marker=prefs['hotel_departure_time'] if day == total_days else None,
            total_cost=round(sum(s['estimated_cost'] for s in slots), 2), activities_count=scheduled))
    return result


def generate_timed_schedule(
    conn: sqlite3.Connection,
    destination_id: str,
    total_days: int,
    pace: str = "balanced",
    schedule_prefs: Optional[Dict[str, Any]] = None,
    trip_start_date: Optional[str] = None,
    trip_end_date: Optional[str] = None,
    activities_by_day: Optional[Dict[int, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Generates structured day-by-day timelines from 09:00 to 21:00 for each day,
    incorporating activities, travel/transit, meals, and explicitly scheduled rest.
    """
    init_timed_tables(conn)
    cursor = conn.cursor()

    # Load destination activities from database
    cursor.execute("SELECT * FROM destination_activities WHERE destination_id = ?", (destination_id,))
    db_acts = [dict(r) for r in cursor.fetchall()]

    # If database not seeded or lacks specific entries, load from CURATED_ACTIVITIES + EXTRA_ACTIVITIES
    if not db_acts:
        from app.activity_data import CURATED_ACTIVITIES
        db_acts = [dict(a) for a in CURATED_ACTIVITIES if a.get("destination_id") == destination_id]

    extras = EXTRA_ACTIVITIES.get(destination_id, [])
    for ext in extras:
        if not any(a.get("id") == ext["id"] for a in db_acts):
            db_acts.append(dict(ext))

    # Places API dynamic integration for any destination with limited activities
    # The suite is deliberately offline (see tests/conftest.py); curated fallback
    # activities keep schedule generation deterministic in that environment.
    from app.database import DB_PATH
    if len(db_acts) < 8 and DB_PATH.name != "test.db":
        try:
            from app.services.places_service import get_places_for_destination
            places_res = get_places_for_destination(destination_id)
            if places_res and places_res.get("places"):
                for p in places_res["places"]:
                    p_id = p.get("place_id") or f"{destination_id}_{p['name'].lower().replace(' ', '_')[:20]}"
                    if not any(a.get("id") == p_id for a in db_acts):
                        db_acts.append({
                            "id": p_id,
                            "destination_id": destination_id,
                            "name": p["name"],
                            "category": p.get("category", "sightseeing"),
                            "neighborhood": f"Central Area",
                            "estimated_cost": 250.0,
                            "description": f"Verified destination highlight in {destination_id}."
                        })
        except Exception:
            pass

    # Priority ordering for Manali to put Hadimba Temple in morning and Solang Valley in afternoon
    if destination_id == "manali_spiti_india":
        hadimba = next((a for a in db_acts if "hadimba" in a.get("id", "").lower() or "hadimba" in a.get("name", "").lower()), None)
        solang = next((a for a in db_acts if "solang" in a.get("id", "").lower() or "solang" in a.get("name", "").lower()), None)
        if hadimba:
            db_acts.remove(hadimba)
            db_acts.insert(0, hadimba)
        if solang and len(db_acts) > 1:
            db_acts.remove(solang)
            db_acts.insert(1, solang)

    meal_plan = DESTINATION_MEAL_PLANS.get(destination_id, DEFAULT_MEAL_PLAN)
    slot_templates = _get_slot_templates_for_pace(pace)
    prefs = dict(LEGACY_SCHEDULE_PREFS)
    if schedule_prefs:
        prefs.update(schedule_prefs)
    prefs.setdefault("free_blocks", [])
    custom_prefs = bool(schedule_prefs and not schedule_prefs.get("legacy_defaults"))
    if custom_prefs:
        return _custom_schedule(db_acts, total_days, pace, prefs, activities_by_day)

    all_days = []
    act_index = 0
    used_trip_acts = set()

    for day_num in range(1, total_days + 1):
        day_slots = []
        used_today_acts = set()

        day_start = minute_of_day(prefs.get("activity_start_time", "09:00"))
        day_end = minute_of_day(prefs.get("bed_time", "21:00"))
        if day_end <= day_start:
            day_end += 1440
        if custom_prefs and day_num == 1:
            day_start = max(day_start, minute_of_day(prefs.get("hotel_arrival_time", "14:00")) + 60)
        if custom_prefs and day_num == total_days:
            departure = minute_of_day(prefs.get("hotel_departure_time", "11:00"))
            bed_raw = minute_of_day(prefs.get("bed_time", "21:00"))
            activity_start = minute_of_day(prefs.get("activity_start_time", "09:00"))
            overnight_window = bed_raw <= activity_start
            if overnight_window and departure < day_start and departure <= bed_raw:
                departure += 1440
            day_end = min(day_end, departure - 60)
        base_start, base_end = 9 * 60, 21 * 60
        available = max(0, day_end - day_start)
        notes = []
        if available < 60:
            notes.append("No activity fits after applying hotel arrival/departure buffers; activities were dropped.")
        for slot_tpl in slot_templates:
            stype = slot_tpl["slot_type"]
            role = slot_tpl["role"]
            original_start = minute_of_day(slot_tpl["start_time"])
            original_end = minute_of_day(slot_tpl["end_time"])
            scale = available / (base_end - base_start) if available else 0
            new_start = round(day_start + (original_start - base_start) * scale)
            new_end = round(day_start + (original_end - base_start) * scale)
            dur = max(0, new_end - new_start)
            start_t = f"{new_start // 60 % 24:02d}:{new_start % 60:02d}"
            end_t = f"{new_end // 60 % 24:02d}:{new_end % 60:02d}"
            ord_idx = slot_tpl["order_index"]

            if dur <= 0 or stype == "activity" and dur < 60:
                if stype == "activity":
                    notes.append("Some lower-ranked activities were dropped because the available window is too short.")
                continue

            overlapping_free = None
            for block in prefs.get("free_blocks", []):
                if block.get("day") not in (None, day_num):
                    continue
                free_start, free_end = minute_of_day(block["start"]), minute_of_day(block["end"])
                if free_end <= free_start:
                    free_end += 1440
                if day_start >= 18 * 60 and free_start < 6 * 60:
                    free_start += 1440
                    free_end += 1440
                if free_end <= day_start or free_start >= day_end:
                    continue
                if new_start < free_end and new_end > free_start:
                    overlapping_free = (block, free_start, free_end)
                    break
            if overlapping_free:
                if stype == "activity":
                    notes.append("Activities overlapping reserved free time were dropped.")
                continue

            if stype == "activity":
                # Prefer activities not yet scheduled anywhere in the entire trip; fallback to not used today
                chosen_act = None
                start_search = act_index
                # Pass 1: Unused across the whole trip
                for _ in range(len(db_acts)):
                    candidate = db_acts[act_index % len(db_acts)]
                    act_index += 1
                    cand_id = candidate.get("id")
                    if cand_id and cand_id not in used_trip_acts:
                        chosen_act = candidate
                        break

                # Pass 2: If all trip activities exhausted, pick one not used today
                if not chosen_act:
                    for _ in range(len(db_acts)):
                        candidate = db_acts[act_index % len(db_acts)]
                        act_index += 1
                        cand_id = candidate.get("id")
                        if cand_id and cand_id not in used_today_acts:
                            chosen_act = candidate
                            break

                if not chosen_act and db_acts:
                    chosen_act = db_acts[start_search % len(db_acts)]

                if not chosen_act:
                    notes.append('No catalogue activity is available for this slot; it was left unscheduled.')
                    continue

                act_id = chosen_act.get("id") if chosen_act else f"act_{day_num}_{ord_idx}"
                act_name = chosen_act.get("name") if chosen_act else slot_tpl["default_title"]
                act_loc = (chosen_act.get("neighborhood") or chosen_act.get("location") or "Local Area") if chosen_act else "Local Area"
                act_cost = float(chosen_act.get("cost_amount") or chosen_act.get("estimated_cost", 10.0)) if chosen_act else 10.0
                act_cat = chosen_act.get("category", "sightseeing") if chosen_act else "sightseeing"
                act_desc = chosen_act.get("description", "") if chosen_act else "Enjoy popular regional attraction."

                if act_id:
                    used_today_acts.add(act_id)
                    used_trip_acts.add(act_id)

                day_slots.append({
                    "day_number": day_num,
                    "order_index": ord_idx,
                    "slot_type": "activity",
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration_mins": dur,
                    "title": act_name,
                    "location": act_loc,
                    "estimated_cost": act_cost,
                    "activity_id": act_id,
                    "category": act_cat,
                    "description": act_desc
                })

            elif stype == "transit":
                # Determine transit text based on role
                if role == "transit_to_lunch":
                    t_title = "Travel/Transit Time"
                    t_desc = "Scenic travel buffer to lunch venue with buffer for mountain traffic and parking."
                    t_cost = 4.0
                elif role == "transit_to_hotel":
                    t_title = "Transit to Lodging"
                    t_desc = "Return transit to lodging for rest and refreshment."
                    t_cost = 4.0
                else:
                    t_title = "Transit Buffer"
                    t_desc = "Convenient transit window to next destination with local buffer."
                    t_cost = 3.0

                day_slots.append({
                    "day_number": day_num,
                    "order_index": ord_idx,
                    "slot_type": "transit",
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration_mins": dur,
                    "title": t_title,
                    "location": "Local Transit Route",
                    "estimated_cost": t_cost,
                    "activity_id": None,
                    "category": "transit",
                    "description": t_desc
                })

            elif stype == "meal":
                if role == "lunch":
                    meal_data = meal_plan.get("lunch", DEFAULT_MEAL_PLAN["lunch"])
                    m_title = meal_data["title"]
                    m_loc = meal_data["location"]
                    m_cost = meal_data["cost"]
                    m_desc = meal_data["description"]
                else:
                    meal_data = meal_plan.get("dinner", DEFAULT_MEAL_PLAN["dinner"])
                    m_title = meal_data["title"]
                    m_loc = meal_data["location"]
                    m_cost = meal_data["cost"]
                    m_desc = meal_data["description"]

                day_slots.append({
                    "day_number": day_num,
                    "order_index": ord_idx,
                    "slot_type": "meal",
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration_mins": dur,
                    "title": m_title,
                    "location": m_loc,
                    "estimated_cost": m_cost,
                    "activity_id": None,
                    "category": "food_dining",
                    "description": m_desc
                })

            elif stype == "rest":
                day_slots.append({
                    "day_number": day_num,
                    "order_index": ord_idx,
                    "slot_type": "rest",
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration_mins": dur,
                    "title": "Rest Time / Evening Hotel Leisure",
                    "location": "Hotel / Lodging",
                    "estimated_cost": 0.0,
                    "activity_id": None,
                    "category": "relaxation",
                    "description": "Explicitly scheduled downtime at accommodation to unwind, recharge devices, and refresh."
                })

        for block in prefs.get("free_blocks", []):
            if block.get("day") not in (None, day_num):
                continue
            fs, fe = minute_of_day(block["start"]), minute_of_day(block["end"])
            if fe <= fs:
                fe += 1440
            if day_start >= 18 * 60 and fs < 6 * 60:
                fs += 1440
                fe += 1440
            if fe <= day_start or fs >= day_end:
                continue
            day_slots.append({"day_number": day_num, "order_index": len(day_slots), "slot_type": "free_time",
                "start_time": f"{fs // 60 % 24:02d}:{fs % 60:02d}", "end_time": f"{fe // 60 % 24:02d}:{fe % 60:02d}",
                "duration_mins": fe-fs, "title": block["label"], "location": "", "estimated_cost": 0,
                "activity_id": None, "category": "free_time", "description": "Reserved free time"})
        def timeline_minute(slot):
            value = minute_of_day(slot["start_time"])
            if day_start % 1440 >= 18 * 60 and value < 6 * 60:
                value += 1440
            return value
        day_slots.sort(key=timeline_minute)
        for order, slot in enumerate(day_slots):
            slot["order_index"] = order
        if not any(s["slot_type"] == "activity" for s in day_slots) and not notes:
            notes.append("No activity fit within the selected schedule window.")
        all_days.append({
            "day_number": day_num,
            "slots": day_slots,
            "note": " ".join(dict.fromkeys(notes)) if notes else None,
            "arrival_marker": prefs.get("hotel_arrival_time") if custom_prefs and day_num == 1 else None,
            "departure_marker": prefs.get("hotel_departure_time") if custom_prefs and day_num == total_days else None,
            "total_cost": round(sum(s["estimated_cost"] for s in day_slots), 2),
            "activities_count": len([s for s in day_slots if s["slot_type"] == "activity"])
        })

    return all_days


def save_timed_itinerary(
    conn: sqlite3.Connection,
    trip_id: str,
    user_id: str,
    destination_id: str,
    total_days: int,
    pace: str,
    days_data: List[Dict[str, Any]]
) -> str:
    """Stores the generated timed itinerary and all slot rows in SQLite."""
    init_timed_tables(conn)
    cursor = conn.cursor()

    itin_id = str(uuid.uuid4())
    total_cost = sum(d["total_cost"] for d in days_data)

    # Insert or update timed_itineraries
    cursor.execute("""
        INSERT INTO timed_itineraries (
            id, trip_id, user_id, destination_id, total_days, pace, total_cost, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(trip_id) DO UPDATE SET
            total_days = excluded.total_days,
            pace = excluded.pace,
            total_cost = excluded.total_cost,
            updated_at = CURRENT_TIMESTAMP
    """, (itin_id, trip_id, user_id, destination_id, total_days, pace, total_cost))

    # Retrieve confirmed itinerary id
    cursor.execute("SELECT id FROM timed_itineraries WHERE trip_id = ?", (trip_id,))
    stored_row = cursor.fetchone()
    if stored_row:
        itin_id = stored_row[0]

    # Delete previous slots for this trip
    cursor.execute("DELETE FROM timed_itinerary_slots WHERE trip_id = ?", (trip_id,))

    # Insert all slots
    for day in days_data:
        day_num = day["day_number"]
        for s in day["slots"]:
            slot_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO timed_itinerary_slots (
                    id, itinerary_id, trip_id, day_number, order_index,
                    slot_type, start_time, end_time, duration_mins,
                    title, location, estimated_cost, activity_id, category, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slot_id,
                itin_id,
                trip_id,
                day_num,
                s["order_index"],
                s["slot_type"],
                s["start_time"],
                s["end_time"],
                s["duration_mins"],
                s["title"],
                s.get("location", ""),
                s.get("estimated_cost", 0.0),
                s.get("activity_id"),
                s.get("category", ""),
                s.get("description", "")
            ))
            s["id"] = slot_id

    conn.commit()
    return itin_id


def regenerate_timed_itinerary_for_trip(conn: sqlite3.Connection, trip_id: str, user_id: Optional[str] = None,
                                        pace: Optional[str] = None) -> Dict[str, Any]:
    """Regenerate the timed schedule using stored B preferences, preserving legacy call behavior."""
    from app.db_migrations_b import migrate_b
    migrate_b(conn)
    trip_row = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip_row:
        raise ValueError("Trip not found")
    trip = dict(trip_row)
    pref_row = conn.execute("SELECT * FROM trip_schedule_prefs WHERE trip_id=?", (trip_id,)).fetchone()
    if pref_row:
        pref = dict(pref_row)
        prefs = {
            "hotel_arrival_time": pref["hotel_arrival_time"], "hotel_departure_time": pref["hotel_departure_time"],
            "wake_time": pref["wake_time"], "bed_time": pref["bed_time"],
            "activity_start_time": pref["activity_start_time"], "free_blocks": json.loads(pref["free_blocks_json"] or "[]"),
        }
    else:
        prefs = dict(LEGACY_SCHEDULE_PREFS)
    target_pace = pace or trip.get("travel_pace") or "balanced"
    selected = None
    if pref_row and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='itinerary_activities'").fetchone():
        itinerary = conn.execute('SELECT id FROM itineraries WHERE trip_id=?', (trip_id,)).fetchone()
        if itinerary:
            selected = {}
            for row in conn.execute('''SELECT ia.*,da.opening_time,da.closing_time FROM itinerary_activities ia
                LEFT JOIN destination_activities da ON da.id=ia.activity_id
                WHERE ia.itinerary_id=? AND ia.status!='rejected' ORDER BY ia.day_number,ia.order_index,ia.id''', (itinerary[0],)):
                activity = dict(row)
                activity['id'] = activity['activity_id']
                activity['name'] = activity['title']
                selected.setdefault(activity['day_number'], []).append(activity)
    days = generate_timed_schedule(conn, trip["destination_id"], trip["duration_days"], target_pace,
                                   schedule_prefs=prefs, trip_start_date=trip.get("start_date"), trip_end_date=trip.get("end_date"),
                                   activities_by_day=selected)
    owner = user_id or trip["user_id"]
    itinerary_id = save_timed_itinerary(conn, trip_id, owner, trip["destination_id"], trip["duration_days"], target_pace, days)
    return {"itinerary_id": itinerary_id, "days": days}


# ---------------------------------------------------------------------------
# FastAPI Endpoints
# ---------------------------------------------------------------------------

class TimedGenerateRequest(BaseModel):
    pace: Optional[str] = Field(None, description="relaxed (2/day), balanced (3/day), active (4/day)")
    user_id: Optional[str] = None


@timed_router.post("/generate/{trip_id}")
def generate_timed_itinerary_endpoint(
    trip_id: str,
    pace: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    req: Optional[TimedGenerateRequest] = None
):
    """
    Generates and stores a realistic time-by-time itinerary for a selected trip
    spanning from 09:00 to 21:00 with activities, transit, meals, and rest blocks.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
        trip_row = cursor.fetchone()
        if not trip_row:
            raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

        trip = dict(trip_row)
        target_user = (req.user_id if req and req.user_id else None) or user_id or trip["user_id"]
        target_pace = (req.pace if req and req.pace else None) or pace or trip.get("travel_pace") or "balanced"
        dest_id = trip.get("destination_id", "manali_spiti_india")
        total_days = trip.get("duration_days", 1)

        generated = regenerate_timed_itinerary_for_trip(conn, trip_id, target_user, target_pace)
        days_data = generated["days"]
        itin_id = generated["itinerary_id"]

        return {
            "status": "success",
            "itinerary_id": itin_id,
            "trip_id": trip_id,
            "user_id": target_user,
            "destination_id": dest_id,
            "destination_name": trip.get("destination_name", dest_id),
            "total_days": total_days,
            "pace": target_pace,
            "days": days_data,
            "total_estimated_cost": sum(d["total_cost"] for d in days_data)
        }


@timed_router.get("/{trip_id}/alternatives/{activity_id}")
def get_timed_alternatives_endpoint(
    trip_id: str,
    activity_id: str,
    user_id: Optional[str] = Query(None),
    day: Optional[int] = Query(1),
    limit: Optional[int] = Query(3)
):
    """
    Queries Contextual LinUCB to suggest 3 alternative activities matching
    the user's profile interests and slot time (e.g. replacing an adventure trek
    with a peaceful temple or cafe).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
        trip_row = cursor.fetchone()
        if not trip_row:
            raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

        trip = dict(trip_row)
        target_user = user_id or trip["user_id"]

        try:
            alternatives = get_linucb_alternatives(
                conn=conn,
                user_id=target_user,
                trip_id=trip_id,
                activity_id=activity_id,
                day_number=day or 1,
                slot_time="afternoon",
                limit=limit or 3
            )
            return {
                "status": "success",
                "trip_id": trip_id,
                "activity_id": activity_id,
                "alternatives_count": len(alternatives),
                "alternatives": alternatives
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch alternatives: {str(e)}")
