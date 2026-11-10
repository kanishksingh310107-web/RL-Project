# Converts user travel preferences into a feature vector for RL state & downstream models
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.precision import build_precision_vector, get_precision_feature_names, derive_insights

# Canonical 12 interest tags used in RL agent state
INTERESTS = [
    "culture_history",
    "food_dining",
    "nature_outdoors",
    "beaches",
    "mountains",
    "adventure",
    "photography",
    "shopping",
    "nightlife",
    "relaxation",
    "events_festivals",
    "local_experiences"
]

COMPANIONS = ["solo", "couple", "friends", "family"]

BUDGET_MAP = {
    # Legacy tiers
    "very_budget": 0.1,
    "budget": 0.25,
    "balanced": 0.6,
    "mid_range": 0.6,
    "premium": 0.85,
    "luxury": 1.0,
    # India-specific INR tiers
    "budget_under_2500": 0.2,
    "mid_2500_6000": 0.5,
    "premium_6000_15000": 0.8,
    "luxury_above_15000": 1.0,
}

CLIMATE_MAP = {
    # Legacy climates
    "cold": 0.1,
    "cool": 0.3,
    "mild": 0.5,
    "warm": 0.75,
    "hot": 0.9,
    "tropical": 1.0,
    "adapt_easily": 0.5,
    # India-specific climate zones
    "cold_himalayan": 0.15,
    "cool_hill_station": 0.35,
    "moderate_pleasant": 0.55,
    "warm_tropical": 0.85,
    "flexible_any": 0.5,
}

# Avoidances and constraints
AVOIDANCES = [
    "extreme_heights",
    "crowded_clubs",
    "strenuous_hikes",
    "long_bus_rides",
    "early_starts",
    "late_nights",
    "long_queues",
    "tourist_traps"
]

AVOIDANCE_ALIASES = {
    "crowded_spaces": "crowded_clubs",
    "noisy_nightlife": "crowded_clubs",
    "early_morning_rush": "early_starts",
    "extreme_heights": "extreme_heights",
    "crowded_temple_queues": "long_queues",
    "strenuous_trekking": "strenuous_hikes",
    "long_winding_ghat_roads": "long_bus_rides",
    "late_night_transit": "late_nights",
    "commercial_tourist_traps": "tourist_traps",
    "nightclubs_loud_pubs": "crowded_clubs",
}

STAY_STYLES = ["boutique", "budget_hostel", "resort", "apartment"]
TRANSIT_PREFS = ["public_transit", "walking", "rental_car", "taxi"]

WALKING_MAP = {"low": 0.2, "medium": 0.6, "high": 1.0}
DENSITY_MAP = {"relaxed_1_major": 0.3, "balanced_2_3": 0.6, "packed_all_day": 1.0}
REPETITION_MAP = {"explore_new": 1.0, "similar_vibes": 0.5, "familiar_return": 0.1}

# Mapping questionnaire answers (both legacy and India-specific) to RL interest tags
QUESTION_TO_INTEREST_MAP = {
    # Legacy place types
    "mountains_nature": ["mountains", "nature_outdoors"],
    "beaches_coastal": ["beaches", "relaxation"],
    "forests_wildlife": ["nature_outdoors"],
    "historical_sites": ["culture_history"],
    "museums_art": ["culture_history"],
    "local_markets": ["shopping", "local_experiences"],
    "cafes_restaurants": ["food_dining"],
    "religious_spiritual": ["culture_history"],
    "theme_parks": ["adventure"],
    "nightlife_music": ["nightlife"],
    "villages_communities": ["local_experiences"],
    "architecture_photo": ["photography", "culture_history"],
    "nature": ["nature_outdoors"],
    "adventure": ["adventure"],
    "food_dining": ["food_dining"],
    "shopping": ["shopping"],
    "photography": ["photography"],
    "socializing": ["local_experiences", "nightlife"],
    "relaxation": ["relaxation"],

    # Redesigned India-specific place types (b06_place_interests)
    "himalayan_valleys": ["mountains", "nature_outdoors"],
    "coastal_beaches": ["beaches", "relaxation"],
    "heritage_forts_palaces": ["culture_history", "photography"],
    "temple_towns_spiritual": ["culture_history"],
    "backwaters_tea_estates": ["relaxation", "nature_outdoors"],
    "desert_circuits": ["adventure", "photography"],
    "wildlife_jungles": ["nature_outdoors", "adventure"],
    "bustling_bazaars_markets": ["shopping", "local_experiences"],
    "culinary_food_trails": ["food_dining", "local_experiences"],

    # Redesigned India-specific travel goals (b05_travel_goals)
    "nature_scenic": ["nature_outdoors", "relaxation"],
    "spiritual_pilgrimage": ["culture_history"],
    "heritage_architecture": ["culture_history", "photography"],
    "culinary_exploration": ["food_dining"],
    "high_altitude_adventure": ["adventure", "mountains"],
    "wellness_ayurveda": ["relaxation"],
    "wildlife_safari": ["nature_outdoors", "adventure"],
    "photography_culture": ["photography", "culture_history"],
}

class PreferenceVectorizer:
    """Helper to convert profile dict to a normalized feature vector."""

    @classmethod
    def get_feature_names(cls) -> List[str]:
        names = []
        for item in INTERESTS:
            names.append(f"interest_{item}")
        names.extend(["pace", "crowd_tolerance", "spontaneity"])
        for comp in COMPANIONS:
            names.append(f"companion_{comp}")
        names.append("has_children")
        names.append("budget_weight")
        names.append("climate_weight")
        return names

    @classmethod
    def get_detailed_feature_names(cls) -> List[str]:
        names = cls.get_feature_names().copy()
        for a in AVOIDANCES:
            names.append(f"avoid_{a}")
        names.append("walking_capacity")
        names.append("schedule_density")
        for s in STAY_STYLES:
            names.append(f"stay_{s}")
        for t in TRANSIT_PREFS:
            names.append(f"transit_{t}")
        names.append("exploration_weight")
        return names

    @classmethod
    def _extract_active_interests(cls, profile_dict: Dict[str, Any]) -> set:
        active = set(profile_dict.get("interests", []))

        # Check goals and place types from both new IDs and legacy fields
        raw = profile_dict.get("raw_answers") or profile_dict
        goals = raw.get("b05_travel_goals") or profile_dict.get("travel_goals", []) or raw.get("q5", [])
        places = raw.get("b06_place_interests") or profile_dict.get("place_interests", []) or raw.get("q14", [])
        combined = list(goals) + list(places)

        for key in combined:
            if key in INTERESTS:
                active.add(key)
            if key in QUESTION_TO_INTEREST_MAP:
                for mapped in QUESTION_TO_INTEREST_MAP[key]:
                    active.add(mapped)

        return active

    @classmethod
    def vectorize(cls, profile_dict: Dict[str, Any]) -> Tuple[List[float], List[str]]:
        vector: List[float] = []
        user_interests = cls._extract_active_interests(profile_dict)
        raw = profile_dict.get("raw_answers") or profile_dict

        # 1. Interests (one/multi-hot across 12 dimensions)
        for item in INTERESTS:
            vector.append(1.0 if item in user_interests else 0.0)

        # 2. Travel style sliders / planning approach
        pace = profile_dict.get("pace")
        if pace is None:
            pace = raw.get("b07_pace")
        if pace is None:
            exp = str(profile_dict.get("travel_experience", "occasional")).lower()
            pace = 0.4 if exp in ["beginner", "occasional"] else 0.7
        vector.append(float(pace))

        crowd = profile_dict.get("crowd_tolerance")
        if crowd is None:
            crowd = raw.get("b08_crowd_tolerance")
        if crowd is None:
            pref = str(profile_dict.get("experience_preference", "balanced_mix")).lower()
            if pref in ["hidden_gems", "quiet_uncrowded"]:
                crowd = 0.2
            elif pref in ["popular_landmarks"]:
                crowd = 0.8
            else:
                crowd = 0.5
        vector.append(float(crowd))

        structure = profile_dict.get("structure")
        if structure is None:
            autonomy = str(raw.get("b12_autonomy") or profile_dict.get("planning_approach", "plan_essentials")).lower()
            if autonomy in ("plan_advance", "full_schedule"):
                structure = 0.8
            elif autonomy in ("spontaneous", "independent"):
                structure = 0.2
            else:
                structure = 0.5
        vector.append(float(structure))

        # 3. Companions (b03_companions / Q3)
        user_comp = str(raw.get("b03_companions") or profile_dict.get("companions", "solo")).lower()
        if user_comp in ["alone", "solo"]:
            c_tag = "solo"
        elif user_comp in ["partner", "couple"]:
            c_tag = "couple"
        elif user_comp in ["friends", "tour_group"]:
            c_tag = "friends"
        elif "family" in user_comp:
            c_tag = "family"
        else:
            c_tag = "solo"

        for comp in COMPANIONS:
            vector.append(1.0 if comp == c_tag else 0.0)

        # 4. Children (b03_companions or has_children)
        has_kids = (
            profile_dict.get("has_children", False) or
            user_comp in ("family_children", "family_kids")
        )
        vector.append(1.0 if has_kids else 0.0)

        # 5. Budget weight (b10_budget / Q32)
        budget = str(raw.get("b10_budget") or profile_dict.get("budget_tier", "balanced")).lower()
        vector.append(BUDGET_MAP.get(budget, 0.6))

        # 6. Climate weight (b11_climate / Q26)
        climate = str(raw.get("b11_climate") or profile_dict.get("preferred_climate", "mild")).lower()
        vector.append(CLIMATE_MAP.get(climate, 0.4))

        return vector, cls.get_feature_names()

    @classmethod
    def vectorize_detailed(cls, basic_dict: Dict[str, Any], detailed_dict: Dict[str, Any]) -> Tuple[List[float], List[str]]:
        """Creates full 41-dimensional vector including avoidances, walking capacity, stay & transit."""
        base_vec, _ = cls.vectorize(basic_dict)
        vector = list(base_vec)
        raw_d = detailed_dict.get("raw_answers") or detailed_dict

        # 7. Avoidance penalty flags (8 dims)
        user_avoidances = set(raw_d.get("d22_avoidances") or detailed_dict.get("avoidances", []))
        health_factors = set(detailed_dict.get("health_factors", []))

        if "stairs_difficulty" in health_factors:
            user_avoidances.add("steep_stairs")
        if "walking_difficulty" in health_factors:
            user_avoidances.add("strenuous_hikes")
        for raw_id, canonical in AVOIDANCE_ALIASES.items():
            if raw_id in user_avoidances:
                user_avoidances.add(canonical)

        for a in AVOIDANCES:
            is_avoided = (
                a in user_avoidances or
                a.replace("avoid_", "") in user_avoidances or
                ("stairs" in a and "steep_stairs" in user_avoidances) or
                ("heights" in a and "extreme_heights" in user_avoidances) or
                ("hikes" in a and "strenuous_hikes" in user_avoidances)
            )
            vector.append(1.0 if is_avoided else 0.0)

        # 8. Walking capacity (1 dim)
        walk_val = raw_d.get("d19_daily_walking_km")
        if isinstance(walk_val, (int, float)):
            walk_norm = min(max(float(walk_val), 1.0), 20.0) / 20.0
            vector.append(round(walk_norm, 4))
        else:
            walk = str(detailed_dict.get("walking_tolerance", "medium")).lower()
            if "physical_demand" in detailed_dict and walk == "medium":
                demand = detailed_dict["physical_demand"]
                if demand in ["very_relaxed", "light_breaks"]:
                    walk = "low"
                elif demand == "highly_active":
                    walk = "high"
            vector.append(WALKING_MAP.get(walk, 0.6))

        # 9. Schedule density (1 dim)
        density = str(detailed_dict.get("schedule_density", "balanced_2_3")).lower()
        if "time_per_attraction" in detailed_dict and density == "balanced_2_3":
            t_attr = detailed_dict["time_per_attraction"]
            if t_attr == "longer_deep":
                density = "relaxed_1_major"
            elif t_attr == "quick":
                density = "packed_all_day"
        vector.append(DENSITY_MAP.get(density, 0.6))

        # 10. Stay style one-hot (4 dims)
        stay = str(raw_d.get("d17_stay_types") or detailed_dict.get("stay_style", "boutique")).lower()
        if stay in ("heritage_haveli", "plantation_homestay", "ashram"):
            stay = "boutique"
        elif stay in ("budget_hotel", "hostel", "dormitory"):
            stay = "budget_hostel"
        elif stay in ("luxury_resort", "resort"):
            stay = "resort"
        elif stay in ("homestay", "serviced_apartment"):
            stay = "apartment"

        for s in STAY_STYLES:
            vector.append(1.0 if s == stay else 0.0)

        # 11. Transit preference one-hot (4 dims)
        transit = str(raw_d.get("d14_road_transit") or detailed_dict.get("transit_pref", "public_transit")).lower()
        if transit in ("hired_cab_driver", "local_auto_taxi"):
            transit = "taxi"
        elif transit in ("volvo_intercity_bus", "vande_bharat_train"):
            transit = "public_transit"
        elif transit in ("self_drive_car", "rental_car"):
            transit = "rental_car"
        elif transit in ("walking"):
            transit = "walking"
        else:
            transit = "public_transit"

        for t in TRANSIT_PREFS:
            vector.append(1.0 if t == transit else 0.0)

        # 12. Exploration vs exploitation weight (1 dim)
        rep = str(detailed_dict.get("repetition_strategy", "similar_vibes")).lower()
        vector.append(REPETITION_MAP.get(rep, 0.5))

        return vector, cls.get_detailed_feature_names()

    @classmethod
    def get_precision_full_feature_names(cls) -> List[str]:
        return cls.get_detailed_feature_names() + get_precision_feature_names()

    @classmethod
    def vectorize_precision(cls, basic_dict: Dict[str, Any], detailed_dict: Dict[str, Any],
                            precision_answers: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[List[float], List[str]]:
        """Level 3 state = the 41 detailed dims + the precision block."""
        base_vec, _ = cls.vectorize_detailed(basic_dict, detailed_dict)
        extra, _ = build_precision_vector(precision_answers, context)
        return base_vec + extra, cls.get_precision_full_feature_names()

    @classmethod
    def summarize_profile(cls, profile_dict: Dict[str, Any]) -> str:
        active_interests = list(cls._extract_active_interests(profile_dict))
        clean_interests = [i.replace("_", " ").title() for i in active_interests]
        if not clean_interests:
            clean_interests = ["Sightseeing", "Local Culture"]

        pace_val = profile_dict.get("pace", 0.5)
        pace_desc = "relaxed" if pace_val < 0.35 else ("fast-paced" if pace_val > 0.65 else "balanced")

        crowd_val = profile_dict.get("crowd_tolerance", 0.5)
        crowd_desc = "hidden gems" if crowd_val < 0.4 else "popular sights"

        comp = profile_dict.get("companions", "solo").replace("_", " ").title()
        budget = profile_dict.get("budget_tier", "balanced").replace("_", " ").title()

        return (
            f"Interested in {', '.join(clean_interests[:3])} with a {pace_desc} pace, "
            f"preferring {crowd_desc}. Travelling {comp} on a {budget} budget."
        )

    @classmethod
    def summarize_detailed(cls, basic_dict: Dict[str, Any], detailed_dict: Dict[str, Any]) -> str:
        base_summary = cls.summarize_profile(basic_dict)
        avoid = [a.replace("_", " ").title() for a in detailed_dict.get("avoidances", [])]
        avoid_str = f" Avoids: {', '.join(avoid[:3])}." if avoid else ""
        walk = detailed_dict.get("walking_tolerance", "medium").title()
        stay = detailed_dict.get("stay_style", "boutique").replace("_", " ").title()
        transit = detailed_dict.get("transit_pref", "public transit").replace("_", " ").title()

        diet = detailed_dict.get("dietary", [])
        diet_str = f" Diet: {', '.join(diet)}." if diet and diet != ["none"] else ""

        return (
            f"{base_summary}{avoid_str}{diet_str} Prefers {stay} stays, travelling by {transit} with {walk} walking capacity."
        )


class SchemaAdapter:
    """
    Model-Agnostic Adapter and Feature Extractor.
    Extracts features for LinUCB, ranking models, tabular ML (scikit-learn), or LLM prompts.
    """

    _schema_cache: Dict[str, Any] = None

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        if cls._schema_cache is None:
            p = Path(__file__).resolve().parent / "data" / "questionnaire_schema.json"
            with open(p, "r", encoding="utf-8") as f:
                cls._schema_cache = json.load(f)
        return cls._schema_cache

    @classmethod
    def migrate_answers(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Translates legacy question IDs/values into canonical schema keys and vice versa."""
        migrated: Dict[str, Any] = dict(raw or {})
        schema = cls.get_schema()

        # Map legacy IDs to canonical IDs
        for q in schema.get("questions", []):
            qid = q["id"]
            leg = q.get("legacy_id")
            if leg and leg in raw and qid not in migrated:
                migrated[qid] = raw[leg]
            elif qid in raw and leg and leg not in migrated:
                migrated[leg] = raw[qid]

        return migrated

    @classmethod
    def extract_features(cls, answers: Dict[str, Any], format_type: str = "named") -> Dict[str, Any]:
        """
        Extracts features in one of three formats:
        - 'named': dict of feature_name -> numerical float value
        - 'vector': {'feature_names': [...], 'vector': [...]}
        - 'onehot': full onehot/multihot binary dictionary
        """
        schema = cls.get_schema()
        clean = cls.migrate_answers(answers)
        features: Dict[str, float] = {}

        for q in schema.get("questions", []):
            qid = q["id"]
            val = clean.get(qid)
            enc = q.get("encoding", {})
            etype = enc.get("type")

            if etype in ("numeric_normalised", "scale"):
                if val is not None and isinstance(val, (int, float)):
                    lo = float(q.get("min", 1))
                    hi = float(q.get("max", 5))
                    features[qid] = round((min(max(float(val), lo), hi) - lo) / (hi - lo), 4)
                else:
                    features[qid] = 0.5

            elif etype == "ordinal_0_1":
                opts = [o["id"] for o in q.get("options", [])]
                if val in opts:
                    idx = opts.index(val)
                    step = 1.0 / max(len(opts) - 1, 1)
                    features[qid] = round(idx * step, 4)
                else:
                    features[qid] = 0.5

            elif etype in ("onehot", "multihot"):
                chosen = set(val if isinstance(val, list) else ([val] if val else []))
                for opt in q.get("options", []):
                    opt_id = opt["id"]
                    feat_name = f"{qid}_{opt_id}"
                    features[feat_name] = 1.0 if opt_id in chosen else 0.0

        if format_type == "vector":
            names = sorted(features.keys())
            return {
                "feature_names": names,
                "vector": [features[k] for k in names]
            }
        elif format_type == "onehot":
            onehot_dict = {}
            for q in schema.get("questions", []):
                qid = q["id"]
                val = clean.get(qid)
                etype = q.get("encoding", {}).get("type")
                if etype in ("onehot", "multihot"):
                    chosen = set(val if isinstance(val, list) else ([val] if val else []))
                    for opt in q.get("options", []):
                        opt_id = opt["id"]
                        onehot_dict[f"{qid}_{opt_id}"] = 1.0 if opt_id in chosen else 0.0
            return onehot_dict
        else:
            return features

    @classmethod
    def export_profile(cls, user_id: str, raw_answers: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Full model-agnostic JSON profile ready for storage, downstream models, or LLM system prompts."""
        schema = cls.get_schema()
        migrated = cls.migrate_answers(raw_answers)
        features = cls.extract_features(migrated, format_type="named")
        insights = derive_insights(migrated, context)

        # Generate structured LLM context string
        llm_context_lines = [
            f"User Profile (Travel Planner v2.0 - India Scope)",
            f"- Age: {migrated.get('b01_age', 'Not specified')}",
            f"- Home Region: {migrated.get('b02_home_region', 'India')}",
            f"- Party: {migrated.get('b03_companions', 'solo')}",
            f"- Travel Goals: {', '.join(migrated.get('b05_travel_goals', []))}",
            f"- Interests: {', '.join(migrated.get('b06_place_interests', []))}",
            f"- Diet: {', '.join(migrated.get('b09_dietary', ['Standard']))}",
            f"- Budget Band: {migrated.get('b10_budget', 'Mid-range')}",
            f"- Climate Preference: {migrated.get('b11_climate', 'Pleasant')}",
        ]
        if insights:
            llm_context_lines.append("Key Rules & Hard Constraints:")
            for ins in insights:
                llm_context_lines.append(f"  * [{ins['kind'].upper()}] {ins['text']}")

        return {
            "schema_version": schema.get("schema_version", "2.0.0"),
            "user_id": user_id,
            "country_scope": schema.get("country_scope", "IN"),
            "currency": schema.get("currency", "INR"),
            "raw_answers": raw_answers,
            "standardized_answers": migrated,
            "features": features,
            "hard_constraints": [i for i in insights if i["kind"] == "constraint"],
            "planner_rules": [i for i in insights if i["kind"] == "rule"],
            "reminders": [i for i in insights if i["kind"] == "reminder"],
            "llm_system_context": "\n".join(llm_context_lines)
        }

    @classmethod
    def summarize_narrative(cls, answers: Dict[str, Any]) -> Dict[str, Any]:
        """Returns structured narrative summary across distinct travel dimensions."""
        migrated = cls.migrate_answers(answers)
        insights = derive_insights(migrated)

        comp = str(migrated.get("b03_companions", "solo")).replace("_", " ").title()
        origin = str(migrated.get("b02_home_region", "India")).replace("_", " ").title()
        goals = [g.replace("_", " ").title() for g in migrated.get("b05_travel_goals", [])]
        places = [p.replace("_", " ").title() for p in migrated.get("b06_place_interests", [])]

        diet = [d.replace("_", " ").title() for d in migrated.get("b09_dietary", [])]
        budget = str(migrated.get("b10_budget", "Mid-range")).replace("_", " ").title()

        return {
            "overview": f"Traveler based in {origin}, exploring {', '.join(places[:2]) or 'India'} with a focus on {', '.join(goals[:2]) or 'sightseeing'}.",
            "travel_party": {
                "composition": comp,
                "has_kids": "family_kids" in comp.lower(),
                "has_seniors": "family_seniors" in comp.lower(),
                "solo_safety_verified": migrated.get("d01_solo_safety") == "always_prefer_verified"
            },
            "climate_and_terrain": {
                "preferred_climate": migrated.get("b11_climate", "moderate_pleasant"),
                "monsoon_tolerance": migrated.get("d05_monsoon_rain", 3),
                "high_altitude_tolerance": migrated.get("d06_high_altitude", 3),
                "winter_cold_tolerance": migrated.get("d08_winter_cold", 3)
            },
            "food_and_diet": {
                "restrictions": diet,
                "spice_tolerance": migrated.get("d09_spice_tolerance", 3),
                "street_food_comfort": migrated.get("d10_street_food", 3),
                "allergens": migrated.get("d11_food_allergens", [])
            },
            "transit_and_stay": {
                "preferred_train": migrated.get("d13_train_class", "vande_bharat"),
                "road_transit": migrated.get("d14_road_transit", "hired_cab_driver"),
                "stay_type": migrated.get("d17_stay_types", "heritage_haveli"),
                "budget_tier": budget
            },
            "constraints_and_avoidances": [i["text"] for i in insights]
        }
