# Questionnaire Data Dictionary & Field Specification

**Schema Version:** `2.0.0`  
**Country Scope:** `IN` (Republic of India)  
**Currency:** `INR` (₹)  
**Total Questions:** 39 (12 Basic + 27 Deep)  
**Single Source of Truth:** `app/data/questionnaire_schema.json`  

---

## 1. Overview and Architectural Principles

### 1.1 India-Centric Scope
This questionnaire redesign tailors the travel recommendation and proactive planning pipeline to the realities of Indian domestic travel:
- **Geographic and Cultural Nuances:** Himalayan high-altitude acclimatization (Ladakh, Spiti), Western Ghats and North-East monsoon patterns and landslide advisories, coastal and tropical humidity, and desert heat.
- **Dietary Realities:** Fine-grained support for Indian dietary traditions: Pure Vegetarian (separate kitchen/utensils), Jain (no onion/garlic/potato/root vegetables), Eggetarian, Halal, Vegan, and Regional Cuisines.
- **Transit Infrastructure:** Indian Railways hierarchy (Vande Bharat Express, 1A/2A/3A AC sleepers, Sleeper class), chauffeur-driven hired tourist cabs vs. tricky ghat self-drives, intercity Volvo buses, and local autorickshaws.
- **Currency and Cost Bands:** Indicative daily spend per person in Indian Rupees (INR): Budget (<₹2,500/day), Mid-Range (₹2,500–₹6,000/day), Premium (₹6,000–₹15,000/day), and Luxury (>₹15,000/day).
- **Safety and Demographics:** Solo women traveler safety preferences (verified homestays, daytime station arrivals), multi-generational family dynamics (child-safe pacing, senior citizen stairs and temple terrain accessibility).

### 1.2 Deduplication and Coarse-to-Fine Progression
- **Basic Tier (12 Questions, 3 Steps):** Fast 60-second baseline capturing high-level demographic, style, budget, dietary, and interest requirements.
- **Deep Tier (27 Questions, 8 Sections):** Targeted follow-ups that refine basic concepts using `refines` and `prefill_from`. A user is never asked the same question twice; coarse answers prefill editable fine-grained options.
- **Zero Concept Duplication:** Every biological, logistical, or comfort concept has exactly one canonical definition.

### 1.3 Model-Agnostic Features
Stored answers are completely decoupled from any single machine learning algorithm:
- **LinUCB Context:** Continuous vectors in $[0, 1]$ with constraint masks (`is_constraint_mask: true`) for hard restrictions (allergens, severe mobility, Jain diet).
- **Ranking & Filtering:** Multi-hot and categorical flags matched directly against destination tags.
- **Tabular ML / Scikit-Learn:** Deterministic one-hot and normalized numerical feature dictionaries.
- **LLM Prompts:** Structured system context strings ready for immediate injection into prompt templates.

---

## 2. Master Data Dictionary Table

| ID | Legacy ID | Concept | Tier | Type | Options / Range | Prefill From | Model Features & Encoding | Consumers | Hard Constraint / Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `b01_age` | `q1` | `demographics.age` | Basic | `single` | `18_24`<br>`25_34`<br>`35_49`<br>`50_64`<br>*(+1 more)* | — | onehot: `age_18_24`, `age_25_34`, `age_35_49` (+2) | recommender, rl_context, summary | Standard preference |
| `b02_home_region` | `b02` | `origin.home_region` | Basic | `single` | `north_india`<br>`west_india`<br>`south_india`<br>`east_india`<br>*(+2 more)* | — | onehot: `origin_north`, `origin_west`, `origin_south` (+3) | recommender, summary | Standard preference |
| `b03_companions` | `q3` | `party.composition` | Basic | `single` | `solo`<br>`partner_couple`<br>`friends`<br>`family_kids`<br>*(+1 more)* | — | onehot: `companion_solo`, `companion_couple`, `companion_friends` (+2) | recommender, rl_context, itinerary, summary | Standard preference |
| `b04_experience` | `q2` | `travel.experience` | Basic | `single` | `first_time`<br>`occasional`<br>`frequent`<br>`veteran_explorer` | — | ordinal_0_1 (`b04_experience`) | recommender, rl_context, summary | Standard preference |
| `b05_travel_goals` | `q5` | `interests.primary_goals` | Basic | `multi` | `heritage_history`<br>`spiritual_pilgrimage`<br>`nature_wildlife`<br>`adventure_trekking`<br>*(+3 more)* | — | multihot: `goal_heritage`, `goal_spiritual`, `goal_nature` (+4) | recommender, rl_context, ranking, summary | Standard preference |
| `b06_place_interests` | `q14` | `interests.landscapes` | Basic | `multi` | `himalayan_mountains`<br>`beaches_coastal`<br>`royal_forts_palaces`<br>`holy_temple_ghats`<br>*(+3 more)* | — | multihot: `place_himalayas`, `place_beaches`, `place_forts` (+4) | recommender, rl_context, ranking, summary | Standard preference |
| `b07_pace` | `q17` | `trip.pacing` | Basic | `single` | `relaxed_1_2`<br>`balanced_2_3`<br>`packed_all_day` | — | ordinal_0_1 (`b07_pace`) | recommender, rl_context, itinerary, summary | Standard preference |
| `b08_crowd_tolerance` | `crowd` | `comfort.crowd_level` | Basic | `single` | `prefer_quiet_secluded`<br>`moderate_crowds_fine`<br>`love_bustling_festive` | — | ordinal_0_1 (`b08_crowd_tolerance`) | recommender, rl_context, summary | Standard preference |
| `b09_dietary` | `q20` | `food.diet_preference` | Basic | `multi` | `pure_veg`<br>`jain`<br>`eggetarian`<br>`non_veg`<br>*(+3 more)* | — | multihot: `diet_veg`, `diet_jain`, `diet_eggetarian` (+4) | recommender, itinerary, prep, summary | **Strict restaurant filtering** |
| `b10_budget` | `q32` | `budget.daily_tier` | Basic | `single` | `budget_backpacker`<br>`mid_range_comfortable`<br>`premium_luxury` | — | ordinal_0_1 (`b10_budget`) | recommender, rl_context, ranking, summary | Standard preference |
| `b11_climate` | `q26` | `climate.comfort_zone` | Basic | `single` | `cold_himalayan`<br>`cool_hillstation`<br>`moderate_pleasant`<br>`warm_tropical` | — | onehot: `clim_cold`, `clim_cool`, `clim_moderate` (+1) | recommender, rl_context, summary | Standard preference |
| `b12_autonomy` | `q41` | `ai.assistance_level` | Basic | `single` | `full_curated_schedule`<br>`shortlist_with_explanations`<br>`on_demand_advice_only` | — | ordinal_0_1 (`b12_autonomy`) | recommender, rl_context, summary | Standard preference |
| `d01_solo_safety` | `—` | `party.solo_safety_preference` | Deep | `single` | `always_prefer_verified`<br>`appreciate_options`<br>`neutral` | `b03_companions` | onehot: `solo_safety_strict`, `solo_safety_flexible`, `solo_safety_neutral` | itinerary, prep, summary | **Daylight arrival scheduling** |
| `d02_children_age_group` | `q64` | `party.child_age_bracket` | Deep | `single` | `infant_under_2`<br>`toddler_2_5`<br>`child_6_12`<br>`teen_13_17` | `b03_companions` | ordinal_0_1 (`d02_children_age_group`) | itinerary, prep, summary | Standard preference |
| `d03_senior_accessibility` | `—` | `party.senior_mobility_needs` | Deep | `single` | `essential_step_free`<br>`moderate_stairs_fine`<br>`fully_active_elders` | `b03_companions` | ordinal_0_1 (`d03_senior_accessibility`) | itinerary, prep, summary | Standard preference |
| `d04_languages` | `—` | `communication.languages` | Deep | `multi` | `hindi`<br>`english`<br>`bengali`<br>`tamil`<br>*(+4 more)* | — | multihot: `lang_hindi`, `lang_english`, `lang_bengali` (+5) | summary | Standard preference |
| `d05_monsoon_rain` | `q81` | `climate.monsoon_rain_tolerance` | Deep | `scale` | Scale 1–5 (`Head indoors immediately` to `Love the rain, keep exploring`) | `b11_climate` | numeric_normalised (`d05_monsoon_rain`) | prep, itinerary, summary | Standard preference |
| `d06_high_altitude` | `—` | `climate.himalayan_altitude_comfort` | Deep | `scale` | Scale 1–5 (`Sensitive to altitude` to `Acclimatize easily & thrive`) | `b11_climate` | numeric_normalised (`d06_high_altitude`) | recommender, prep, itinerary, summary | **Mandatory 48h rest rule** |
| `d07_heat_humidity` | `q79` | `climate.heat_humidity_tolerance` | Deep | `scale` | Scale 1–5 (`Exhausted quickly` to `Handle heat very well`) | `b11_climate` | numeric_normalised (`d07_heat_humidity`) | prep, itinerary, summary | Standard preference |
| `d08_winter_cold` | `q78` | `climate.cold_snow_tolerance` | Deep | `scale` | Scale 1–5 (`Dislike cold intensely` to `Thrive in snow & cold`) | `b11_climate` | numeric_normalised (`d08_winter_cold`) | prep, itinerary, summary | Standard preference |
| `d09_spice_tolerance` | `q91` | `food.spice_tolerance` | Deep | `scale` | Scale 1–5 (`Mild / zero chili` to `Love authentic spicy desi food`) | `b09_dietary` | numeric_normalised (`d09_spice_tolerance`) | itinerary, prep, summary | Standard preference |
| `d10_street_food` | `q92` | `food.street_food_interest` | Deep | `scale` | Scale 1–5 (`Only seated hygienic restaurants` to `Eager street food explorer`) | — | numeric_normalised (`d10_street_food`) | itinerary, summary | Standard preference |
| `d11_food_allergens` | `q95` | `health.food_allergies` | Deep | `multi` | `peanuts`<br>`tree_nuts`<br>`lactose_dairy`<br>`gluten_wheat`<br>*(+4 more)* | — | multihot: `allergen_peanuts`, `allergen_tree_nuts`, `allergen_dairy` (+4) | itinerary, prep, summary | **Hard food safety constraint** |
| `d12_regional_cuisines` | `q101` | `food.regional_traditions` | Deep | `multi` | `mughlai_awadhi`<br>`rajasthani_dalbaati`<br>`kerala_coastal`<br>`pahadi_himachali`<br>*(+3 more)* | — | multihot: `cuisine_mughlai`, `cuisine_rajasthani`, `cuisine_kerala` (+4) | itinerary, summary | Standard preference |
| `d13_train_class` | `—` | `transport.train_class` | Deep | `single` | `vande_bharat_executive`<br>`ac_first_class`<br>`ac_2_tier`<br>`ac_3_tier`<br>*(+2 more)* | — | onehot: `train_vande_bharat`, `train_1a`, `train_2a` (+3) | prep, itinerary, summary | Standard preference |
| `d14_road_transit` | `q35` | `transport.road_mode` | Deep | `single` | `chauffeur_hired_cab`<br>`self_drive_rental`<br>`volvo_overnight_bus`<br>`local_autos_taxis` | — | onehot: `road_hired_cab`, `road_self_drive`, `road_volvo_bus` (+1) | itinerary, summary | Standard preference |
| `d15_motion_sickness` | `q104` | `health.motion_sensitivity` | Deep | `multi` | `winding_mountain_roads`<br>`boats_ferries`<br>`none` | — | multihot: `nausea_ghat_roads`, `nausea_boats`, `nausea_none` | prep, itinerary, summary | Standard preference |
| `d16_early_starts` | `q75` | `trip.early_starts_comfort` | Deep | `scale` | Scale 1–5 (`Prefer sleeping in, starts after 9 AM` to `Happy to rise before dawn for magic light`) | `b07_pace` | numeric_normalised (`d16_early_starts`) | itinerary, summary | Standard preference |
| `d17_stay_types` | `q34` | `stay.preferred_style` | Deep | `single` | `heritage_haveli_palace`<br>`boutique_plantation_homestay`<br>`ashram_wellness_retreat`<br>`comfortable_city_hotel`<br>*(+2 more)* | `b10_budget` | onehot: `stay_heritage`, `stay_homestay`, `stay_ashram` (+3) | itinerary, summary | Standard preference |
| `d18_stay_amenities` | `—` | `stay.essential_amenities` | Deep | `multi` | `power_backup_generator`<br>`room_heating_geyser`<br>`high_speed_wifi`<br>`pure_veg_kitchen`<br>*(+1 more)* | — | multihot: `amenity_power_backup`, `amenity_heating`, `amenity_wifi` (+2) | summary | Standard preference |
| `d19_daily_walking_km` | `q73` | `physical.daily_walking_capacity_km` | Deep | `number` | 1–20 km | `b07_pace` | numeric_normalised (`d19_daily_walking_km`) | rl_context, itinerary, summary | Standard preference |
| `d20_temple_stairs_terrain` | `q74` | `physical.stairs_and_uneven_terrain` | Deep | `scale` | Scale 1–5 (`Need flat terrain / lifts` to `Love climbing steep fort steps`) | — | numeric_normalised (`d20_temple_stairs_terrain`) | itinerary, prep, summary | Standard preference |
| `d21_medical_logistics` | `q103` | `health.medical_logistics` | Deep | `multi` | `needs_refrigeration`<br>`prescription_meds`<br>`sensitive_to_dust`<br>`no_medical_logistics` | — | multihot: `med_refrigeration`, `med_prescription`, `med_dust_asthma` (+1) | prep, summary | Standard preference |
| `d22_avoidances` | `q12` | `experience.avoidances` | Deep | `multi` | `avoid_strenuous_hikes`<br>`avoid_extreme_heights`<br>`avoid_crowded_clubs`<br>`avoid_early_starts`<br>*(+2 more)* | — | multihot: `avoid_hikes`, `avoid_heights`, `avoid_clubs` (+3) | recommender, rl_context, itinerary, summary | Standard preference |
| `d23_cultural_depth` | `q107` | `interests.cultural_depth` | Deep | `single` | `deep_historical_guide`<br>`mythology_temple_rituals`<br>`crafts_and_artisans`<br>`scenic_photo_overview` | `b05_travel_goals` | onehot: `cult_deep_history`, `cult_mythology`, `cult_crafts` (+1) | itinerary, summary | Standard preference |
| `d24_permits` | `—` | `trip.permit_willingness` | Deep | `single` | `happy_to_organize`<br>`prefer_hassle_free` | — | ordinal_0_1 (`d24_permits`) | recommender, prep, summary | Standard preference |
| `d25_budget_flexibility` | `q125` | `budget.flexibility_scale` | Deep | `scale` | Scale 1–5 (`Strict hard cap, never exceed` to `Very flexible for once-in-a-lifetime moments`) | `b10_budget` | numeric_normalised (`d25_budget_flexibility`) | rl_context, summary | Standard preference |
| `d26_proactivity` | `q42` | `ai.proactivity_level` | Deep | `scale` | Scale 1–5 (`Quiet, only answer when asked` to `Proactive alerts for events, delays & weather`) | `b12_autonomy` | numeric_normalised (`d26_proactivity`) | live, summary | Standard preference |
| `d27_privacy_saving` | `q47` | `privacy.storage_consent` | Deep | `multi` | `travel_prefs`<br>`dietary_needs`<br>`health_accessibility`<br>`budget_comfort` | — | multihot: `priv_prefs`, `priv_diet`, `priv_health` (+1) | summary | Standard preference |

---

## 3. Section Hierarchy

### Basic Sections (Onboarding)
- **`b_sec_1` - Traveller Profile & Party:** Basic details about who is travelling and your travel style
- **`b_sec_2` - Interests, Landscapes & Rhythm:** What you love exploring and your preferred trip pace
- **`b_sec_3` - Dining, Budget & Comfort:** Food preferences, comfort zone and daily budget in India

### Deep Sections (Personalisation)
- **`d_sec_1` - Party & Personal Comfort:** Safety, accessibility, and party-specific details
- **`d_sec_2` - Terrain, Weather & Altitude:** Tolerance for monsoon rains, Himalayan heights, and weather extremes
- **`d_sec_3` - Dining, Spice & Regional Food:** Spice comfort, street food appetite, and food allergies
- **`d_sec_4` - Transport & Long-Distance Transit:** Train classes, road transit, and mountain road comfort
- **`d_sec_5` - Stays & Hospitality Styles:** Havelis, homestays, ashrams, and essential room amenities
- **`d_sec_6` - Physical Capacity & Walking:** Daily walking distance, temple steps, and health items
- **`d_sec_7` - Avoidances, Permits & Culture:** Things to exclude, paperwork comfort, and depth of cultural history
- **`d_sec_8` - Planning Autonomy & Privacy:** Budget flexibility, companion proactivity, and data saving preferences

---

## 4. API & Integration Endpoints

The questionnaire system provides four dedicated endpoints for client apps and models:

### 1. `GET /api/config/questionnaire-schema`
Returns the complete single-source-of-truth JSON schema specification (version 2.0.0).

### 2. `GET /api/profile/{user_id}/features?format=named|vector|onehot`
Returns numerical feature extraction for user answers:
- `format=named`: Dict of `{"feature_name": float_value}`.
- `format=vector`: Ordered float array and corresponding feature names list.
- `format=onehot`: Sparse dictionary containing one-hot indicator variables.

### 3. `GET /api/profile/{user_id}/export`
Returns a complete, model-agnostic profile export with standardized answers, normalized features, active hard constraints, and formatted LLM system prompt context.

### 4. `GET /api/profile/{user_id}/summary`
Returns structured narrative breakdown covering travel party, climate/terrain, food/diet, transit/stay, and safety/medical constraints.