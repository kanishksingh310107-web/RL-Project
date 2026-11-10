# Questionnaire Usage Reference (Profile Field to Code Mapping)

This document lists every question ID (`q1` through `q126` and basic/detailed fields) and the exact codebase locations (`file:function`) where the question answer directly influences a decision: destination ranking, itinerary activity slot selection, constraint-based filtering, pacing, budget limits, dietary/allergen safety, pre-trip packing, document checklists, live alerts, or the Contextual LinUCB bandit feature vector.

---

## Complete Question Mapping Table (Q1 – Q126)

| Question ID | Question Text / Field | Tier & Section | Codebase Usage (`file:function`) | Decision / Action Influenced |
|---|---|---|---|---|
| **q1** | Which age group do you belong to? (`age_group`) | Basic (sec_1) | `app.vectorizer:vectorize`, `app.precision:derive_insights` | LinUCB feature vector component; pace baseline calibration |
| **q2** | How would you describe your travel experience? (`travel_experience`) | Basic (sec_1) | `app.vectorizer:vectorize`, `app.modules.prep:generate_reminders` | Experience level weighting; guidance verbosity in prep reminders |
| **q3** | Who do you usually travel with? (`companions`) | Basic (sec_1) | `app.recommender:score_destination_for_user`, `app.precision:build_context_answers` | Destination companion suitability match (solo, partner, family); triggers conditional questions (q64, q65, q66) |
| **q4** | How do you usually approach planning? (`planning_approach`) | Basic (sec_1) | `app.vectorizer:vectorize`, `app.precision:derive_insights` | LinUCB structure feature; proactive suggestion frequency |
| **q5** | What are your main travel goals? (`travel_goals`) | Basic (sec_1) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:score_activity_for_slot` | Primary interest score for destination recommendations; activity slot category preference |
| **q6** | What parts of planning would you like help with? (`prep_assistance`) | Level 2 / Precision (p8) | `app.modules.prep:generate_reminders`, `app.modules.prep:generate_packing_list` | Selects which pre-trip checklists and alerts are surfaced |
| **q7** | Any health factors affecting travel? (`health_factors`) | Level 2 (sec_2) | `app.precision:derive_insights`, `app.itinerary_generator:is_activity_safe_and_valid` | Hard safety constraint; filters high-altitude and extreme exertion |
| **q8** | Physical demand and walking capacity? (`physical_demand`) | Level 2 (sec_2) | `app.itinerary_generator:is_activity_safe_and_valid`, `app.vectorizer:vectorize_detailed` | Activity intensity constraint; walking vs vehicle transit routing |
| **q9** | Accessibility requirements? (`accessibility`) | Level 2 (sec_2) | `app.itinerary_generator:is_activity_safe_and_valid`, `app.modules.common:get_user_context` | Hard mobility constraint: filters step-heavy ruins and non-accessible venues |
| **q10** | Specific allergy triggers? (`allergies_triggers`) | Level 2 / Precision (p5) | `app.itinerary_generator:is_activity_safe_and_valid`, `app.modules.prep:generate_packing_list` | Hard allergen filter on dining venues; triggers antihistamine / EpiPen packing reminder |
| **q11** | Health items carried on trips? (`health_items`) | Level 2 / Precision (p5) | `app.modules.prep:generate_packing_list`, `app.modules.prep:generate_documents_checklist` | Medication carry-on packing items; prescription document reminders; triggers q103 |
| **q12** | Specific things you avoid? (`avoidances`) | Level 2 (sec_2) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:is_activity_safe_and_valid` | Hard avoidance filter: strictly eliminates conflicting destinations and activities |
| **q13** | How should the assistant handle discomfort? (`discomfort_response`) | Level 2 (sec_2) | `app.modules.live:handle_delay`, `app.precision:derive_insights` | Automatic safe fallback substitution vs manual prompt |
| **q14** | Types of places or environments enjoyed? (`place_interests`) | Basic (sec_3) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:generate_itinerary` | Core destination tag matching; primary LinUCB activity arm alignment |
| **q15** | Specific activities enjoyed? (`activities_enjoyed`) | Level 2 (sec_3) | `app.itinerary_generator:score_activity_for_slot`, `app.vectorizer:vectorize_detailed` | Detailed activity candidate ranking bonus |
| **q16** | Hobbies relevant to travel (`hobbies_text`) | Level 2 (sec_3) | `app.precision:derive_insights`, `app.itinerary_generator:score_activity_for_slot` | Custom text keyword matching for specialty niche activities |
| **q17** | Overall experience style preference (`experience_preference`) | Basic (sec_3) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:generate_itinerary` | Balanced vs intensive scheduling; sightseeing vs immersion |
| **q18** | Disliked activities (`disliked_activities_text`) | Level 2 (sec_3) | `app.itinerary_generator:is_activity_safe_and_valid` | Hard filter: excludes activities mentioning disliked keywords |
| **q19** | Typical time spent per attraction (`time_per_attraction`) | Level 2 (sec_3) | `app.itinerary_generator:generate_itinerary` | Activity duration scaling (60 min vs 90 min vs 150 min) |
| **q20** | Dietary preferences or restrictions (`dietary`) | Basic (sec_4) | `app.itinerary_generator:is_activity_safe_and_valid`, `app.modules.common:get_user_context` | Hard constraint: filters non-conforming dining (veg, vegan, halal, jain, kosher) |
| **q21** | General food & dining style (`food_style`) | Level 2 (sec_4) | `app.itinerary_generator:generate_itinerary` | Street food vs fine dining vs regional traditional selection |
| **q22** | How meals are managed (`meal_management`) | Level 2 (sec_4) | `app.itinerary_generator:generate_itinerary`, `app.precision:build_context_answers` | Restaurant bookings vs self-catering; triggers q102 (kitchen needs) |
| **q23** | Strictness of dietary adherence (`dietary_importance`) | Level 2 (sec_4) | `app.precision:derive_insights`, `app.itinerary_generator:is_activity_safe_and_valid` | Cross-contamination and certified kitchen threshold enforcement |
| **q24** | Fallback when suitable food unavailable (`food_fallback`) | Level 2 (sec_4) | `app.modules.prep:generate_packing_list`, `app.precision:derive_insights` | Emergency snack rations packing rule |
| **q25** | Specific food habits & preferences (`food_habits_text`) | Level 2 (sec_4) | `app.precision:derive_insights` | Dining advisory notes in pre-trip briefing |
| **q26** | Preferred climate (`preferred_climate`) | Basic (sec_5) | `app.recommender:score_destination_for_user` | Exact and adjacent climate destination matching score |
| **q27** | Reaction to unpredicted weather (`weather_reaction`) | Level 2 (sec_5) | `app.modules.prep:generate_weather_forecast`, `app.modules.live:check_weather_alerts` | Threshold sensitivity for indoor replanning triggers |
| **q28** | Weather conditions requiring alerts (`weather_alerts`) | Level 2 (sec_5) | `app.modules.live:check_weather_alerts`, `app.precision:derive_insights` | Proactive rain, heat, and cold alert activation |
| **q29** | Packing habits (`packing_habits`) | Level 2 (sec_5) | `app.modules.prep:generate_packing_list` | Packing list timing: early checklist vs departure countdown |
| **q30** | Packing priorities (`packing_priorities`) | Level 2 / Precision (p7) | `app.modules.prep:generate_packing_list` | Weights packing item priorities: minimal light vs prepared comprehensive |
| **q31** | Special clothing requirements (`clothing_notes`) | Level 2 (sec_5) | `app.modules.prep:generate_packing_list` | Injected custom clothing items in pre-trip gear checklist |
| **q32** | Budget tier (`budget_tier`) | Basic (sec_6) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:generate_itinerary` | Destination budget tier matching; max per-activity expenditure |
| **q33** | Where to spend vs save (`spend_priorities`) | Level 2 (sec_6) | `app.itinerary_generator:score_activity_for_slot` | Allocation of higher budget activities to priority category |
| **q34** | Accommodation preferences (`accommodation_types`) | Level 2 (sec_6) | `app.api:create_trip`, `app.precision:derive_insights` | Default accommodation tier prefill in trip planning form |
| **q35** | Transport options used (`transport_options`) | Level 2 (sec_6) | `app.itinerary_generator:generate_itinerary` | Transit routing preference (metro, walking, private cab) |
| **q36** | Travel concerns & worries (`travel_concerns`) | Level 2 (sec_6) | `app.precision:derive_insights`, `app.modules.prep:generate_reminders` | Contextual safety and logistics reassurance notes |
| **q37** | Preparation assistance needs (`prep_assistance`) | Level 2 (sec_7) | `app.modules.prep:generate_reminders` | Frequency of pre-trip reminder notifications |
| **q38** | Reminder timing and style (`reminder_style`) | Level 2 / Precision (p7) | `app.modules.prep:generate_reminders` | Countdown cadence (14 days, 7 days, 48 hours, departure morning) |
| **q39** | Items frequently forgotten (`forgotten_essentials_text`) | Level 2 / Precision (p7) | `app.modules.prep:generate_packing_list` | Highlighted high-priority packing alert items |
| **q40** | Primary decision criteria (`decision_criteria`) | Level 2 (sec_8) | `app.recommender:score_destination_for_user`, `app.rl_planner:predict_score` | Weighting between interest overlap, budget fit, and novelty |
| **q41** | Assistant autonomy level (`assistance_autonomy`) | Basic (sec_8) | `app.modules.live:handle_delay`, `app.precision:derive_insights` | Suggestion vs automated reschedule behavior |
| **q42** | Proactive suggestion level (`proactive_level`) | Level 2 / Precision (p8) | `app.rl_planner:extract_context_vector`, `app.modules.live:generate_alerts` | LinUCB exploration parameter alpha; frequency of unsolicited suggestions |
| **q43** | Events that trigger alerts (`proactive_alerts`) | Level 2 / Precision (p8) | `app.modules.live:generate_alerts` | Event mask: flight delays, weather shifts, crowd spikes |
| **q44** | Handling data uncertainty (`uncertainty_handling`) | Level 2 / Precision (p8) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:generate_itinerary` | Conservative scheduling with clear uncertainty labels |
| **q45** | How feedback should be handled (`feedback_handling`) | Level 2 / Precision (p8) | `app.rl_planner:update_policy` | LinUCB learning rate and ridge regularisation adjustment |
| **q46** | Trip update frequency (`update_frequency`) | Level 2 / Precision (p8) | `app.modules.live:get_live_context` | Morning briefing vs real-time periodic notifications |
| **q47** | Allowed categories for saving (`privacy_saving`) | Level 2 / Precision (p8) | `app.precision:apply_privacy_filter` | Hard privacy gate: scrubs disallowed categories before DB write |
| **q48** | Remembering past trips (`remember_past_trips`) | Level 2 (sec_9) | `app.recommender:score_destination_for_user` | Past trip rating bonus / penalty enabled or disabled |
| **q49** | Information shown with recommendations (`trust_factors`) | Level 2 / Precision (p8) | `app.recommender:score_destination_for_user` | Controls visibility of cost breakdown and LinUCB score factors |
| **q50** | Topics never to remember (`never_remember_text`) | Level 2 / Precision (p8) | `app.precision:apply_privacy_filter` | Specific privacy exclusion keywords scrubbed from notes |
| **q51** | Data retention and delete preference (`data_controls`) | Level 2 / Precision (p8) | `app.precision:derive_insights` | User data control display and retention policy enforcement |
| **q52** | Ideal trip description (`ideal_trip_text`) | Level 2 (sec_10) | `app.precision:derive_insights` | Natural language goal extraction for bonus destination scoring |
| **q53** | Trip enjoyment ruiners (`enjoyment_ruiners_text`) | Level 2 (sec_10) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:is_activity_safe_and_valid` | Hard keyword avoidance filtering |
| **q54** | What assistant should do best (`assistant_wish_text`) | Level 2 / Precision (p8) | `app.precision:derive_insights` | Companion focus emphasis (hidden gems, pacing, smooth transit) |
| **q55** | Past travel problems to prevent (`prevent_problems_text`) | Level 2 / Precision (p8) | `app.modules.prep:generate_reminders`, `app.itinerary_generator:is_activity_safe_and_valid` | Pre-trip preventative warnings |
| **q56** | Any additional notes (`additional_notes_text`) | Level 2 / Precision (p8) | `app.precision:derive_insights` | Freeform notes surfaced on active profile summary |
| **q57** | Typical trip duration preference | Precision (p1) | `app.recommender:score_destination_for_user` | Filters destinations outside preferred trip length |
| **q58** | Travel distance tolerance (domestic vs international) | Precision (p1) | `app.recommender:score_destination_for_user`, `app.api:create_trip` | Domestic vs regional flight constraint |
| **q59** | Daily schedule density preference | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Number of activity slots generated per day (1, 2-3, or 4+) |
| **q60** | Preferred daily pacing | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Buffer times inserted between scheduled activities |
| **q61** | Luggage style (carry-on vs checked) | Precision (p1) | `app.modules.prep:generate_packing_list` | Carry-on 100ml liquid limits; strictly compact item counts |
| **q62** | Travel tempo consistency across days | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Steady pacing vs alternating active and rest days |
| **q63** | Buffer time between activities | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Inter-activity transit margin (15 min vs 45 min) |
| **q64** | Traveling with children logistics | Precision (p1: show_if q3=children) | `app.itinerary_generator:is_activity_safe_and_valid`, `app.modules.prep:generate_packing_list` | Filters non-child-friendly venues; adds child essentials to packing |
| **q65** | Traveling with older companions | Precision (p1: show_if q3=elderly) | `app.itinerary_generator:is_activity_safe_and_valid` | Hard constraint: ensures elevator access and eliminates steep stairs |
| **q66** | Group consensus and preference balance | Precision (p1: show_if q3=group) | `app.itinerary_generator:score_activity_for_slot` | LinUCB entropy bonus to balance diverse group tastes |
| **q67** | Typical wake-up time during travel | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Morning activity start time (07:30 vs 09:30 vs 11:00) |
| **q68** | Typical evening wind-down time | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Night activity cut-off time (20:00 vs 23:00) |
| **q69** | Afternoon rest / nap requirement | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Clears afternoon slot (14:00-16:00) for hotel downtime |
| **q70** | Energy distribution across the day | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Places demanding activities in morning vs late afternoon |
| **q71** | Walking capacity in steps / km per day | Precision (p2) | `app.itinerary_generator:is_activity_safe_and_valid` | Daily cumulative walking distance cap |
| **q72** | Standing tolerance in museum queues | Precision (p2) | `app.itinerary_generator:is_activity_safe_and_valid` | Recommends skip-the-line bookings or outdoor alternatives |
| **q73** | Stairs and steep incline tolerance | Precision (p2) | `app.itinerary_generator:is_activity_safe_and_valid` | Filters cliffside viewpoints without funicular / vehicular access |
| **q74** | Walking distance comfort band | Precision (p2) | `app.itinerary_generator:generate_itinerary`, `app.modules.common:get_user_context` | Primary transit mode selector (walking vs transit vs cab) |
| **q75** | Rest break frequency | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Schedules cafe / park stops between major visits |
| **q76** | Meal timing flexibility | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Strict meal slots (12:30/19:30) vs flexible snacking |
| **q77** | Jetlag recovery day requirement | Precision (p2) | `app.itinerary_generator:generate_itinerary` | Day 1 designated as light relaxation / arrival buffer |
| **q78** | Cold weather tolerance (1-5 scale) | Precision (p3) | `app.modules.prep:generate_weather_forecast`, `app.modules.prep:generate_packing_list` | Low score triggers thermal underwear, gloves, and heavy coat rules |
| **q79** | Heat weather tolerance (1-5 scale) | Precision (p3) | `app.modules.prep:generate_weather_forecast`, `app.modules.prep:generate_packing_list` | Low score triggers hydration reminders, midday shade, and sunscreen |
| **q80** | Wind tolerance (1-5 scale) | Precision (p3) | `app.modules.prep:generate_packing_list`, `app.modules.live:check_weather_alerts` | Low score triggers windproof outer shell (Scotland coat rule) |
| **q81** | Rain tolerance (1-5 scale) | Precision (p3) | `app.modules.prep:generate_packing_list`, `app.modules.live:check_weather_alerts` | Low score triggers compact umbrella and waterproof footwear rules |
| **q82** | Humidity tolerance (1-5 scale) | Precision (p3) | `app.recommender:score_destination_for_user`, `app.modules.prep:generate_packing_list` | Penalizes tropical destinations for low tolerance; breathable fabrics |
| **q83** | Altitude sensitivity (1-5 scale) | Precision (p3) | `app.recommender:score_destination_for_user` | Low tolerance strictly filters high-altitude Himalayan passes (>3000m) |
| **q84** | Crowd tolerance (1-5 scale) | Precision (p3) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:score_activity_for_slot` | Early-morning timing recommendations; low-density hidden gems |
| **q85** | Noise tolerance (1-5 scale) | Precision (p3) | `app.api:create_trip`, `app.precision:derive_insights` | Filters nightlife-adjacent stays; quiet neighborhood preference |
| **q86** | Uncertainty tolerance (1-5 scale) | Precision (p3) | `app.itinerary_generator:generate_itinerary` | All bookings pre-confirmed vs spontaneous open exploration |
| **q87** | Physical risk tolerance (1-5 scale) | Precision (p3) | `app.itinerary_generator:is_activity_safe_and_valid` | High risk unlocks Class IV rafting, bouldering, paragliding |
| **q88** | Motion sickness sensitivity (1-5 scale) | Precision (p3) | `app.recommender:score_destination_for_user`, `app.modules.prep:generate_packing_list` | Filters winding ghat roads and ferry cruises; travel sickness pills |
| **q89** | Cultural immersion preference (1-5 scale) | Precision (p6) | `app.itinerary_generator:score_activity_for_slot` | Weighting for local homestays and community cultural workshops |
| **q90** | Nature immersion preference (1-5 scale) | Precision (p6) | `app.itinerary_generator:score_activity_for_slot` | National park, trekking and dark-sky reserve preference |
| **q91** | Architecture interest (1-5 scale) | Precision (p6) | `app.itinerary_generator:score_activity_for_slot` | Weighting for historic forts, UNESCO palaces, and heritage temples |
| **q92** | Photography priority (1-5 scale) | Precision (p6) | `app.itinerary_generator:generate_itinerary` | Schedules visits at Golden Hour (sunrise/sunset) for scenic spots |
| **q93** | Detailed dietary profile | Precision (p4: show_if q20) | `app.itinerary_generator:is_activity_safe_and_valid` | Filters dining by Jain (no root veg), Halal, Kosher, Gluten-Free |
| **q94** | Strict vegetarian/vegan requirements | Precision (p4: show_if q20) | `app.itinerary_generator:is_activity_safe_and_valid` | Strict 100% pure vegetarian / vegan restaurant filtering |
| **q95** | Specific food allergen triggers | Precision (p4: show_if q10) | `app.itinerary_generator:is_activity_safe_and_valid`, `app.modules.prep:generate_packing_list` | Hard filtering of seafood/peanut kitchens; translation card in prep |
| **q96** | Severe allergen cross-contamination | Precision (p4: show_if q95) | `app.itinerary_generator:is_activity_safe_and_valid` | Excludes street food stalls for severe anaphylaxis risks |
| **q97** | Spice tolerance (1-5 scale) | Precision (p4) | `app.itinerary_generator:select_dining_for_slot` | Recommends mild cuisine vs fiery authentic regional curries |
| **q98** | Willingness to try unfamiliar street foods | Precision (p4) | `app.itinerary_generator:select_dining_for_slot` | Street food stalls vs sanitized dining recommendations |
| **q99** | Coffee / tea ritual preference | Precision (p4) | `app.itinerary_generator:generate_itinerary` | Morning specialty cafe and tea estate tasting slot insertions |
| **q100** | Alcohol and nightlife preference | Precision (p4) | `app.itinerary_generator:generate_itinerary` | Evening lounge vs quiet sunset viewpoint slot selection |
| **q101** | Breakfast style preference | Precision (p4) | `app.itinerary_generator:generate_itinerary` | Hotel hearty breakfast vs local morning street market walk |
| **q102** | Self-catering kitchen requirements | Precision (p4: show_if q22) | `app.api:create_trip` | Selects apartment / Airbnb with full kitchen |
| **q103** | Medication storage / refrigeration | Precision (p5: show_if q11) | `app.modules.prep:generate_reminders`, `app.api:create_trip` | Refrigerated stay requirement; pre-trip cool-pack packing rule |
| **q104** | Public transit navigation comfort | Precision (p7) | `app.itinerary_generator:generate_itinerary` | Metro/bus directions vs pre-booked private cab transit |
| **q105** | Taxi / rideshare reliance | Precision (p7) | `app.itinerary_generator:generate_itinerary` | Injects taxi fare estimate into daily budget total |
| **q106** | Camera gear carried | Precision (p7: show_if q5=photo) | `app.modules.prep:generate_packing_list` | Injects spare SD cards, lens cleaning kit, tripod rules |
| **q107** | Depth of cultural / museum visits | Precision (p6: show_if q14) | `app.itinerary_generator:generate_itinerary` | Comprehensive audio-guided tour (2.5h) vs quick highlights (45m) |
| **q108** | Hiking difficulty comfort band | Precision (p6: show_if q14) | `app.itinerary_generator:is_activity_safe_and_valid` | Trail grade filtering: flat nature walk vs technical ridge hike |
| **q109** | Shopping interest and souvenir focus | Precision (p6) | `app.itinerary_generator:generate_itinerary` | Dedicated craft bazaar / handloom market slot |
| **q110** | Passport validity check | Precision (p7) | `app.modules.prep:generate_documents_checklist` | 6-month validity countdown alert |
| **q111** | Visa readiness and requirements | Precision (p7) | `app.modules.prep:generate_documents_checklist` | eVisa / embassy application timeline reminder |
| **q112** | International driving permit held | Precision (p7) | `app.modules.prep:generate_documents_checklist` | Self-drive rental car eligibility check |
| **q113** | Student / senior discount cards | Precision (p7) | `app.modules.prep:generate_documents_checklist` | Concession card reminder for museum ticket savings |
| **q114** | Travel adapter and voltage readiness | Precision (p7) | `app.modules.prep:generate_packing_list` | Type-specific electrical plug adapter rule |
| **q115** | Travel insurance coverage held | Precision (p7) | `app.modules.prep:generate_reminders` | Policy purchase and emergency helpline card reminder |
| **q116** | Payment preference (cards, cash, UPI) | Precision (p7) | `app.modules.prep:generate_reminders` | ATM cash buffer alert for rural and mountain destinations |
| **q117** | Mobile data / connectivity needs | Precision (p7) | `app.modules.prep:generate_reminders` | eSIM / local SIM purchase vs offline maps download |
| **q118** | Typical spend per night on stay | Precision (p7) | `app.api:create_trip` | Accommodation budget calibration |
| **q119** | Typical daily spend on meals and activities | Precision (p7) | `app.itinerary_generator:filter_activity_by_constraints` | Hard cap: total day activity costs cannot exceed daily budget |
| **q120** | Languages spoken comfortably | Precision (p7) | `app.modules.prep:generate_reminders` | Translation app download reminder for non-fluent regions |
| **q121** | Explanation verbosity desired | Precision (p8) | `app.recommender:score_destination_for_user`, `app.itinerary_generator:generate_itinerary` | Brief one-line vs detailed multi-factor "Because you said..." text |
| **q122** | Schedule delay / interruption handling | Precision (p8) | `app.modules.live:handle_delay` | Automated rescheduling vs 2-3 option prompt vs manual alert |
| **q123** | Local etiquette and dress code advisories | Precision (p8) | `app.modules.live:generate_alerts`, `app.modules.prep:generate_reminders` | Briefing on temple dress codes, shoe removal, and photography etiquette |
| **q124** | Diversity of LinUCB alternative suggestions | Precision (p8) | `app.services.suggestion_engine:get_linucb_alternatives` | Same-theme replacement vs contrasting serendipitous alternatives |
| **q125** | Daily budget cap enforcement strictness | Precision (p8) | `app.itinerary_generator:filter_activity_by_constraints` | Strict zero-tolerance cap vs 15% flexibility for exceptional activities |
| **q126** | Assistant communication tone | Precision (p8) | `app.precision:derive_insights`, `app.modules.live:get_live_context` | Formats companion briefing voice (concise pro vs warm friendly vs detailed guide) |

---

## Architectural Verification

1. **Hard Constraints vs Soft Ranking:**
   - **Allergies & Medical (q10, q95, q96):** Checked in `app.itinerary_generator:is_activity_safe_and_valid`. Non-conforming activities are strictly rejected (`is_safe = False`) and never scheduled.
   - **Mobility (q8, q9, q74):** High-stamina / steep stairs activities are eliminated for low-mobility users.
   - **Avoidances (q12, q53):** Destinations and activities matching avoidance triggers are filtered out in `app.recommender` and `app.itinerary_generator`.
   - **Budget Cap (q32, q119, q125):** Activities whose cost exceeds the remaining day budget are filtered out unless user explicitly set flexible budget elasticity in `q125`.

2. **Transparent "Because you said..." Attribution:**
   - Destination recommendations include `because_you_said` naming specific question IDs (`Q14`, `Q26`, `Q3`, `Q32`).
   - Itinerary activities include `because_you_said` citing interests (`Q14`), pacing (`Q60`), and walking tolerance (`Q74`).

3. **Single Source of Truth:**
   - All companion modules (`app/modules/prep.py`, `app/modules/live.py`, `app/modules/ranking.py`) read user answers through `app.modules.common:get_user_context()`.
