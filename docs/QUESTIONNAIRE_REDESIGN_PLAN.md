# Questionnaire Redesign Plan: India-Centric, Deduplicated & Model-Agnostic

## 1. Executive Summary & Verification of Known Context

### 1.1 Context Verification Against Codebase
- **Basic Tier**: 11 questions (`q1`, `q2`, `q3`, `q4`, `q5`, `q14`, `q17`, `q20`, `q26`, `q32`, `q41`) in `app/questionnaire.py`. Stored in table `traveller_profiles`. Encoded into a 22-dimensional continuous feature vector via `app/vectorizer.py`.
- **Detailed Tier**: Master questionnaire bank in `app/questionnaire.py` consisting of 56 questions across 10 sections (`sec_1` to `sec_10`). Stored in `detailed_profiles`. Vectorized to 41 dimensions.
- **Precision Tier**: Adaptive questionnaire bank in `app/precision.py` with 88 total questions (70 `NEW_QUESTIONS` + 18 `CARRYOVER` from `app/questionnaire.py`). Vectorized to 90 precision features, combining with detailed base features to form the 131-dimensional combined vector (`PreferenceVectorizer.get_precision_full_feature_names()`).
- **Downstream Consumers**:
  - `app/recommender.py`: Matches destinations across interests, climate, budget, pace, and companions.
  - `app/rl_planner.py`: Constructs a 24-dimensional context vector for LinUCB bandit arms.
  - `app/itinerary_generator.py`: Enforces dietary constraints, walking capacities, avoidances, and travel pace.
  - `app/modules/prep.py`: Generates preparation checklists, packing items, and weather advisories.
  - `app/modules/ranking.py`: Multi-criteria destination ranking engine.
  - `app/modules/live.py` & `app/modules/common.py`: Context extraction and profile gate checks (`has_completed_deep_profile`).
- **India-Only Scope**: Itineraries are restricted to India. International trip creations are rejected (HTTP 400). Any foreign travel assumptions (e.g., USD prices, time-zone jetlag, international visas) are invalid and must be removed.

---

## 2. Complete Question Inventory (Before Redesign)

The current system spans 126 distinct question identifiers (`q1` to `q126`) across the three tiers:

| ID | Tier | Question Text | Type | Consumers (File:Line) | Vector Dimension / Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `q1` | BASIC | Age group | single | `api.py:186`, `vectorizer.py:133` | basic: `age_group` context |
| `q2` | BASIC | Travel experience | single | `api.py:186`, `vectorizer.py:138` | basic: `travel_experience` context |
| `q3` | BASIC | Who do you usually travel with? | single | `api.py:186`, `vectorizer.py:143`, `precision.py:114` | basic: `companion_solo/couple/friends/family`, `has_children` |
| `q4` | BASIC | Usual approach to planning a trip | single | `api.py:186`, `vectorizer.py:155` | basic: `spontaneity` / structure |
| `q5` | BASIC | What do you most want to get out of travelling? | multi | `api.py:186`, `vectorizer.py:160`, `recommender.py:270` | basic: `interest_*` (culture, food, nature, adventure, relaxation) |
| `q6` | DET / PREC | Planning tasks to take off hands | multi | `precision.py:468` | precision: planning delegation |
| `q7` | DETAILED | Physical or health-related factors | multi | `api.py:365`, `itinerary_generator.py:48` | detailed: accessibility & physical demand |
| `q8` | DETAILED | Physical demand level | single | `vectorizer.py:240` | detailed: `walking_capacity` |
| `q9` | DETAILED | Wheelchair / step-free access needed | single | `api.py:821`, `itinerary_generator.py:54` | detailed: `accessibility` |
| `q10` | DET / PREC | Allergies, intolerances, triggers | multi | `common.py:74`, `prep.py:350`, `test_prep.py:170` | precision: `allergen_*` constraint masks |
| `q11` | DET / PREC | Health-related items to carry | single | `prep.py:351`, `test_prep.py:170` | precision: medical documentation & prep |
| `q12` | DETAILED | Activities/environments to avoid | multi | `api.py:789`, `recommender.py:1199`, `vectorizer.py:220` | detailed: `avoid_*` penalty masks |
| `q13` | DETAILED | Discomfort response strategy | single | `api.py:365` | detailed: safety rerouting preference |
| `q14` | BASIC | Which types of places interest you most? | multi | `api.py:186`, `vectorizer.py:170`, `recommender.py:275` | basic: `interest_*` (beaches, mountains, shopping, nightlife) |
| `q15` | DETAILED | Specific activities enjoyed | multi | `api.py:365` | detailed: activity preference |
| `q16` | DETAILED | Hobbies / personal interests (text) | text | `api.py:365` | detailed: freeform text |
| `q17` | BASIC | Kinds of experiences generally preferred | single | `api.py:186`, `vectorizer.py:177` | basic: `pace`, `spontaneity` |
| `q18` | DETAILED | Disliked activities/places (text) | text | `api.py:365` | detailed: negative preference |
| `q19` | DETAILED | Time spent at each attraction | single | `api.py:820`, `vectorizer.py:245` | detailed: `schedule_density` |
| `q20` | BASIC | Dietary preferences or restrictions | multi | `api.py:822`, `common.py:84`, `itinerary_generator.py:50` | basic: dietary safety constraint |
| `q21` | DETAILED | Food style preferred while travelling | single | `api.py:365` | detailed: food preference |
| `q22` | DETAILED | Meal management style | single | `api.py:365` | detailed: dining logistics |
| `q23` | DETAILED | Dietary preference importance | single | `api.py:365` | detailed: dietary strictness |
| `q24` | DETAILED | Food fallback strategy | single | `api.py:365` | detailed: meal fallback rule |
| `q25` | DETAILED | Specific food habits (text) | text | `api.py:365` | detailed: dining notes |
| `q26` | BASIC | Comfortable temperatures | single | `vectorizer.py:190`, `recommender.py:280` | basic: `climate_weight` |
| `q27` | DETAILED | Weather reaction | single | `api.py:365` | detailed: weather adaptability |
| `q28` | DETAILED | Weather alerts preferred | multi | `api.py:365`, `live.py:110` | detailed: advisory triggers |
| `q29` | DETAILED | Packing habits | single | `api.py:365`, `prep.py:320` | detailed: checklist style |
| `q30` | DET / PREC | Packing priorities | single | `prep.py:325` | precision: packing optimization |
| `q31` | DETAILED | Clothing notes (text) | text | `api.py:365` | detailed: wardrobe preferences |
| `q32` | BASIC | Typical travel budget | single | `vectorizer.py:185`, `ranking.py:140` | basic: `budget_weight` |
| `q33` | DETAILED | Willingness to spend more on comfort | multi | `api.py:365` | detailed: budget distribution |
| `q34` | DETAILED | Type of accommodation preferred | single | `api.py:823`, `vectorizer.py:250` | detailed: `stay_*` onehot |
| `q35` | DETAILED | Transportation options preferred | single | `api.py:824`, `vectorizer.py:260` | detailed: `transit_*` onehot |
| `q36` | DETAILED | Specific travel concerns | multi | `api.py:365` | detailed: travel worry flags |
| `q37` | DETAILED | Preparation assistance desired | multi | `api.py:365`, `prep.py:310` | detailed: checklist features |
| `q38` | DET / PREC | Reminder style | single | `prep.py:330` | precision: notification timing |
| `q39` | DET / PREC | Forgotten essentials | text | `prep.py:335` | precision: custom checklist items |
| `q40` | DETAILED | Decision criteria for choices | single | `api.py:365` | detailed: evaluation criteria |
| `q41` | BASIC | Independence level in decisions | single | `vectorizer.py:195` | basic: `assistance_autonomy` |
| `q42` | DET / PREC | Proactive suggestion level | single | `precision.py:480` | precision: `proactivity` scalar |
| `q43` | DET / PREC | Proactive alert triggers | multi | `live.py:115` | precision: alert event triggers |
| `q44` | DET / PREC | Data uncertainty handling | single | `precision.py:490` | precision: explanation mode |
| `q45` | DET / PREC | Rejected recommendation handling | single | `precision.py:495` | precision: learning rate / signal |
| `q46` | DET / PREC | Notification update frequency | single | `precision.py:500` | precision: `update_frequency` scalar |
| `q47` | DET / PREC | Privacy saving categories | multi | `precision.py:320` | precision: privacy filter drop mask |
| `q48` | DETAILED | Past trips memory preference | single | `vectorizer.py:270` | detailed: `exploration_weight` |
| `q49` | DET / PREC | Recommendation transparency factors | multi | `precision.py:510` | precision: card metadata display |
| `q50` | DET / PREC | Things never to remember | text | `precision.py:515` | precision: exclusion list |
| `q51` | DET / PREC | Profile edit/delete controls | single | `precision.py:520` | precision: UI control flag |
| `q52` | DETAILED | Ideal trip description (text) | text | `api.py:365` | detailed: freeform narrative |
| `q53` | DETAILED | Trip ruiners (text) | text | `api.py:365` | detailed: negative narrative |
| `q54` | DET / PREC | Assistant wish (text) | text | `precision.py:525` | precision: freeform narrative |
| `q55` | DET / PREC | Top failure cases to prevent (text) | text | `precision.py:530` | precision: freeform narrative |
| `q56` | DET / PREC | Catch-all open notes (text) | text | `precision.py:535` | precision: freeform narrative |
| `q57`-`q60` | PRECISION | Home climate, booking window | single | `precision.py:140` | precision: context features |
| `q61` | PRECISION | Luggage capacity (carry-on vs checked) | single | `prep.py:349`, `test_prep.py:137` | precision: luggage constraint |
| `q62` | PRECISION | Journey transport modes | multi | `precision.py:165` | precision: transit mode flags |
| `q63`-`q69` | PRECISION | Party detail (infant/child ages, senior) | single | `api.py:793`, `precision.py:175` | precision: party constraint scalars |
| `q70`-`q76` | PRECISION | Day schedule, night return, break times, walking distance | mixed | `common.py:80`, `precision.py:210` | precision: `walk_km`, daily bounds |
| `q77`-`q81` | PRECISION | Weather tolerance (cold, heat, wind, rain) | scale | `prep.py:346-348`, `test_prep.py:415` | precision: environmental tolerance scalars |
| `q82`-`q90` | PRECISION | Comfort in crowds, noise, darkness, bargaining | scale | `precision.py:270` | precision: social/environmental tolerances |
| `q91`-`q101`| PRECISION | Spice tolerance, allergens, meal timing, cooking | mixed | `common.py:74,84`, `prep.py:352`, `models.py:188` | precision: food constraints & scalars |
| `q102`-`q106`| PRECISION | Kitchen access, motion sickness, transport comfort | mixed | `precision.py:350` | precision: nausea & stay logistics |
| `q107`-`q110`| PRECISION | Cultural themes, audio tours, photography gear | mixed | `precision.py:375` | precision: theme weights |
| `q111`-`q117`| PRECISION | Electronics carried, IDs/documents held, fitness | mixed | `precision.py:400` | precision: packing & checklist items |
| `q118`-`q121`| PRECISION | Accommodation/daily spending in USD ($) | single | `precision.py:430` | precision: stale USD budget metrics |
| `q122`-`q126`| PRECISION | Delay handling, alternative styles, tone | single | `precision.py:450` | precision: agent behavior parameters |

---

## 3. Duplication, Flaws & Non-India Assumptions Identified

1. **Stale US Dollar Currency**:
   - `q99` ("spend on main meal": under $5, $5-$15, $15-$30, over $30)
   - `q118` ("spend per night on stay": under $30, $30-$70, $70-$150, over $150)
   - `q119` ("daily spending excluding stay": under $20, $20-$50, $50-$100, over $100)
   - **Fix**: Replaced by unified INR daily spending tiers (`< ₹1,500`, `₹1,500-₹3,500`, `₹3,500-₹8,000`, `₹8,000+` per day) tied directly to standard Indian travel bands.

2. **Cross-Tier Duplication (Same Concept Repeated Blankly)**:
   - **Budget**: Asked in `q32` (basic: budget/mid_range/luxury), `q33` (detailed: where to spend), `q99`, `q118`, `q119` (precision: meal, stay, daily).
   - **Dietary & Food**: Asked in `q20` (basic: dietary restrictions), `q21` (detailed: food style), `q22` (detailed: meal management), `q23` (detailed: dietary importance), `q24` (detailed: fallback), `q25` (detailed: text), `q91` (precision: spice), `q93` (precision: diet strictness), `q94` (precision: diet extras), `q95` (precision: allergens).
   - **Weather & Climate**: Asked in `q26` (basic: comfortable temperatures), `q27` (detailed: weather reaction), `q60` (precision: home climate), `q78`-`q81` (precision: cold, heat, wind, rain scales).
   - **Walking & Pacing**: Asked in `q8` (detailed: physical demand), `q19` (detailed: attraction time), `q71` (precision: downtime), `q73` (precision: walk km), `q74` (precision: break interval).
   - **Fix**: Concept deduplication rule. The concept is defined once. If a Deep question elaborates on a Basic concept, it declares `refines: <basic_concept>` and `prefill_from: <basic_question_id>`.

3. **Missing Critical Indian Travel Realities**:
   - No question captured monsoon/landslide sensitivity (crucial for Himachal, Uttarakhand, Kerala, Western Ghats).
   - No high-altitude acclimatization preference (essential for Leh Ladakh, Spiti Valley).
   - Train travel classes (Vande Bharat, 1st AC, 2nd AC, 3AC, Sleeper) and chauffeur-driven hired vehicles were absent.
   - Specific Indian dietary nuances (Jain satvik, pure vegetarian, halal, eggetarian, street-food hygiene tolerance) were scattered or missing.
   - Women solo safety preferences and senior-citizen pilgrimage/stairs accessibility were neglected.

---

## 4. Redesigned Questionnaire Architecture

### 4.1 Single Source of Truth: `app/data/questionnaire_schema.json`
Every question across all tiers is declared in a machine-readable, versioned schema (`schema_version: "2.0.0"`).

```json
{
  "id": "b09_dietary",
  "concept": "food.dietary_preference",
  "tier": "basic",
  "section": "b_sec_3",
  "text": "What are your dietary preferences for travel dining in India?",
  "type": "multi",
  "required": true,
  "options": [
    {"id": "pure_veg", "label": "Pure Vegetarian", "desc": "No meat, fish or eggs; dairy is fine"},
    {"id": "jain", "label": "Jain Vegetarian", "desc": "Strict vegetarian without root vegetables (onion, garlic, potato)"},
    {"id": "eggetarian", "label": "Eggetarian", "desc": "Vegetarian + eggs; no meat or seafood"},
    {"id": "non_veg", "label": "Non-Vegetarian", "desc": "Chicken, mutton, seafood as available"},
    {"id": "halal", "label": "Halal Certified", "desc": "Halal-prepared food only"},
    {"id": "vegan", "label": "Vegan", "desc": "100% plant-based, no dairy or animal products"}
  ],
  "encoding": {"type": "multihot", "features": ["diet_veg", "diet_jain", "diet_eggetarian", "diet_nonveg", "diet_halal", "diet_vegan"]},
  "consumers": ["recommender", "itinerary", "prep", "features"]
}
```

### 4.2 Tier Breakdown

#### BASIC TIER (12 Questions in 3 Focused Steps)
- **Step 1: Traveller Profile & Party**
  1. `b01_age`: Age group (`18_24`, `25_34`, `35_49`, `50_64`, `65_plus`). Concept: `demographics.age`.
  2. `b02_home_region`: Home State/Region in India (Northern, Western, Southern, Eastern, Central, North-Eastern). Concept: `origin.region`.
  3. `b03_companions`: Who are you traveling with? (`solo`, `partner_couple`, `friends`, `family_kids`, `family_seniors`). Concept: `party.composition`.
  4. `b04_experience`: Travel experience in India (`first_time`, `occasional`, `frequent`, `veteran_explorer`). Concept: `travel.experience`.
- **Step 2: Interests, Landscapes & Pacing**
  5. `b05_travel_goals`: Primary trip goals (Select at least 2: heritage_history, spiritual_pilgrimage, nature_wildlife, adventure_trekking, relaxation_wellness, culinary_food_trails, photography_scenic). Concept: `interests.primary_goals`.
  6. `b06_place_interests`: Preferred landscapes in India (Select at least 2: himalayan_mountains, beaches_coastal, royal_forts_palaces, holy_temple_ghats, lush_backwaters_plantations, desert_dunes, dense_jungles). Concept: `interests.landscapes`.
  7. `b07_pace`: Daily rhythm (`relaxed_1_2`, `balanced_2_3`, `packed_all_day`). Concept: `trip.pacing`.
  8. `b08_crowd_tolerance`: Comfort with bustling crowds and markets (`prefer_quiet_secluded`, `moderate_crowds_fine`, `love_bustling_festive`). Concept: `comfort.crowd_level`.
- **Step 3: Food, Budget & Logistics**
  9. `b09_dietary`: Dietary preferences (`pure_veg`, `jain`, `eggetarian`, `non_veg`, `halal`, `vegan`). Concept: `food.dietary_preference`.
  10. `b10_budget`: Indicative per-person per-day budget band in INR (`budget_backpacker`: ₹1,000–₹2,500; `mid_range_comfortable`: ₹2,500–₹6,000; `premium_luxury`: ₹6,000–₹15,000+). Concept: `budget.daily_tier`.
  11. `b11_climate`: Preferred climate comfort (`cold_himalayan`, `cool_hillstation`, `moderate_pleasant`, `warm_tropical`). Concept: `climate.comfort_zone`.
  12. `b12_autonomy`: Desired AI assistant autonomy (`full_curated_schedule`, `shortlist_with_explanations`, `on_demand_advice_only`). Concept: `ai.assistance_level`.

#### DEEP TIER (Target: ~48 Questions with Smart Branching)
Organized into 8 coherent, non-duplicative sections. A user typically encounters **25 to 32 questions** based on `show_if` branches:
1. **Party & Personal Comfort (`d_party`)**:
   - `d01_solo_safety`: Solo travel comfort & safety preferences (`show_if: b03_companions == solo`).
   - `d02_child_age`: Youngest child age bracket (`show_if: b03_companions == family_kids`).
   - `d03_senior_mobility`: Senior citizen mobility limits (`show_if: b03_companions == family_seniors`).
   - `d04_language`: Languages comfortable communicating in (`hindi`, `english`, `regional`).
2. **Terrain, Season & Weather (`d_climate`)**:
   - `d05_monsoon_rain`: Sightseeing in monsoon rain (Scale 1-5).
   - `d06_high_altitude`: High-altitude Himalayan comfort (Scale 1-5).
   - `d07_heat_humidity`: Tolerance for tropical heat/humidity (Scale 1-5).
   - `d08_cold_snow`: Tolerance for sub-zero winter temperatures (Scale 1-5).
3. **Dining, Spice & Street Food (`d_food`)**:
   - `d09_spice_tolerance`: Indian spice tolerance (Scale 1-5).
   - `d10_street_food`: Street food exploration comfort (Scale 1-5).
   - `d11_food_allergies`: Allergies to strictly exclude (peanuts, seafood, gluten, dairy; sensitive, optional).
   - `d12_regional_cuisines`: Regional Indian cuisines of high interest (Mughlai, Coastal/Kerala, Rajasthani, Pahadi, etc.).
4. **Transport & Transit (`d_transit`)**:
   - `d13_train_class`: Preferred Indian Railways class (Vande Bharat/Tejas, 1st AC, 2nd AC, 3AC, Sleeper).
   - `d14_road_transit`: Preferred road travel (Chauffeur hired cab, Self-drive, Overnight Volvo, Local autos/taxis).
   - `d15_motion_sickness`: Nausea triggers (Himalayan ghat roads, ferry boats, none).
   - `d16_early_departures`: Comfort with pre-6 AM departures for safaris/trains (Scale 1-5).
5. **Stay & Accommodation (`d_stay`)**:
   - `d17_stay_types`: Preferred stay types (Heritage haveli/palace, Boutique homestay, Luxury resort, Eco-tents, Budget guesthouse).
   - `d18_stay_amenities`: Essential amenities (Reliable Wi-Fi, Elevator/ground floor, Pure-veg kitchen, Swimming pool).
6. **Physical Capacity & Health (`d_health`)**:
   - `d19_walk_distance`: Comfortable daily walking distance in km (Slider 1 to 20 km).
   - `d20_temple_stairs`: Comfort with steep temple stairs or uneven terrain (Scale 1-5).
   - `d21_medical_logistics`: Health items requiring refrigeration or special handling (Sensitive, optional).
7. **Activities & Avoidances (`d_activities`)**:
   - `d22_avoidances`: Specific elements to avoid (strenuous_hikes, crowded_clubs, high_altitudes, long_bus_rides, extreme_heat).
   - `d23_cultural_themes`: Specialized cultural interests (temple_architecture, textiles_handicrafts, wildlife_birding, yoga_meditation).
   - `d24_permits`: Willingness to arrange local permits (Inner Line Permit, protected sanctuary permits).
8. **Planning Style, Budgeting & Agent Behavior (`d_agent`)**:
   - `d25_budget_flexibility`: Strictness of daily budget cap (Scale 1-5).
   - `d26_proactivity`: How proactively the assistant suggests real-time tweaks (Scale 1-5).
   - `d27_privacy`: Categories opted in for persistent profile storage.

---

## 5. Model-Agnostic Feature Engineering & Endpoints

### 5.1 Backward Compatibility Adapters
To guarantee that `app/recommender.py`, `app/rl_planner.py`, `app/itinerary_generator.py`, `app/modules/prep.py`, and `app/modules/ranking.py` continue functioning without disruption:
1. **Basic Adapter (`to_basic_vector`)**: Derives the canonical 22-dimensional basic vector from either the new schema answers or legacy basic profiles.
2. **Detailed Adapter (`to_detailed_vector`)**: Derives the 41-dimensional extended vector from new schema answers.
3. **Precision Adapter (`to_precision_vector`)**: Derives the 131-dimensional combined vector from new schema answers.
4. **RL Context Adapter (`to_rl_context_24`)**: Derives the 24-dimensional LinUCB context vector.
5. **Legacy Profile Migration Adapter (`migrate_legacy_answers`)**: Reads existing records from `traveller_profiles`, `detailed_profiles`, and `precision_profiles` (which used keys `q1`...`q126` and field names), mapping them safely into new concept answers so existing users suffer zero disruption.

### 5.2 New API Endpoints
1. `GET /api/config/questionnaire-schema`: Serves the complete JSON schema with question metadata, concept identifiers, option codes, prefill relationships, and consumers.
2. `GET /api/profile/{user_id}/features?format=named|vector|onehot`: Exports clean, model-agnostic feature representations with `<concept>.<value>`, numeric types, and explicit `<feature>__missing` indicators (no silent zeros).
3. `GET /api/profile/{user_id}/export`: Exports validated raw answers tagged with `schema_version`.
4. `GET /api/profile/{user_id}/summary`: Generates a natural-language traveller description ready for LLM prompts, safely excluding sensitive health/diet items unless explicitly authorized.

---

## 6. Implementation & Verification Plan

### Files to Modify / Create
1. **Create** `app/data/questionnaire_schema.json`: Complete, validated schema definition.
2. **Refactor** `app/questionnaire.py`: Load from schema; expose clean getters, backwards-compatible constants.
3. **Refactor** `app/precision.py`: Modernize adaptive bank to consume schema while preserving branching and privacy filtering.
4. **Update** `app/vectorizer.py`: Integrate adapters for 22, 41, 131, and 24 dimensions.
5. **Update** `app/api.py`: Add the 4 new endpoints (`/config/questionnaire-schema`, `/profile/{id}/features`, `/profile/{id}/export`, `/profile/{id}/summary`) while preserving existing endpoints.
6. **Update** `static/app.js`: Ensure basic onboarding and personal profile modals render from new options and support prefill indicators.
7. **Generate** `docs/questionnaire_data_dictionary.md`: Markdown data dictionary documenting all concepts and encodings.
8. **Update Tests**:
   - `tests/test_questionnaire_schema.py`: Validate schema integrity, concept uniqueness, India-only compliance, prefill derivations, and feature extraction determinism.
   - `run_tests.py`: Update questionnaire bank expectations to align with new clean counts.

Proceeding directly to Phase 2 implementation.
