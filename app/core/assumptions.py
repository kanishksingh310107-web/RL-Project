"""Central assumptions repository for RL Travel Guide.

All numeric assumptions (speeds, durations, budget shares, thresholds, limits)
live in this single file, each annotated with a one-line explanatory note
and explicitly labelled 'team assumption, not measured'.
"""
from typing import Dict, Any

# Indicative INR planning assumptions, never live quotes. Room prices are per
# room/night (hostels are conservatively budgeted as private/shared rooms).
STAY_RATES_INR = {'hostel': (600, 900), 'budget': (1000, 1600),
                  'mid_range': (2200, 3500), 'boutique': (4000, 6500),
                  'luxury': (8000, 14000)}
TIER_LABELS = {'hostel': 'Hostel', 'budget': 'Budget', 'mid_range': 'Mid-range',
               'boutique': 'Boutique & Heritage', 'luxury': 'Luxury'}
# At most two travellers per room, including children; conservative, no free beds.
ROOM_OCCUPANCY = 2
# Round-trip road distance uses CIRCUITY_FACTOR; per-person per-km and one-way
# fare floors for public transit, taxi/car, scooter and walking (intercity by bus).
INTERCITY_RATES_INR = {'public_transit': (1.8, 250), 'taxi': (7, 800),
                       'rental_car': (6, 700), 'scooter': (3, 300), 'walking': (1.8, 250)}
LOCAL_DAILY_INR = {'public_transit': 180, 'taxi': 900, 'rental_car': 750,
                   'scooter': 350, 'walking': 60}
# Meals, drinking water and snacks per person/day, scaled by stay tier.
FOOD_DAILY_INR = {'street_food': 400, 'local': 650, 'all': 650,
                  'vegetarian': 600, 'vegan': 700, 'fine_dining': 1500}
FOOD_TIER_MULTIPLIER = {'hostel': 1, 'budget': 1.1, 'mid_range': 1.25,
                        'boutique': 1.5, 'luxury': 2}
INCIDENTALS_DAILY_INR = 90  # data, shoe storage and small necessary incidentals
SHOPPING_INR = 1500  # optional per-person trip allowance
CONTINGENCY_RATE = .10  # reserve on all planned expenses
CHILD_ENTRY_FACTOR = .5  # indicative only; confirm actual ticket eligibility/ages
SENIOR_ENTRY_FACTOR = 1.0  # no unverified senior concession assumed
UNKNOWN_ENTRY_INR = 150  # only used when no catalogue ticket value is available
LEGACY_USD_TO_INR = 83  # explicitly marked legacy catalogue currency conversion
BUDGET_BAND_LABELS = {'insufficient': 'Below minimum',
                      'budget_conscious': 'Budget-Conscious', 'comfortable': 'Comfortable'}

# Transport speeds (km/h) across local Indian transit modes
# team assumption, not measured: typical Indian pedestrian walking speed with stops
SPEED_WALK_KMH: float = 4.5
# team assumption, not measured: auto-rickshaw navigating congested urban Indian streets
SPEED_AUTO_KMH: float = 22.0
# team assumption, not measured: city cab/taxi factoring in signals and traffic bottlenecks
SPEED_CAB_KMH: float = 25.0
# team assumption, not measured: self-drive rental car including parking search time
SPEED_RENTAL_CAR_KMH: float = 28.0
# team assumption, not measured: rented two-wheeler/scooter navigating traffic flows
SPEED_SCOOTER_KMH: float = 24.0
# team assumption, not measured: city bus or metro including station walk and wait dwell time
SPEED_BUS_METRO_KMH: float = 18.0

MODE_SPEEDS_KMH: Dict[str, float] = {
    "walk": SPEED_WALK_KMH,
    "auto": SPEED_AUTO_KMH,
    "cab": SPEED_CAB_KMH,
    "rental_car": SPEED_RENTAL_CAR_KMH,
    "scooter": SPEED_SCOOTER_KMH,
    "bus_metro": SPEED_BUS_METRO_KMH,
}

# Distance & transit overhead
# team assumption, not measured: urban road network circuity multiplier over Euclidean straight-line distance
CIRCUITY_FACTOR: float = 1.35
# team assumption, not measured: fixed boarding, waiting, or parking overhead in minutes per transit leg
TRANSIT_FIXED_OVERHEAD_MINUTES: float = 5.0

# Visit durations per activity category (minutes)
# team assumption, not measured: average museum, fort, or historical site exploration time
DURATION_CULTURE_HISTORY_MINUTES: int = 90
# team assumption, not measured: average outdoor park, lake, trail, or nature spot exploration time
DURATION_NATURE_OUTDOORS_MINUTES: int = 120
# team assumption, not measured: sit-down meal or authentic culinary dining experience time
DURATION_FOOD_DINING_MINUTES: int = 60
# team assumption, not measured: active adventure sport, rafting, or trekking slot time
DURATION_ADVENTURE_MINUTES: int = 150
# team assumption, not measured: beach, garden, or quiet relaxation pause time
DURATION_RELAXATION_MINUTES: int = 75
# team assumption, not measured: local bazaar, artisan market, or shopping stroll time
DURATION_SHOPPING_LOCAL_MINUTES: int = 60
# team assumption, not measured: scenic viewpoint, photo stop, or panoramic overlook time
DURATION_SCENIC_MINUTES: int = 45

CATEGORY_DURATIONS_MINUTES: Dict[str, int] = {
    "culture_history": DURATION_CULTURE_HISTORY_MINUTES,
    "nature_outdoors": DURATION_NATURE_OUTDOORS_MINUTES,
    "food_dining": DURATION_FOOD_DINING_MINUTES,
    "adventure": DURATION_ADVENTURE_MINUTES,
    "relaxation": DURATION_RELAXATION_MINUTES,
    "shopping_local": DURATION_SHOPPING_LOCAL_MINUTES,
    "scenic": DURATION_SCENIC_MINUTES,
}

# Day scheduling utilization fraction by pace
# team assumption, not measured: fraction of available day minutes scheduled for relaxed pace
PACE_UTILIZATION_RELAXED: float = 0.65
# team assumption, not measured: fraction of available day minutes scheduled for balanced pace
PACE_UTILIZATION_BALANCED: float = 0.80
# team assumption, not measured: fraction of available day minutes scheduled for packed pace
PACE_UTILIZATION_PACKED: float = 0.95

PACE_UTILIZATION: Dict[str, float] = {
    "relaxed": PACE_UTILIZATION_RELAXED,
    "balanced": PACE_UTILIZATION_BALANCED,
    "packed": PACE_UTILIZATION_PACKED,
}

# Meal windows and durations
# team assumption, not measured: standard morning breakfast time window
MEAL_WINDOW_BREAKFAST: Dict[str, Any] = {"start": "08:30", "end": "09:30", "duration_minutes": 45}
# team assumption, not measured: standard midday lunch time window
MEAL_WINDOW_LUNCH: Dict[str, Any] = {"start": "12:30", "end": "14:00", "duration_minutes": 60}
# team assumption, not measured: standard evening dinner time window
MEAL_WINDOW_DINNER: Dict[str, Any] = {"start": "19:30", "end": "21:00", "duration_minutes": 75}

# Budget breakdown shares (fraction of total trip budget, must sum to 1.0)
# team assumption, not measured: accommodation budget share of total budget
BUDGET_SHARE_STAY: float = 0.35
# team assumption, not measured: food and dining budget share of total budget
BUDGET_SHARE_FOOD: float = 0.25
# team assumption, not measured: activities, entries, and sightseeing budget share of total budget
BUDGET_SHARE_ACTIVITIES: float = 0.20
# team assumption, not measured: local transit, cabs, and conveyance budget share of total budget
BUDGET_SHARE_TRANSPORT: float = 0.10
# team assumption, not measured: local market and souvenir shopping budget share of total budget
BUDGET_SHARE_SHOPPING: float = 0.05
# team assumption, not measured: unallocated emergency and miscellaneous buffer budget share
BUDGET_SHARE_BUFFER: float = 0.05

BUDGET_SHARES: Dict[str, float] = {
    "stay": BUDGET_SHARE_STAY,
    "food": BUDGET_SHARE_FOOD,
    "activities": BUDGET_SHARE_ACTIVITIES,
    "transport": BUDGET_SHARE_TRANSPORT,
    "shopping": BUDGET_SHARE_SHOPPING,
    "buffer": BUDGET_SHARE_BUFFER,
}

# Shopping venue tier mappings
# team assumption, not measured: venue categories mapped to user shopping budget tiers
SHOPPING_TIERS: Dict[str, Dict[str, Any]] = {
    "bargain_markets": {"preferred_category": "commercial.marketplace", "budget_level": "budget"},
    "local_crafts": {"preferred_category": "commercial.gift_and_souvenir", "budget_level": "mid_range"},
    "malls_brands": {"preferred_category": "commercial.shopping_mall", "budget_level": "mid_range"},
    "boutique": {"preferred_category": "commercial.clothing", "budget_level": "luxury"},
}

# Climate & seasonality evaluation thresholds
# team assumption, not measured: lower bound in Celsius for pleasant outdoor sightseeing
SEASON_TEMP_COMFORT_MIN_C: float = 14.0
# team assumption, not measured: upper bound in Celsius before heat stress reduces tourism appeal
SEASON_TEMP_COMFORT_MAX_C: float = 32.0
# team assumption, not measured: monthly rainfall in mm above which monsoon disruptions are likely
SEASON_RAIN_HEAVY_MONTHLY_MM: float = 120.0

# Destination ranking component default weights (must sum to 1.0)
# team assumption, not measured: default weight for user preference alignment in destination ranking
RANKING_WEIGHT_INTEREST: float = 0.25
# team assumption, not measured: default weight for climate and seasonal suitability in destination ranking
RANKING_WEIGHT_SEASON: float = 0.20
# team assumption, not measured: default weight for popularity and tourist infrastructure density
RANKING_WEIGHT_POPULARITY: float = 0.15
# team assumption, not measured: default weight for travel pace and budget feasibility
RANKING_WEIGHT_FEASIBILITY: float = 0.15
# team assumption, not measured: default weight for real-time live availability and weather
RANKING_WEIGHT_LIVE: float = 0.10
# team assumption, not measured: default weight for past user rating and return feedback
RANKING_WEIGHT_FEEDBACK: float = 0.15

RANKING_DEFAULT_WEIGHTS: Dict[str, float] = {
    "interest": RANKING_WEIGHT_INTEREST,
    "season": RANKING_WEIGHT_SEASON,
    "popularity": RANKING_WEIGHT_POPULARITY,
    "feasibility": RANKING_WEIGHT_FEASIBILITY,
    "live": RANKING_WEIGHT_LIVE,
    "feedback": RANKING_WEIGHT_FEEDBACK,
}

# Currency conversion
# team assumption, not measured: approximate INR to USD conversion rate for budget estimation
INR_TO_USD_RATE: float = 0.012

# External API guard rails
# team assumption, not measured: Geoapify free tier daily credit guard limit
GEOAPIFY_DAILY_CREDIT_LIMIT: int = 2500
# team assumption, not measured: maximum Geoapify API calls allowed per single user interaction
GEOAPIFY_MAX_CALLS_PER_REQUEST: int = 8
# team assumption, not measured: HTTP timeout in seconds for third-party provider calls
PROVIDER_HTTP_TIMEOUT_SECONDS: float = 8.0
# team assumption, not measured: cache time-to-live in days for geocoding and places
CACHE_TTL_DAYS_PLACES: int = 7
# team assumption, not measured: cache time-to-live in hours for dynamic weather forecasts
CACHE_TTL_HOURS_WEATHER: int = 1

# Indicative transport comparison assumptions; same shared model supplies leg
# and daily option estimates. These are not quotes from cab/rental operators.
LOCAL_LEG_RATE_INR = {'walk':0, 'auto':18, 'cab':26, 'rental_car':32, 'scooter':8, 'bus_metro':5}
LOCAL_LEG_BASE_INR = 50
RENTAL_DAY_INR = 2500
RENTAL_INCLUDED_KM = 80
RENTAL_EXTRA_KM_INR = 16
CAB_PICKUP_INR = 60
PUBLIC_BOARDING_INR = 25
PUBLIC_CONNECTOR_KM_INR = 12
FALLBACK_CATEGORY_PRICE_INR = {'culture_history':250, 'food_dining':450, 'other':150}
