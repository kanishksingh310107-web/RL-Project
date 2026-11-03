"""Read-only helpers shared by all modules. Do not put module-specific logic here.
If you need a new shared helper, add it in YOUR module file instead (avoids merge conflicts)."""
import json
from typing import Any, Dict, List, Optional
from app.database import get_connection

def _decode(row) -> Dict[str, Any]:
    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, str) and v[:1] in "[{":
            try:
                d[k] = json.loads(v)
            except ValueError:
                pass
    return d

def get_trip(trip_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        r = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        return _decode(r) if r else None

def get_user_context(user_id: str) -> Dict[str, Any]:
    """Whatever the user has told us so far (any of these can be None)."""
    out: Dict[str, Any] = {}
    with get_connection() as conn:
        for key, table in (("basic", "traveller_profiles"), ("detailed", "detailed_profiles"),
                           ("precision", "precision_profiles")):
            r = conn.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)).fetchone()
            out[key] = _decode(r) if r else None
    return out

def get_itinerary(trip_id: str) -> Optional[Dict[str, Any]]:
    """Itinerary row + 'activities' list ordered by day/order. None if not generated yet."""
    with get_connection() as conn:
        it = conn.execute("SELECT * FROM itineraries WHERE trip_id = ?", (trip_id,)).fetchone()
        if not it:
            return None
        d = _decode(it)
        acts = conn.execute(
            "SELECT * FROM itinerary_activities WHERE itinerary_id = ? ORDER BY day_number, order_index",
            (d["id"],)).fetchall()
        d["activities"] = [_decode(a) for a in acts]
        return d

def has_completed_deep_profile(conn, user_id: str) -> bool:
    """Verifies whether the user has successfully completed and saved a deep personalization profile."""
    if not user_id:
        return False
    cursor = conn.cursor()
    # 1. Check Level 3 adaptive precision profile
    cursor.execute("SELECT answers_json, coverage FROM precision_profiles WHERE user_id = ?", (user_id,))
    p_row = cursor.fetchone()
    if p_row and p_row[0]:
        try:
            answers = json.loads(p_row[0]) if isinstance(p_row[0], str) else p_row[0]
            if isinstance(answers, dict) and len(answers) >= 2:
                return True
        except Exception:
            pass

    # 2. Check Level 2 comprehensive detailed profile
    cursor.execute("SELECT raw_answers_json, avoidances, dietary, accessibility, schedule_density FROM detailed_profiles WHERE user_id = ?", (user_id,))
    d_row = cursor.fetchone()
    if d_row:
        raw_val = d_row[0]
        if raw_val:
            try:
                raw_ans = json.loads(raw_val) if isinstance(raw_val, str) else raw_val
                if isinstance(raw_ans, dict) and len(raw_ans) >= 2:
                    return True
            except Exception:
                pass
        # Check if substantive answers exist
        for col_idx in (1, 2, 3):
            val = d_row[col_idx]
            if val and val not in ("[]", '""', "null"):
                try:
                    parsed = json.loads(val) if isinstance(val, str) else val
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return True
                except Exception:
                    pass
    return False
