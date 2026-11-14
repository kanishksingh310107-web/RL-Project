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
        if not r:
            return None
        trip = _decode(r)
        from app.core.party import normalize_party, party_type, party_label
        trip['party'] = normalize_party(trip)
        trip['companions'] = trip['party_type'] = party_type(trip['party'])
        trip['party_label'] = party_label(trip['party'])
        trip['has_children'] = bool(trip['party']['children'])
        trip['has_elderly'] = bool(trip['party']['seniors'])
        return trip

def get_user_context(user_id: str) -> Dict[str, Any]:
    """Whatever the user has told us so far, unified into structured dict and answer lookup."""
    out: Dict[str, Any] = {}
    with get_connection() as conn:
        for key, table in (("basic", "traveller_profiles"), ("detailed", "detailed_profiles"),
                           ("precision", "precision_profiles")):
            r = conn.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)).fetchone()
            out[key] = _decode(r) if r else None

    # Build unified answers map across all three tiers
    answers: Dict[str, Any] = {}
    if out.get("basic"):
        raw_b = out["basic"].get("raw_answers_json") or {}
        if isinstance(raw_b, str):
            try: raw_b = json.loads(raw_b)
            except Exception: raw_b = {}
        answers.update(raw_b)
        for f in ["age_group", "travel_experience", "companions", "planning_approach", "travel_goals",
                  "place_interests", "experience_preference", "dietary", "preferred_climate", "budget_tier", "assistance_autonomy"]:
            if f in out["basic"] and out["basic"][f] is not None:
                answers[f] = out["basic"][f]

    if out.get("detailed"):
        raw_d = out["detailed"].get("raw_answers_json") or {}
        if isinstance(raw_d, str):
            try: raw_d = json.loads(raw_d)
            except Exception: raw_d = {}
        answers.update(raw_d)
        for f in ["avoidances", "walking_tolerance", "schedule_density", "accessibility", "dietary", "stay_style", "transit_pref"]:
            if f in out["detailed"] and out["detailed"][f] is not None:
                answers[f] = out["detailed"][f]

    if out.get("precision"):
        raw_p = out["precision"].get("answers_json") or {}
        if isinstance(raw_p, str):
            try: raw_p = json.loads(raw_p)
            except Exception: raw_p = {}
        answers.update(raw_p)

    out["answers"] = answers
    
    # Extract hard constraints
    from app.precision import derive_insights
    out["insights"] = derive_insights(answers, answers)
    
    # Avoidances set
    av = answers.get("q12") or answers.get("avoidances") or []
    if isinstance(av, str): av = [av]
    out["avoidances"] = set([str(x).lower() for x in av])
    
    # Allergies set
    allergies = set()
    for q_all in ["q10", "q95", "q96"]:
        val = answers.get(q_all) or []
        if isinstance(val, str): val = [val]
        allergies.update([str(x).lower() for x in val])
    out["allergies"] = allergies
    
    out["walking_tolerance"] = answers.get("q74") or answers.get("walking_tolerance") or "medium"
    
    # Dietary restrictions
    diet = set()
    for q_diet in ["q20", "dietary", "q93"]:
        val = answers.get(q_diet) or []
        if isinstance(val, str): val = [val]
        diet.update([str(x).lower() for x in val if x != "none"])
    out["dietary_restrictions"] = diet

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
    """Recognize the saved Level 2 questionnaire or completed Level 3 profile."""
    if not user_id:
        return False
    cursor = conn.cursor()
    # 1. Check Level 3 adaptive precision profile
    cursor.execute("SELECT answers_json, coverage FROM precision_profiles WHERE user_id = ?", (user_id,))
    p_row = cursor.fetchone()
    if p_row and p_row[0]:
        try:
            answers = json.loads(p_row[0]) if isinstance(p_row[0], str) else p_row[0]
            if isinstance(answers, dict) and answers and float(p_row[1] or 0) >= 0.999:
                return True
        except Exception:
            pass

    row = conn.execute('SELECT raw_answers_json FROM detailed_profiles WHERE user_id=?', (user_id,)).fetchone()
    if row and row[0]:
        try:
            answers = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            if isinstance(answers, dict) and answers:
                return True
        except (TypeError, ValueError):
            pass
    return False
