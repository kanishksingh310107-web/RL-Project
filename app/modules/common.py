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
