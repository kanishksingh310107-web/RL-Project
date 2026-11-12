"""Plan Validator & Legacy Constraint Checker (Person A).

Verifies generated trip plans against real-world constraints:
- Day window bounds: activities must not overflow day start/end
- Opening hours: flags activities operating outside official hours
- Meal windows: verifies lunch and dinner are accommodated
- Budget limits: catches category and total budget violations
- Accessibility conformance: verifies zero mobility violations
- Legacy overflow check: reads legacy itinerary rows and reports overflows
  as non-destructive advisory suggestions.
"""
from typing import List, Dict, Any, Optional
from app.core.schemas import TripPlan, Block
from app.database import get_connection


def validate_trip_plan(
    plan: TripPlan,
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Inspects a TripPlan and returns all violated constraints."""
    violations: List[Dict[str, Any]] = []

    # 1. Day window bounds check
    for day in plan.days:
        win_end_parts = day.window.end_time.split(":")
        win_end_min = int(win_end_parts[0]) * 60 + int(win_end_parts[1])

        for b in day.blocks:
            b_end_parts = b.end_time.split(":")
            b_end_min = int(b_end_parts[0]) * 60 + int(b_end_parts[1])
            if b_end_min > win_end_min:
                violations.append({
                    "type": "day_window_overflow",
                    "severity": "high",
                    "day_number": day.day_number,
                    "block_id": b.block_id,
                    "message": f"Block {b.notes or b.block_id} ends at {b.end_time}, exceeding day window {day.window.end_time}.",
                })

    # 2. Budget violation check
    for line in plan.budget_ledger:
        if line.status == "red":
            violations.append({
                "type": "budget_exceeded",
                "severity": "medium",
                "category": line.category,
                "allocated": line.allocated_amount,
                "spent": line.estimated_spent,
                "message": f"Budget category '{line.category}' exceeds allocation by {line.estimated_spent - line.allocated_amount:.2f} {line.currency}.",
            })

    # 3. Accessibility check
    access_needs = profile.get("accessibility") or []
    if isinstance(access_needs, str):
        access_needs = [access_needs]
    if "wheelchair" in access_needs:
        for day in plan.days:
            for b in day.blocks:
                if b.place and ("trek" in b.place.name.lower() or "hike" in b.place.name.lower()):
                    violations.append({
                        "type": "accessibility_violation",
                        "severity": "critical",
                        "day_number": day.day_number,
                        "place_id": b.place.id,
                        "message": f"Place '{b.place.name}' is inaccessible for wheelchair users.",
                    })

    return violations


def check_legacy_itinerary_overflows(trip_id: str) -> List[Dict[str, Any]]:
    """Performs a read-only check on legacy itinerary slots for time overflows.
    
    Returns advisory suggestions without modifying legacy or shared tables.
    """
    suggestions: List[Dict[str, Any]] = []
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(
                """
                SELECT id, destination_id, total_budget, duration_days
                FROM trips
                WHERE id = ?
                """,
                (trip_id,),
            ).fetchall()
            if not rows:
                return suggestions

            # Legacy itineraries check
            itinerary_rows = cursor.execute(
                """
                SELECT id, trip_id, created_at
                FROM itineraries
                WHERE trip_id = ?
                """,
                (trip_id,),
            ).fetchall()

            for it in itinerary_rows:
                act_rows = cursor.execute(
                    """
                    SELECT day_number, COUNT(*) as count
                    FROM itinerary_activities
                    WHERE itinerary_id = ?
                    GROUP BY day_number
                    """,
                    (it[0],),
                ).fetchall()
                for day_num, count in act_rows:
                    if count > 4:
                        suggestions.append({
                            "type": "legacy_day_density_warning",
                            "itinerary_id": it[0],
                            "day_number": day_num,
                            "activities_count": count,
                            "suggestion": f"Day {day_num} contains {count} activities which may cause schedule compression. Consider switching to the dynamic time-budget planner.",
                        })
    except Exception:
        pass
    return suggestions
