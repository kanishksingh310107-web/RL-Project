"""Core domain schemas for RL-Based Proactive Travel Guide.

Defines the contract data types shared across foundation (Person C),
planning (Person A), and stay/prep/live (Person B).
Every externally derived field is Optional and carries Provenance metadata.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Metadata tracking the origin, timestamp, and authenticity of data.
    
    Guarantees no invented data by explicitly recording whether an attribute
    is live, estimated, simulated, or from an offline curated fallback.
    """
    source: str = "curated_catalogue"  # 'geoapify', 'open-meteo', 'curated_catalogue', 'assumed'
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_live: bool = False
    is_estimate: bool = False
    notes: Optional[str] = None


class Place(BaseModel):
    """Normalized place or activity representation."""
    id: str
    name: str
    category: str  # culture_history, nature_outdoors, food_dining, adventure, relaxation, shopping_local, scenic
    destination_id: Optional[str] = None
    city: Optional[str] = None
    lat: float
    lon: float
    address: Optional[str] = None
    neighbourhood: Optional[str] = None
    opening_hours: Optional[str] = None
    opening_days: Optional[List[str]] = None
    typical_duration_minutes: Optional[int] = None
    rating: Optional[float] = None
    price_level: Optional[str] = None  # budget, mid_range, luxury
    cost_amount: Optional[float] = None  # None if unknown, NEVER 0 for unknown
    cuisine: Optional[List[str]] = None
    diet_tags: Optional[List[str]] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    photo_url: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class DayWindow(BaseModel):
    """Available time span for a single day."""
    day_number: int
    date: Optional[str] = None  # YYYY-MM-DD
    start_time: str = "09:00"   # HH:MM
    end_time: str = "21:00"     # HH:MM
    available_minutes: int = 720


class MealWindow(BaseModel):
    """Time anchor reserved for a meal break."""
    meal_type: str  # breakfast, lunch, dinner
    start_time: str  # HH:MM
    end_time: str    # HH:MM
    duration_minutes: int = 60
    preferred_cuisine: Optional[List[str]] = None
    dietary_tags: Optional[List[str]] = None


class TripPrefs(BaseModel):
    """Trip scheduling preferences and parameters."""
    trip_id: str
    user_id: str
    pace: str = "balanced"  # relaxed, balanced, packed
    start_time: str = "09:00"
    end_time: str = "21:00"
    arrival_time: Optional[str] = None
    departure_time: Optional[str] = None
    meal_windows: List[MealWindow] = []
    shopping_style: str = "mix"  # bargain_markets, local_crafts, malls_brands, mix
    shopping_budget: Optional[float] = None
    transport_preferences: List[str] = []
    budget_shares: Dict[str, float] = {}
    provenance: Provenance = Field(default_factory=Provenance)


class TravelLeg(BaseModel):
    """Transit leg between two stops in an itinerary."""
    from_place_id: Optional[str] = None
    to_place_id: Optional[str] = None
    mode: str = "cab"  # walk, auto, cab, rental_car, scooter, bus_metro
    duration_minutes: int
    distance_km: float
    estimated_cost: Optional[float] = None
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(source="assumed", is_estimate=True, notes="straight-line estimate")
    )


class Block(BaseModel):
    """A scheduled block within a day plan (activity, meal, shopping, travel)."""
    block_id: str
    block_type: str  # activity, meal, shopping, travel, buffer
    start_time: str  # HH:MM
    end_time: str    # HH:MM
    duration_minutes: int
    place: Optional[Place] = None
    travel_leg: Optional[TravelLeg] = None
    notes: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class DayPlan(BaseModel):
    """A complete single day plan."""
    day_number: int
    date: Optional[str] = None
    window: DayWindow
    blocks: List[Block] = []
    leftovers: List[Place] = []
    warnings: List[str] = []


class BudgetLine(BaseModel):
    """A line item in the trip budget ledger."""
    category: str  # stay, food, transport, activities, shopping, buffer
    allocated_amount: float
    estimated_spent: float
    currency: str = "INR"
    status: str = "green"  # green, amber, red
    notes: Optional[str] = None


class Stay(BaseModel):
    """Accommodation selection or recommendation."""
    kind: str = 'accommodation'
    distance_km: Optional[float] = None
    tier: Optional[str] = None
    tier_label: Optional[str] = None
    price_bands: Dict[str, Any] = {}
    label: Optional[str] = None
    stay_id: str
    trip_id: str
    name: str
    stay_type: str = "mid_range"  # budget_guesthouse, boutique_hotel, resort, homestay, apartment
    lat: float
    lon: float
    address: Optional[str] = None
    neighbourhood: Optional[str] = None
    stars: Optional[float] = None
    estimated_nightly_budget: Optional[float] = None  # budget band, NEVER a hotel price
    external_search_url: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class TripPlan(BaseModel):
    """Overall multi-day trip plan."""
    trip_id: str
    user_id: str
    destination_id: str
    destination_name: str
    total_days: int
    days: List[DayPlan] = []
    budget_ledger: List[BudgetLine] = []
    overall_budget_status: str = "green"  # green, amber, red
    stay_anchor: Optional[Stay] = None
    created_at: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance: Provenance = Field(default_factory=Provenance)
