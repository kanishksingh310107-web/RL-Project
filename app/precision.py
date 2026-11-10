"""
Level 3 "Precision Profile": Adaptive Deep Personalisation for Indian Travel Realities
Single source of truth: app/data/questionnaire_schema.json (Schema v2.0.0)

Features:
  1. PRECISION_SECTIONS / PRECISION_QUESTIONS: 27 focused deep questions across 8 sections.
  2. Conditional follow-ups (show_if): Branching based on solo safety, children, seniors, etc.
  3. Pre-fill & refinement: Connects to basic onboarding concepts.
  4. validate_answers / sanitize / privacy filter: Enforces data integrity and privacy choices.
  5. build_precision_vector: Generates normalized numerical features for RL state.
  6. derive_insights: Derives India-specific travel rules and hard constraints.
"""
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.questionnaire import QUESTIONS as BASE_QUESTIONS

_SCHEMA_PATH = Path(__file__).resolve().parent / "data" / "questionnaire_schema.json"

with open(_SCHEMA_PATH, "r", encoding="utf-8") as _f:
    SCHEMA_DATA: Dict[str, Any] = json.load(_f)

# Deep Sections (8 sections)
PRECISION_SECTIONS: List[Dict[str, Any]] = list(SCHEMA_DATA.get("deep_sections", []))

# Tunable environmental constants for insights
COLD_C = 15
WIND_KMH = 30

# Canonical Deep Question Bank
_DEEP_RAW: List[Dict[str, Any]] = [
    q for q in SCHEMA_DATA.get("questions", []) if q.get("tier") == "deep"
]

PRECISION_QUESTIONS: Dict[str, Dict[str, Any]] = {}
NEW_QUESTIONS: List[Dict[str, Any]] = []
CARRYOVER: Dict[str, Tuple[str, Dict[str, Any]]] = {}

# Alias lookup maps between new IDs and legacy IDs
LEGACY_TO_CANONICAL: Dict[str, str] = {}
CANONICAL_TO_LEGACY: Dict[str, str] = {}

for _raw in _DEEP_RAW:
    q = copy.deepcopy(_raw)
    qid = q["id"]
    if "question" not in q and "text" in q:
        q["question"] = q["text"]
    q["tier"] = "precision"
    
    PRECISION_QUESTIONS[qid] = q
    NEW_QUESTIONS.append(q)
    
    leg_id = q.get("legacy_id")
    if leg_id:
        LEGACY_TO_CANONICAL[leg_id] = qid
        CANONICAL_TO_LEGACY[qid] = leg_id
        # Also index in PRECISION_QUESTIONS under legacy id
        PRECISION_QUESTIONS[leg_id] = q

# Additional legacy question aliases for backwards compatibility
EXTRA_LEGACY_ALIASES = {
    "q95": "d11_food_allergens",
    "q103": "d21_medical_logistics",
    "q12": "d22_avoidances",
    "q64": "d02_children_age_group",
    "q73": "d19_daily_walking_km",
    "q74": "d19_daily_walking_km",
    "q75": "d16_early_starts",
    "q78": "d08_winter_cold",
    "q79": "d07_heat_humidity",
    "q81": "d05_monsoon_rain",
    "q42": "d26_proactivity",
    "q47": "d27_privacy_saving",
}

for leg, can in EXTRA_LEGACY_ALIASES.items():
    if leg not in LEGACY_TO_CANONICAL:
        LEGACY_TO_CANONICAL[leg] = can
    if leg not in PRECISION_QUESTIONS and can in PRECISION_QUESTIONS:
        PRECISION_QUESTIONS[leg] = PRECISION_QUESTIONS[can]

# Explicit legacy question definitions for backwards compatibility
PRECISION_QUESTIONS["q10"] = {
    "id": "q10", "section": "d_sec_3", "tier": "precision",
    "question": "Do you have any health or allergy triggers?", "type": "multi",
    "options": [
        {"id": "food_allergies", "label": "Food allergies"},
        {"id": "pollen_environmental", "label": "Pollen & environmental"},
        {"id": "mobility_concerns", "label": "Mobility concerns"},
        {"id": "no_concerns", "label": "No concerns"},
    ]
}
PRECISION_QUESTIONS["q11"] = {
    "id": "q11", "section": "d_sec_6", "tier": "precision",
    "question": "Do you carry personal medication or medical supplies?", "type": "multi",
    "options": [
        {"id": "personal_medication", "label": "Personal medication"},
        {"id": "daily_prescription", "label": "Daily prescription"},
        {"id": "refrigeration_needed", "label": "Refrigeration needed"},
        {"id": "no", "label": "No medication"},
    ]
}
PRECISION_QUESTIONS["q61"] = {
    "id": "q61", "section": "d_sec_4", "tier": "precision",
    "question": "How do you usually handle luggage?", "type": "single",
    "options": [
        {"id": "carry_on", "label": "Carry-on only"},
        {"id": "backpack", "label": "One backpack / duffel"},
        {"id": "one_checked", "label": "One checked bag + carry-on"},
        {"id": "multi_checked", "label": "Multiple checked bags"},
    ]
}
PRECISION_QUESTIONS["q96"] = {
    "id": "q96", "section": "d_sec_3", "tier": "precision",
    "question": "How severe are your food allergies?", "type": "single",
    "options": [
        {"id": "mild", "label": "Mild"},
        {"id": "moderate", "label": "Moderate"},
        {"id": "severe", "label": "Severe"},
    ]
}
PRECISION_QUESTIONS["q80"] = {
    "id": "q80", "section": "d_sec_2", "tier": "precision",
    "question": "Wind comfort tolerance", "type": "scale", "low": "Low", "high": "High"
}
PRECISION_QUESTIONS["q100"] = {
    "id": "q100", "section": "d_sec_3", "tier": "precision",
    "question": "Other food dislikes or ingredients to omit", "type": "text"
}

PRIVACY_CATEGORIES = [
    "interests_hobbies", "travel_prefs", "dietary_needs", "accessibility_needs",
    "env_sensitivities", "budget_prefs", "health_travel_needs", "trip_feedback",
    "save_all", "omit_health_diet", "omit_budget", "minimal"
]

CONTEXT_QIDS = [
    "b03_companions", "b05_travel_goals", "b06_place_interests", "b09_dietary",
    "q3", "q5", "q14", "q20", "q22"
]

def resolve_qid(qid: str) -> str:
    """Resolve a question ID to its canonical deep or basic question ID."""
    return LEGACY_TO_CANONICAL.get(qid, qid)

def build_context_answers(base: Dict[str, Any], detailed: Dict[str, Any]) -> Dict[str, Any]:
    """Maps stored Level 1/2 answers so show_if rules can use them."""
    ctx: Dict[str, Any] = {}
    raw = base.get("raw_answers") or base
    
    # Companions
    comp = raw.get("b03_companions") or base.get("companions") or raw.get("q3")
    if comp:
        ctx["b03_companions"] = comp
        ctx["q3"] = comp
        if comp in ("alone", "solo"):
            ctx["b03_companions"] = "solo"
        elif comp in ("family_children", "family_kids"):
            ctx["b03_companions"] = "family_kids"
            ctx["q3"] = "family_children"
        elif comp in ("family_older", "family_seniors"):
            ctx["b03_companions"] = "family_seniors"
            ctx["q3"] = "family_older"

    # Travel goals
    goals = raw.get("b05_travel_goals") or base.get("travel_goals") or raw.get("q5")
    if goals:
        ctx["b05_travel_goals"] = list(goals)
        ctx["q5"] = list(goals)

    # Place interests
    places = raw.get("b06_place_interests") or base.get("place_interests") or raw.get("q14")
    if places:
        ctx["b06_place_interests"] = list(places)
        ctx["q14"] = list(places)

    # Dietary
    diet = raw.get("b09_dietary") or base.get("dietary") or raw.get("q20")
    if diet:
        ctx["b09_dietary"] = list(diet)
        ctx["q20"] = list(diet)

    return ctx

def public_bank() -> Dict[str, Any]:
    """What the frontend receives: no internal vectorisation specs."""
    hidden = {"vec", "privacy"}
    # Return canonical deep questions only (27 questions)
    canonical_qs = {}
    for q in _DEEP_RAW:
        item = {k: v for k, v in q.items() if k not in hidden}
        if "question" not in item and "text" in item:
            item["question"] = item["text"]
        elif "text" not in item and "question" in item:
            item["text"] = item["question"]
        canonical_qs[q["id"]] = item
    return {
        "sections": PRECISION_SECTIONS,
        "questions": canonical_qs,
        "total": len(canonical_qs),
        "new_count": len(canonical_qs),
        "carried_over_count": 0
    }

# --------------------------------------------------------------------------------------
# Conditional visibility
# --------------------------------------------------------------------------------------
def _as_list(v: Any) -> List[Any]:
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple, set)) else [v]

def _cond_true(cond: Dict[str, Any], answers: Dict[str, Any]) -> bool:
    if "any" in cond:
        return any(_cond_true(c, answers) for c in cond["any"])
    if "all" in cond:
        return all(_cond_true(c, answers) for c in cond["all"])
    src = cond["q"]
    resolved_src = resolve_qid(src)

    # Check parent visibility if it is in deep questions
    if resolved_src in PRECISION_QUESTIONS and resolved_src.startswith("d") and not is_visible(resolved_src, answers):
        return False

    val = answers.get(src)
    if val is None:
        val = answers.get(resolved_src)
    if val is None and src == "q3":
        val = answers.get("b03_companions")
    if val is None and src == "b03_companions":
        val = answers.get("q3")

    arr = _as_list(val)
    # Check includes_any with normalized mapping
    targets = set(cond.get("includes_any", []))
    if "family_kids" in targets:
        targets.add("family_children")
    if "family_seniors" in targets:
        targets.add("family_older")
    if "solo" in targets:
        targets.add("alone")

    # Check allergens follow-up backwards compatibility
    if src == "q10" and "food_allergies" in targets:
        if any("allergen" in str(x).lower() or x == "food_allergies" for x in arr):
            return True

    return bool(set(arr) & targets)

def is_visible(qid: str, answers: Dict[str, Any]) -> bool:
    canonical_id = resolve_qid(qid)
    q = PRECISION_QUESTIONS.get(canonical_id) or PRECISION_QUESTIONS.get(qid)
    if not q:
        return False
    cond = q.get("show_if")
    return True if not cond else _cond_true(cond, answers)

def _is_answered(v: Any) -> bool:
    return not (v is None or v == "" or v == [] or v == {})

# --------------------------------------------------------------------------------------
# Validation, sanitising, privacy
# --------------------------------------------------------------------------------------
def validate_answers(raw: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[Dict[str, Any], List[str]]:
    """Returns (clean_answers, errors). Unanswered values are dropped. Answers to hidden questions are dropped."""
    errors: List[str] = []
    clean: Dict[str, Any] = {}
    full_ctx = {**(context or {}), **(raw or {})}

    for orig_qid, val in (raw or {}).items():
        qid = resolve_qid(orig_qid)
        q = PRECISION_QUESTIONS.get(qid)
        if q is None:
            errors.append(f"{orig_qid}: unknown question")
            continue
        if not _is_answered(val):
            continue

        # If question is hidden by show_if, drop it silently
        if not is_visible(qid, full_ctx) and not is_visible(orig_qid, full_ctx):
            continue

        t = q["type"]
        ids = [o["id"] for o in q.get("options", [])]

        if t == "single":
            if not isinstance(val, str) or (ids and val not in ids):
                # Check legacy aliases for single choice options
                if orig_qid == "q64" and val in ("infant", "toddler", "school_age", "teen"):
                    clean[orig_qid] = val
                    clean[qid] = "under_5" if val in ("infant", "toddler") else "5_12"
                    continue
                errors.append(f"{orig_qid}: must be one of {ids}")
                continue
            clean[qid] = val
            clean[orig_qid] = val

        elif t == "multi":
            if isinstance(val, str):
                val = [val]
            if not isinstance(val, list):
                errors.append(f"{orig_qid}: must be a list of option ids")
                continue
            normalized_val = []
            for item in val:
                s = str(item)
                if s in ids:
                    normalized_val.append(s)
                elif s.replace("allergen_", "") in ids:
                    normalized_val.append(s.replace("allergen_", ""))
                elif s in ("omit_health_diet", "omit_health"):
                    normalized_val.append("omit_health_diet")
                elif s == "omit_budget" and "budget_comfort" in ids:
                    normalized_val.append("budget_comfort")
                else:
                    normalized_val.append(s)
            val = list(dict.fromkeys(normalized_val))
            allowed_extras = {"omit_health_diet", "omit_health"} if qid in ("d27_privacy_saving", "q47") else set()
            bad = [x for x in val if ids and x not in ids and x not in allowed_extras]
            if bad:
                errors.append(f"{orig_qid}: unknown option ids {bad}")
                continue
            clean[qid] = val
            clean[orig_qid] = val

        elif t == "scale":
            if not isinstance(val, int) or not (1 <= val <= 5):
                errors.append(f"{orig_qid}: scale value must be integer 1..5")
                continue
            clean[qid] = val
            clean[orig_qid] = val

        elif t == "number":
            lo = q.get("min", 1)
            hi = q.get("max", 100)
            if not isinstance(val, (int, float)) or not (lo <= val <= hi):
                errors.append(f"{orig_qid}: must be a number between {lo} and {hi}")
                continue
            clean[qid] = val
            clean[orig_qid] = val

        elif t == "text":
            s = str(val).strip()
            if s:
                clean[qid] = s
                clean[orig_qid] = s

    return clean, errors

def apply_privacy_filter(answers: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Enforces privacy preferences from d27_privacy_saving or legacy q47."""
    priv = answers.get("d27_privacy_saving") or answers.get("q47")
    if not priv:
        return dict(answers), []

    priv_list = _as_list(priv)
    dropped: List[str] = []
    kept: Dict[str, Any] = {}

    sensitive_diet = {"d11_food_allergens", "q10", "q95", "q96"}
    sensitive_health = {"d21_medical_logistics", "q11", "q103"}
    sensitive_comfort = {"d08_winter_cold", "d07_heat_humidity", "q78", "q79", "q80"}

    drop_health_diet = "omit_health_diet" in priv_list
    has_optin = any(x in priv_list for x in ("travel_prefs", "health_accessibility", "dietary_needs", "budget_comfort"))

    for k, v in answers.items():
        can_k = resolve_qid(k)
        drop = False
        if drop_health_diet and (can_k in sensitive_diet or can_k in sensitive_health or can_k in sensitive_comfort or k in sensitive_comfort or k in sensitive_diet):
            drop = True
        elif has_optin:
            if (can_k in sensitive_diet or k in sensitive_diet) and "dietary_needs" not in priv_list:
                drop = True
            elif (can_k in sensitive_health or k in sensitive_health) and "health_accessibility" not in priv_list:
                drop = True
            elif (can_k in sensitive_comfort or k in sensitive_comfort) and "health_accessibility" not in priv_list and "travel_prefs" not in priv_list:
                drop = True

        if drop:
            dropped.append(k)
        else:
            kept[k] = v

    return kept, dropped

# --------------------------------------------------------------------------------------
# Vectorisation
# --------------------------------------------------------------------------------------
def get_precision_feature_names() -> List[str]:
    names: List[str] = []
    for q in _DEEP_RAW:
        spec = q.get("vec") or {}
        stype = spec.get("type")
        if stype == "flags":
            prefix = spec.get("prefix", q["id"])
            for opt in spec.get("options", []):
                names.append(f"{prefix}_{opt}")
        elif stype in ("scale", "number", "ordinal"):
            names.append(spec.get("name", q["id"]))
        else:
            enc = q.get("encoding", {})
            if enc.get("features"):
                names.extend(enc["features"])
            else:
                names.append(q["id"])
    names.append("precision_coverage")
    return names

def coverage(answers: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[int, int]:
    full = {**(context or {}), **answers}
    visible = [q["id"] for q in _DEEP_RAW if is_visible(q["id"], full)]
    answered = [qid for qid in visible if _is_answered(answers.get(qid) or answers.get(CANONICAL_TO_LEGACY.get(qid)))]
    return len(answered), len(visible)

def build_precision_vector(answers: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[List[float], List[str]]:
    """
    Encoding rules (all features in [0, 1]):
      - question hidden by show_if         -> 0.0
      - question visible but unanswered    -> 0.5 neutral for scales/numbers/ordinals, 0.0 for flags
      - scale 1-5                          -> (v-1)/4
      - number                             -> (v-min)/(max-min)
      - ordinal single choice              -> mapped value from spec
      - flags                              -> 1.0 if selected, else 0.0
      - last dimension                     -> precision_coverage
    """
    full = {**(context or {}), **answers}
    vec: List[float] = []

    for q in _DEEP_RAW:
        qid = q["id"]
        leg_id = q.get("legacy_id")
        visible = is_visible(qid, full)
        
        val = None
        if visible:
            val = answers.get(qid)
            if val is None and leg_id:
                val = answers.get(leg_id)

        answered = visible and _is_answered(val)
        spec = q.get("vec", {})
        stype = spec.get("type", "scale")

        if stype == "flags":
            chosen = set(_as_list(val)) if answered else set()
            for opt in spec.get("options", []):
                # Check option id or allergen name
                is_on = (opt in chosen) or (f"allergen_{opt}" in chosen) or (opt.replace("allergen_", "") in chosen)
                vec.append(1.0 if is_on else 0.0)

        elif not visible:
            vec.append(0.0)

        elif not answered:
            vec.append(0.5)

        elif stype == "scale":
            v = float(val) if isinstance(val, (int, float)) else 3.0
            vec.append(round((v - 1.0) / 4.0, 4))

        elif stype == "number":
            lo = float(q.get("min", 1))
            hi = float(q.get("max", 20))
            v = float(val) if isinstance(val, (int, float)) else lo
            vec.append(round((min(max(v, lo), hi) - lo) / (hi - lo), 4))

        elif stype == "ordinal":
            mapping = spec.get("map", {})
            vec.append(float(mapping.get(val, 0.5)))

        else:
            vec.append(0.5)

    n_ans, n_vis = coverage(answers, context)
    cov = round(n_ans / n_vis, 4) if n_vis else 0.0
    vec.append(cov)

    return [round(v, 4) for v in vec], get_precision_feature_names()

# --------------------------------------------------------------------------------------
# Insights: India-Specific Planner Rules & Constraints
# --------------------------------------------------------------------------------------
def derive_insights(answers: Dict[str, Any], context: Dict[str, Any] = None) -> List[Dict[str, str]]:
    a = {**(context or {}), **answers}
    out: List[Dict[str, str]] = []

    def add(kind, text):
        out.append({"kind": kind, "text": text})

    def sel(qid):
        can = resolve_qid(qid)
        return _as_list(a.get(can) or a.get(qid))

    def low(qid, n=2):
        can = resolve_qid(qid)
        v = a.get(can)
        if v is None:
            v = a.get(qid)
        return isinstance(v, (int, float)) and v <= n

    # 1. Allergens (Hard constraint)
    allergens = sel("d11_food_allergens") or sel("q95") or sel("q10")
    if allergens and "no_concerns" not in allergens:
        names = ", ".join(str(x).replace("allergen_", "").replace("_", " ").lower() for x in allergens)
        add("constraint", f"Hard food-safety constraint: never recommend anything containing {names}.")

    # 2. Winter Cold & Wind
    if low("d08_winter_cold") or low("q78") or low("q80"):
        add("rule", f"Cold/wind-sensitive: packing adds a windproof outer layer and an insulating mid-layer whenever the forecast is below {COLD_C}°C or gusts exceed {WIND_KMH} km/h.")

    # 3. Monsoon & Rain
    if low("d05_monsoon_rain") or low("q81"):
        add("rule", "Rain-averse / Monsoon alert: every outdoor plan gets an indoor backup; mountain routes in Himachal/Uttarakhand check for landslide alerts.")

    # 4. High Altitude Acclimatization
    if low("d06_high_altitude") or a.get("d06_high_altitude", 5) <= 2:
        add("constraint", "High-altitude safety constraint: mandatory 48-hour rest/acclimatization schedule before undertaking Khardung La, Pangong, or Spiti high passes.")

    # 5. Solo Women / Safety
    if a.get("d01_solo_safety") == "always_prefer_verified":
        add("rule", "Solo travel safety: schedule arrivals during daylight hours and prioritize verified women-friendly accommodations.")

    # 6. Carry-on Luggage
    if a.get("q61") == "carry_on" or a.get("d14_road_transit") == "carry_on":
        add("rule", "Carry-on only: packing list is capped to cabin-bag size, with a liquids-limit reminder for flights.")

    # 7. Medical Logistics
    meds = set(sel("d21_medical_logistics")) | set(sel("q103")) | set(sel("q11"))
    if meds & {"refrigeration", "prescription", "fridge", "documents", "personal_medication"}:
        add("reminder", "Medication logistics: keep medication in cabin baggage, carry a doctor's prescription copy, and verify hotel refrigerator availability.")

    # 8. Railway Class
    train = a.get("d13_train_class")
    if train in ("vande_bharat", "1a", "2a"):
        add("rule", "Premium rail preference: prioritize Vande Bharat chair cars or 2A/1A sleeper berths for intercity journeys.")

    # 9. Jain / Pure Veg Dietary
    diet = sel("b09_dietary") or sel("q20") or sel("dietary")
    if "jain" in diet:
        add("constraint", "Strict Jain dietary constraint: filter restaurants ensuring zero root vegetables (onion, garlic, potato) and separate kitchen preparation.")
    elif "pure_veg" in diet:
        add("rule", "Pure vegetarian preference: prioritize 100% vegetarian dhabas and restaurants.")

    return out

def summarize_precision(answers: Dict[str, Any], context: Dict[str, Any] = None) -> str:
    n_ans, n_vis = coverage(answers, context)
    insights = derive_insights(answers, context)
    constraints = sum(1 for i in insights if i["kind"] == "constraint")
    pct = round(100 * n_ans / n_vis) if n_vis else 0
    return f"Precision profile: {n_ans}/{n_vis} applicable questions answered ({pct}%), {constraints} hard constraints, {len(insights)} planner rules active."

# --------------------------------------------------------------------------------------
# Mandatory Profile Tracking and Enforcement
# --------------------------------------------------------------------------------------
BASIC_QUESTION_MAP = {
    "q1": ("age_group", "Age group"),
    "q2": ("travel_experience", "Travel experience"),
    "q3": ("companions", "Travel companions"),
    "q4": ("planning_approach", "Planning approach"),
    "q5": ("travel_goals", "Primary travel goals"),
    "q14": ("place_interests", "Favorite place types"),
    "q17": ("experience_preference", "Experience style"),
    "q20": ("dietary", "Dietary preferences"),
    "q26": ("preferred_climate", "Preferred climate"),
    "q32": ("budget_tier", "Budget tier"),
    "q41": ("assistance_autonomy", "Assistance autonomy"),
}

# Canonical schema question aliases
CANONICAL_BASIC_ALIASES = {
    "age_group": "b01_age",
    "travel_experience": "b04_experience",
    "companions": "b03_companions",
    "travel_goals": "b05_travel_goals",
    "place_interests": "b06_place_interests",
    "experience_preference": "b07_pace",
    "dietary": "b09_dietary",
    "preferred_climate": "b11_climate",
    "budget_tier": "b10_budget",
    "assistance_autonomy": "b12_autonomy",
}

def check_basic_missing(profile_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    missing = []
    if not profile_dict:
        for qid, (field, label) in BASIC_QUESTION_MAP.items():
            missing.append({
                "id": qid,
                "field": field,
                "label": label,
                "level": "basic",
                "question": label
            })
        return missing

    raw = profile_dict.get("raw_answers") or profile_dict
    for qid, (field, label) in BASIC_QUESTION_MAP.items():
        val = raw.get(field)
        if val is None:
            val = profile_dict.get(field)
        if val is None:
            val = raw.get(qid)
        if val is None and field == "experience_preference":
            val = raw.get("pace") or profile_dict.get("pace")
        if val is None and field in CANONICAL_BASIC_ALIASES:
            can_id = CANONICAL_BASIC_ALIASES[field]
            val = raw.get(can_id) or profile_dict.get(can_id)

        if not _is_answered(val):
            # Special check for travel_goals and place_interests (need min 2 items)
            missing.append({
                "id": qid,
                "field": field,
                "label": label,
                "level": "basic",
                "question": label
            })
        elif field in ("travel_goals", "place_interests") and isinstance(val, (list, set)) and len(val) < 2:
            # Need at least 2 selections
            missing.append({
                "id": qid,
                "field": field,
                "label": label,
                "level": "basic",
                "question": f"{label} (minimum 2 required)"
            })

    return missing

def check_precision_missing(answers: Dict[str, Any], context: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int, int]:
    full = {**(context or {}), **(answers or {})}
    missing = []
    total_vis = 0
    total_ans = 0

    for q in _DEEP_RAW:
        qid = q["id"]
        leg_id = q.get("legacy_id")
        if is_visible(qid, full):
            total_vis += 1
            val = (answers or {}).get(qid)
            if val is None and leg_id:
                val = (answers or {}).get(leg_id)

            if _is_answered(val):
                total_ans += 1
            else:
                missing.append({
                    "id": qid,
                    "label": q.get("question", qid),
                    "question": q.get("question", qid),
                    "section": q.get("section", "d_sec_1"),
                    "level": "precision",
                    "type": q.get("type", "single")
                })
    return missing, total_ans, total_vis

def missing_required(user_id: str) -> List[Dict[str, Any]]:
    """Returns list of applicable unanswered questions across Basic and Precision."""
    from app.database import get_connection
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT raw_answers_json, companions, budget_tier, preferred_climate, interests FROM traveller_profiles WHERE user_id = ?", (user_id,))
        b_row = cursor.fetchone()
        base_dict = {}
        if b_row:
            raw_s = b_row[0]
            if raw_s:
                try:
                    base_dict = json.loads(raw_s) if isinstance(raw_s, str) else raw_s
                except Exception:
                    pass
            if not base_dict:
                base_dict = {
                    "companions": b_row[1],
                    "budget_tier": b_row[2],
                    "preferred_climate": b_row[3],
                    "interests": json.loads(b_row[4]) if b_row[4] else []
                }
        basic_missing = check_basic_missing(base_dict)

        cursor.execute("SELECT raw_answers_json FROM detailed_profiles WHERE user_id = ?", (user_id,))
        d_row = cursor.fetchone()
        detailed_dict = {}
        if d_row and d_row[0]:
            try:
                detailed_dict = json.loads(d_row[0]) if isinstance(d_row[0], str) else d_row[0]
            except Exception:
                pass

        context = build_context_answers(base_dict, detailed_dict)

        cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
        p_row = cursor.fetchone()
        prec_answers = {}
        if p_row and p_row[0]:
            try:
                prec_answers = json.loads(p_row[0]) if isinstance(p_row[0], str) else p_row[0]
            except Exception:
                pass

        prec_missing, _, _ = check_precision_missing(prec_answers, context)
        return basic_missing + prec_missing

def profile_status(user_id: str) -> Dict[str, Any]:
    """Returns status dictionary: complete flag, missing list, percent, and breakdowns."""
    from app.database import get_connection
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT raw_answers_json, companions, budget_tier, preferred_climate, interests FROM traveller_profiles WHERE user_id = ?", (user_id,))
        b_row = cursor.fetchone()
        base_dict = {}
        if b_row:
            raw_s = b_row[0]
            if raw_s:
                try:
                    base_dict = json.loads(raw_s) if isinstance(raw_s, str) else raw_s
                except Exception:
                    pass
            if not base_dict:
                base_dict = {
                    "companions": b_row[1],
                    "budget_tier": b_row[2],
                    "preferred_climate": b_row[3],
                    "interests": json.loads(b_row[4]) if b_row[4] else []
                }
        basic_missing = check_basic_missing(base_dict)
        has_basic = b_row is not None and len(basic_missing) == 0

        cursor.execute("SELECT 1 FROM detailed_profiles WHERE user_id = ?", (user_id,))
        has_detailed = cursor.fetchone() is not None

        cursor.execute("SELECT answers_json, coverage FROM precision_profiles WHERE user_id = ?", (user_id,))
        p_row = cursor.fetchone()
        has_precision = p_row is not None
        prec_answers = {}
        if p_row and p_row[0]:
            try:
                prec_answers = json.loads(p_row[0]) if isinstance(p_row[0], str) else p_row[0]
            except Exception:
                pass

        context = build_context_answers(base_dict, {})
        prec_missing, prec_ans, prec_app = check_precision_missing(prec_answers, context)

        total_questions = 12 + prec_app
        answered_questions = (12 - len(basic_missing)) + prec_ans
        pct = round(100 * answered_questions / total_questions) if total_questions else 0

        return {
            "user_id": user_id,
            "has_basic_profile": has_basic,
            "has_detailed_profile": has_detailed,
            "has_precision_profile": has_precision,
            "complete": has_basic,
            "is_complete": has_basic,
            "completion_percentage": pct,
            "missing": basic_missing + prec_missing,
            "breakdown": {
                "basic": {
                    "complete": has_basic,
                    "missing_count": len(basic_missing),
                    "total": 12
                },
                "precision": {
                    "answered": prec_ans,
                    "applicable": prec_app,
                    "coverage": round(prec_ans / prec_app, 4) if prec_app else 0.0,
                    "missing_count": len(prec_missing)
                }
            }
        }
