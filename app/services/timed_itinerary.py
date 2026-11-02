"""Timed Day-by-Day Itinerary Engine.
Schedules a realistic time-by-time itinerary for a selected trip starting from 09:00 to 21:00,
incorporating transit buffers, meal times, rest periods, and activities based on travel pace.
"""
import uuid
import json
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database import get_connection
from app.api import router
from app.services.suggestion_engine import get_linucb_alternatives

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

def generate_timed_schedule(
    conn: sqlite3.Connection,
    destination_id: str,
    total_days: int,
    pace: str = "balanced"
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

    all_days = []
    act_index = 0

    for day_num in range(1, total_days + 1):
        day_slots = []
        used_today_acts = set()

        for slot_tpl in slot_templates:
            stype = slot_tpl["slot_type"]
            role = slot_tpl["role"]
            start_t = slot_tpl["start_time"]
            end_t = slot_tpl["end_time"]
            dur = slot_tpl["duration_mins"]
            ord_idx = slot_tpl["order_index"]

            if stype == "activity":
                # Find an unused activity for today
                chosen_act = None
                start_search = act_index
                for _ in range(len(db_acts)):
                    candidate = db_acts[act_index % len(db_acts)]
                    act_index += 1
                    if candidate.get("id") not in used_today_acts:
                        chosen_act = candidate
                        break
                if not chosen_act and db_acts:
                    chosen_act = db_acts[start_search % len(db_acts)]

                act_id = chosen_act.get("id") if chosen_act else f"act_{day_num}_{ord_idx}"
                act_name = chosen_act.get("name") if chosen_act else slot_tpl["default_title"]
                act_loc = chosen_act.get("neighborhood") or chosen_act.get("location") or "Local Area"
                act_cost = float(chosen_act.get("cost_amount") or chosen_act.get("estimated_cost", 10.0)) if chosen_act else 10.0
                act_cat = chosen_act.get("category", "sightseeing") if chosen_act else "sightseeing"
                act_desc = chosen_act.get("description", "") if chosen_act else "Enjoy popular regional attraction."

                if act_id:
                    used_today_acts.add(act_id)

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

        all_days.append({
            "day_number": day_num,
            "slots": day_slots,
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

        days_data = generate_timed_schedule(
            conn=conn,
            destination_id=dest_id,
            total_days=total_days,
            pace=target_pace
        )

        itin_id = save_timed_itinerary(
            conn=conn,
            trip_id=trip_id,
            user_id=target_user,
            destination_id=dest_id,
            total_days=total_days,
            pace=target_pace,
            days_data=days_data
        )

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


# ---------------------------------------------------------------------------
# Route Registration Hooks
# ---------------------------------------------------------------------------

# Register routes on app.api.router (prefix "/api")
router.include_router(timed_router)

# Also expose standalone /api/itinerary/timed routes directly
@router.post("/itinerary/timed/generate/{trip_id}")
def direct_generate_timed(
    trip_id: str,
    pace: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    req: Optional[TimedGenerateRequest] = None
):
    return generate_timed_itinerary_endpoint(trip_id=trip_id, pace=pace, user_id=user_id, req=req)


@router.get("/itinerary/timed/{trip_id}/alternatives/{activity_id}")
def direct_get_timed_alternatives(
    trip_id: str,
    activity_id: str,
    user_id: Optional[str] = Query(None),
    day: Optional[int] = Query(1),
    limit: Optional[int] = Query(3)
):
    return get_timed_alternatives_endpoint(trip_id=trip_id, activity_id=activity_id, user_id=user_id, day=day, limit=limit)
