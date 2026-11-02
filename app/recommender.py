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
        "id": "kyoto_japan",
        "name": "Kyoto",
        "country": "Japan",
        "tagline": "Ancient temples, serene zen gardens, and timeless tea culture",
        "image_url": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 7 days",
        "tags": ["culture", "history", "food", "cafes", "nature", "photography", "relaxation", "architecture"],
        "style": "relaxed",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "$85 - $130 / day · Balanced",
        "preferred_climate": ["mild", "cool"],
        "suitable_companions": ["alone", "partner", "friends", "family_older"],
        "best_seasons": ["Spring (Mar - May)", "Autumn (Oct - Nov)"],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Autumn Foliage & Night Temple Illuminations (Oct - Nov)",
        "available_experiences": [
            "Walking through Arashiyama Bamboo Grove at sunrise",
            "Traditional matcha tea ceremony in historic Gion",
            "Exploring Fushimi Inari torii gates along mountain paths",
            "Sampling artisan street food in Nishiki Market"
        ],
        "travel_style_and_atmosphere": "Serene, historic, pedestrian-friendly with rich traditional charm",
        "practical_considerations": "Reserve temple tea ceremonies and popular restaurants 1-2 weeks in advance. Get an IC card for seamless bus and subway travel.",
        "limitations_or_uncertainties": "Major shrines get crowded between 10 AM - 3 PM; involves extensive walking on stone paths.",
        "avoidance_triggers": ["crowds", "steep_stairs", "long_walking"],
        "icon": "fa-torii-gate",
        "is_sample_data": True
    },
    {
        "id": "manali_spiti_india",
        "name": "Manali & Spiti Valley",
        "country": "India",
        "tagline": "High Himalayan passes, ancient cliffside monasteries, and crisp mountain air",
        "image_url": "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=800&q=80",
        "duration": "7 - 10 days",
        "tags": ["mountains", "nature", "adventure", "photography", "scenic_landscapes", "hiking"],
        "style": "active",
        "crowd_level": "low",
        "budget_tier": "budget",
        "estimated_cost": "₹2,500 - ₹4,500 ($30 - $55) / day · Budget",
        "preferred_climate": ["cool", "cold"],
        "suitable_companions": ["alone", "friends", "partner"],
        "best_seasons": ["Summer (May - Jun) for Spiti", "Winter (Dec - Feb) for snow"],
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
        "avoidance_triggers": ["high_altitude", "strenuous_hikes", "long_bus_rides", "motion_sickness"],
        "icon": "fa-mountain-sun",
        "is_sample_data": True
    },
    {
        "id": "santorini_greece",
        "name": "Santorini & Cyclades",
        "country": "Greece",
        "tagline": "Iconic whitewashed caldera villages, Aegean sunsets, and coastal relaxation",
        "image_url": "https://images.unsplash.com/photo-1570077188670-e3a8d69ac5ff?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 6 days",
        "tags": ["beaches", "coastal", "relaxation", "photography", "food", "cafes", "culture"],
        "style": "relaxed",
        "crowd_level": "high",
        "budget_tier": "luxury",
        "estimated_cost": "$180 - $320 / day · Luxury",
        "preferred_climate": ["warm", "mild"],
        "suitable_companions": ["partner", "friends", "alone"],
        "best_seasons": ["Late Spring (May)", "Autumn (Sep - Oct)"],
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
        "avoidance_triggers": ["steep_stairs", "extreme_heat", "crowds", "high_prices"],
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
        "tags": ["mountains", "nature", "scenic_landscapes", "adventure", "photography", "relaxation"],
        "style": "comfort",
        "crowd_level": "moderate",
        "budget_tier": "luxury",
        "estimated_cost": "$210 - $360 / day · Luxury",
        "preferred_climate": ["cool", "cold"],
        "suitable_companions": ["partner", "family_children", "family_older", "alone"],
        "best_seasons": ["Summer (Jul - Aug) for hiking", "Winter (Dec - Mar) for skiing"],
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
        "avoidance_triggers": ["extreme_cold", "extreme_heights", "high_prices"],
        "icon": "fa-snowflake",
        "is_sample_data": True
    },
    {
        "id": "south_goa_india",
        "name": "South Goa (Palolem & Agonda)",
        "country": "India",
        "tagline": "Golden uncrowded sands, palm-fringed bays, and laid-back coastal cafes",
        "image_url": "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 6 days",
        "tags": ["beaches", "relaxation", "food", "cafes", "nature", "coastal", "wellness"],
        "style": "relaxed",
        "crowd_level": "low",
        "budget_tier": "budget",
        "estimated_cost": "₹2,200 - ₹4,000 ($28 - $50) / day · Budget",
        "preferred_climate": ["warm", "tropical"],
        "suitable_companions": ["alone", "partner", "friends", "family_children"],
        "best_seasons": ["November to February (dry and breezy)"],
        "is_trending": True,
        "trending_reason": "Top domestic winter getaway for peaceful beaches, remote work cafes, and sunset spots",
        "is_seasonal": True,
        "seasonal_event": "Winter Beach Season & Coastal Music Evenings (Nov - Feb)",
        "available_experiences": [
            "Morning kayak along silent backwaters near Cola Beach",
            "Yoga classes overlooking gentle waves in Agonda",
            "Sunset dining with fresh Konkani fish curry at beach shacks",
            "Exploring Portuguese heritage mansions and spice plantations"
        ],
        "travel_style_and_atmosphere": "Laid-back coastal rhythm, warm breezes, unhurried and rejuvenating",
        "practical_considerations": "Renting a scooter or booking pre-paid taxis is the most practical way to explore quiet southern beaches.",
        "limitations_or_uncertainties": "Afternoon humidity can feel high; monsoons (June-August) bring rough seas.",
        "avoidance_triggers": ["extreme_heat", "crowded_clubs"],
        "icon": "fa-umbrella-beach",
        "is_sample_data": True
    },
    {
        "id": "rome_florence_italy",
        "name": "Rome & Florence",
        "country": "Italy",
        "tagline": "Colosseum legends, Renaissance masterpieces, and world-class culinary art",
        "image_url": "https://images.unsplash.com/photo-1552832230-c0197dd311b5?auto=format&fit=crop&w=800&q=80",
        "duration": "6 - 8 days",
        "tags": ["history", "heritage", "culture", "food", "museums", "architecture", "photography"],
        "style": "balanced",
        "crowd_level": "high",
        "budget_tier": "balanced",
        "estimated_cost": "$95 - $155 / day · Balanced",
        "preferred_climate": ["mild", "warm"],
        "suitable_companions": ["partner", "alone", "friends", "family_older"],
        "best_seasons": ["Spring (Apr - May)", "Autumn (Oct - Nov)"],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Autumn Truffle & New Olive Oil Harvest Festivals (Oct - Nov)",
        "available_experiences": [
            "Walking inside the ancient Roman Colosseum and Forum",
            "Viewing Michelangelo's David at Florence's Accademia Gallery",
            "Authentic pasta carbonara and gelato hopping in Trastevere",
            "Sunset overlook of Florence from Piazzale Michelangelo"
        ],
        "travel_style_and_atmosphere": "Lively open-air museum, vibrant piazzas, deeply historic and artistic",
        "practical_considerations": "Pre-book Vatican and Uffizi tickets weeks ahead to skip hours of queues. High-speed train connects Rome and Florence in 90 minutes.",
        "limitations_or_uncertainties": "Walking averages 10-14 km per day; summer months (July-August) can be very hot.",
        "avoidance_triggers": ["crowds", "long_walking", "tourist_traps"],
        "icon": "fa-landmark",
        "is_sample_data": True
    },
    {
        "id": "banff_canada",
        "name": "Banff National Park",
        "country": "Canada",
        "tagline": "Vivid turquoise glacial waters, rugged Rockies, and wild alpine beauty",
        "image_url": "https://images.unsplash.com/photo-1503614472-8c93d56e92ce?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 7 days",
        "tags": ["nature", "mountains", "scenic_landscapes", "adventure", "photography", "relaxation"],
        "style": "balanced",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "$120 - $190 / day · Balanced",
        "preferred_climate": ["cool", "cold"],
        "suitable_companions": ["family_children", "partner", "friends", "alone"],
        "best_seasons": ["Summer (Jun - Aug) for lakes", "Winter (Dec - Mar) for snow"],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Northern Lights Viewing & Frozen Lake Louise Ice Skating (Nov - Feb)",
        "available_experiences": [
            "Canoeing on the turquoise waters of Lake Louise and Moraine Lake",
            "Gondola ride to the summit of Sulphur Mountain for 360-degree views",
            "Soaking in Banff Upper Hot Springs surrounded by snow-capped peaks",
            "Spotting elk and bighorn sheep along the Icefields Parkway"
        ],
        "travel_style_and_atmosphere": "Majestic wilderness, crisp pine-scented air, and cozy alpine lodge charm",
        "practical_considerations": "Parks Canada park pass required. Parks shuttles for Moraine Lake must be booked early on the official portal.",
        "limitations_or_uncertainties": "Winter temperatures can dip below -15°C; rental car with winter tires recommended.",
        "avoidance_triggers": ["extreme_cold", "strenuous_hikes"],
        "icon": "fa-tree",
        "is_sample_data": True
    },
    {
        "id": "chiang_mai_thailand",
        "name": "Chiang Mai",
        "country": "Thailand",
        "tagline": "Golden mountain wats, lantern-filled skies, vibrant night markets, and artisan cafes",
        "image_url": "https://images.unsplash.com/photo-1528181304800-259b08848526?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 6 days",
        "tags": ["culture", "food", "cafes", "relaxation", "shopping", "wellness", "local_traditions"],
        "style": "relaxed",
        "crowd_level": "moderate",
        "budget_tier": "budget",
        "estimated_cost": "$25 - $45 / day · Budget",
        "preferred_climate": ["warm", "tropical"],
        "suitable_companions": ["alone", "friends", "partner", "family_children"],
        "best_seasons": ["November to February (cool and dry)"],
        "is_trending": True,
        "trending_reason": "High international interest for the magical Yi Peng Sky Lantern Festival",
        "is_seasonal": True,
        "seasonal_event": "Yi Peng & Loy Krathong Lantern Celebrations (November)",
        "available_experiences": [
            "Releasing floating lanterns during the annual Yi Peng festival",
            "Taking a hands-on northern Thai cooking class at an organic farm",
            "Visiting Wat Phra That Doi Suthep high above the city",
            "Exploring artisan craft stalls at Sunday Walking Street"
        ],
        "travel_style_and_atmosphere": "Gentle, spiritual, culturally rich, and extremely affordable",
        "practical_considerations": "Dress modestly (shoulders and knees covered) when visiting sacred temples.",
        "limitations_or_uncertainties": "Agricultural burning season causes haze between February and April.",
        "avoidance_triggers": ["extreme_heat", "poor_air_quality"],
        "icon": "fa-fan",
        "is_sample_data": True
    },
    {
        "id": "reykjavik_iceland",
        "name": "Reykjavik & South Coast",
        "country": "Iceland",
        "tagline": "Dancing Auroras, black sand shores, roaring waterfalls, and geothermal lagoons",
        "image_url": "https://images.unsplash.com/photo-1504893524553-b855bce32c67?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 7 days",
        "tags": ["nature", "adventure", "scenic_landscapes", "photography", "wellness"],
        "style": "active",
        "crowd_level": "low",
        "budget_tier": "luxury",
        "estimated_cost": "$190 - $310 / day · Luxury",
        "preferred_climate": ["cold", "cool"],
        "suitable_companions": ["partner", "friends", "alone"],
        "best_seasons": ["Oct - Mar for Auroras", "Jun - Aug for Midnight Sun"],
        "is_trending": True,
        "trending_reason": "Solar maximum cycle delivering the brightest Northern Lights displays in 11 years",
        "is_seasonal": True,
        "seasonal_event": "Peak Aurora Borealis Activity & Blue Ice Cave Treks (Oct - Mar)",
        "available_experiences": [
            "Hunting the Northern Lights across dark volcanic lava fields",
            "Walking behind the roaring water curtains at Seljalandsfoss",
            "Relaxing in warm silica waters of the Blue Lagoon",
            "Exploring crystal-blue natural ice caves under Vatnajökull glacier"
        ],
        "travel_style_and_atmosphere": "Otherworldly volcanic beauty, crisp Arctic air, and peaceful wilderness",
        "practical_considerations": "Rent a 4x4 vehicle with gravel and ash insurance. Check vedur.is daily for sudden weather shifts.",
        "limitations_or_uncertainties": "Sudden Atlantic winter storms can close roads; dining and car rentals are pricey.",
        "avoidance_triggers": ["extreme_cold", "wind_sensitivity", "high_prices"],
        "icon": "fa-icicles",
        "is_sample_data": True
    },
    {
        "id": "oaxaca_mexico",
        "name": "Oaxaca City",
        "country": "Mexico",
        "tagline": "UNESCO heritage architecture, indigenous craft markets, and legendary gastronomy",
        "image_url": "https://images.unsplash.com/photo-1518638150340-f706e86654de?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 6 days",
        "tags": ["food", "culture", "history", "cafes", "shopping", "local_traditions", "photography"],
        "style": "relaxed",
        "crowd_level": "moderate",
        "budget_tier": "budget",
        "estimated_cost": "$35 - $60 / day · Budget",
        "preferred_climate": ["mild", "warm"],
        "suitable_companions": ["alone", "partner", "friends"],
        "best_seasons": ["October to March"],
        "is_trending": True,
        "trending_reason": "Global acclaim for authentic indigenous food, artisan mezcal, and Day of the Dead traditions",
        "is_seasonal": True,
        "seasonal_event": "Día de los Muertos (Day of the Dead) Cultural Festivities (Late Oct - Early Nov)",
        "available_experiences": [
            "Tasting 7 styles of complex Oaxacan mole in Mercado 20 de Noviembre",
            "Visiting Monte Albán's ancient Zapotec pyramids on a flattened mountaintop",
            "Exploring traditional wool-weaving studios in Teotitlán del Valle",
            "Sipping artisan hot chocolate in shaded colonial zócalo cafes"
        ],
        "travel_style_and_atmosphere": "Colorful, artistic, warm, and deeply immersed in culinary heritage",
        "practical_considerations": "Carry cash in Mexican Pesos as most local markets and artisan workshops do not accept cards.",
        "limitations_or_uncertainties": "Located at 1,550m altitude; streets can be bustling during festive weeks.",
        "avoidance_triggers": ["crowds", "food_allergies"],
        "icon": "fa-utensils",
        "is_sample_data": True
    },
    {
        "id": "udaipur_india",
        "name": "Udaipur & Mewar",
        "country": "India",
        "tagline": "Royal marble lake palaces, shimmering waters, and romantic Rajput heritage",
        "image_url": "https://images.unsplash.com/photo-1615836245337-f5b9b2303f10?auto=format&fit=crop&w=800&q=80",
        "duration": "3 - 5 days",
        "tags": ["history", "heritage", "culture", "photography", "relaxation", "architecture"],
        "style": "relaxed",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "₹3,000 - ₹5,500 ($38 - $68) / day · Balanced",
        "preferred_climate": ["warm", "mild"],
        "suitable_companions": ["partner", "family_older", "alone", "family_children"],
        "best_seasons": ["October to March (sunny days, cool evenings)"],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Winter Heritage Season & Lake Pichola Sunset Cruises (Nov - Feb)",
        "available_experiences": [
            "Sunset boat cruise around Lake Pichola with views of Jag Mandir",
            "Exploring the sprawling courtyards and mirrored halls of City Palace",
            "Rooftop dining with Rajasthani thalis overlooking illuminated palace waters",
            "Watching evening folk dances and puppet arts at Bagore Ki Haveli"
        ],
        "travel_style_and_atmosphere": "Regal, romantic, peaceful lakeside elegance with artistic craftsmanship",
        "practical_considerations": "Old city streets are very narrow; walking or electric auto-rickshaws are the best way to get around.",
        "limitations_or_uncertainties": "Summer months (April to June) can exceed 40°C.",
        "avoidance_triggers": ["extreme_heat", "crowds"],
        "icon": "fa-monument",
        "is_sample_data": True
    },
    {
        "id": "queenstown_nz",
        "name": "Queenstown & Fiordland",
        "country": "New Zealand",
        "tagline": "Crystal alpine lakes, dramatic peaks, fiord cruises, and outdoor thrills",
        "image_url": "https://images.unsplash.com/photo-1507699622108-4be3abd695ad?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 8 days",
        "tags": ["adventure", "mountains", "nature", "scenic_landscapes", "hiking", "photography"],
        "style": "active",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "$125 - $210 / day · Balanced",
        "preferred_climate": ["cool", "mild"],
        "suitable_companions": ["friends", "partner", "alone"],
        "best_seasons": ["Summer (Dec - Feb) for hiking", "Winter (Jun - Aug) for skiing"],
        "is_trending": False,
        "is_seasonal": True,
        "seasonal_event": "Milford Sound Scenic Cruising & Routeburn Alpine Hike Season (Dec - Mar)",
        "available_experiences": [
            "Scenic day cruise under towering waterfalls in Milford Sound",
            "Riding the Skyline Gondola for panoramic views of Lake Wakatipu",
            "Jet boating through narrow canyons of the Shotover River",
            "Wine tasting Central Otago Pinot Noir at boutique vineyard estates"
        ],
        "travel_style_and_atmosphere": "Energetic, breathtaking, pristine outdoors, and friendly Kiwi hospitality",
        "practical_considerations": "Book Milford Sound coach/cruises in advance as day trips take around 12 hours from Queenstown.",
        "limitations_or_uncertainties": "Fiordland gets frequent rainfall; long travel transit times from most global regions.",
        "avoidance_triggers": ["extreme_heights", "strenuous_hikes", "long_bus_rides"],
        "icon": "fa-compass",
        "is_sample_data": True
    },
    {
        "id": "kerala_alleppey_india",
        "name": "Kerala (Munnar & Alleppey)",
        "country": "India",
        "tagline": "Rolling emerald tea plantations, gentle backwater houseboats, and spice coast wellness",
        "image_url": "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 7 days",
        "tags": ["nature", "relaxation", "scenic_landscapes", "food", "wellness", "culture"],
        "style": "relaxed",
        "crowd_level": "low",
        "budget_tier": "balanced",
        "estimated_cost": "₹2,800 - ₹5,000 ($35 - $62) / day · Balanced",
        "preferred_climate": ["mild", "warm", "tropical"],
        "suitable_companions": ["partner", "family_children", "family_older", "alone"],
        "best_seasons": ["September to March"],
        "is_trending": True,
        "trending_reason": "High domestic & global demand for peaceful houseboat stays and Ayurvedic healing",
        "is_seasonal": True,
        "seasonal_event": "Winter Backwater Sailing & Fresh Spice Harvest Season (Nov - Feb)",
        "available_experiences": [
            "Overnight stay on a traditional thatched houseboat cruising palm-fringed backwaters",
            "Morning walk through misty tea estates in Munnar with fresh tea tasting",
            "Traditional Ayurvedic rejuvenation massage and herbal steam therapy",
            "Sampling Kerala sadhya feast served fresh on a banana leaf"
        ],
        "travel_style_and_atmosphere": "Tranquil, verdant, therapeutic, and deeply comforting",
        "practical_considerations": "Hire a private cab for the scenic 4-hour drive between Kochi, Munnar, and Alleppey.",
        "limitations_or_uncertainties": "Winding mountain roads up to Munnar can trigger motion sickness for sensitive travellers.",
        "avoidance_triggers": ["motion_sickness", "long_bus_rides"],
        "icon": "fa-leaf",
        "is_sample_data": True
    },
    {
        "id": "barcelona_spain",
        "name": "Barcelona & Costa Brava",
        "country": "Spain",
        "tagline": "Gaudí's architectural wonders, golden Mediterranean beaches, and lively tapas culture",
        "image_url": "https://images.unsplash.com/photo-1583422409516-2895a77efded?auto=format&fit=crop&w=800&q=80",
        "duration": "4 - 7 days",
        "tags": ["architecture", "food", "beaches", "culture", "nightlife", "photography", "cafes"],
        "style": "balanced",
        "crowd_level": "high",
        "budget_tier": "balanced",
        "estimated_cost": "$90 - $145 / day · Balanced",
        "preferred_climate": ["warm", "mild"],
        "suitable_companions": ["friends", "partner", "alone"],
        "best_seasons": ["May to June", "September to October"],
        "is_seasonal": False,
        "is_trending": False,
        "available_experiences": [
            "Marveling at the stained glass light inside Sagrada Família",
            "Strolling down pedestrian Las Ramblas into the historic Gothic Quarter",
            "Tasting fresh seafood tapas and Iberian ham at La Boqueria Market",
            "Relaxing on Barceloneta beach with afternoon sangria"
        ],
        "travel_style_and_atmosphere": "Vibrant, creative, sun-drenched, with celebrated gastronomy and lively street life",
        "practical_considerations": "Book Sagrada Família and Park Güell entry tickets online in advance to avoid sold-out days.",
        "limitations_or_uncertainties": "Pickpocketing is common in crowded transit stations; summer queues are long.",
        "avoidance_triggers": ["crowds", "tourist_traps"],
        "icon": "fa-palette",
        "is_sample_data": True
    },
    {
        "id": "tokyo_japan",
        "name": "Tokyo",
        "country": "Japan",
        "tagline": "Futuristic neon cityscapes, quiet hidden shrines, and the world's finest culinary scene",
        "image_url": "https://images.unsplash.com/photo-1503899036084-c55cdd92da26?auto=format&fit=crop&w=800&q=80",
        "duration": "5 - 8 days",
        "tags": ["food", "culture", "shopping", "nightlife", "museums", "technology", "cafes"],
        "style": "active",
        "crowd_level": "high",
        "budget_tier": "balanced",
        "estimated_cost": "$95 - $160 / day · Balanced",
        "preferred_climate": ["mild", "cool"],
        "suitable_companions": ["alone", "friends", "partner"],
        "best_seasons": ["Spring (Mar - May)", "Autumn (Oct - Nov)"],
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
        "avoidance_triggers": ["crowds", "complex_transit"],
        "icon": "fa-city",
        "is_sample_data": True
    },
    {
        "id": "cape_town_south_africa",
        "name": "Cape Town & Peninsula",
        "country": "South Africa",
        "tagline": "Towering ocean cliffs, coastal penguins, vineyard valleys, and vibrant waterfront dining",
        "image_url": "https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=800&q=80",
        "duration": "6 - 9 days",
        "tags": ["nature", "beaches", "scenic_landscapes", "adventure", "food", "photography"],
        "style": "balanced",
        "crowd_level": "moderate",
        "budget_tier": "balanced",
        "estimated_cost": "$70 - $120 / day · Balanced",
        "preferred_climate": ["warm", "mild"],
        "suitable_companions": ["partner", "friends", "alone"],
        "best_seasons": ["November to March (warm summer)"],
        "is_trending": True,
        "trending_reason": "High traveler ratings for coastal drives, favorable exchange rate, and culinary vineyard tours",
        "is_seasonal": True,
        "seasonal_event": "Southern Summer Season & Boulders Beach Penguin Colony Visits (Nov - Feb)",
        "available_experiences": [
            "Taking the rotating cable car up to the flat top of Table Mountain",
            "Visiting the wild African penguin colony at Boulders Beach",
            "Scenic coastal drive along Chapman's Peak overlooking crashing waves",
            "Wine tasting at historical vineyards in Franschhoek and Stellenbosch"
        ],
        "travel_style_and_atmosphere": "Dramatic natural spectacle where mountains drop right into two oceans",
        "practical_considerations": "Rent a car for flexibility along the coast and Cape Peninsula. Check Table Mountain cable car operational status on windy mornings.",
        "limitations_or_uncertainties": "Windy weather can temporarily close mountain cable cars.",
        "avoidance_triggers": ["wind_sensitivity", "extreme_heights"],
        "icon": "fa-sun",
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

    scored = []
    for d in DESTINATIONS:
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
