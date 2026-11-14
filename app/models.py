# Data models for auth and traveller profile
from pydantic import BaseModel, Field, model_validator, field_validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

# Auth models
class AuthRequest(BaseModel):
    provider: str
    identifier: str
    mode: Optional[str] = None
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
    credential: str = Field(min_length=20,max_length=8192)

class GoogleClientConfig(BaseModel):
    client_id: str = Field(pattern=r'^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$', max_length=200)

    @field_validator('client_id',mode='before')
    @classmethod
    def trim_client_id(cls,value):
        return value.strip() if isinstance(value,str) else value

# Basic Starting Profile (Sections 1, 3, 4, 5, 6, 8 - ~30-60s setup)
class ShortProfileCreate(BaseModel):
    residence_country: Optional[str] = Field(default=None,max_length=2)
    residence_state: Optional[str] = Field(default=None,max_length=100)
    residence_city: Optional[str] = Field(default=None,max_length=100)
    preferred_currency: Optional[str] = Field(default=None,max_length=3)

    @field_validator('residence_country','residence_state','residence_city','preferred_currency',mode='before')
    @classmethod
    def normalise_home_text(cls,value,info):
        if value is None:
            return None
        if not isinstance(value,str):
            raise ValueError('Enter text for this field.')
        value = value.strip()
        return value.upper() if info.field_name in ('residence_country','preferred_currency') else value
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
    residence_country: Optional[str] = None
    residence_state: Optional[str] = None
    residence_city: Optional[str] = None
    preferred_currency: str = 'INR'
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
    additional_info: Optional[str] = None

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
    additional_info: Optional[str] = None

# Recommendations models
class DestinationRecommendation(BaseModel):
    estimated_cost_inr: Optional[float] = None
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

class Party(BaseModel):
    adults: int = Field(1, ge=1, le=30, strict=True)
    children: int = Field(0, ge=0, le=30, strict=True)
    seniors: int = Field(0, ge=0, le=30, strict=True)


TRIP_PLANNING_DETAIL_FIELDS = (
    'destination_arrival_time', 'hotel_checkin_time', 'hotel_checkout_time',
    'transport_departure_time', 'departure_terminal', 'departure_transport_mode',
    'final_day_activities', 'luggage_storage', 'terminal_arrival_buffer_minutes',
    'station_arrival_buffer_minutes', 'terminal_journey_minutes', 'lunch_start_time',
    'lunch_end_time', 'lunch_duration_minutes', 'dinner_start_time', 'dinner_end_time',
    'dinner_duration_minutes', 'rest_preference', 'shopping_enabled', 'shopping_duration_minutes', 'shopping_budget_inr',
)


class TripCreate(BaseModel):
    @field_validator('destination_id','destination_name','departure_location', mode='before')
    @classmethod
    def clean_trip_text(cls, value, info):
        if value is None and info.field_name != 'destination_id':
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Enter a non-empty '+info.field_name.replace('_',' ')+'.')
        value=value.strip()
        limits={'destination_id':120,'destination_name':200,'departure_location':200}
        if len(value)>limits[info.field_name]:
            raise ValueError(info.field_name.replace('_',' ').title()+' is too long.')
        return value

    @field_validator('accommodation_tier','travel_pace','transit_pref')
    @classmethod
    def valid_trip_option(cls,value,info):
        options = {
            'accommodation_tier': {'hostel','budget','mid_range','boutique','luxury','budget_hostel','budget_hotel',
                'budget_guesthouse','balanced','boutique_hotel','heritage','resort','apartment','homestay'},
            'travel_pace': {'relaxed','balanced','active','packed'},
            'transit_pref': {'public_transit','taxi','rental_car','scooter','walking','bus_metro','train','cab','cab_rental','walk','auto'},
        }
        value=value.strip().lower()
        if value not in options[info.field_name]:
            raise ValueError('Choose a valid '+info.field_name.replace('_',' ')+'.')
        return value
    schedule_prefs: Optional[Dict[str, Any]] = None
    party: Optional[Party] = None
    @model_validator(mode='after')
    def sync_party(self):
        from app.core.party import normalize_party, party_type
        explicitly_solo = ('companions' in self.model_fields_set and self.companions == 'solo') or self.trip_type == 'solo'
        composition = normalize_party(self.model_dump())
        if sum(composition.values()) > 30:
            raise ValueError('A trip can include at most 30 travellers.')
        if explicitly_solo and (sum(composition.values()) > 1 or self.travellers_count > 1):
            raise ValueError('Solo requires exactly one adult. Change the party type or traveller counts.')
        self.party = Party(**composition)
        self.travellers_count = sum(composition.values())
        # trip_type is the user's relationship/context choice. Keep the old
        # companions alias derived from counts for clients that still consume it.
        if self.trip_type is None:
            aliases = {'partner': 'couple', 'alone': 'solo'}
            legacy = aliases.get((self.companions or '').strip().lower(), (self.companions or '').strip().lower()) if 'companions' in self.model_fields_set else None
            self.trip_type = legacy if legacy in ('solo','couple','friends','family') else (
                'family' if composition['children'] or composition['seniors'] else
                ('solo' if composition['adults'] == 1 else 'couple' if composition['adults'] == 2 else 'friends'))
        self.companions = party_type(composition)
        self.has_children = composition['children'] > 0
        self.has_elderly = composition['seniors'] > 0
        self.trip_preferences = dict(self.trip_preferences or {}, party=composition, trip_type=self.trip_type)
        if any(key in self.model_fields_set for key in TRIP_PLANNING_DETAIL_FIELDS):
            for key in TRIP_PLANNING_DETAIL_FIELDS:
                value = getattr(self, key, None)
                if value is not None:
                    self.trip_preferences[key] = value
        from datetime import date
        try:
            start_date = date.fromisoformat(self.start_date)
            end_date = date.fromisoformat(self.end_date)
        except (TypeError, ValueError) as exc:
            raise ValueError('Use valid YYYY-MM-DD travel dates.') from exc
        if (end_date - start_date).days not in range(0, 90):
            raise ValueError('A trip must last between 1 and 90 days.')
        if self.departure_transport_mode=='flight' and self.terminal_arrival_buffer_minutes<120:
            raise ValueError('Allow at least 120 minutes at the airport.')
        if self.dinner_end_time <= self.dinner_start_time:
            raise ValueError('Dinner end time must be after dinner start time.')
        if self.lunch_end_time <= self.lunch_start_time:
            raise ValueError('Lunch end time must be after lunch start time.')
        if self.trip_type == 'solo' and composition != {'adults': 1, 'children': 0, 'seniors': 0}:
            raise ValueError('Solo trips require exactly one adult.')
        return self

    destination_id: str
    destination_name: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lon: Optional[float] = None
    resolved_location: Optional[str] = None
    start_date: str # YYYY-MM-DD
    end_date: str # YYYY-MM-DD
    duration_days: Optional[int] = None
    travellers_count: int = Field(1, ge=1, le=30, strict=True)
    companions: Optional[str] = "solo"
    has_children: Optional[bool] = False
    has_elderly: Optional[bool] = False
    departure_location: Optional[str] = "Delhi"
    total_budget: float = Field(25000.0, gt=0, le=1_000_000_000)
    currency: str = "INR"
    accommodation_tier: str = "balanced" # 'budget_hostel', 'boutique', 'resort', 'apartment'
    transit_pref: str = "public_transit" # 'public_transit', 'walking', 'rental_car', 'taxi'
    travel_pace: str = "balanced" # 'relaxed', 'balanced', 'packed'
    specific_interests: List[str] = []
    trip_preferences: Optional[Dict[str, Any]] = None
    trip_type: Optional[Literal['solo','couple','friends','family']] = None
    destination_arrival_time: Optional[str] = None
    hotel_checkin_time: Optional[str] = None
    hotel_checkout_time: Optional[str] = None
    transport_departure_time: Optional[str] = None
    departure_terminal: Optional[str] = Field(None, max_length=200)
    departure_transport_mode: Optional[Literal['flight','train','bus','other']] = None
    final_day_activities: bool = False
    luggage_storage: bool = False
    terminal_arrival_buffer_minutes: int = Field(120, ge=0, le=360, strict=True)
    station_arrival_buffer_minutes: int = Field(45, ge=30, le=60, strict=True)
    terminal_journey_minutes: int = Field(0, ge=0, le=600, strict=True)
    lunch_start_time: str = '12:30'
    lunch_end_time: str = '14:30'
    lunch_duration_minutes: int = Field(60, ge=15, le=180, strict=True)
    dinner_start_time: str = '19:00'
    dinner_end_time: str = '21:00'
    dinner_duration_minutes: int = Field(60,ge=15,le=180,strict=True)
    rest_preference: Literal['none','short','standard','long'] = 'standard'
    shopping_enabled: bool = False
    shopping_duration_minutes: int = Field(0, ge=0, le=480, strict=True)
    shopping_budget_inr: Optional[int] = Field(None, ge=0, le=1_000_000_000, strict=True)

    @field_validator('destination_arrival_time','hotel_checkin_time','hotel_checkout_time',
                     'transport_departure_time','lunch_start_time','lunch_end_time','dinner_start_time','dinner_end_time')
    @classmethod
    def valid_trip_times(cls, value):
        if value is None:
            return value
        try:
            if len(value) != 5 or datetime.strptime(value, '%H:%M').strftime('%H:%M') != value:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError('Use 24-hour HH:MM time.') from exc
        return value

    @field_validator('departure_terminal', mode='before')
    @classmethod
    def clean_terminal(cls, value):
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Enter a terminal, station or stop, or leave it blank.')
        return value.strip()

    @field_validator('total_budget', mode='before')
    @classmethod
    def whole_budget_amount(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer():
            raise ValueError('Budget must be a whole amount.')
        return int(value)

    @field_validator('currency')
    @classmethod
    def valid_currency_code(cls, value):
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError('Use a valid three-letter currency code.')
        return value
    stay_id: Optional[str] = None
    stay_name: Optional[str] = None
    stay_lat: Optional[float] = None
    stay_lon: Optional[float] = None
    stay_address: Optional[str] = None
    stay_type: Optional[str] = None

class TripResponse(BaseModel):
    cost_breakdown: Dict[str, Any] = {}
    assumptions: Dict[str, Any] = {}
    confidence: str = 'indicative'

    party: Optional[Party] = None
    party_type: Optional[str] = None
    trip_type: Optional[str] = None
    destination_arrival_time: Optional[str] = None
    hotel_checkin_time: Optional[str] = None
    hotel_checkout_time: Optional[str] = None
    transport_departure_time: Optional[str] = None
    departure_terminal: Optional[str] = None
    departure_transport_mode: Optional[str] = None
    final_day_activities: bool = False
    luggage_storage: bool = False
    terminal_arrival_buffer_minutes: int = 120
    station_arrival_buffer_minutes: int = 45
    terminal_journey_minutes: int = 0
    lunch_start_time: str = '12:30'
    lunch_end_time: str = '14:30'
    lunch_duration_minutes: int = 60
    dinner_start_time: str = '19:00'
    dinner_end_time: str = '21:00'
    dinner_duration_minutes: int = Field(60,ge=15,le=180,strict=True)
    rest_preference: str = 'standard'
    shopping_enabled: bool = False
    shopping_duration_minutes: int = 0
    shopping_budget_inr: Optional[int] = None
    party_label: Optional[str] = None
    status: str = 'planned'
    message: Optional[str] = None
    cost_estimate: Optional[Dict[str, Any]] = None

    id: str
    user_id: str
    destination_id: str
    destination_name: str
    destination_lat: Optional[float] = None
    destination_lon: Optional[float] = None
    resolved_location: Optional[str] = None
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
    schedule_prefs: Optional[Dict[str, Any]] = None
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
    cost_breakdown: Dict[str, Any] = {}
    cost_estimate: Dict[str, Any] = {}
    assumptions: Dict[str, Any] = {}
    confidence: str = 'indicative'

    id: str
    trip_id: str
    user_id: str
    title: str
    destination_id: Optional[str] = None
    destination_name: str
    destination_lat: Optional[float] = None
    destination_lon: Optional[float] = None
    resolved_location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
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
    occurrence_id: Optional[str] = None
    action_type: str # 'accept', 'reject', 'modify'
    rejection_reason: Optional[str] = None # 'too_expensive', 'too_crowded', 'too_physically_demanding', 'not_interested', 'schedule_conflict', 'trip_specific_other'
    is_trip_specific: bool = False # If True, don't permanently modify user general profile
    replacement_activity_id: Optional[str] = None # For modify


class ItineraryAcceptAllRequest(BaseModel):
    itinerary_id: str = Field(min_length=1, max_length=100)

class ActivityFeedbackResponse(BaseModel):
    status: str
    message: str
    reward_assigned: float
    is_trip_specific: bool
    policy_updated: bool
    accepted_count: int = 0
    remaining_unreviewed: int = 0
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
    party: Optional[Party] = None
    food_style: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lon: Optional[float] = None

    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    departure_location: Optional[str] = "Delhi"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_days: Optional[int] = None
    travellers_count: int = Field(1, ge=1)
    accommodation_tier: Optional[str] = "boutique"
    transit_pref: Optional[str] = "public_transit"
    travel_pace: Optional[str] = "balanced"
    include_shopping: bool = False
    user_id: Optional[str] = None

class MinimumBudgetResponse(BaseModel):
    budget_band_labels: Dict[str, str] = {}

    cost_breakdown: Dict[str, Any] = {}
    assumptions: Dict[str, Any] = {}
    confidence: str = 'indicative'

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


