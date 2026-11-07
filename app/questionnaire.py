# Master Questionnaire Bank (56 Questions across 10 Sections)
# Organised into Basic Profile (30-60s setup) and Deep Personalisation (Full Bank)

QUESTIONNAIRE_SECTIONS = [
    {
        "id": "sec_1",
        "title": "Section 1: Personal and Travel Background",
        "purpose": "Understand general travel behaviour, experience, and the kind of support needed."
    },
    {
        "id": "sec_2",
        "title": "Section 2: Health, Mobility and Personal Comfort",
        "purpose": "Identify travel-related needs that could affect recommendations, activities, food, and safety (all optional)."
    },
    {
        "id": "sec_3",
        "title": "Section 3: Interests, Hobbies and Activities",
        "purpose": "Recommend places the traveller is genuinely likely to enjoy rather than generic tourist rankings."
    },
    {
        "id": "sec_4",
        "title": "Section 4: Food, Diet and Daily Lifestyle",
        "purpose": "Make food recommendations useful for the individual, finding suitable restaurants and grocery shops."
    },
    {
        "id": "sec_5",
        "title": "Section 5: Weather, Clothing and Environmental Preferences",
        "purpose": "Personalise packing lists and proactive weather warnings using comfort preferences."
    },
    {
        "id": "sec_6",
        "title": "Section 6: Budget, Accommodation and Transport",
        "purpose": "Understand practical trade-offs so recommendations are feasible."
    },
    {
        "id": "sec_7",
        "title": "Section 7: Travel Documents, Essentials and Preparedness",
        "purpose": "Discover which reminders the user needs before and during a trip."
    },
    {
        "id": "sec_8",
        "title": "Section 8: Behaviour, Decision-Making and Proactive Assistance",
        "purpose": "Understand how the user makes decisions and how the RL system evaluates recommendations."
    },
    {
        "id": "sec_9",
        "title": "Section 9: Trust, Privacy and Personalization Boundaries",
        "purpose": "Establish what the system may remember and how information is handled."
    },
    {
        "id": "sec_10",
        "title": "Section 10: Final Personalization Questions",
        "purpose": "Open-ended insights revealing preferences that fixed-choice questions miss."
    }
]

# Complete Master Question Bank
QUESTIONS = {
    # --- Section 1 ---
    "q1": {
        "id": "q1",
        "section": "sec_1",
        "tier": "basic",
        "question": "Which age group do you belong to?",
        "type": "single",
        "options": [
            {"id": "under_18", "label": "Under 18"},
            {"id": "18_24", "label": "18–24"},
            {"id": "25_34", "label": "25–34"},
            {"id": "35_44", "label": "35–44"},
            {"id": "45_54", "label": "45–54"},
            {"id": "55_plus", "label": "55+"},
            {"id": "prefer_not_to_say", "label": "Prefer not to say"}
        ]
    },
    "q2": {
        "id": "q2",
        "section": "sec_1",
        "tier": "basic",
        "question": "How would you describe your travel experience?",
        "type": "single",
        "options": [
            {"id": "beginner", "label": "Beginner", "desc": "I need guidance with most travel arrangements."},
            {"id": "occasional", "label": "Occasional traveller", "desc": "I know the basics but need help with unfamiliar destinations."},
            {"id": "experienced", "label": "Experienced traveller", "desc": "I can handle most situations independently."},
            {"id": "frequent", "label": "Frequent traveller", "desc": "I mainly need specialized recommendations and timely updates."}
        ]
    },
    "q3": {
        "id": "q3",
        "section": "sec_1",
        "tier": "basic",
        "question": "Who do you usually travel with?",
        "type": "single",
        "options": [
            {"id": "alone", "label": "Alone (Solo)"},
            {"id": "partner", "label": "Partner"},
            {"id": "friends", "label": "Friends"},
            {"id": "family_children", "label": "Family with children"},
            {"id": "family_older", "label": "Family with older adults"},
            {"id": "tour_group", "label": "Organized tour group"},
            {"id": "varies", "label": "It varies by trip"}
        ]
    },
    "q4": {
        "id": "q4",
        "section": "sec_1",
        "tier": "basic",
        "question": "What is your usual approach to planning a trip?",
        "type": "single",
        "options": [
            {"id": "plan_advance", "label": "I plan everything in advance."},
            {"id": "plan_essentials", "label": "I plan essentials and decide the rest later."},
            {"id": "spontaneous", "label": "I prefer spontaneous travel."},
            {"id": "rely_agent", "label": "I rely on another person or a travel agent."},
            {"id": "ai_guided", "label": "I want an AI assistant to guide me through the process."}
        ]
    },
    "q5": {
        "id": "q5",
        "section": "sec_1",
        "tier": "basic",
        "question": "What do you most want to get out of travelling? (Select at least 2)",
        "type": "multi",
        "options": [
            {"id": "relaxation", "label": "Relaxation and stress relief", "icon": "fa-umbrella-beach"},
            {"id": "adventure", "label": "Adventure and excitement", "icon": "fa-person-hiking"},
            {"id": "culture_history", "label": "Learning history and culture", "icon": "fa-landmark"},
            {"id": "nature", "label": "Experiencing nature", "icon": "fa-tree"},
            {"id": "food_dining", "label": "Trying new foods", "icon": "fa-utensils"},
            {"id": "shopping", "label": "Shopping", "icon": "fa-bag-shopping"},
            {"id": "socializing", "label": "Meeting people and socializing", "icon": "fa-users"},
            {"id": "photography", "label": "Photography and sightseeing", "icon": "fa-camera"},
            {"id": "growth", "label": "Personal or spiritual growth", "icon": "fa-spa"},
            {"id": "quality_time", "label": "Quality time with family/friends", "icon": "fa-heart"},
            {"id": "work_study", "label": "Work or education", "icon": "fa-briefcase"}
        ]
    },
    "q6": {
        "id": "q6",
        "section": "sec_1",
        "tier": "detailed",
        "question": "What usually makes travelling difficult or stressful for you? (Select up to 3)",
        "type": "multi",
        "max": 3,
        "options": [
            {"id": "planning_decisions", "label": "Planning and decision-making"},
            {"id": "unfamiliar_env", "label": "Unfamiliar environments"},
            {"id": "language_barriers", "label": "Language barriers"},
            {"id": "navigating_transit", "label": "Navigating public transport"},
            {"id": "managing_expenses", "label": "Managing expenses"},
            {"id": "weather_packing", "label": "Weather and packing"},
            {"id": "finding_food", "label": "Finding suitable food"},
            {"id": "crowds_queues", "label": "Crowds and queues"},
            {"id": "safety_concerns", "label": "Safety concerns"},
            {"id": "physical_tiredness", "label": "Physical tiredness"},
            {"id": "keeping_docs", "label": "Keeping track of documents"},
            {"id": "unexpected_changes", "label": "Unexpected changes"}
        ]
    },

    # --- Section 2: Health, Mobility and Comfort ---
    "q7": {
        "id": "q7",
        "section": "sec_2",
        "tier": "detailed",
        "question": "Are there any physical or health-related factors you would like the assistant to consider?",
        "type": "multi",
        "options": [
            {"id": "none", "label": "None"},
            {"id": "cold_wind_sensitive", "label": "Sensitivity to cold or wind"},
            {"id": "heat_humidity_sensitive", "label": "Sensitivity to heat or humidity"},
            {"id": "motion_sickness", "label": "Motion sickness"},
            {"id": "altitude_discomfort", "label": "Altitude-related discomfort"},
            {"id": "air_quality_sensitive", "label": "Respiratory or air-quality sensitivity"},
            {"id": "sun_sensitive", "label": "Sun sensitivity"},
            {"id": "allergies", "label": "Allergies"},
            {"id": "food_health_restrictions", "label": "Food-related health restrictions"},
            {"id": "walking_difficulty", "label": "Difficulty walking long distances"},
            {"id": "stairs_difficulty", "label": "Difficulty climbing stairs"},
            {"id": "fatigue_stamina", "label": "Fatigue or limited stamina"},
            {"id": "activity_affecting_condition", "label": "Condition affecting activities"}
        ]
    },
    "q8": {
        "id": "q8",
        "section": "sec_2",
        "tier": "detailed",
        "question": "How physically demanding would you like your typical trip to be?",
        "type": "single",
        "options": [
            {"id": "very_relaxed", "label": "Very relaxed, with minimal physical effort"},
            {"id": "light_breaks", "label": "Light activity with frequent breaks"},
            {"id": "moderate_walking", "label": "Moderate walking and sightseeing"},
            {"id": "highly_active", "label": "Highly active, with hiking or outdoor activities"},
            {"id": "depends_destination", "label": "It depends on the destination"}
        ]
    },
    "q9": {
        "id": "q9",
        "section": "sec_2",
        "tier": "detailed",
        "question": "Do you have any accessibility requirements?",
        "type": "multi",
        "options": [
            {"id": "step_free", "label": "Step-free access"},
            {"id": "wheelchair", "label": "Wheelchair-accessible transport/attractions"},
            {"id": "accessible_toilets", "label": "Accessible toilets"},
            {"id": "rest_stops", "label": "Frequent seating and rest stops"},
            {"id": "short_walks", "label": "Short walking distances"},
            {"id": "sensory_assistance", "label": "Assistance with hearing or visual information"},
            {"id": "none", "label": "No specific requirements"}
        ]
    },
    "q10": {
        "id": "q10",
        "section": "sec_2",
        "tier": "detailed",
        "question": "Are there any allergies, intolerances, or environmental triggers?",
        "type": "multi",
        "options": [
            {"id": "no_concerns", "label": "No known concerns"},
            {"id": "food_allergies", "label": "Food allergies"},
            {"id": "medication_allergies", "label": "Medication allergies"},
            {"id": "pollen_environmental", "label": "Pollen or environmental allergies"},
            {"id": "dust_air", "label": "Dust or air-quality sensitivity"},
            {"id": "insect_stings", "label": "Insect bites or stings"}
        ]
    },
    "q11": {
        "id": "q11",
        "section": "sec_2",
        "tier": "detailed",
        "question": "Do you regularly need to carry any health-related items while travelling?",
        "type": "single",
        "options": [
            {"id": "no", "label": "No"},
            {"id": "personal_medication", "label": "Personal medication"},
            {"id": "medical_equipment", "label": "Medical equipment"},
            {"id": "mobility_aids", "label": "Mobility aids"},
            {"id": "emergency_supplies", "label": "Allergy-related emergency supplies"}
        ]
    },
    "q12": {
        "id": "q12",
        "section": "sec_2",
        "tier": "detailed",
        "question": "Are there any activities or environments you need to avoid for personal comfort or health?",
        "type": "multi",
        "options": [
            {"id": "strenuous_hikes", "label": "Strenuous hikes"},
            {"id": "extreme_heights", "label": "Heights / Steep edges"},
            {"id": "extreme_heat", "label": "Extreme heat & humidity"},
            {"id": "steep_stairs", "label": "Steep stairs or climbs"},
            {"id": "crowded_spaces", "label": "Dense, packed crowds"},
            {"id": "noisy_nightlife", "label": "Loud nightclubs / blaring music"},
            {"id": "long_bus_rides", "label": "Long continuous bus rides"},
            {"id": "early_morning_rush", "label": "Early morning rushes"}
        ]
    },
    "q13": {
        "id": "q13",
        "section": "sec_2",
        "tier": "detailed",
        "question": "How should the assistant respond when conditions might be uncomfortable for you?",
        "type": "single",
        "options": [
            {"id": "warn_before", "label": "Warn me before the activity."},
            {"id": "suggest_safer", "label": "Suggest a safer or more comfortable alternative."},
            {"id": "auto_adjust", "label": "Adjust the itinerary automatically and ask me to confirm."},
            {"id": "info_only", "label": "Give me information and let me decide."},
            {"id": "significant_only", "label": "Alert me only when the concern is significant."}
        ]
    },

    # --- Section 3: Interests, Hobbies and Activities ---
    "q14": {
        "id": "q14",
        "section": "sec_3",
        "tier": "basic",
        "question": "Which types of places interest you most? (Select at least 2)",
        "type": "multi",
        "options": [
            {"id": "mountains_nature", "label": "Mountains and natural landscapes", "icon": "fa-mountain"},
            {"id": "beaches_coastal", "label": "Beaches and coastal areas", "icon": "fa-water"},
            {"id": "forests_wildlife", "label": "Forests, lakes and wildlife", "icon": "fa-paw"},
            {"id": "historical_sites", "label": "Historical sites and monuments", "icon": "fa-monument"},
            {"id": "museums_art", "label": "Museums and art galleries", "icon": "fa-palette"},
            {"id": "local_markets", "label": "Local markets and shopping streets", "icon": "fa-store"},
            {"id": "cafes_restaurants", "label": "Cafés and restaurants", "icon": "fa-mug-hot"},
            {"id": "religious_spiritual", "label": "Religious or spiritual sites", "icon": "fa-place-of-worship"},
            {"id": "theme_parks", "label": "Theme parks and entertainment", "icon": "fa-ticket"},
            {"id": "nightlife_music", "label": "Nightlife and live music", "icon": "fa-music"},
            {"id": "villages_communities", "label": "Villages and local communities", "icon": "fa-house-chimney"},
            {"id": "architecture_photo", "label": "Architecture and photography spots", "icon": "fa-building-columns"}
        ]
    },
    "q15": {
        "id": "q15",
        "section": "sec_3",
        "tier": "detailed",
        "question": "Which activities would you enjoy on a trip?",
        "type": "multi",
        "options": [
            {"id": "walking_tours", "label": "Walking tours"},
            {"id": "hiking_trekking", "label": "Hiking or trekking"},
            {"id": "cycling", "label": "Cycling"},
            {"id": "water_sports", "label": "Water sports"},
            {"id": "wildlife_experiences", "label": "Wildlife experiences"},
            {"id": "food_tours", "label": "Cooking or food tours"},
            {"id": "museum_tours", "label": "Museums and guided tours"},
            {"id": "cultural_workshops", "label": "Cultural workshops"},
            {"id": "shopping_crafts", "label": "Shopping & local crafts"},
            {"id": "spa_resort", "label": "Relaxing at a spa or resort"},
            {"id": "festivals_events", "label": "Festivals and events"},
            {"id": "nightlife_fun", "label": "Nightlife"},
            {"id": "unfamiliar_exp", "label": "Trying unfamiliar experiences"}
        ]
    },
    "q16": {
        "id": "q16",
        "section": "sec_3",
        "tier": "detailed",
        "question": "Any hobbies or personal interests you want incorporated? (e.g., photography, birdwatching, books)",
        "type": "text"
    },
    "q17": {
        "id": "q17",
        "section": "sec_3",
        "tier": "basic",
        "question": "What kinds of experiences do you generally prefer?",
        "type": "single",
        "options": [
            {"id": "popular_landmarks", "label": "Popular attractions and famous landmarks"},
            {"id": "hidden_gems", "label": "Lesser-known local places (hidden gems)"},
            {"id": "balanced_mix", "label": "A mixture of popular and hidden places"},
            {"id": "authentic_local", "label": "Authentic local experiences"},
            {"id": "unique_unusual", "label": "Unique or unusual experiences"},
            {"id": "quiet_uncrowded", "label": "Quiet, less crowded places"}
        ]
    },
    "q18": {
        "id": "q18",
        "section": "sec_3",
        "tier": "detailed",
        "question": "Are there activities, places, or experiences you prefer NOT to receive recommendations for?",
        "type": "text"
    },
    "q19": {
        "id": "q19",
        "section": "sec_3",
        "tier": "detailed",
        "question": "How much time do you like to spend at each attraction?",
        "type": "single",
        "options": [
            {"id": "quick", "label": "Quick visits to see several places"},
            {"id": "moderate", "label": "A moderate amount of time at each place"},
            {"id": "longer_deep", "label": "Longer visits with time to explore deeply"},
            {"id": "depends_attraction", "label": "It depends on the attraction"}
        ]
    },

    # --- Section 4: Food, Diet and Daily Lifestyle ---
    "q20": {
        "id": "q20",
        "section": "sec_4",
        "tier": "basic",
        "question": "Which dietary preferences or restrictions should the assistant consider?",
        "type": "multi",
        "options": [
            {"id": "none", "label": "No restrictions"},
            {"id": "vegetarian", "label": "Vegetarian"},
            {"id": "vegan", "label": "Vegan"},
            {"id": "jain", "label": "Jain"},
            {"id": "halal", "label": "Halal"},
            {"id": "kosher", "label": "Kosher"},
            {"id": "gluten_free", "label": "Gluten-Free"},
            {"id": "lactose_free", "label": "Lactose-Free"}
        ]
    },
    "q21": {
        "id": "q21",
        "section": "sec_4",
        "tier": "detailed",
        "question": "What kind of food do you usually prefer while travelling?",
        "type": "single",
        "options": [
            {"id": "local_cuisine", "label": "Local cuisine"},
            {"id": "familiar_food", "label": "Familiar food from home"},
            {"id": "street_food", "label": "Street food"},
            {"id": "healthy_light", "label": "Healthy or light meals"},
            {"id": "fine_dining", "label": "Fine dining"},
            {"id": "budget_friendly", "label": "Budget-friendly meals"},
            {"id": "mix_cuisines", "label": "A mixture of different cuisines"}
        ]
    },
    "q22": {
        "id": "q22",
        "section": "sec_4",
        "tier": "detailed",
        "question": "How do you usually manage meals while travelling?",
        "type": "single",
        "options": [
            {"id": "restaurants", "label": "Eat at restaurants"},
            {"id": "cafes_fast", "label": "Prefer cafés and quick-service food"},
            {"id": "cook_own", "label": "Cook my own meals"},
            {"id": "groceries_ready", "label": "Buy groceries and ready-to-eat food"},
            {"id": "mix_all", "label": "Mix restaurants, groceries, and cooking"}
        ]
    },
    "q23": {
        "id": "q23",
        "section": "sec_4",
        "tier": "detailed",
        "question": "How important is it to find food that matches your preferences?",
        "type": "single",
        "options": [
            {"id": "optional_experiment", "label": "Optional — I am happy to experiment."},
            {"id": "somewhat", "label": "Somewhat important."},
            {"id": "important", "label": "Important — I prefer suitable options at every meal."},
            {"id": "essential", "label": "Essential — dietary restrictions make this a necessity."}
        ]
    },
    "q24": {
        "id": "q24",
        "section": "sec_4",
        "tier": "detailed",
        "question": "What would you like the assistant to do when suitable food is difficult to find?",
        "type": "single",
        "options": [
            {"id": "find_restaurants", "label": "Find nearby restaurants meeting my requirements."},
            {"id": "find_groceries", "label": "Find grocery shops with suitable ingredients."},
            {"id": "suggest_alternatives", "label": "Suggest familiar or alternative cuisines."},
            {"id": "kitchen_stays", "label": "Identify accommodation with cooking facilities."},
            {"id": "multiple_options", "label": "Provide several alternatives and let me choose."}
        ]
    },
    "q25": {
        "id": "q25",
        "section": "sec_4",
        "tier": "detailed",
        "question": "Do you have any specific food habits? (e.g. meal times, spicy food tolerance, eating early)",
        "type": "text"
    },

    # --- Section 5: Weather, Clothing and Environmental Preferences ---
    "q26": {
        "id": "q26",
        "section": "sec_5",
        "tier": "basic",
        "question": "Which temperatures do you generally feel most comfortable in?",
        "type": "single",
        "options": [
            {"id": "cold", "label": "Cold weather"},
            {"id": "cool", "label": "Cool weather"},
            {"id": "mild", "label": "Mild weather"},
            {"id": "warm", "label": "Warm weather"},
            {"id": "hot", "label": "Hot weather"},
            {"id": "adapt_easily", "label": "I adapt easily to most temperatures"}
        ]
    },
    "q27": {
        "id": "q27",
        "section": "sec_5",
        "tier": "detailed",
        "question": "How do you usually react to uncomfortable weather?",
        "type": "single",
        "options": [
            {"id": "tolerate_easily", "label": "I can tolerate it without much difficulty."},
            {"id": "uncomfortable_later", "label": "I become uncomfortable after some time."},
            {"id": "affects_activities", "label": "It significantly affects my activities."},
            {"id": "avoid_activities", "label": "I prefer to avoid activities in such conditions."},
            {"id": "depends_weather", "label": "It depends on the weather and activity."}
        ]
    },
    "q28": {
        "id": "q28",
        "section": "sec_5",
        "tier": "detailed",
        "question": "Which conditions would you want the assistant to alert you about?",
        "type": "multi",
        "options": [
            {"id": "strong_winds", "label": "Strong winds"},
            {"id": "heavy_rain", "label": "Heavy rain"},
            {"id": "cold_temperatures", "label": "Cold temperatures"},
            {"id": "heatwaves", "label": "Heatwaves"},
            {"id": "snow_ice", "label": "Snow or icy paths"},
            {"id": "high_humidity", "label": "High humidity"},
            {"id": "strong_uv", "label": "Strong sunlight or UV"},
            {"id": "poor_air", "label": "Poor air quality"},
            {"id": "thunderstorms", "label": "Thunderstorms"},
            {"id": "unexpected_changes", "label": "Unexpected weather changes"}
        ]
    },
    "q29": {
        "id": "q29",
        "section": "sec_5",
        "tier": "detailed",
        "question": "What are your usual packing habits?",
        "type": "single",
        "options": [
            {"id": "pack_too_much", "label": "I often pack too much."},
            {"id": "forget_essentials", "label": "I often forget essential items."},
            {"id": "only_essentials", "label": "I pack only the essentials."},
            {"id": "checklist", "label": "I pack according to a checklist."},
            {"id": "well_prepared", "label": "I am generally well prepared."}
        ]
    },
    "q30": {
        "id": "q30",
        "section": "sec_5",
        "tier": "detailed",
        "question": "What should the packing assistant prioritize?",
        "type": "single",
        "options": [
            {"id": "avoid_forgotten", "label": "Avoiding forgotten essentials"},
            {"id": "weather_comfort", "label": "Staying comfortable in different weather"},
            {"id": "lightweight", "label": "Keeping luggage lightweight"},
            {"id": "activity_prep", "label": "Preparing for planned activities"},
            {"id": "health_needs", "label": "Packing health-related necessities"},
            {"id": "balance_all", "label": "A balance of all these factors"}
        ]
    },
    "q31": {
        "id": "q31",
        "section": "sec_5",
        "tier": "detailed",
        "question": "Any clothing preferences or cultural requirements? (e.g. modest clothing, comfortable shoes)",
        "type": "text"
    },

    # --- Section 6: Budget, Accommodation and Transport ---
    "q32": {
        "id": "q32",
        "section": "sec_6",
        "tier": "basic",
        "question": "How would you describe your typical travel budget?",
        "type": "single",
        "options": [
            {"id": "very_budget", "label": "Very budget-conscious (Shoestring)"},
            {"id": "budget", "label": "Budget traveller"},
            {"id": "mid_range", "label": "Mid-range (Balanced)"},
            {"id": "premium", "label": "Premium / Boutique"},
            {"id": "luxury", "label": "Luxury"}
        ]
    },
    "q33": {
        "id": "q33",
        "section": "sec_6",
        "tier": "detailed",
        "question": "Where are you willing to spend more for comfort or convenience? (Select up to 3)",
        "type": "multi",
        "max": 3,
        "options": [
            {"id": "accommodation", "label": "Accommodation"},
            {"id": "food_dining", "label": "Food & dining"},
            {"id": "transport", "label": "Transport (faster/direct)"},
            {"id": "guided_activities", "label": "Guided activities"},
            {"id": "safety_convenience", "label": "Safety and convenience"},
            {"id": "unique_experiences", "label": "Unique experiences"},
            {"id": "minimize_all", "label": "I prefer minimizing costs across everything"}
        ]
    },
    "q34": {
        "id": "q34",
        "section": "sec_6",
        "tier": "detailed",
        "question": "What type of accommodation do you prefer?",
        "type": "single",
        "options": [
            {"id": "hostels", "label": "Hostels & Guesthouses"},
            {"id": "budget_hotels", "label": "Budget hotels"},
            {"id": "mid_range_hotels", "label": "Mid-range hotels"},
            {"id": "resorts", "label": "Premium hotels or luxury resorts"},
            {"id": "apartments", "label": "Rental apartments / Airbnb"},
            {"id": "homestays", "label": "Homestays"},
            {"id": "no_preference", "label": "No fixed preference"}
        ]
    },
    "q35": {
        "id": "q35",
        "section": "sec_6",
        "tier": "detailed",
        "question": "Which transportation options do you generally prefer?",
        "type": "single",
        "options": [
            {"id": "walking", "label": "Walking everywhere"},
            {"id": "public_transit", "label": "Public transport (Metro, Bus, Tram)"},
            {"id": "taxi_rideshare", "label": "Taxi or ride-hailing (Uber/Grab)"},
            {"id": "rental_car", "label": "Rental car / Scooter"},
            {"id": "trains", "label": "High-speed and scenic trains"},
            {"id": "mix_convenience", "label": "A combination, depending on convenience"}
        ]
    },
    "q36": {
        "id": "q36",
        "section": "sec_6",
        "tier": "detailed",
        "question": "What are your biggest practical travel concerns? (Select up to 3)",
        "type": "multi",
        "max": 3,
        "options": [
            {"id": "unexpected_expenses", "label": "Unexpected expenses"},
            {"id": "long_travel_times", "label": "Long travel times"},
            {"id": "missing_connections", "label": "Missing connections"},
            {"id": "safety", "label": "Safety"},
            {"id": "difficult_navigation", "label": "Difficult navigation"},
            {"id": "heavy_luggage", "label": "Heavy luggage"},
            {"id": "limited_food", "label": "Limited food options"},
            {"id": "language_barriers", "label": "Language barriers"},
            {"id": "changes_to_plans", "label": "Changes to plans"}
        ]
    },

    # --- Section 7: Travel Documents and Essentials ---
    "q37": {
        "id": "q37",
        "section": "sec_7",
        "tier": "detailed",
        "question": "Which parts of travel preparation do you usually need help with?",
        "type": "multi",
        "options": [
            {"id": "visa_passports", "label": "Passport, visa, and entry requirements"},
            {"id": "tickets_passes", "label": "Tickets and boarding passes"},
            {"id": "insurance", "label": "Travel insurance"},
            {"id": "local_transit", "label": "Local transport arrangements"},
            {"id": "currency_cards", "label": "Currency and payment methods"},
            {"id": "sim_data", "label": "SIM card or roaming data"},
            {"id": "adapters", "label": "Electrical adapters"},
            {"id": "meds_health", "label": "Medicines and health essentials"},
            {"id": "none", "label": "None — I manage independently"}
        ]
    },
    "q38": {
        "id": "q38",
        "section": "sec_7",
        "tier": "detailed",
        "question": "How would you like the assistant to help with important travel reminders?",
        "type": "single",
        "options": [
            {"id": "checklist_departure", "label": "Give me a complete checklist before departure."},
            {"id": "timely_reminders", "label": "Remind me at appropriate times."},
            {"id": "critical_only", "label": "Prioritize only critical reminders."},
            {"id": "customizable", "label": "Let me choose which reminders I receive."}
        ]
    },
    "q39": {
        "id": "q39",
        "section": "sec_7",
        "tier": "detailed",
        "question": "What essentials do you tend to forget or worry about? (e.g. chargers, adapters, medicines)",
        "type": "text"
    },

    # --- Section 8: Behaviour and Decision-Making ---
    "q40": {
        "id": "q40",
        "section": "sec_8",
        "tier": "detailed",
        "question": "When presented with several travel options, how do you usually choose?",
        "type": "single",
        "options": [
            {"id": "cheapest", "label": "I select the cheapest option."},
            {"id": "convenient", "label": "I select the most convenient option."},
            {"id": "reviews_ratings", "label": "I compare reviews and ratings."},
            {"id": "personal_interests", "label": "I choose based on personal interests."},
            {"id": "safety_comfort", "label": "I prioritize safety and comfort."},
            {"id": "assistant_narrow", "label": "I prefer the assistant to narrow the options down."}
        ]
    },
    "q41": {
        "id": "q41",
        "section": "sec_8",
        "tier": "basic",
        "question": "How much independence do you want when making travel decisions?",
        "type": "single",
        "options": [
            {"id": "make_all_myself", "label": "I want to make every decision myself."},
            {"id": "choose_independently", "label": "I want recommendations but will choose independently."},
            {"id": "shortlist_explain", "label": "I want the assistant to shortlist and explain the best options."},
            {"id": "suggest_confirm", "label": "I want it to suggest a preferred option and ask for confirmation."},
            {"id": "handle_routine", "label": "I want it to handle routine planning within limits I define."}
        ]
    },
    "q42": {
        "id": "q42",
        "section": "sec_8",
        "tier": "detailed",
        "question": "How proactive should the assistant be?",
        "type": "single",
        "options": [
            {"id": "only_when_asked", "label": "Only respond when I ask."},
            {"id": "relevant_suggestions", "label": "Offer suggestions when relevant."},
            {"id": "notify_opportunities", "label": "Notify me when a useful opportunity or problem arises."},
            {"id": "alert_immediately", "label": "Alert me immediately about important changes."},
            {"id": "adapt_situation", "label": "Adapt the level of assistance to the situation."}
        ]
    },
    "q43": {
        "id": "q43",
        "section": "sec_8",
        "tier": "detailed",
        "question": "Which situations justify an unsolicited alert?",
        "type": "multi",
        "options": [
            {"id": "severe_weather", "label": "Dangerous or severely uncomfortable weather"},
            {"id": "missing_docs", "label": "Missing documents or preparation"},
            {"id": "transport_disruption", "label": "Transport disruption"},
            {"id": "attraction_closures", "label": "Attraction closures"},
            {"id": "booking_changes", "label": "Important booking changes"},
            {"id": "suitable_food_nearby", "label": "Suitable food or essential supplies nearby"},
            {"id": "cost_savings", "label": "An opportunity to avoid unnecessary spending"},
            {"id": "better_activity", "label": "A better activity based on current conditions"},
            {"id": "urgent_only", "label": "Only urgent or high-priority situations"}
        ]
    },
    "q44": {
        "id": "q44",
        "section": "sec_8",
        "tier": "detailed",
        "question": "How should the assistant handle uncertainty?",
        "type": "single",
        "options": [
            {"id": "show_source", "label": "Show the available information and its source."},
            {"id": "explain_uncertainty", "label": "Explain what is uncertain and suggest verification."},
            {"id": "conservative_choice", "label": "Recommend a conservative option when consequences could be serious."},
            {"id": "avoid_recommendation", "label": "Avoid making a recommendation if reliable info is unavailable."}
        ]
    },
    "q45": {
        "id": "q45",
        "section": "sec_8",
        "tier": "detailed",
        "question": "If you ignore or reject a recommendation, what should the assistant do?",
        "type": "single",
        "options": [
            {"id": "offer_different", "label": "Offer a different option."},
            {"id": "ask_why", "label": "Ask me why."},
            {"id": "leave_alone", "label": "Leave the decision alone."},
            {"id": "learn_gradually", "label": "Learn gradually from repeated feedback, while allowing me to correct it."}
        ]
    },
    "q46": {
        "id": "q46",
        "section": "sec_8",
        "tier": "detailed",
        "question": "How often would you like updates during a trip?",
        "type": "single",
        "options": [
            {"id": "only_important", "label": "Only when something important changes"},
            {"id": "before_activity", "label": "Once before each major activity"},
            {"id": "morning_briefing", "label": "A morning briefing each day"},
            {"id": "periodic_day", "label": "Periodic updates throughout the day"}
        ]
    },

    # --- Section 9: Trust and Boundaries ---
    "q47": {
        "id": "q47",
        "section": "sec_9",
        "tier": "detailed",
        "question": "Which information are you comfortable saving in your travel profile?",
        "type": "multi",
        "options": [
            {"id": "interests_hobbies", "label": "Interests and hobbies"},
            {"id": "travel_prefs", "label": "Travel and activity preferences"},
            {"id": "dietary_needs", "label": "Dietary preferences"},
            {"id": "accessibility_needs", "label": "Accessibility needs"},
            {"id": "env_sensitivities", "label": "Environmental sensitivities"},
            {"id": "budget_prefs", "label": "Budget preferences"},
            {"id": "health_travel_needs", "label": "Relevant health-related travel needs"},
            {"id": "trip_feedback", "label": "Previous trip feedback"}
        ]
    },
    "q48": {
        "id": "q48",
        "section": "sec_9",
        "tier": "detailed",
        "question": "Would you like the assistant to remember preferences from previous trips?",
        "type": "single",
        "options": [
            {"id": "yes_auto", "label": "Yes, automatically for future recommendations"},
            {"id": "yes_ask_first", "label": "Yes, but ask before saving new preferences"},
            {"id": "current_trip_only", "label": "Only for the current trip"},
            {"id": "no", "label": "No"}
        ]
    },
    "q49": {
        "id": "q49",
        "section": "sec_9",
        "tier": "detailed",
        "question": "What would make you trust a travel recommendation? (Select up to 3)",
        "type": "multi",
        "max": 3,
        "options": [
            {"id": "reliable_info", "label": "Reliable and current information"},
            {"id": "clear_explanation", "label": "Clear explanation of why it is recommended"},
            {"id": "source_links", "label": "Source links"},
            {"id": "user_reviews", "label": "User reviews"},
            {"id": "transparent_pricing", "label": "Transparent pricing"},
            {"id": "preference_alignment", "label": "Recommendations tailored to my preferences"},
            {"id": "correct_reject", "label": "Ability to correct or reject recommendations"}
        ]
    },
    "q50": {
        "id": "q50",
        "section": "sec_9",
        "tier": "detailed",
        "question": "What information would you prefer NOT to share or have remembered?",
        "type": "text"
    },
    "q51": {
        "id": "q51",
        "section": "sec_9",
        "tier": "detailed",
        "question": "Would you like to review, edit, or delete saved profile information anytime?",
        "type": "single",
        "options": [
            {"id": "yes", "label": "Yes"},
            {"id": "no_preference", "label": "No preference"}
        ]
    },

    # --- Section 10: Final Open Personalization ---
    "q52": {
        "id": "q52",
        "section": "sec_10",
        "tier": "detailed",
        "question": "Describe your ideal travel experience in a few sentences.",
        "type": "text"
    },
    "q53": {
        "id": "q53",
        "section": "sec_10",
        "tier": "detailed",
        "question": "What frequently ruins or reduces your enjoyment of a trip?",
        "type": "text"
    },
    "q54": {
        "id": "q54",
        "section": "sec_10",
        "tier": "detailed",
        "question": "What is one thing you wish a travel assistant understood without you asking every time?",
        "type": "text"
    },
    "q55": {
        "id": "q55",
        "section": "sec_10",
        "tier": "detailed",
        "question": "If the assistant could prevent three problems on every trip, which three would you choose?",
        "type": "text"
    },
    "q56": {
        "id": "q56",
        "section": "sec_10",
        "tier": "detailed",
        "question": "Anything else about your preferences, routines, or travel style to help recommendations?",
        "type": "text"
    }
}

# The basic 30-60 second questionnaire flow is mapped to these core questions:
BASIC_QUESTION_IDS = ["q1", "q2", "q3", "q4", "q5", "q14", "q17", "q20", "q26", "q32", "q41"]
