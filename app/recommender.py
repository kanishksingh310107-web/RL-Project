# Recommendation engine for RL Travel Guide
# Matches destinations against traveller preferences (interests, budget, climate, companions, avoidances)
# Uses configurable scoring weights, transparent reasoning, and accounts for missing information
from typing import List, Dict, Any, Optional

# Configurable scoring weights for transparent ranking
SCORING_WEIGHTS = {
    "interests_max": 40.0,          # Maximum contribution from interest/goal overlap
    "interest_tag_match": 12.0,     # Points per shared interest tag
    "climate_exact_match": 20.0,    # Exact match with preferred climate
    "climate_adjacent_match": 12.0, # Seasonally adjacent climate (e.g. cold vs cool, warm vs tropical)
    "climate_unspecified": 15.0,    # Neutral baseline when traveler has no climate preference
    "budget_exact_match": 20.0,     # Exact match with traveler's budget category
    "budget_adjacent_match": 10.0,  # Adjacent budget tier (e.g. balanced vs budget)
    "budget_unspecified": 12.0,     # Neutral baseline when budget is unspecified
    "companions_match": 10.0,       # Destination suits traveler's companion arrangement
    "pace_match": 10.0,             # Destination style aligns with traveler's pace
    "avoidance_penalty": 35.0,      # Severe penalty when destination conflicts with a stated avoidance
    "past_trip_bonus": 5.0,         # Bonus for destinations sharing vibes of high-rated past trips
    "baseline_discovery": 10.0      # Baseline score for unexplored destinations
}

# Catalog of curated destinations with rich metadata and real photography
DESTINATIONS: List[Dict[str, Any]] = [
    {
        "id": "manali_spiti_india",
        "name": "Manali & Spiti Valley",
        "country": "India",
        "tagline": "High Himalayan passes, ancient cliffside monasteries, and crisp mountain air",
        "image_url": "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=800&q=80",
        "duration": "7 - 10 days",
        "tags": [
            "mountains",
            "nature",
            "adventure",
            "photography",
            "scenic_landscapes",
            "hiking"
        ],
        "style": "active",
        "crowd_level": "low",
        "budget_tier": "budget",
        "estimated_cost": "\u20b92,500 - \u20b94,500 / day \u00b7 Budget",
        "preferred_climate": [
            "cool",
            "cold"
        ],
        "suitable_companions": [
            "alone",
            "friends",
            "partner"
        ],
        "best_seasons": [
            "Summer (May - Jun) for Spiti",
            "Winter (Dec - Feb) for snow"
        ],
        "is_trending": True,
        "trending_reason": "High demand for rugged Himalayan road trips and high-altitude dark-sky stargazing",
        "is_seasonal": True,
        "seasonal_event": "Winter Snow Sports & Skiing in Solang Valley (Dec - Feb)",
        "available_experiences": [
            "Crossing high mountain passes like Kunzum and Rohtang",
            "Staying in 1000-year-old Key Monastery with monks",
            "Stargazing under crystal dark skies in Langza",
            "Cafe hopping along Old Manali's cedar trails"
        ],
        "travel_style_and_atmosphere": "Rugged, awe-inspiring, adventurous, and close to raw nature",
        "practical_considerations": "Spiti elevation (>3,500m) requires 48-hour acclimatization in Kaza or Manali. Carry cash as ATMs are sparse.",
        "limitations_or_uncertainties": "Mountain roads can be bumpy and weather-dependent during landslides or snowfall.",
        "avoidance_triggers": [
            "high_altitude",
            "strenuous_hikes",
            "long_bus_rides",
            "motion_sickness"
        ],
        "icon": "fa-mountain-sun",
        "is_sample_data": True
    },
    {
        "id": "south_goa_india",
        "name": "South Goa (Palolem & Agonda)",
        "country": "India",
        "tagline": "Pristine crescent beaches, serene coastal yoga retreats, and heritage Portuguese quarters",
        "image_url": "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 7 days",
        "tags": [
            "beaches",
            "coastal",
            "relaxation",
            "food",
            "cafes",
            "photography",
            "wellness",
            "nightlife"
        ],
        "style": "relaxed",
        "crowd_level": "low",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,500 - \u20b96,000 / day \u00b7 Balanced",
        "preferred_climate": [
            "warm",
            "tropical"
        ],
        "suitable_companions": [
            "partner",
            "friends",
            "alone"
        ],
        "best_seasons": [
            "Winter (Nov - Feb) peak sunshine",
            "Late Autumn (Oct) peaceful"
        ],
        "is_trending": True,
        "trending_reason": "Surge in slow-travel remote workers preferring calm south beaches over crowded north strips",
        "is_seasonal": True,
        "seasonal_event": "Beach Shack Season & Dolphin Kayaking in Palolem (Nov - Feb)",
        "available_experiences": [
            "Early morning kayaking alongside wild dolphins in Palolem bay",
            "Sunset dining with fresh garlic-butter tiger prawns right on the sand",
            "Exploring 400-year-old pastel Portuguese mansions in Chandor and Fontainhas",
            "Motorbike riding along coconut-lined coastal backroads to Cabo de Rama"
        ],
        "travel_style_and_atmosphere": "Bohemian, tranquil, laid-back beach bliss with golden sunsets",
        "practical_considerations": "Renting a scooter (\u20b9350-500/day) is the most flexible way to explore hidden bays.",
        "limitations_or_uncertainties": "Many beach shacks pack down between June and September during the heavy monsoon.",
        "avoidance_triggers": [
            "extreme_heat",
            "intense_nightclubs",
            "commercial_crowds"
        ],
        "icon": "fa-umbrella-beach",
        "is_sample_data": True
    },
    {
        "id": "udaipur_india",
        "name": "Udaipur & Mewar",
        "country": "India",
        "tagline": "Gleaming marble lake palaces, romantic boat cruises, and vibrant Mewari craft bazaars",
        "image_url": "https://images.unsplash.com/photo-1599661046289-e31897846e41?auto=format&fit=crop&w=800&q=80",
        "duration": "3 - 5 days",
        "tags": [
            "history",
            "culture",
            "photography",
            "architecture",
            "food",
            "relaxation"
        ],
        "style": "comfort",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,000 - \u20b95,500 / day \u00b7 Balanced",
        "preferred_climate": [
            "mild",
            "warm"
        ],
        "suitable_companions": [
            "partner",
            "family_older",
            "family_children",
            "alone"
        ],
        "best_seasons": [
            "Winter (Oct - Mar) pleasant cool days",
            "Monsoon (Jul - Aug) lush lakes"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Shilpgram Crafts Fair & Lake Pichola Winter Music Nights (Dec - Jan)",
        "available_experiences": [
            "Sunset boat ride on Lake Pichola gliding past the floating Lake Palace",
            "Walking through the ornate City Palace courtyards and crystal gallery",
            "Evening Dharohar Rajasthani folk dance and puppet show at Bagore Ki Haveli",
            "Rooftop dining with illuminated panoramic views of the water palace"
        ],
        "travel_style_and_atmosphere": "Regal, romantic, culturally rich with timeless Rajput grandeur",
        "practical_considerations": "Old city streets are extremely narrow; use autorickshaws or walk rather than renting cars.",
        "limitations_or_uncertainties": "Lake water levels fluctuate depending on monsoon rainfall.",
        "avoidance_triggers": [
            "extreme_heat",
            "aggressive_touts"
        ],
        "icon": "fa-crown",
        "is_sample_data": True
    },
    {
        "id": "kerala_alleppey_india",
        "name": "Kerala (Munnar & Alleppey)",
        "country": "India",
        "tagline": "Emerald rolling tea plantations, mist-covered mountain valleys, and tranquil palm-fringed backwaters",
        "image_url": "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 8 days",
        "tags": [
            "nature",
            "relaxation",
            "scenic_landscapes",
            "food",
            "wellness",
            "photography"
        ],
        "style": "relaxed",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,500 - \u20b96,500 / day \u00b7 Balanced",
        "preferred_climate": [
            "mild",
            "tropical"
        ],
        "suitable_companions": [
            "partner",
            "family_children",
            "family_older",
            "friends",
            "alone"
        ],
        "best_seasons": [
            "Winter (Sep - Mar) cool hills & pleasant backwaters"
        ],
        "is_trending": True,
        "trending_reason": "Top-rated Ayurvedic wellness holidays and scenic glass-cab slow transit",
        "is_seasonal": True,
        "seasonal_event": "Winter Spice Harvest & Alleppey Houseboat Season (Nov - Feb)",
        "available_experiences": [
            "Overnight slow cruise on a traditional thatched houseboat through Vembanad Lake",
            "Walking through century-old tea gardens in misty Top Station Munnar",
            "Authentic Ayurvedic herbal massage and wellness rejuvenation session",
            "Traditional Kerala Sadya feast served on fresh banana leaves"
        ],
        "travel_style_and_atmosphere": "Serene, lush green, spiritually restorative, and deeply natural",
        "practical_considerations": "Winding mountain roads to Munnar can induce motion sickness; carry preventative mints.",
        "limitations_or_uncertainties": "Heavy southwest monsoon rain showers from June to August.",
        "avoidance_triggers": [
            "motion_sickness",
            "humidity"
        ],
        "icon": "fa-leaf",
        "is_sample_data": True
    },
    {
        "id": "ladakh_leh_india",
        "name": "Leh & Ladakh",
        "country": "India",
        "tagline": "Dramatic cold desert moonscapes, turquoise high-altitude lakes, and centuries-old Tibetan gompas",
        "image_url": "https://images.unsplash.com/photo-1581793745862-99fde7fa73d2?auto=format&fit=crop&w=800&q=80",
        "duration": "6 - 9 days",
        "tags": [
            "mountains",
            "adventure",
            "nature",
            "photography",
            "culture",
            "scenic_landscapes"
        ],
        "style": "active",
        "crowd_level": "low",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,800 - \u20b96,800 / day \u00b7 Balanced",
        "preferred_climate": [
            "cold",
            "cool"
        ],
        "suitable_companions": [
            "friends",
            "alone",
            "partner"
        ],
        "best_seasons": [
            "Summer (May - Sep) open passes",
            "Winter (Jan - Feb) for Chadar trek"
        ],
        "is_trending": True,
        "trending_reason": "Unrivalled high-altitude photography, motorcycle expeditions, and pristine night skies",
        "is_seasonal": True,
        "seasonal_event": "Ladakh Festival & Hemis Tsechu Monastery Mask Dances (Jun - Jul)",
        "available_experiences": [
            "Watching the shifting blue waters of Pangong Tso lake at 14,000 feet",
            "Riding across Khardung La, one of the world's highest motorable passes",
            "Morning prayers with chanting Buddhist monks at Thiksey Monastery",
            "Stargazing under Bortle-1 certified dark skies in Hanle"
        ],
        "travel_style_and_atmosphere": "Epic, spiritual, otherworldly high-altitude frontier",
        "practical_considerations": "Strict 48-hour rest mandatory upon landing in Leh (3,500m) for altitude acclimatization.",
        "limitations_or_uncertainties": "High mountain passes close during heavy winter snowfall.",
        "avoidance_triggers": [
            "high_altitude",
            "extreme_cold",
            "strenuous_hikes"
        ],
        "icon": "fa-mountain",
        "is_sample_data": True
    },
    {
        "id": "varanasi_kashi_india",
        "name": "Varanasi (Kashi)",
        "country": "India",
        "tagline": "The spiritual heart of India: eternal Ganga ghats, devotional chanting, and labyrinthine silk alleys",
        "image_url": "https://images.unsplash.com/photo-1561361513-2d000a50f0dc?auto=format&fit=crop&w=800&q=80",
        "duration": "3 - 5 days",
        "tags": [
            "culture",
            "history",
            "spiritual",
            "photography",
            "food",
            "architecture"
        ],
        "style": "active",
        "crowd_level": "high",
        "budget_tier": "budget",
        "estimated_cost": "\u20b92,000 - \u20b94,000 / day \u00b7 Budget",
        "preferred_climate": [
            "mild",
            "cool"
        ],
        "suitable_companions": [
            "alone",
            "family_older",
            "partner",
            "friends"
        ],
        "best_seasons": [
            "Winter (Oct - Mar) cool pleasant weather"
        ],
        "is_trending": True,
        "trending_reason": "Revitalized Kashi Vishwanath Corridor and surging interest in living ancient heritage",
        "is_seasonal": True,
        "seasonal_event": "Dev Deepawali with millions of earthen lamps along the ghats (Nov - Dec)",
        "available_experiences": [
            "Witnessing the mesmerizing grand evening Ganga Aarti at Dashashwamedh Ghat",
            "Sunrise wooden rowboat cruise along the historic bathing ghats",
            "Exploring the golden spire of Kashi Vishwanath and Sarnath Buddhist stupas",
            "Sampling rich malaiyyo foam sweets, kachoris, and creamy Banarasi lassi"
        ],
        "travel_style_and_atmosphere": "Intense, mystical, deeply transformative, and sensory-rich",
        "practical_considerations": "Wear slip-on shoes for temple visits. Navigate narrow galis on foot.",
        "limitations_or_uncertainties": "Ghats can be crowded during auspicious festival dates.",
        "avoidance_triggers": [
            "crowds",
            "sensory_overload",
            "complex_walking"
        ],
        "icon": "fa-om",
        "is_sample_data": True
    },
    {
        "id": "jaipur_rajasthan_india",
        "name": "Jaipur (The Pink City)",
        "country": "India",
        "tagline": "Monumental hilltop forts, honeycomb pink palaces, and world-renowned textile and jewelry bazaars",
        "image_url": "https://images.unsplash.com/photo-1477587458883-47145ed94245?auto=format&fit=crop&w=800&q=80",
        "duration": "3 - 5 days",
        "tags": [
            "history",
            "culture",
            "architecture",
            "shopping",
            "food",
            "photography"
        ],
        "style": "balanced",
        "crowd_level": "high",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,000 - \u20b95,500 / day \u00b7 Balanced",
        "preferred_climate": [
            "mild",
            "cool"
        ],
        "suitable_companions": [
            "family_children",
            "partner",
            "friends",
            "alone"
        ],
        "best_seasons": [
            "Winter (Oct - Mar) peak heritage season"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Jaipur Literature Festival & Elephant Festival (Jan - Mar)",
        "available_experiences": [
            "Walking up the ramparts of majestic Amer Fort at sunrise",
            "Photographing the honeycomb facade of Hawa Mahal (Palace of Winds)",
            "Browsing handcrafted gemstone jewelry and block-print textiles in Johari Bazaar",
            "Feasting on traditional dal baati churma and ghewar sweets"
        ],
        "travel_style_and_atmosphere": "Vibrant, historic, regal, and bustling with colorful street life",
        "practical_considerations": "Buy the composite monument entry ticket to save queues at major forts.",
        "limitations_or_uncertainties": "Summer months (April to June) reach extreme 42\u00b0C+ temperatures.",
        "avoidance_triggers": [
            "extreme_heat",
            "aggressive_vendors"
        ],
        "icon": "fa-fort-awesome",
        "is_sample_data": True
    },
    {
        "id": "rishikesh_haridwar_india",
        "name": "Rishikesh & Haridwar",
        "country": "India",
        "tagline": "The Yoga Capital of the World: emerald river rafting, Himalayan foothills, and serene ashram life",
        "image_url": "https://images.unsplash.com/photo-1596761427218-356a646c0a0c?auto=format&fit=crop&w=800&q=80",
        "duration": "3 - 6 days",
        "tags": [
            "adventure",
            "wellness",
            "nature",
            "spiritual",
            "cafes",
            "hiking"
        ],
        "style": "active",
        "crowd_level": "moderate",
        "budget_tier": "budget",
        "estimated_cost": "\u20b92,200 - \u20b94,200 / day \u00b7 Budget",
        "preferred_climate": [
            "cool",
            "mild"
        ],
        "suitable_companions": [
            "alone",
            "friends",
            "partner"
        ],
        "best_seasons": [
            "Spring (Feb - May) for rafting",
            "Autumn (Sep - Nov) for yoga"
        ],
        "is_trending": True,
        "trending_reason": "High demand for clean Himalayan wellness retreats, riverside camping, and white-water rapids",
        "is_seasonal": True,
        "seasonal_event": "International Yoga Festival & Ganga Kayak Festival (Feb - Mar)",
        "available_experiences": [
            "White-water rafting through Grade III & IV rapids on the crystal Ganga",
            "Attending sunset musical Ganga Aarti at Parmarth Niketan ashram",
            "Visiting the legendary Beatles Ashram with psychedelic mural art",
            "Healthy vegan cafe hopping overlooking the river in Tapovan"
        ],
        "travel_style_and_atmosphere": "Peaceful, active, spiritually refreshing, and adventurous",
        "practical_considerations": "Rishikesh is an alcohol-free and fully vegetarian sacred town.",
        "limitations_or_uncertainties": "River rafting is strictly closed during the monsoon season (July to mid-September).",
        "avoidance_triggers": [
            "non_vegetarian",
            "alcohol_seeking"
        ],
        "icon": "fa-spa",
        "is_sample_data": True
    },
    {
        "id": "hampi_karnataka_india",
        "name": "Hampi & Tungabhadra",
        "country": "India",
        "tagline": "Surreal boulder-strewn landscapes, majestic ruined Vijayanagara temples, and sunset hippie hills",
        "image_url": "https://images.unsplash.com/photo-1600100397608-f010f443b811?auto=format&fit=crop&w=800&q=80",
        "duration": "3 - 5 days",
        "tags": [
            "history",
            "architecture",
            "photography",
            "scenic_landscapes",
            "adventure"
        ],
        "style": "active",
        "crowd_level": "low",
        "budget_tier": "budget",
        "estimated_cost": "\u20b92,200 - \u20b94,000 / day \u00b7 Budget",
        "preferred_climate": [
            "mild",
            "warm"
        ],
        "suitable_companions": [
            "alone",
            "friends",
            "partner"
        ],
        "best_seasons": [
            "Winter (Nov - Feb) pleasant daytime temperatures"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Hampi Utsav Cultural & Light Festival (Jan - Feb)",
        "available_experiences": [
            "Exploring the intricate musical stone pillars of the 15th-century Vijaya Vittala Temple",
            "Climbing Matanga Hill for a panoramic 360-degree sunrise over the ruins",
            "Crossing the Tungabhadra River in a traditional round woven coracle boat",
            "Bicycle riding through the royal elephant stables and lotus mahal"
        ],
        "travel_style_and_atmosphere": "Ancient, surreal, open-air archaeological marvel with bohemian charm",
        "practical_considerations": "Wear good walking shoes for climbing uneven granite boulders.",
        "limitations_or_uncertainties": "Limited luxury hotel options; homestays and heritage lodges are standard.",
        "avoidance_triggers": [
            "steep_stairs",
            "midday_heat"
        ],
        "icon": "fa-landmark",
        "is_sample_data": True
    },
    {
        "id": "meghalaya_shillong_india",
        "name": "Meghalaya (Shillong & Cherrapunji)",
        "country": "India",
        "tagline": "The Abode of Clouds: bio-engineered living root bridges, crystal turquoise rivers, and roaring waterfalls",
        "image_url": "https://images.unsplash.com/photo-1605335198108-724d27f27236?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 8 days",
        "tags": [
            "nature",
            "adventure",
            "hiking",
            "photography",
            "scenic_landscapes"
        ],
        "style": "active",
        "crowd_level": "low",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,000 - \u20b95,500 / day \u00b7 Balanced",
        "preferred_climate": [
            "cool",
            "mild"
        ],
        "suitable_companions": [
            "friends",
            "alone",
            "partner"
        ],
        "best_seasons": [
            "Autumn (Oct - Nov) clear waterfalls",
            "Spring (Feb - Apr) blooming hills"
        ],
        "is_trending": True,
        "trending_reason": "High interest in sustainable eco-trekking and the crystal-clear waters of Dawki river",
        "is_seasonal": True,
        "seasonal_event": "Shillong Cherry Blossom Festival (Nov)",
        "available_experiences": [
            "Trekking down to the double-decker living root bridge in Nongriat",
            "Boating on the transparent glass-like waters of Umngot River in Dawki",
            "Standing in front of the thunderous plunge of Nohkalikai Falls in Cherrapunji",
            "Caving through the limestone formations of Mawsmai and Arwah"
        ],
        "travel_style_and_atmosphere": "Untamed, mystical, pristine, and deeply connected to indigenous Khasi nature",
        "practical_considerations": "Trekking down to Nongriat involves 3,000 stone steps; decent fitness needed.",
        "limitations_or_uncertainties": "Heavy rainfall during monsoon; carry waterproof gear.",
        "avoidance_triggers": [
            "strenuous_hikes",
            "steep_stairs"
        ],
        "icon": "fa-water",
        "is_sample_data": True
    },
    {
        "id": "darjeeling_sikkim_india",
        "name": "Darjeeling & Gangtok",
        "country": "India",
        "tagline": "Panoramic views of Mount Kanchenjunga, heritage Himalayan toy train, and emerald tea valleys",
        "image_url": "https://images.unsplash.com/photo-1544735716-392fe2489ffa?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 7 days",
        "tags": [
            "mountains",
            "tea",
            "culture",
            "nature",
            "scenic_landscapes",
            "food"
        ],
        "style": "balanced",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,200 - \u20b95,800 / day \u00b7 Balanced",
        "preferred_climate": [
            "cool",
            "cold"
        ],
        "suitable_companions": [
            "family_children",
            "partner",
            "family_older",
            "friends"
        ],
        "best_seasons": [
            "Spring (Mar - May) rhododendrons",
            "Autumn (Oct - Nov) crystal mountain views"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Tiger Hill Golden Sunrise Viewing Season (Oct - Dec)",
        "available_experiences": [
            "Early morning sunrise over Mount Kanchenjunga from Tiger Hill summit",
            "Riding the UNESCO World Heritage Darjeeling Himalayan Railway steam toy train",
            "Tasting muscatel champagne teas at Glenburn Tea Estate",
            "Visiting Rumtek Monastery and high-altitude Tsomgo Lake in Sikkim"
        ],
        "travel_style_and_atmosphere": "Colonial hill station charm blended with vibrant Tibetan Buddhist spirituality",
        "practical_considerations": "Sikkim requires Inner Line Permits (ILP), easily obtained with passport/voter ID.",
        "limitations_or_uncertainties": "Monsoon landslides can temporarily affect road transit to Gangtok.",
        "avoidance_triggers": [
            "extreme_cold",
            "winding_roads"
        ],
        "icon": "fa-mountain-sun",
        "is_sample_data": True
    },
    {
        "id": "andaman_havelock_india",
        "name": "Andaman Islands (Havelock & Neil)",
        "country": "India",
        "tagline": "Powder-white beaches, bioluminescent night kayaking, and world-class coral reef diving",
        "image_url": "https://images.unsplash.com/photo-1589308078059-be1415eab4c3?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 8 days",
        "tags": [
            "beaches",
            "scuba",
            "nature",
            "relaxation",
            "adventure",
            "coastal"
        ],
        "style": "relaxed",
        "crowd_level": "low",
        "budget_tier": "luxury",
        "estimated_cost": "\u20b95,000 - \u20b99,500 / day \u00b7 Luxury",
        "preferred_climate": [
            "warm",
            "tropical"
        ],
        "suitable_companions": [
            "partner",
            "friends",
            "alone",
            "family_children"
        ],
        "best_seasons": [
            "Winter (Oct - May) calm sea conditions and high underwater visibility"
        ],
        "is_trending": True,
        "trending_reason": "Voted Asia's best beach destination with pristine marine sanctuaries",
        "is_seasonal": True,
        "seasonal_event": "Scuba Diving & Coral Spawning Season (Nov - Apr)",
        "available_experiences": [
            "Walking along Asia's top-rated Radhanagar Beach at sunset",
            "Scuba diving and snorkeling amongst manta rays and turtles at Elephant Beach",
            "Night kayaking through glowing bioluminescent mangrove creeks in Havelock",
            "Catamaran ferry rides across azure Andaman sea waters"
        ],
        "travel_style_and_atmosphere": "Tropical, pristine island paradise with unmatched coastal luxury",
        "practical_considerations": "Book private catamaran ferries (Makruzz/Nautika) between islands in advance.",
        "limitations_or_uncertainties": "Ferry services depend on fair weather; monsoon brings strong sea swells.",
        "avoidance_triggers": [
            "seasickness",
            "extreme_heat"
        ],
        "icon": "fa-water",
        "is_sample_data": True
    },
    {
        "id": "amritsar_punjab_india",
        "name": "Amritsar & Wagah",
        "country": "India",
        "tagline": "The spiritual Golden Temple, heartfelt community langar, and patriotic Wagah border ceremony",
        "image_url": "https://images.unsplash.com/photo-1588714477688-cf28a50e94f7?auto=format&fit=crop&w=800&q=80",
        "duration": "2 - 4 days",
        "tags": [
            "culture",
            "history",
            "food",
            "spiritual",
            "photography"
        ],
        "style": "comfort",
        "crowd_level": "high",
        "budget_tier": "budget",
        "estimated_cost": "\u20b92,000 - \u20b94,000 / day \u00b7 Budget",
        "preferred_climate": [
            "cool",
            "mild"
        ],
        "suitable_companions": [
            "family_older",
            "family_children",
            "partner",
            "friends",
            "alone"
        ],
        "best_seasons": [
            "Winter (Oct - Mar) cool and crisp Punjab days"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Guru Nanak Jayanti & Baisakhi Celebrations (Nov & Apr)",
        "available_experiences": [
            "Sitting peacefully beside the illuminated Amrit Sarovar at the Golden Temple at night",
            "Volunteering at the world's largest community free kitchen (Langar)",
            "Experiencing the patriotic sunset Beating Retreat ceremony at the Wagah Border",
            "Indulging in piping hot butter-drenched Amritsari kulchas and thick sweet lassi"
        ],
        "travel_style_and_atmosphere": "Devotional, welcoming, emotionally moving, and culinary paradise",
        "practical_considerations": "Head covering is mandatory inside the temple complex; scarves available at entrance.",
        "limitations_or_uncertainties": "Winter mornings can have thick fog affecting early transport.",
        "avoidance_triggers": [
            "crowds"
        ],
        "icon": "fa-place-of-worship",
        "is_sample_data": True
    },
    {
        "id": "ooty_coorg_india",
        "name": "Ooty & Coorg (Nilgiris)",
        "country": "India",
        "tagline": "Aromatic coffee and spice plantations, misty Nilgiri blue mountains, and gushing forest waterfalls",
        "image_url": "https://images.unsplash.com/photo-1596401057633-54a8fe8ef647?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 6 days",
        "tags": [
            "nature",
            "relaxation",
            "scenic_landscapes",
            "food",
            "cafes"
        ],
        "style": "relaxed",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "\u20b93,200 - \u20b95,800 / day \u00b7 Balanced",
        "preferred_climate": [
            "cool",
            "mild"
        ],
        "suitable_companions": [
            "partner",
            "family_children",
            "family_older",
            "alone"
        ],
        "best_seasons": [
            "Year-round cool hills (Oct - May)"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Winter Coffee Berry Picking Season (Dec - Feb)",
        "available_experiences": [
            "Staying in an authentic heritage coffee planter's bungalow in Madikeri",
            "Riding the historic Nilgiri Mountain Railway wooden toy train to Ooty",
            "Walking through spice plantations tasting fresh cardamom and pepper",
            "Tasting traditional Kodava pork curry (Pandi Curry) and homemade chocolates"
        ],
        "travel_style_and_atmosphere": "Cozy, verdant, aromatic, and tranquil colonial mountain getaway",
        "practical_considerations": "Evenings are chilly; bring light woolens even in summer.",
        "limitations_or_uncertainties": "Popular viewpoints around Ooty lake get busy on weekend afternoons.",
        "avoidance_triggers": [
            "winding_roads"
        ],
        "icon": "fa-mug-saucer",
        "is_sample_data": True
    },
    {
        "id": "rann_of_kutch_india",
        "name": "Rann of Kutch",
        "country": "India",
        "tagline": "Endless surreal white salt desert, moonlit folk music, and vibrant Kutchi artisan embroidery",
        "image_url": "https://images.unsplash.com/photo-1578328819058-b69f3a3b0f6b?auto=format&fit=crop&w=800&q=80",
        "duration": "3 - 5 days",
        "tags": [
            "culture",
            "photography",
            "scenic_landscapes",
            "art",
            "shopping"
        ],
        "style": "comfort",
        "crowd_level": "moderate",
        "budget_tier": "luxury",
        "estimated_cost": "\u20b94,500 - \u20b98,500 / day \u00b7 Luxury",
        "preferred_climate": [
            "cool",
            "mild"
        ],
        "suitable_companions": [
            "partner",
            "family_children",
            "friends"
        ],
        "best_seasons": [
            "Winter (Nov - Feb) dry salt desert season"
        ],
        "is_trending": True,
        "trending_reason": "High acclaim for full-moon desert nights and world-renowned Rann Utsav tent cities",
        "is_seasonal": True,
        "seasonal_event": "The Great Rann Utsav Cultural & Music Festival (Nov - Feb)",
        "available_experiences": [
            "Walking across the gleaming white salt plains under a brilliant full moon",
            "Meeting master artisan weavers and Rogan art painters in Nirona village",
            "Watching the sunset from the highest peak of Kala Dungar (Black Hill)",
            "Luxury glamping in traditional Bhunga mud cottages with Gujarati folk dance"
        ],
        "travel_style_and_atmosphere": "Otherworldly, festive, culturally rich, and visually magnificent",
        "practical_considerations": "Permit is required for visiting the White Rann (easily obtained online or at checkpost).",
        "limitations_or_uncertainties": "The salt marsh is fully submerged underwater from June to October.",
        "avoidance_triggers": [
            "extreme_heat"
        ],
        "icon": "fa-campground",
        "is_sample_data": True
    },
    {
        "id": "agra_braj_india",
        "name": "Agra & Braj",
        "country": "India",
        "tagline": "The immortal marble poetry of the Taj Mahal, imperial Mughal palaces, and Braj heritage",
        "image_url": "https://images.unsplash.com/photo-1564507592333-c60657eea523?auto=format&fit=crop&w=800&q=80",
        "duration": "2 - 3 days",
        "tags": [
            "history",
            "architecture",
            "culture",
            "photography",
            "food"
        ],
        "style": "balanced",
        "crowd_level": "high",
        "budget_tier": "budget",
        "estimated_cost": "\u20b92,500 - \u20b94,800 / day \u00b7 Budget",
        "preferred_climate": [
            "mild",
            "cool"
        ],
        "suitable_companions": [
            "partner",
            "family_children",
            "family_older",
            "alone"
        ],
        "best_seasons": [
            "Winter (Oct - Mar) pleasant daytime strolls"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Taj Mahotsav Artisan & Cultural Fair (Feb)",
        "available_experiences": [
            "Watching the sunrise illuminate the white marble dome of the Taj Mahal",
            "Exploring the massive red sandstone walls and palaces of Agra Fort",
            "Walking through the ghost city of Fatehpur Sikri and Buland Darwaza",
            "Tasting authentic Agra petha sweets and bedmi puri breakfast"
        ],
        "travel_style_and_atmosphere": "Monumental, historic, iconic, and architectural world wonder",
        "practical_considerations": "Taj Mahal is closed for tourists on Fridays.",
        "limitations_or_uncertainties": "Dense winter morning fog in December and January can delay views.",
        "avoidance_triggers": [
            "crowds",
            "touts"
        ],
        "icon": "fa-monument",
        "is_sample_data": True
    },
    {
        "id": "kyoto_japan",
        "name": "Kyoto",
        "country": "Japan",
        "tagline": "Ancient temples, serene zen gardens, and timeless tea culture",
        "image_url": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 7 days",
        "tags": [
            "culture",
            "history",
            "food",
            "cafes",
            "nature",
            "photography",
            "relaxation",
            "architecture"
        ],
        "style": "relaxed",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "$85 - $130 / day \u00b7 Balanced",
        "preferred_climate": [
            "mild",
            "cool"
        ],
        "suitable_companions": [
            "alone",
            "partner",
            "friends",
            "family_older"
        ],
        "best_seasons": [
            "Spring (Mar - May)",
            "Autumn (Oct - Nov)"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Autumn Foliage & Night Temple Illuminations (Oct - Nov)",
        "available_experiences": [
            "Walking through Arashiyama Bamboo Grove at sunrise",
            "Traditional matcha tea ceremony in historic Gion"
        ],
        "travel_style_and_atmosphere": "Serene, historic, pedestrian-friendly with rich traditional charm",
        "practical_considerations": "Reserve temple tea ceremonies in advance.",
        "limitations_or_uncertainties": "Major shrines get crowded.",
        "avoidance_triggers": [
            "crowds"
        ],
        "icon": "fa-torii-gate",
        "is_sample_data": True
    },
    {
        "id": "santorini_greece",
        "name": "Santorini & Cyclades",
        "country": "Greece",
        "tagline": "Iconic whitewashed caldera villages, Aegean sunsets, and coastal relaxation",
        "image_url": "https://images.unsplash.com/photo-1570077188670-e3a8d69ac5ff?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 6 days",
        "tags": [
            "beaches",
            "coastal",
            "relaxation",
            "photography",
            "food",
            "cafes",
            "culture"
        ],
        "style": "relaxed",
        "crowd_level": "high",
        "budget_tier": "luxury",
        "estimated_cost": "$180 - $320 / day \u00b7 Luxury",
        "preferred_climate": [
            "warm",
            "mild"
        ],
        "suitable_companions": [
            "partner",
            "friends",
            "alone"
        ],
        "best_seasons": [
            "Late Spring (May)",
            "Autumn (Sep - Oct)"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Aegean Wine Harvest & Sunset Sailing Cruises (Sep - Oct)",
        "available_experiences": [
            "Walking cliffside paths from Fira to Oia overlooking the caldera",
            "Catamaran sailing cruise around volcanic red and black sand beaches",
            "Tasting Assyrtiko wine in centuries-old volcanic vineyards",
            "Dining at sunset tavernas with fresh Mediterranean seafood"
        ],
        "travel_style_and_atmosphere": "Romantic, scenic, laid-back Mediterranean luxury with postcard panoramas",
        "practical_considerations": "Book sunset dinner tables and caldera view stays months in advance. Wear shoes with good grip on polished cobblestones.",
        "limitations_or_uncertainties": "Steep cobblestone caldera stairs with no vehicular access; high peak-season crowds.",
        "avoidance_triggers": [
            "steep_stairs",
            "extreme_heat",
            "crowds",
            "high_prices"
        ],
        "icon": "fa-water",
        "is_sample_data": True
    },
    {
        "id": "swiss_alps",
        "name": "Swiss Alps (Interlaken & Zermatt)",
        "country": "Switzerland",
        "tagline": "Glacier lakes, iconic Matterhorn views, and seamless mountain rail transit",
        "image_url": "https://images.unsplash.com/photo-1530122037265-a5f1f91d3b99?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 8 days",
        "tags": [
            "mountains",
            "nature",
            "scenic_landscapes",
            "adventure",
            "photography",
            "relaxation"
        ],
        "style": "comfort",
        "crowd_level": "moderate",
        "budget_tier": "luxury",
        "estimated_cost": "$210 - $360 / day \u00b7 Luxury",
        "preferred_climate": [
            "cool",
            "cold"
        ],
        "suitable_companions": [
            "partner",
            "family_children",
            "family_older",
            "alone"
        ],
        "best_seasons": [
            "Summer (Jul - Aug) for hiking",
            "Winter (Dec - Mar) for skiing"
        ],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Winter Glacier Skiing & Mountain Village Christmas Markets (Dec - Jan)",
        "available_experiences": [
            "Scenic cogwheel train ride to Jungfraujoch (Top of Europe)",
            "Hiking flower-carpeted trails around Zermatt beneath the Matterhorn",
            "Cruising glacial waters of Lake Brienz and Lake Thun",
            "Cozy traditional Swiss cheese fondue in alpine chalets"
        ],
        "travel_style_and_atmosphere": "Pristine, orderly, scenic alpine luxury with punctual transit",
        "practical_considerations": "A Swiss Travel Pass covers almost all trains, boats, and mountain discounts.",
        "limitations_or_uncertainties": "Higher dining and lodging costs; weather at mountain summits changes swiftly.",
        "avoidance_triggers": [
            "extreme_cold",
            "extreme_heights",
            "high_prices"
        ],
        "icon": "fa-snowflake",
        "is_sample_data": True
    },
    {
        "id": "tokyo_japan",
        "name": "Tokyo",
        "country": "Japan",
        "tagline": "Futuristic neon cityscapes, quiet hidden shrines, and the world's finest culinary scene",
        "image_url": "https://images.unsplash.com/photo-1503899036084-c55cdd92da26?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 8 days",
        "tags": [
            "food",
            "culture",
            "shopping",
            "nightlife",
            "museums",
            "technology",
            "cafes"
        ],
        "style": "active",
        "crowd_level": "high",
        "budget_tier": "balanced",
        "estimated_cost": "$95 - $160 / day \u00b7 Balanced",
        "preferred_climate": [
            "mild",
            "cool"
        ],
        "suitable_companions": [
            "alone",
            "friends",
            "partner"
        ],
        "best_seasons": [
            "Spring (Mar - May)",
            "Autumn (Oct - Nov)"
        ],
        "is_trending": True,
        "trending_reason": "Global culinary capital with unmatched transit convenience and modern pop culture",
        "is_seasonal": False,
        "available_experiences": [
            "Walking through the world's busiest pedestrian crossing at Shibuya",
            "Sampling Michelin-starred ramen at tiny alley counters in Shinjuku",
            "Visiting ancient Senso-ji temple in historic Asakusa",
            "Browsing electronic, gaming, and anime districts in Akihabara"
        ],
        "travel_style_and_atmosphere": "Hyper-modern, ultra-clean, endlessly fascinating, and fast-paced",
        "practical_considerations": "Get a digital Suica or Pasmo transit card on your phone for seamless travel on all subways and trains.",
        "limitations_or_uncertainties": "Major transit stations can feel like mazes; dense crowds during peak morning hours.",
        "avoidance_triggers": [
            "crowds",
            "complex_transit"
        ],
        "icon": "fa-city",
        "is_sample_data": True
    }
]


def score_destination_for_user(
    dest: Dict[str, Any],
    profile: Dict[str, Any],
    detailed_profile: Optional[Dict[str, Any]] = None,
    past_trips: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Computes a transparent match score [0.0 - 100.0] and dynamic explanation for why a destination
    suits the user's stated answers, gracefully handling missing information without penalties.
    """
    w = SCORING_WEIGHTS
    score = 0.0
    suitability_reasons = []
    warnings = []

    # 1. Interests & Goals match
    user_interests = set()
    for key in ["interests", "place_interests", "travel_goals"]:
        val = profile.get(key)
        if isinstance(val, list):
            for item in val:
                user_interests.add(str(item).lower())
        elif isinstance(val, str) and val:
            user_interests.add(val.lower())

    goal_mapping = {
        "nature": "nature",
        "experiencing_nature": "nature",
        "adventure": "adventure",
        "relaxation": "relaxation",
        "history": "history",
        "history_culture": "history",
        "culture": "culture",
        "food": "food",
        "trying_new_foods": "food",
        "photography": "photography",
        "sightseeing": "photography",
        "beaches": "beaches",
        "mountains": "mountains",
        "shopping": "shopping",
        "wellness": "wellness",
        "cafes": "cafes",
        "hidden_gems": "nature",
        "nightlife": "nightlife"
    }

    normalized_user_tags = set()
    for ui in user_interests:
        normalized_user_tags.add(ui)
        mapped = goal_mapping.get(ui)
        if mapped:
            normalized_user_tags.add(mapped)

    dest_tags = set([t.lower() for t in dest.get("tags", [])])
    shared_tags = normalized_user_tags.intersection(dest_tags)

    if shared_tags:
        interest_score = min(w["interests_max"], len(shared_tags) * w["interest_tag_match"])
        score += interest_score
        tag_labels = [t.replace("_", " ").title() for t in list(shared_tags)[:3]]
        suitability_reasons.append(f"Recommended because you enjoy {', '.join(tag_labels)}")
    else:
        score += w["baseline_discovery"]

    # 2. Climate preference match (handles missing/unspecified gracefully)
    raw_climate = profile.get("preferred_climate")
    dest_climates = [c.lower() for c in dest.get("preferred_climate", [])]

    if not raw_climate or raw_climate in ["no_preference", "any", "unspecified", "none"]:
        score += w["climate_unspecified"]
    else:
        user_climate = raw_climate.lower()
        if user_climate in dest_climates:
            score += w["climate_exact_match"]
            suitability_reasons.append(f"offers the {user_climate.title()} weather you prefer")
        elif (user_climate in ["cold", "cool"] and any(c in ["cold", "cool"] for c in dest_climates)) or \
             (user_climate in ["warm", "tropical"] and any(c in ["warm", "tropical"] for c in dest_climates)):
            score += w["climate_adjacent_match"]
            suitability_reasons.append(f"comfortably aligns with your {user_climate.title()} climate preference")
        else:
            score += 5.0

    # 3. Budget tier match (handles missing/unspecified gracefully)
    raw_budget = profile.get("budget_tier")
    dest_budget = dest.get("budget_tier", "balanced").lower()

    if not raw_budget or raw_budget in ["unspecified", "any", "none"]:
        score += w["budget_unspecified"]
    else:
        budget_normalized = {
            "budget": "budget",
            "shoestring": "budget",
            "mid_range": "balanced",
            "balanced": "balanced",
            "luxury": "luxury",
            "premium": "luxury"
        }
        user_b_norm = budget_normalized.get(raw_budget.lower(), "balanced")

        if user_b_norm == dest_budget:
            score += w["budget_exact_match"]
            suitability_reasons.append(f"fits your {user_b_norm.title()} travel budget")
        elif (user_b_norm == "balanced" and dest_budget in ["budget", "luxury"]) or \
             (user_b_norm == "budget" and dest_budget == "balanced") or \
             (user_b_norm == "luxury" and dest_budget == "balanced"):
            score += w["budget_adjacent_match"]
        else:
            score += 5.0

    # 4. Companions match
    raw_comp = profile.get("companions")
    if raw_comp and raw_comp not in ["varies", "unspecified"]:
        user_companions = raw_comp.lower()
        suitable_companions = [c.lower() for c in dest.get("suitable_companions", [])]
        if user_companions in suitable_companions:
            score += w["companions_match"]
            comp_title = user_companions.replace("_", " ").title()
            suitability_reasons.append(f"is well suited for {comp_title} travel")

    # 5. Travel style & pace match
    try:
        user_pace = float(profile.get("pace", 0.5))
        dest_style = dest.get("style", "balanced")
        if (user_pace <= 0.4 and dest_style == "relaxed") or \
           (0.4 < user_pace <= 0.6 and dest_style in ["balanced", "comfort"]) or \
           (user_pace > 0.6 and dest_style == "active"):
            score += w["pace_match"]
    except Exception:
        pass

    # 6. Deep Profile Constraints (Avoidances penalty)
    active_avoidances = []
    if detailed_profile and detailed_profile.get("avoidances"):
        active_avoidances.extend([str(a).lower() for a in detailed_profile["avoidances"]])
    
    raw_answers = profile.get("raw_answers") or {}
    if "q12" in raw_answers and isinstance(raw_answers["q12"], list):
        active_avoidances.extend([str(a).lower() for a in raw_answers["q12"]])

    dest_triggers = [t.lower() for t in dest.get("avoidance_triggers", [])]
    for avoid in set(active_avoidances):
        for trigger in dest_triggers:
            if avoid in trigger or trigger in avoid:
                score = max(5.0, score - w["avoidance_penalty"])
                warnings.append(f"Notice: May conflict with your avoidance of {avoid.replace('_', ' ')}")

    # 7. Past trip preference adjustment
    if past_trips:
        for pt in past_trips:
            if pt.get("destination", "").lower() in dest["name"].lower():
                try:
                    rating = float(pt.get("rating", 3.0))
                    if rating >= 4.0:
                        score += w["past_trip_bonus"]
                    else:
                        score -= 10.0
                except Exception:
                    pass

    # Normalize final score [15.0, 98.0]
    final_score = round(min(98.0, max(15.0, score)), 1)

    # Build clear, natural explanation string
    if suitability_reasons:
        if len(suitability_reasons) == 1:
            why_text = f"{suitability_reasons[0]}."
        elif len(suitability_reasons) == 2:
            why_text = f"{suitability_reasons[0]}, and {suitability_reasons[1]}."
        else:
            why_text = f"{suitability_reasons[0]}, {suitability_reasons[1]}, and {suitability_reasons[2]}."
    else:
        why_text = f"Offers diverse {dest['style']} experiences suitable for general exploration."

    return {
        "id": dest["id"],
        "name": dest["name"],
        "country": dest["country"],
        "tagline": dest["tagline"],
        "image_url": dest.get("image_url"),
        "duration": dest.get("duration", "4 - 7 days"),
        "match_score": final_score,
        "why_it_suits": why_text,
        "tags": [t.replace("_", " ").title() for t in dest.get("tags", [])[:4]],
        "available_experiences": dest["available_experiences"],
        "travel_style_and_atmosphere": dest["travel_style_and_atmosphere"],
        "practical_considerations": dest.get("practical_considerations", "Check visa regulations and book seasonal activities ahead."),
        "budget_tier": dest["budget_tier"].title(),
        "estimated_cost": dest["estimated_cost"],
        "best_season_and_weather": ", ".join(dest["best_seasons"]),
        "limitations_or_uncertainties": dest["limitations_or_uncertainties"],
        "warnings": warnings,
        "is_trending": dest.get("is_trending", False),
        "trending_reason": dest.get("trending_reason"),
        "is_seasonal": dest.get("is_seasonal", False),
        "seasonal_event": dest.get("seasonal_event"),
        "icon": dest.get("icon", "fa-map-pin"),
        "is_sample_data": True,
        "is_shortlisted": False
    }


def get_categorized_recommendations(
    profile: Dict[str, Any],
    detailed_profile: Optional[Dict[str, Any]] = None,
    past_trips: Optional[List[Dict[str, Any]]] = None,
    offset: int = 0,
    shortlisted_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Returns recommendations cleanly separated into the 3 required categories:
    1. Recommended For You (scored & tailored to profile, with offset rotation on refresh)
    2. Trending Trips (popular & timely)
    3. Seasonal and Upcoming Experiences (season/event-specific)
    """
    shortlist_set = set(shortlisted_ids or [])

    # Serve 100% authentic Indian destinations for user exploration and recommendations
    indian_destinations = [d for d in DESTINATIONS if d.get("country") == "India"]
    candidate_pool = indian_destinations if indian_destinations else DESTINATIONS

    scored = []
    for d in candidate_pool:
        sc = score_destination_for_user(d, profile, detailed_profile, past_trips)
        sc["is_shortlisted"] = sc["id"] in shortlist_set
        scored.append(sc)

    # Sort all by match score descending
    scored_sorted = sorted(scored, key=lambda x: x["match_score"], reverse=True)
    total_candidates = len(scored_sorted)

    # Rotate through top matching candidates when user clicks 'Refresh Options'
    batch_size = 4
    effective_offset = offset % total_candidates if total_candidates > 0 else 0
    end_idx = effective_offset + batch_size

    if end_idx <= total_candidates:
        recommended_for_you = scored_sorted[effective_offset:end_idx]
    else:
        # Wrap around to beginning of top ranked pool
        recommended_for_you = scored_sorted[effective_offset:] + scored_sorted[:end_idx - total_candidates]

    recommended_ids = set(r["id"] for r in recommended_for_you)

    # 2. Trending Trips: High buzz, curated popular options
    trending_trips = []
    for s in scored:
        if s.get("is_trending") and s["id"] not in recommended_ids:
            trending_trips.append(s)
    if len(trending_trips) < 3:
        for s in scored:
            if s.get("is_trending") and s not in trending_trips:
                trending_trips.append(s)
    trending_trips = trending_trips[:3]

    # 3. Seasonal & Upcoming Experiences
    seasonal_experiences = []
    already_shown = recommended_ids.union(set(t["id"] for t in trending_trips))
    for s in scored:
        if s.get("is_seasonal") and s["id"] not in already_shown:
            seasonal_experiences.append(s)
    if len(seasonal_experiences) < 3:
        for s in scored:
            if s.get("is_seasonal") and s not in seasonal_experiences:
                seasonal_experiences.append(s)
    seasonal_experiences = seasonal_experiences[:3]

    # Basis summary in plain language
    if detailed_profile and detailed_profile.get("avoidances"):
        basis = "Personalized around your stated interests, budget, climate, and personal comfort constraints."
    else:
        basis = "Selected around your starting profile interests, preferred climate, and travel budget."

    return {
        "basis_summary": basis,
        "total_candidates": total_candidates,
        "offset": effective_offset,
        "recommended_for_you": recommended_for_you,
        "trending_trips": trending_trips,
        "seasonal_and_upcoming": seasonal_experiences
    }
