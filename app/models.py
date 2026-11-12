# Data models for auth and traveller profile
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# Auth models
class AuthRequest(BaseModel):
    provider: str
    identifier: str
    password: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None

class AuthResponse(BaseModel):
    user_id: str
    auth_provider: str
    identifier: str
    display_name: str
    avatar_url: Optional[str] = None
    has_profile: bool
    token: str

class GoogleTokenRequest(BaseModel):
    credential: str

class GoogleClientConfig(BaseModel):
    client_id: str

# Basic Starting Profile (Sections 1, 3, 4, 5, 6, 8 - ~30-60s setup)
class ShortProfileCreate(BaseModel):
    # Core survey fields
    age_group: str = "18_24"
    travel_experience: str = "occasional"
    companions: str = "alone"
    planning_approach: str = "plan_essentials"
    travel_goals: List[str] = [] # Q5 (Select at least 2)
    place_interests: List[str] = [] # Q14 (Select at least 2)
    experience_preference: str = "balanced_mix" # Q17
    dietary: List[str] = ["none"] # Q20
    preferred_climate: str = "mild" # Q26
    budget_tier: str = "mid_range" # Q32
    assistance_autonomy: str = "shortlist_explain" # Q41
    
    # Backward compatible & slider fields
    interests: List[str] = []
    pace: float = 0.5
    crowd_tolerance: float = 0.5
    structure: float = 0.5
    has_children: bool = False
    planning_experience: str = "intermediate"
    
    # Store complete raw questionnaire answers dictionary
    raw_answers: Optional[Dict[str, Any]] = None

# Profile response with RL state vector
class ProfileResponse(BaseModel):
    user_id: str
    profile_type: str
    interests: List[str]
    travel_goals: List[str] = []
    place_interests: List[str] = []
    age_group: str = "18_24"
    travel_experience: str = "occasional"
    companions: str = "alone"
    planning_approach: str = "plan_essentials"
    experience_preference: str = "balanced_mix"
    dietary: List[str] = []
    pace: float = 0.5
    crowd_tolerance: float = 0.5
    structure: float = 0.5
    has_children: bool = False
    budget_tier: str = "mid_range"
    preferred_climate: str = "mild"
    assistance_autonomy: str = "shortlist_explain"
    planning_experience: str = "intermediate"
    rl_state_vector: List[float]
    feature_dimension: int
    feature_names: List[str]
    summary_text: str
    has_detailed_profile: bool = False
    has_precision_profile: bool = False
    raw_answers: Optional[Dict[str, Any]] = None

# Past Trip Entry (Section 5.3)
class PastTripCreate(BaseModel):
    destination: str
    rating: float = 4.0
    favorite_activity: Optional[str] = None
    skipped_or_disliked: Optional[str] = None

# Deep Personalisation Model (Sections 2, 3, 4, 5, 6, 7, 8, 9, 10)
class DetailedProfileCreate(BaseModel):
    # Health & Mobility (Section 2: Q7-Q13)
    health_factors: List[str] = []
    physical_demand: str = "moderate_walking"
    accessibility: List[str] = []
    allergies_triggers: List[str] = []
    health_items: str = "no"
    avoidances: List[str] = [] # Q12
    discomfort_response: str = "suggest_safer" # Q13

    # Activities & Style (Section 3: Q15-Q19)
    activities_enjoyed: List[str] = [] # Q15
    hobbies_text: Optional[str] = None # Q16
    disliked_activities_text: Optional[str] = None # Q18
    time_per_attraction: str = "moderate" # Q19

    # Food & Dining (Section 4: Q21-Q25)
    food_style: str = "local_cuisine" # Q21
    meal_management: str = "restaurants" # Q22
    dietary_importance: str = "somewhat" # Q23
    food_fallback: str = "find_restaurants" # Q24
    food_habits_text: Optional[str] = None # Q25

    # Weather & Packing (Section 5: Q27-Q31)
    weather_reaction: str = "tolerate_easily" # Q27
    weather_alerts: List[str] = [] # Q28
    packing_habits: str = "checklist" # Q29
    packing_priorities: str = "balance_all" # Q30
    clothing_notes: Optional[str] = None # Q31

    # Budget & Transport (Section 6: Q33-Q36)
    spend_priorities: List[str] = [] # Q33
    accommodation_types: List[str] = [] # Q34
    transport_options: List[str] = [] # Q35
    travel_concerns: List[str] = [] # Q6 & Q36

    # Prep & Reminders (Section 7: Q37-Q39)
    prep_assistance: List[str] = [] # Q37
    reminder_style: str = "timely_reminders" # Q38
    forgotten_essentials_text: Optional[str] = None # Q39

    # Decision & Proactivity (Section 8: Q40-Q46)
    decision_criteria: str = "personal_interests" # Q40
    proactive_level: str = "relevant_suggestions" # Q42
    proactive_alerts: List[str] = [] # Q43
    uncertainty_handling: str = "explain_uncertainty" # Q44
    feedback_handling: str = "learn_gradually" # Q45
    update_frequency: str = "before_activity" # Q46

    # Privacy (Section 9: Q47-Q51)
    privacy_saving: List[str] = [] # Q47
    remember_past_trips: str = "yes_auto" # Q48
    trust_factors: List[str] = [] # Q49

    # Open-ended Insights (Section 10: Q52-Q56)
    ideal_trip_text: Optional[str] = None # Q52
    enjoyment_ruiners_text: Optional[str] = None # Q53
    assistant_wish_text: Optional[str] = None # Q54
    prevent_problems_text: Optional[str] = None # Q55
    additional_notes_text: Optional[str] = None # Q56

    # Past Trips (Section 5.3)
    past_trips: Optional[List[PastTripCreate]] = []

    # Backward compatible fields
    walking_tolerance: str = "medium"
    schedule_density: str = "balanced_2_3"
    stay_style: str = "boutique"
    transit_pref: str = "public_transit"
    repetition_strategy: str = "similar_vibes"
    dietary: List[str] = []

    # Full raw dictionary of all answered questions
    raw_answers: Optional[Dict[str, Any]] = None

class DetailedProfileResponse(BaseModel):
    user_id: str
    avoidances: List[str] = []
    health_factors: List[str] = []
    physical_demand: str = "moderate_walking"
    walking_tolerance: str = "medium"
    schedule_density: str = "balanced_2_3"
    accessibility: List[str] = []
    dietary: List[str] = []
    stay_style: str = "boutique"
    transit_pref: str = "public_transit"
    repetition_strategy: str = "similar_vibes"
    past_trips: List[Dict[str, Any]] = []
    rl_state_vector: List[float]
    feature_dimension: int
    feature_names: List[str]
    summary_text: str
    raw_answers: Optional[Dict[str, Any]] = None


# Level 3: Precision Profile (adaptive questionnaire)
class PrecisionProfileCreate(BaseModel):
    # Full set of answers keyed by question id, e.g. {"q78": 2, "q95": ["peanuts"], "q100": "mushrooms"}
    answers: Dict[str, Any] = {}

class PrecisionInsight(BaseModel):
    kind: str   # constraint | rule | reminder
    text: str

class PrecisionProfileResponse(BaseModel):
    user_id: str
    exists: bool = True
    answers: Dict[str, Any] = {}
    context_answers: Dict[str, Any] = {}
    answered: int = 0
    applicable: int = 0
    coverage: float = 0.0
    dropped_for_privacy: List[str] = []
    insights: List[PrecisionInsight] = []
    rl_state_vector: List[float] = []
    feature_dimension: int = 0
    feature_names: List[str] = []
    summary_text: str = ""

# Recommendations models
class DestinationRecommendation(BaseModel):
    id: str
    name: str
    country: str
    tagline: str
    image_url: Optional[str] = None
    duration: Optional[str] = "4 - 7 days"
    match_score: float
    why_it_suits: str
    tags: List[str] = []
    because_you_said: Optional[str] = None
    available_experiences: List[str] = []
    travel_style_and_atmosphere: str
    practical_considerations: Optional[str] = None
    budget_tier: str
    estimated_cost: str
    best_season_and_weather: str
    limitations_or_uncertainties: str
    warnings: List[str] = []
    is_trending: bool = False
    trending_reason: Optional[str] = None
    is_seasonal: bool = False
    seasonal_event: Optional[str] = None
    icon: str = "fa-map-pin"
    is_sample_data: bool = True
    is_shortlisted: bool = False

class RecommendationsResponse(BaseModel):
    user_id: str
    basis_summary: str
    total_candidates: int = 16
    offset: int = 0
    recommended_for_you: List[DestinationRecommendation]
    trending_trips: List[DestinationRecommendation]
    seasonal_and_upcoming: List[DestinationRecommendation]

class ShortlistToggleRequest(BaseModel):
    destination_id: str

class ShortlistResponse(BaseModel):
    user_id: str
    destination_id: Optional[str] = None
    is_shortlisted: Optional[bool] = None
    shortlisted_ids: List[str] = []
    message: Optional[str] = None

# =============================================================
# ADAPTIVE PRE-TRIP ITINERARY PLANNER MODELS
# =============================================================

class TripCreate(BaseModel):
    destination_id: str
    destination_name: Optional[str] = None
    start_date: str # YYYY-MM-DD
    end_date: str # YYYY-MM-DD
    duration_days: Optional[int] = None
    travellers_count: int = 1
    companions: Optional[str] = "solo"
    has_children: Optional[bool] = False
    has_elderly: Optional[bool] = False
    departure_location: Optional[str] = "Delhi"
    total_budget: float = 25000.0
    currency: str = "INR"
    accommodation_tier: str = "balanced" # 'budget_hostel', 'boutique', 'resort', 'apartment'
    transit_pref: str = "public_transit" # 'public_transit', 'walking', 'rental_car', 'taxi'
    travel_pace: str = "balanced" # 'relaxed', 'balanced', 'packed'
    specific_interests: List[str] = []
    trip_preferences: Optional[Dict[str, Any]] = None
    stay_id: Optional[str] = None
    stay_name: Optional[str] = None
    stay_lat: Optional[float] = None
    stay_lon: Optional[float] = None
    stay_address: Optional[str] = None
    stay_type: Optional[str] = None

class TripResponse(BaseModel):
    id: str
    user_id: str
    destination_id: str
    destination_name: str
    start_date: str
    end_date: str
    duration_days: int
    travellers_count: int
    companions: Optional[str] = "solo"
    has_children: Optional[bool] = False
    has_elderly: Optional[bool] = False
    departure_location: Optional[str] = "Delhi"
    total_budget: float
    currency: str
    accommodation_tier: str
    transit_pref: str
    travel_pace: str
    specific_interests: List[str] = []
    trip_preferences: Optional[Dict[str, Any]] = None
    stay_id: Optional[str] = None
    stay_name: Optional[str] = None
    created_at: str

class ItineraryActivityModel(BaseModel):
    id: str
    itinerary_id: str
    day_number: int
    time_slot: str # 'morning', 'afternoon', 'evening', 'meal'
    activity_id: str
    title: str
    category: str
    description: Optional[str] = None
    location_name: Optional[str] = None
    neighborhood: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    duration_minutes: int = 90
    cost_estimate: float = 0.0
    transit_suggestion: Optional[str] = None
    transit_duration_minutes: int = 15
    why_it_suits: Optional[str] = None
    because_you_said: Optional[str] = None
    status: str = "proposed" # 'proposed', 'accepted', 'rejected', 'modified'
    rejection_reason: Optional[str] = None
    order_index: int = 0
    photo_url: Optional[str] = None
    data_source: str = "curated"

class ItineraryDayModel(BaseModel):
    day_number: int
    date: str
    theme: str
    neighborhood: str
    activities: List[ItineraryActivityModel]
    total_cost: float
    total_duration_minutes: int

class ItineraryResponse(BaseModel):
    id: str
    trip_id: str
    user_id: str
    title: str
    destination_name: str
    total_days: int
    status: str
    total_estimated_cost: float
    summary_notes: str
    days: List[ItineraryDayModel]
    created_at: str
    updated_at: str

class ActivityFeedbackRequest(BaseModel):
    itinerary_id: str
    activity_id: str
    action_type: str # 'accept', 'reject', 'modify'
    rejection_reason: Optional[str] = None # 'too_expensive', 'too_crowded', 'too_physically_demanding', 'not_interested', 'schedule_conflict', 'trip_specific_other'
    is_trip_specific: bool = False # If True, don't permanently modify user general profile
    replacement_activity_id: Optional[str] = None # For modify

class ActivityFeedbackResponse(BaseModel):
    status: str
    message: str
    reward_assigned: float
    is_trip_specific: bool
    policy_updated: bool
    replacement_activity: Optional[ItineraryActivityModel] = None

class ItineraryRegenerateRequest(BaseModel):
    itinerary_id: str
    day_number: Optional[int] = None # None means regenerate entire itinerary

class PolicyArmState(BaseModel):
    arm_id: str
    pull_count: int
    estimated_theta_norm: float
    top_feature_weights: Dict[str, float]
    average_reward: float

class PolicyInspectionResponse(BaseModel):
    user_id: str
    algorithm: str
    feature_dimension: int
    feature_names: List[str]
    arms: List[PolicyArmState]
    total_interactions: int
    exploration_param_alpha: float
    recent_feedback: List[Dict[str, Any]]

class BudgetCategoryItem(BaseModel):
    category: str
    name: str
    description: str
    minimum_cost: float
    recommended_cost: float
    per_person_min: float
    per_person_rec: float
    cost_basis: str
    data_source: str
    assumptions: str

class SliderConfig(BaseModel):
    min: float
    default: float
    max: float
    step: float

class MinimumBudgetRequest(BaseModel):
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    departure_location: Optional[str] = "Delhi"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_days: Optional[int] = None
    travellers_count: int = 1
    accommodation_tier: Optional[str] = "boutique"
    transit_pref: Optional[str] = "public_transit"
    travel_pace: Optional[str] = "balanced"
    include_shopping: bool = False
    user_id: Optional[str] = None

class MinimumBudgetResponse(BaseModel):
    destination: Dict[str, Any]
    departure_location: str
    duration_days: int
    nights_count: int
    travellers_count: int
    rooms_count: int
    intercity_distance_km: float
    bare_minimum_budget: float
    recommended_budget: float
    bare_minimum_per_person: float
    recommended_per_person: float
    bare_minimum_daily_per_person: float
    recommended_daily_per_person: float
    categories: List[BudgetCategoryItem]
    slider_config: SliderConfig
    currency: str = "INR"

class BudgetValidationRequest(BaseModel):
    selected_budget: float
    bare_minimum_budget: float
    recommended_budget: float

class BudgetValidationResponse(BaseModel):
    is_sufficient: bool
    tier: str
    shortfall: Optional[float] = None
    surplus_above_min: Optional[float] = None
    surplus_above_recommended: Optional[float] = None
    warning: Optional[str] = None
    message: str


