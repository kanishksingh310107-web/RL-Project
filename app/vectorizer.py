# Converts user travel preferences into a feature vector for RL state
from typing import List, Dict, Tuple, Any
from app.precision import build_precision_vector, get_precision_feature_names

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
    "very_budget": 0.1,
    "budget": 0.25,
    "balanced": 0.6,
    "mid_range": 0.6,
    "premium": 0.85,
    "luxury": 1.0
}

CLIMATE_MAP = {
    "cold": 0.1,
    "cool": 0.3,
    "mild": 0.5,
    "warm": 0.75,
    "hot": 0.9,
    "tropical": 1.0,
    "adapt_easily": 0.5
}

# Deep Personalisation Constants (Section 2 & 3: Avoidances and constraints)
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

# Q12 option ids that differ from the canonical avoidance names above.
# Without this, answers like "noisy_nightlife" or "early_morning_rush" were silently lost.
AVOIDANCE_ALIASES = {
    "crowded_spaces": "crowded_clubs",
    "noisy_nightlife": "crowded_clubs",
    "early_morning_rush": "early_starts",
}

STAY_STYLES = ["boutique", "budget_hostel", "resort", "apartment"]
TRANSIT_PREFS = ["public_transit", "walking", "rental_car", "taxi"]

WALKING_MAP = {"low": 0.2, "medium": 0.6, "high": 1.0}
DENSITY_MAP = {"relaxed_1_major": 0.3, "balanced_2_3": 0.6, "packed_all_day": 1.0}
REPETITION_MAP = {"explore_new": 1.0, "similar_vibes": 0.5, "familiar_return": 0.1}

# Mapping questionnaire answers to RL interest tags
QUESTION_TO_INTEREST_MAP = {
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
    "relaxation": ["relaxation"]
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
        # Starts with base 22 features, expands to 41 features
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

        # Check Q5 goals and Q14 place types
        goals = profile_dict.get("travel_goals", [])
        places = profile_dict.get("place_interests", [])
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

        # 1. Interests (one/multi-hot across 12 dimensions)
        for item in INTERESTS:
            vector.append(1.0 if item in user_interests else 0.0)

        # 2. Travel style sliders / planning approach
        pace = profile_dict.get("pace")
        if pace is None:
            # Map from travel_experience if pace slider not passed
            exp = str(profile_dict.get("travel_experience", "occasional")).lower()
            pace = 0.4 if exp in ["beginner", "occasional"] else 0.7
        vector.append(float(pace))

        crowd = profile_dict.get("crowd_tolerance")
        if crowd is None:
            # Map from Q17 experience_preference
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
            # Map from Q4 planning_approach
            plan = str(profile_dict.get("planning_approach", "plan_essentials")).lower()
            if plan == "plan_advance":
                structure = 0.8
            elif plan == "spontaneous":
                structure = 0.2
            else:
                structure = 0.5
        vector.append(float(structure))

        # 3. Companions (Q3)
        user_comp = str(profile_dict.get("companions", "solo")).lower()
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

        # 4. Children (Q3 or has_children)
        has_kids = profile_dict.get("has_children", False) or user_comp == "family_children"
        vector.append(1.0 if has_kids else 0.0)

        # 5. Budget weight (Q32)
        budget = str(profile_dict.get("budget_tier", "balanced")).lower()
        vector.append(BUDGET_MAP.get(budget, 0.6))

        # 6. Climate weight (Q26)
        climate = str(profile_dict.get("preferred_climate", "mild")).lower()
        vector.append(CLIMATE_MAP.get(climate, 0.4))

        return vector, cls.get_feature_names()

    @classmethod
    def vectorize_detailed(cls, basic_dict: Dict[str, Any], detailed_dict: Dict[str, Any]) -> Tuple[List[float], List[str]]:
        """Creates full 41-dimensional vector including avoidances, walking capacity, stay & transit."""
        base_vec, _ = cls.vectorize(basic_dict)
        vector = list(base_vec)

        # 7. Avoidance penalty flags (8 dims)
        user_avoidances = set(detailed_dict.get("avoidances", []))
        health_factors = set(detailed_dict.get("health_factors", []))
        
        # Map questionnaire health triggers to avoidances
        if "stairs_difficulty" in health_factors:
            user_avoidances.add("steep_stairs")
        if "walking_difficulty" in health_factors:
            user_avoidances.add("strenuous_hikes")
        for raw_id, canonical in AVOIDANCE_ALIASES.items():
            if raw_id in user_avoidances:
                user_avoidances.add(canonical)

        for a in AVOIDANCES:
            # Map canonical names
            is_avoided = (
                a in user_avoidances or
                a.replace("avoid_", "") in user_avoidances or
                ("stairs" in a and "steep_stairs" in user_avoidances) or
                ("heights" in a and "extreme_heights" in user_avoidances) or
                ("hikes" in a and "strenuous_hikes" in user_avoidances)
            )
            vector.append(1.0 if is_avoided else 0.0)

        # 8. Walking capacity (1 dim)
        walk = str(detailed_dict.get("walking_tolerance", "medium")).lower()
        # Fallback to physical_demand if walking_tolerance is default
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
        stay = str(detailed_dict.get("stay_style", "boutique")).lower()
        acc_types = detailed_dict.get("accommodation_types", [])
        if acc_types:
            first_acc = acc_types[0]
            if first_acc in ["hostels", "budget_hotels"]:
                stay = "budget_hostel"
            elif first_acc == "resorts":
                stay = "resort"
            elif first_acc == "apartments":
                stay = "apartment"
            else:
                stay = "boutique"

        for s in STAY_STYLES:
            vector.append(1.0 if s == stay else 0.0)

        # 11. Transit preference one-hot (4 dims)
        transit = str(detailed_dict.get("transit_pref", "public_transit")).lower()
        trans_options = detailed_dict.get("transport_options", [])
        if trans_options:
            first_trans = trans_options[0]
            if first_trans in ["walking"]:
                transit = "walking"
            elif first_trans in ["public_transit", "trains"]:
                transit = "public_transit"
            elif first_trans in ["rental_car"]:
                transit = "rental_car"
            elif first_trans in ["taxi_rideshare"]:
                transit = "taxi"

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
        """Level 3 state = the 41 detailed dims + the precision block (see app/precision.py)."""
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
