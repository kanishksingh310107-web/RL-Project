"""Curated Pan-India Destinations across North, West, South, East & North-East regions.
Provides rich metadata including regional coordinates, tags, budget tiers,
estimated costs in INR, and optimal travel seasons.
"""

from typing import Any, Dict, List, Optional


INDIAN_DESTINATIONS: List[Dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # North Region
    # -------------------------------------------------------------------------
    {
        "id": "manali_spiti_india",
        "name": "Manali & Spiti Valley",
        "region": "North",
        "state": "Himachal Pradesh",
        "country": "India",
        "lat": 32.2432,
        "lon": 77.1892,
        "budget_tier": "mid_range",
        "estimated_cost_inr": 25000,
        "best_seasons": ["May", "June", "July", "August", "September", "October"],
        "tags": ["mountains", "adventure", "snow", "road_trip", "culture", "nature"],
        "description": "High-altitude Himalayan wonderland with ancient Buddhist monasteries, rugged passes, and alpine pine valleys.",
    },
    {
        "id": "rishikesh_haridwar_india",
        "name": "Rishikesh & Haridwar",
        "region": "North",
        "state": "Uttarakhand",
        "country": "India",
        "lat": 30.0869,
        "lon": 78.2676,
        "budget_tier": "budget",
        "estimated_cost_inr": 15000,
        "best_seasons": ["September", "October", "November", "March", "April", "May"],
        "tags": ["spiritual", "adventure", "yoga", "river_rafting", "nature", "ghats"],
        "description": "Yoga capital of the world on the holy Ganges River, renowned for river rafting, suspension bridges, and evening Ganga Aarti.",
    },
    {
        "id": "leh_ladakh_india",
        "name": "Leh Ladakh",
        "region": "North",
        "state": "Ladakh",
        "country": "India",
        "lat": 34.1526,
        "lon": 77.5771,
        "budget_tier": "luxury",
        "estimated_cost_inr": 45000,
        "best_seasons": ["June", "July", "August", "September"],
        "tags": ["high_altitude", "monasteries", "adventure", "lakes", "road_trip", "scenic"],
        "description": "Breathtaking cold desert trans-Himalayan plateau with azure high-altitude lakes like Pangong Tso and ancient Tibetan gompas.",
    },
    {
        "id": "varanasi_india",
        "name": "Varanasi",
        "region": "North",
        "state": "Uttar Pradesh",
        "country": "India",
        "lat": 25.3176,
        "lon": 82.9739,
        "budget_tier": "budget",
        "estimated_cost_inr": 12000,
        "best_seasons": ["October", "November", "December", "January", "February", "March"],
        "tags": ["spiritual", "culture_history", "ghats", "temple", "food_dining", "heritage"],
        "description": "One of the oldest continuously inhabited cities on Earth, famed for its sacred riverfront ghats, dawn boat rides, and silk weavers.",
    },

    # -------------------------------------------------------------------------
    # West Region
    # -------------------------------------------------------------------------
    {
        "id": "udaipur_mewar_india",
        "name": "Udaipur & Mewar",
        "region": "West",
        "state": "Rajasthan",
        "country": "India",
        "lat": 24.5854,
        "lon": 73.7125,
        "budget_tier": "luxury",
        "estimated_cost_inr": 35000,
        "best_seasons": ["October", "November", "December", "January", "February", "March"],
        "tags": ["royalty", "palaces", "lakes", "culture_history", "romantic", "heritage"],
        "description": "The City of Lakes, crowned by the majestic City Palace complex, floating Lake Palace, and romantic Aravali mountain sunsets.",
    },
    {
        "id": "jaipur_jodhpur_india",
        "name": "Jaipur & Jodhpur",
        "region": "West",
        "state": "Rajasthan",
        "country": "India",
        "lat": 26.9124,
        "lon": 75.7873,
        "budget_tier": "mid_range",
        "estimated_cost_inr": 28000,
        "best_seasons": ["October", "November", "December", "January", "February", "March"],
        "tags": ["forts", "palaces", "heritage", "shopping_local", "food_dining", "culture_history"],
        "description": "Royal fortresses of Rajasthan: the Pink City's Amber Fort and Hawa Mahal paired with the Blue City's towering Mehrangarh Fort.",
    },
    {
        "id": "south_goa_india",
        "name": "South Goa",
        "region": "West",
        "state": "Goa",
        "country": "India",
        "lat": 15.2736,
        "lon": 73.9580,
        "budget_tier": "mid_range",
        "estimated_cost_inr": 26000,
        "best_seasons": ["November", "December", "January", "February", "March"],
        "tags": ["beach", "relaxation", "coastal", "seafood", "nature", "nightlife"],
        "description": "Pristine white sand beaches (Palolem, Agonda), Portuguese baroque colonial churches, and relaxed coastal seafood shacks.",
    },

    # -------------------------------------------------------------------------
    # South Region
    # -------------------------------------------------------------------------
    {
        "id": "kerala_alleppey_india",
        "name": "Munnar & Alleppey (Kerala)",
        "region": "South",
        "state": "Kerala",
        "country": "India",
        "lat": 9.4981,
        "lon": 76.3388,
        "budget_tier": "mid_range",
        "estimated_cost_inr": 28000,
        "best_seasons": ["September", "October", "November", "December", "January", "February", "March"],
        "tags": ["tea_plantations", "backwaters", "houseboat", "nature", "relaxation", "ayurveda"],
        "description": "God's Own Country: emerald tea estates of the Western Ghats flowing into the tranquil palm-fringed backwaters and houseboats of Alleppey.",
    },
    {
        "id": "hampi_india",
        "name": "Hampi",
        "region": "South",
        "state": "Karnataka",
        "country": "India",
        "lat": 15.3350,
        "lon": 76.4600,
        "budget_tier": "budget",
        "estimated_cost_inr": 14000,
        "best_seasons": ["October", "November", "December", "January", "February"],
        "tags": ["unesco_heritage", "ancient_ruins", "architecture", "bouldering", "history", "spiritual"],
        "description": "UNESCO World Heritage ruinscape of the Vijayanagara Empire with monolithic granite boulders, the Stone Chariot, and Tungabhadra riverbanks.",
    },
    {
        "id": "ooty_coorg_india",
        "name": "Ooty & Coorg",
        "region": "South",
        "state": "Tamil Nadu & Karnataka",
        "country": "India",
        "lat": 11.4102,
        "lon": 76.6950,
        "budget_tier": "mid_range",
        "estimated_cost_inr": 22000,
        "best_seasons": ["October", "November", "December", "January", "February", "March", "April", "May"],
        "tags": ["hill_station", "coffee_plantations", "nature", "scenic", "wildlife", "tea_estates"],
        "description": "Lush Nilgiri mountain toy train trails, cascading waterfalls, and aromatic Kodagu coffee estate plantation homestays.",
    },

    # -------------------------------------------------------------------------
    # East & North-East Region
    # -------------------------------------------------------------------------
    {
        "id": "darjeeling_gangtok_india",
        "name": "Darjeeling & Gangtok",
        "region": "East & NE",
        "state": "West Bengal & Sikkim",
        "country": "India",
        "lat": 27.0410,
        "lon": 88.2663,
        "budget_tier": "mid_range",
        "estimated_cost_inr": 30000,
        "best_seasons": ["March", "April", "May", "October", "November", "December"],
        "tags": ["tea_estates", "kanchenjunga", "monasteries", "himalayas", "scenic", "heritage"],
        "description": "Queen of the Hills featuring views of Mount Kanchenjunga, heritage UNESCO Himalayan Toy Train, and colourful Tibetan monasteries.",
    },
    {
        "id": "meghalaya_shillong_india",
        "name": "Meghalaya (Shillong & Cherrapunji)",
        "region": "East & NE",
        "state": "Meghalaya",
        "country": "India",
        "lat": 25.5788,
        "lon": 91.8933,
        "budget_tier": "mid_range",
        "estimated_cost_inr": 32000,
        "best_seasons": ["October", "November", "December", "January", "February", "March", "April"],
        "tags": ["living_root_bridges", "waterfalls", "caves", "clouds", "nature", "adventure"],
        "description": "Abode of Clouds boasting living bio-engineered root bridges, crystal-clear Umngot River at Dawki, and plunging waterfalls.",
    },
]

# Quick lookup map by destination_id
DESTINATIONS_BY_ID: Dict[str, Dict[str, Any]] = {
    d["id"]: d for d in INDIAN_DESTINATIONS
}

# Regional groupings
DESTINATIONS_BY_REGION: Dict[str, List[Dict[str, Any]]] = {}
for dest in INDIAN_DESTINATIONS:
    DESTINATIONS_BY_REGION.setdefault(dest["region"], []).append(dest)


def get_all_indian_destinations() -> List[Dict[str, Any]]:
    """Returns all 12 curated Indian destinations across all regions."""
    return INDIAN_DESTINATIONS


def get_indian_destination(destination_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a specific destination by ID or alias."""
    # Allow matching with or without '_india' suffix
    if destination_id in DESTINATIONS_BY_ID:
        return DESTINATIONS_BY_ID[destination_id]
    alt_id = f"{destination_id}_india"
    if alt_id in DESTINATIONS_BY_ID:
        return DESTINATIONS_BY_ID[alt_id]
    # Check prefix match
    for k, v in DESTINATIONS_BY_ID.items():
        if k.startswith(destination_id) or destination_id.startswith(k.replace("_india", "")):
            return v
    return None


def filter_indian_destinations(
    budget_tier: Optional[str] = None,
    interest: Optional[str] = None,
    max_budget_inr: Optional[int] = None,
    region: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filters Indian destinations based on user constraints."""
    results = INDIAN_DESTINATIONS

    if budget_tier:
        b_clean = budget_tier.lower().strip()
        results = [d for d in results if d["budget_tier"].lower() == b_clean]

    if max_budget_inr is not None:
        results = [d for d in results if d["estimated_cost_inr"] <= max_budget_inr]

    if region:
        r_clean = region.lower().strip()
        results = [d for d in results if r_clean in d["region"].lower()]

    if interest:
        i_clean = interest.lower().strip().replace(" ", "_")
        results = [
            d for d in results
            if any(i_clean in tag or tag in i_clean for tag in d["tags"])
            or i_clean in d["description"].lower()
        ]

    return results
