# Level 3 "Precision Profile": a deeper, adaptive questionnaire on top of the 56-question master bank.
#
# What lives here
#   1. PRECISION_SECTIONS / PRECISION_QUESTIONS - the question bank (65 new questions + 18 that already
#      existed in questionnaire.py but were never shown in the UI).
#   2. Conditional follow-ups ("show_if") - a question only appears when an earlier answer makes it relevant.
#   3. validate_answers() / sanitize / privacy filter - server-side checks so bad or hidden answers never get saved.
#   4. build_precision_vector() - turns answers into extra RL state features, driven by the "vec" spec on each question.
#   5. derive_insights() - human-readable planner rules the RL agent / planner can act on.
import copy
from typing import Any, Dict, List, Tuple

from app.questionnaire import QUESTIONS as BASE_QUESTIONS

# Tunable constants used by the insight rules (design choices, not facts - adjust freely)
COLD_C = 15
WIND_KMH = 30

PRECISION_SECTIONS = [
    {"id": "p1", "title": "Trip Context & Logistics",
     "purpose": "How long, how far, with whom and with what luggage you usually travel."},
    {"id": "p2", "title": "Daily Rhythm & Energy",
     "purpose": "Wake-up and wind-down times, walking capacity and rest needs, so days are paced realistically."},
    {"id": "p3", "title": "Comfort Calibration",
     "purpose": "1-5 scales for weather, crowds, noise, risk and uncertainty so packing and alerts match your body, not an average tourist."},
    {"id": "p4", "title": "Food Precision",
     "purpose": "Spice, strictness of diet, allergens, meal timing and kitchen needs."},
    {"id": "p5", "title": "Health, Safety & Medical Logistics",
     "purpose": "Optional. Allergy triggers, medication logistics and safety check-ins. Treated as hard constraints."},
    {"id": "p6", "title": "Interests Deep-Dive",
     "purpose": "Goes one level below your chosen interests (which themes, how intense, how serious)."},
    {"id": "p7", "title": "Packing, Documents & Money",
     "purpose": "Clothing needs, electronics, documents held, payment habits and typical spend."},
    {"id": "p8", "title": "Assistant Behaviour, Trust & Open Notes",
     "purpose": "How proactive and detailed the assistant should be, plus what it may remember."},
]

# --------------------------------------------------------------------------------------
# helpers to keep the bank readable
# --------------------------------------------------------------------------------------
def _o(*items):
    """('id', 'Label'[, 'description']) -> option dicts"""
    out = []
    for it in items:
        d = {"id": it[0], "label": it[1]}
        if len(it) > 2:
            d["desc"] = it[2]
        out.append(d)
    return out

def _q(qid, sec, text, qtype, **kw):
    d = {"id": qid, "section": sec, "tier": "precision", "question": text, "type": qtype}
    d.update(kw)
    return d

def _scale(qid, sec, text, low, high, name, why, **kw):
    return _q(qid, sec, text, "scale", low=low, high=high, why=why,
              vec={"type": "scale", "name": name}, **kw)

def _ord(name, mapping):
    return {"type": "ordinal", "name": name, "map": mapping}

SPEND_OPTS = _o(("lt_20", "Under $20"), ("20_50", "$20 - $50"), ("50_100", "$50 - $100"),
                ("100_200", "$100 - $200"), ("gt_200", "Over $200"))

# --------------------------------------------------------------------------------------
# NEW questions (q57 - q121)
# --------------------------------------------------------------------------------------
NEW_QUESTIONS: List[Dict[str, Any]] = [
    # ---------------- p1: Trip context ----------------
    _q("q57", "p1", "How long is your typical trip?", "single",
       options=_o(("weekend", "Weekend (1-3 days)"), ("short", "Short (4-7 days)"), ("two_weeks", "1-2 weeks"),
                  ("extended", "2-4 weeks"), ("long", "A month or more")),
       vec=_ord("trip_length", {"weekend": .15, "short": .35, "two_weeks": .6, "extended": .85, "long": 1.0}),
       why="Sets itinerary depth, packing volume and how often laundry/rest days are scheduled."),
    _q("q58", "p1", "How far do you usually travel from home?", "single",
       options=_o(("nearby", "Nearby (same region)"), ("domestic", "Elsewhere in my country"),
                  ("regional", "Neighbouring / short international"), ("long_haul", "Long-haul international")),
       vec=_ord("trip_distance", {"nearby": .15, "domestic": .4, "regional": .7, "long_haul": 1.0}),
       why="Decides transport advice, time-zone handling and passport/visa reminders."),
    _q("q59", "p1", "Which seasons do you usually travel in?", "multi",
       options=_o(("summer", "Summer"), ("monsoon", "Monsoon / rainy season"), ("winter", "Winter"),
                  ("spring_autumn", "Spring / autumn"), ("any", "Whenever it suits")),
       vec={"type": "flags", "prefix": "season", "options": ["summer", "monsoon", "winter"]},
       why="Tells the weather engine which conditions you actually meet."),
    _q("q60", "p1", "What climate are you used to at home?", "single",
       options=_o(("hot_humid", "Hot & humid"), ("hot_dry", "Hot & dry"), ("temperate", "Temperate / mild"),
                  ("cold", "Cold winters"), ("four_season", "Strong four seasons")),
       vec=_ord("home_climate_warmth", {"hot_humid": .9, "hot_dry": .85, "temperate": .5, "cold": .15, "four_season": .45}),
       why="The gap between home and destination weather is what causes surprise purchases (like a second coat). We measure that gap."),
    _q("q61", "p1", "How do you usually handle luggage?", "single",
       options=_o(("carry_on", "Carry-on only"), ("backpack", "One backpack / duffel"),
                  ("one_checked", "One checked bag + carry-on"), ("multi_checked", "Multiple checked bags")),
       vec=_ord("luggage_capacity", {"carry_on": .1, "backpack": .3, "one_checked": .6, "multi_checked": 1.0}),
       why="Caps the packing list and triggers cabin-baggage and liquids reminders."),
    _q("q62", "p1", "Which transport modes do you use for the main journey?", "multi",
       options=_o(("flight", "Flight"), ("train", "Train"), ("bus", "Bus / coach"), ("own_car", "Own car / bike"),
                  ("rental_car", "Rental car"), ("ferry", "Ferry / boat")),
       vec={"type": "flags", "prefix": "mode", "options": ["flight", "train", "bus", "own_car", "rental_car", "ferry"]},
       why="Every mode has different carry-on, document and comfort rules."),
    _q("q63", "p1", "How many people are in your usual travel group (including you)?", "single",
       options=_o(("g1", "Just me"), ("g2", "2"), ("g3_4", "3-4"), ("g5_8", "5-8"), ("g9_plus", "9 or more")),
       vec=_ord("group_size", {"g1": .1, "g2": .3, "g3_4": .55, "g5_8": .8, "g9_plus": 1.0}),
       why="Affects room types, restaurant bookings and transport choices."),
    _q("q64", "p1", "How old is the youngest child travelling with you?", "single",
       show_if={"q": "q3", "includes_any": ["family_children"]},
       options=_o(("infant", "Under 2"), ("toddler", "2-5"), ("child", "6-12"), ("teen", "13-17")),
       vec=_ord("youngest_child_age", {"infant": .25, "toddler": .5, "child": .75, "teen": 1.0}),
       why="Drives stroller access, nap windows, child-friendly food and attraction rules."),
    _q("q65", "p1", "How mobile is the oldest traveller in your group?", "single",
       show_if={"q": "q3", "includes_any": ["family_older"]},
       options=_o(("fully_mobile", "Fully mobile"), ("slower", "Walks slowly / needs frequent rests"),
                  ("assisted", "Needs a cane, walker or wheelchair at times")),
       vec=_ord("oldest_traveller_mobility", {"fully_mobile": .33, "slower": .66, "assisted": 1.0}),
       sensitive=True, privacy="accessibility_needs",
       why="Sets walking distances, step-free routes and seating stops for the whole group."),
    _q("q66", "p1", "Who usually makes the final decisions in your group?", "single",
       show_if={"q": "q3", "includes_any": ["partner", "friends", "family_children", "family_older", "tour_group"]},
       options=_o(("me", "Me"), ("shared", "We decide together"), ("other", "Someone else")),
       vec=_ord("decision_ownership", {"me": 1.0, "shared": .5, "other": .1}),
       why="Tells the assistant whether to persuade you, the group, or present options neutrally."),
    _q("q67", "p1", "How far ahead do you usually book?", "single",
       options=_o(("last_minute", "Within a week"), ("weeks", "2-4 weeks ahead"), ("months", "1-3 months ahead"),
                  ("early", "3+ months ahead")),
       vec=_ord("booking_lead", {"last_minute": .1, "weeks": .4, "months": .7, "early": 1.0}),
       why="Sets when reminders and price-drop nudges should fire."),
    _scale("q68", "p1", "How flexible are your travel dates?", "Fixed dates", "Very flexible", "date_flexibility",
           "Flexible dates let the assistant suggest cheaper or calmer weeks."),

    # ---------------- p2: Daily rhythm ----------------
    _q("q69", "p2", "When do you like to start your day on a trip?", "single",
       options=_o(("very_early", "Before 7:00"), ("early", "7:00 - 8:30"), ("mid", "8:30 - 10:00"), ("late", "After 10:00")),
       vec=_ord("day_start", {"very_early": .1, "early": .35, "mid": .65, "late": 1.0}),
       why="Decides the earliest activity slot the planner may use."),
    _q("q70", "p2", "When do you like to be back at your stay at night?", "single",
       options=_o(("early_eve", "Before 8 pm"), ("evening", "8 - 10 pm"), ("late", "10 pm - midnight"), ("very_late", "After midnight")),
       vec=_ord("evening_end", {"early_eve": .15, "evening": .4, "late": .7, "very_late": 1.0}),
       why="Decides whether evening plans (dinner, shows, night views) are scheduled."),
    _scale("q71", "p2", "How much rest or downtime do you need in a day?", "Almost none", "A long break every day",
           "rest_need", "Controls how many rest blocks are inserted between activities."),
    _q("q72", "p2", "How many hours of active sightseeing feel comfortable per day?", "number",
       min=1, max=14, step=0.5, unit="hours/day", default=6,
       vec={"type": "number", "name": "active_hours"},
       why="Caps the daily plan length."),
    _q("q73", "p2", "How far can you comfortably walk in a day?", "number",
       min=0, max=25, step=0.5, unit="km/day", default=8,
       vec={"type": "number", "name": "walk_km"},
       why="Used as a hard-ish limit when choosing routes and attraction clusters."),
    _q("q74", "p2", "How long can you walk or stand before needing a break?", "single",
       options=_o(("m10", "About 10 minutes"), ("m30", "About 30 minutes"), ("h1", "About an hour"), ("h2_plus", "2 hours or more")),
       vec=_ord("walk_before_break", {"m10": .1, "m30": .35, "h1": .7, "h2_plus": 1.0}),
       sensitive=True, privacy="accessibility_needs",
       why="Decides how often seating or cafe stops appear in a route."),
    _q("q75", "p2", "How do you feel about very early departures (flights or trains before 6 am)?", "single",
       options=_o(("fine", "Fine, no problem"), ("tolerable", "Tolerable if it saves money or time"), ("avoid", "I avoid them")),
       vec=_ord("early_departure_tolerance", {"fine": 1.0, "tolerable": .5, "avoid": .1}),
       why="Filters out inconvenient transport options."),
    _q("q76", "p2", "How do long flights and time-zone changes affect you?", "single",
       options=_o(("none", "Barely at all"), ("mild", "Mild - a day to adjust"), ("strong", "I need several days to adjust")),
       vec=_ord("timezone_sensitivity", {"none": .1, "mild": .5, "strong": 1.0}),
       why="Adds a light first day after long-haul arrivals."),
    _q("q77", "p2", "How sensitive are you to noise and comfort when sleeping?", "single",
       options=_o(("anywhere", "I sleep anywhere"), ("quiet", "I need a fairly quiet room"),
                  ("very", "Quiet, dark and a good bed are essential")),
       vec=_ord("sleep_sensitivity", {"anywhere": .1, "quiet": .6, "very": 1.0}),
       why="Prioritises quiet rooms and bed-quality reviews when ranking stays."),

    # ---------------- p3: Comfort calibration (1-5 scales) ----------------
    _scale("q78", "p3", "How well do you handle cold?", "I feel cold easily", "Cold rarely bothers me", "cold_tolerance",
           "Directly sets how many insulating layers the packing list recommends.",
           sensitive=True, privacy="env_sensitivities"),
    _scale("q79", "p3", "How well do you handle heat?", "Heat drains me", "I thrive in heat", "heat_tolerance",
           "Shifts outdoor plans to cooler hours and adds hydration reminders.",
           sensitive=True, privacy="env_sensitivities"),
    _scale("q80", "p3", "How well do you handle strong wind?", "Wind ruins my day", "Wind doesn't bother me", "wind_tolerance",
           "Wind is why one coat isn't enough in places like Scotland: it triggers windproof-layer advice.",
           sensitive=True, privacy="env_sensitivities"),
    _scale("q81", "p3", "Will you keep sightseeing in the rain?", "No, I'd rather stay in", "Yes, rain won't stop me", "rain_tolerance",
           "Decides whether outdoor plans get indoor fallbacks.",
           sensitive=True, privacy="env_sensitivities"),
    _scale("q82", "p3", "How well do you handle humidity?", "It really bothers me", "Not an issue", "humidity_tolerance",
           "Adjusts clothing fabric advice and activity timing.",
           sensitive=True, privacy="env_sensitivities"),
    _scale("q83", "p3", "How comfortable are you at high altitude (2,500 m and above)?", "Unwell easily / never tried", "Totally fine", "altitude_comfort",
           "Flags high-altitude destinations and suggests acclimatisation days.",
           sensitive=True, privacy="health_travel_needs"),
    _scale("q84", "p3", "How comfortable are you in crowds?", "I avoid them", "No problem", "crowd_comfort",
           "More precise than the one-line experience-style question: decides peak-hour avoidance."),
    _scale("q85", "p3", "How comfortable are you with noise (traffic, nightlife, markets)?", "Easily overwhelmed", "Enjoy the buzz", "noise_tolerance",
           "Influences neighbourhood and stay recommendations.",
           sensitive=True, privacy="env_sensitivities"),
    _scale("q86", "p3", "How comfortable are you when plans change at short notice?", "Very stressful", "I enjoy it", "uncertainty_comfort",
           "Low comfort = prefer robust plans with buffers; high comfort = more spontaneous suggestions."),
    _scale("q87", "p3", "How much adventure or risk do you enjoy?", "Keep it safe", "Bring on the thrills", "risk_appetite",
           "Gates adrenaline activities and off-the-beaten-path suggestions."),
    _scale("q88", "p3", "How comfortable are you walking alone in an unfamiliar city at night?", "Not at all", "Completely", "night_safety_comfort",
           "Low comfort = evening transport is booked and well-lit areas are favoured."),
    _scale("q89", "p3", "How comfortable are you where nobody speaks your language?", "Very uncomfortable", "No problem", "language_barrier_comfort",
           "Low comfort = translation tools, guided options and signage tips are added."),
    _scale("q90", "p3", "How important is eco-friendly / low-impact travel to you?", "Not a factor", "A top priority", "eco_priority",
           "Re-ranks transport and stay options when the trade-off is small."),

    # ---------------- p4: Food precision ----------------
    _scale("q91", "p4", "How much spice can you handle?", "None / mild only", "As hot as possible", "spice_tolerance",
           "Filters and ranks dishes and restaurants."),
    _scale("q92", "p4", "How adventurous are you with unfamiliar food?", "Familiar food only", "I'll try anything", "food_adventurousness",
           "Balances local-specialty suggestions with safe familiar options."),
    _q("q93", "p4", "How strict is your diet?", "single",
       show_if={"q": "q20", "includes_any": ["vegetarian", "vegan", "jain", "halal", "kosher", "gluten_free", "lactose_free"]},
       options=_o(("strict", "Strict - no exceptions"), ("flexible", "Strict when options exist, flexible otherwise"),
                  ("preference", "A preference, not a rule")),
       vec=_ord("diet_strictness", {"strict": 1.0, "flexible": .6, "preference": .3}),
       sensitive=True, privacy="dietary_needs",
       why="Strict = only verified venues; flexible = fall back to the closest match when none exists."),
    _q("q94", "p4", "Which of these also apply to your diet?", "multi",
       show_if={"q": "q20", "includes_any": ["vegetarian", "vegan", "jain"]},
       options=_o(("no_eggs", "No eggs"), ("no_dairy", "No dairy"), ("no_onion_garlic", "No onion or garlic"),
                  ("no_root_veg", "No root vegetables"), ("no_shared_cookware", "Not cooked in the same pans or oil as meat or fish"),
                  ("no_hidden_animal", "No hidden animal products (gelatin, rennet, fish sauce)")),
       vec={"type": "flags", "prefix": "diet", "options": ["no_eggs", "no_onion_garlic", "no_shared_cookware"]},
       sensitive=True, privacy="dietary_needs",
       why="'Vegetarian' means different things; this removes the ambiguity."),
    _q("q95", "p4", "Which food allergens must be avoided?", "multi",
       show_if={"q": "q10", "includes_any": ["food_allergies"]},
       options=_o(("peanuts", "Peanuts"), ("tree_nuts", "Tree nuts"), ("shellfish", "Shellfish"), ("fish", "Fish"),
                  ("milk", "Milk / dairy"), ("eggs", "Eggs"), ("gluten", "Wheat / gluten"), ("soy", "Soy"), ("sesame", "Sesame")),
       vec={"type": "flags", "prefix": "allergen",
            "options": ["peanuts", "tree_nuts", "shellfish", "fish", "milk", "eggs", "gluten", "soy", "sesame"]},
       sensitive=True, privacy="health_travel_needs",
       why="Each allergen becomes a hard constraint (a penalty mask in the RL state): the agent must never recommend it."),
    _q("q96", "p4", "How serious are these allergies?", "single",
       show_if={"q": "q95", "includes_any": ["peanuts", "tree_nuts", "shellfish", "fish", "milk", "eggs", "gluten", "soy", "sesame"]},
       options=_o(("mild", "Mild discomfort"), ("moderate", "Significant reaction"), ("severe", "Severe - I carry emergency medication")),
       vec=_ord("allergy_severity", {"mild": .33, "moderate": .66, "severe": 1.0}),
       sensitive=True, privacy="health_travel_needs",
       why="Severe allergies add emergency-number and medication reminders and stricter venue checks."),
    _q("q97", "p4", "When do you usually eat main meals?", "single",
       options=_o(("early", "Early (dinner before 7 pm)"), ("standard", "Standard (dinner 7-9 pm)"), ("late", "Late (dinner after 9 pm)")),
       vec=_ord("meal_timing", {"early": .1, "standard": .5, "late": .9}),
       why="Matches restaurant opening hours to your routine."),
    _q("q98", "p4", "Which drinks matter to you?", "multi", exclusive="none",
       options=_o(("coffee", "Good coffee"), ("tea", "Tea"), ("alcohol", "Alcohol (bars / local drinks)"),
                  ("bottled_water", "Only bottled or filtered water"), ("fresh_juice", "Fresh juice"), ("none", "None of these")),
       vec={"type": "flags", "prefix": "drink", "options": ["alcohol", "bottled_water"]},
       why="Alcohol-free or water-safety needs change venue and supply suggestions."),
    _q("q99", "p4", "What do you typically spend on a main meal?", "single",
       options=_o(("street", "Street-food level"), ("casual", "Casual restaurant"), ("midrange", "Mid-range sit-down"), ("fine", "Fine dining")),
       vec=_ord("meal_budget", {"street": .15, "casual": .4, "midrange": .7, "fine": 1.0}),
       privacy="budget_prefs",
       why="Separates food budget from overall budget tier."),
    _q("q100", "p4", "Foods you won't eat (not allergies), e.g. mushrooms, organ meats, very sweet desserts", "text",
       placeholder="Anything you simply dislike", why="Soft dislikes are used to rank, not to block.", privacy="dietary_needs"),
    _q("q101", "p4", "Cuisines or dishes you love", "text",
       placeholder="e.g. ramen, South Indian breakfast, Mediterranean seafood", why="Boosts matching restaurants and food tours."),
    _q("q102", "p4", "What cooking facilities do you need at your stay?", "multi",
       show_if={"q": "q22", "includes_any": ["cook_own", "mix_all"]},
       options=_o(("kettle_micro", "Kettle / microwave"), ("stove", "Stove and basic pots"),
                  ("full_kitchen", "Full kitchen"), ("fridge", "Fridge")),
       vec={"type": "count", "name": "kitchen_needs", "max": 4},
       why="Filters accommodation and tells you which groceries to look for."),

    # ---------------- p5: Health, safety (q10, q11 carried over) ----------------
    _q("q103", "p5", "Which medication logistics apply to you?", "multi", exclusive="none",
       show_if={"q": "q11", "includes_any": ["personal_medication"]},
       options=_o(("fridge", "Needs refrigeration"), ("documents", "Needs a doctor's letter or prescription copy"),
                  ("dosing_schedule", "Strict dosing times across time zones"), ("controlled", "Contains a controlled substance"),
                  ("none", "None of these")),
       vec={"type": "count", "name": "med_logistics_load", "max": 4, "exclude": ["none"]},
       sensitive=True, privacy="health_travel_needs",
       why="Adds carry-on, documentation and refrigeration checks to the packing and reminder lists."),
    _q("q104", "p5", "Which kinds of transport make you feel unwell?", "multi", exclusive="none",
       options=_o(("bus_winding", "Buses / winding roads"), ("car", "Cars"), ("boat", "Boats / ferries"),
                  ("flight_turbulence", "Turbulent flights"), ("train", "Trains"), ("none", "None")),
       vec={"type": "count", "name": "motion_sensitivity", "max": 5, "exclude": ["none"]},
       sensitive=True, privacy="health_travel_needs",
       why="Down-ranks the problem modes and suggests seat/route tips."),
    _q("q105", "p5", "Should the assistant remind you to share your itinerary or check in with someone?", "single",
       options=_o(("always", "Yes, always"), ("risky", "Only for solo, remote or late-night plans"), ("never", "No")),
       vec=_ord("safety_checkin", {"always": 1.0, "risky": .5, "never": .1}),
       why="Controls safety reminders."),

    # ---------------- p6: Interests deep-dive ----------------
    _q("q106", "p6", "How central is photography to your trips?", "single",
       show_if={"q": "q5", "includes_any": ["photography"]},
       options=_o(("casual", "Casual phone photos"), ("enthusiast", "Enthusiast - I plan around good light"),
                  ("serious", "Serious - tripod, lenses or drone")),
       vec=_ord("photo_commitment", {"casual": .3, "enthusiast": .7, "serious": 1.0}),
       privacy="interests_hobbies",
       why="Higher commitment = golden-hour scheduling, viewpoint ranking and gear-weight in packing."),
    _q("q107", "p6", "Which cultural themes interest you?", "multi",
       show_if={"any": [{"q": "q14", "includes_any": ["historical_sites", "museums_art", "religious_spiritual"]},
                        {"q": "q5", "includes_any": ["culture_history"]}]},
       options=_o(("ancient", "Ancient history"), ("medieval", "Medieval"), ("colonial", "Colonial era"),
                  ("modern_art", "Modern art"), ("local_history", "Local / folk history"), ("war_heritage", "War heritage"),
                  ("religious_arch", "Religious architecture"), ("crafts", "Traditional crafts")),
       privacy="interests_hobbies",
       why="Ranks heritage sites by theme rather than fame."),
    _q("q108", "p6", "What is the most demanding nature activity you'd actually do?", "single",
       show_if={"any": [{"q": "q14", "includes_any": ["mountains_nature", "forests_wildlife"]},
                        {"q": "q5", "includes_any": ["nature", "adventure"]}]},
       options=_o(("viewpoints", "Scenic viewpoints only"), ("easy_trails", "Easy trails"), ("day_hikes", "Full-day hikes"),
                  ("multi_day", "Multi-day treks / camping"), ("technical", "Technical climbs / rafting")),
       vec=_ord("nature_intensity", {"viewpoints": .2, "easy_trails": .4, "day_hikes": .6, "multi_day": .8, "technical": 1.0}),
       privacy="interests_hobbies",
       why="Sets the upper bound on trail difficulty in recommendations."),
    _q("q109", "p6", "When planning a new trip, what do you lean towards?", "single",
       options=_o(("explore_new", "Somewhere completely new"), ("similar_vibes", "Somewhere with a similar feel to past favourites"),
                  ("familiar_return", "Returning to places I love")),
       vec=_ord("exploration_pref", {"explore_new": 1.0, "similar_vibes": .5, "familiar_return": .1}),
       why="Sets the explore-vs-exploit balance of the agent for this user."),

    # ---------------- p7: Packing, documents, money (q30, q38, q39 carried over) ----------------
    _q("q110", "p7", "Will you do laundry on longer trips?", "single",
       options=_o(("yes_often", "Yes, happily"), ("once", "Once if needed"), ("no", "No - I pack enough")),
       vec=_ord("laundry_willingness", {"yes_often": 1.0, "once": .5, "no": .1}),
       why="Willing to launder = smaller packing list."),
    _q("q111", "p7", "Which electronics do you usually carry?", "multi",
       options=_o(("phone", "Phone"), ("laptop", "Laptop"), ("tablet", "Tablet"), ("camera", "Camera"), ("drone", "Drone"),
                  ("power_bank", "Power bank"), ("smartwatch", "Smartwatch"), ("e_reader", "E-reader")),
       vec={"type": "count", "name": "electronics_load", "max": 8},
       why="Adds adapter, charger and cabin-battery rules to the checklist."),
    _q("q112", "p7", "Which clothing needs apply?", "multi",
       options=_o(("waterproof", "Waterproof jacket always"), ("thermal", "Thermal base layers"), ("formal", "A formal / smart outfit"),
                  ("modest", "Modest clothing (religious sites)"), ("swim", "Swimwear"), ("sport", "Hiking / sports gear")),
       vec={"type": "flags", "prefix": "clothing", "options": ["waterproof", "thermal", "formal", "modest"]},
       why="Always-include items for the packing list."),
    _q("q113", "p7", "Which documents or cards do you currently hold?", "multi", exclusive="none",
       options=_o(("passport", "Valid passport"), ("idp", "International driving permit"), ("student_card", "Student ID (discounts)"),
                  ("visa", "A visa valid for a common destination"), ("vaccination_cert", "Vaccination certificate"), ("none", "None of these")),
       vec={"type": "count", "name": "doc_inventory", "max": 5, "exclude": ["none"]},
       why="Shows which documents the assistant still needs to remind you about."),
    _q("q114", "p7", "What is your passport status?", "single",
       options=_o(("valid", "Valid for 6+ months"), ("expiring", "Expires within 6 months"),
                  ("applying", "Applying / renewing"), ("none", "I don't have one yet")),
       vec=_ord("passport_readiness", {"valid": 1.0, "expiring": .5, "applying": .25, "none": .05}),
       why="Passport problems must be fixed before an international booking is suggested."),
    _q("q115", "p7", "Do you usually buy travel insurance?", "single",
       options=_o(("always", "Always"), ("long_trips", "Only on long / international trips"), ("never", "Never")),
       vec=_ord("insurance_habit", {"always": 1.0, "long_trips": .5, "never": .1}),
       why="Decides whether insurance reminders appear before departure."),
    _q("q116", "p7", "How do you usually pay when travelling?", "single",
       options=_o(("digital", "Cards / UPI / wallets mostly"), ("mix", "A mix of cash and digital"), ("cash", "Mostly cash")),
       vec=_ord("cash_reliance", {"digital": .1, "mix": .5, "cash": 1.0}),
       why="Cash-reliant travellers get ATM and exchange guidance and cash-friendly venues."),
    _q("q117", "p7", "How much mobile data do you need on a trip?", "single",
       options=_o(("constant", "Always connected (maps, work, streaming)"), ("moderate", "Maps and messaging"), ("minimal", "Offline is fine")),
       vec=_ord("connectivity_need", {"constant": 1.0, "moderate": .5, "minimal": .1}),
       why="Triggers eSIM / roaming or offline-map suggestions."),
    _q("q118", "p7", "What do you typically spend per night on accommodation?", "single",
       options=SPEND_OPTS, privacy="budget_prefs",
       vec=_ord("stay_budget", {"lt_20": .1, "20_50": .3, "50_100": .55, "100_200": .8, "gt_200": 1.0}),
       why="A real number-range is more precise than a budget label. (USD equivalent)"),
    _q("q119", "p7", "What do you typically spend per day on food, local transport and activities (excluding stay and flights)?", "single",
       options=SPEND_OPTS, privacy="budget_prefs",
       vec=_ord("daily_spend", {"lt_20": .1, "20_50": .3, "50_100": .55, "100_200": .8, "gt_200": 1.0}),
       why="Caps daily recommendations. (USD equivalent)"),
    _q("q120", "p7", "Which languages do you speak comfortably?", "multi",
       options=_o(("english", "English"), ("hindi", "Hindi"), ("spanish", "Spanish"), ("french", "French"), ("german", "German"),
                  ("arabic", "Arabic"), ("mandarin", "Mandarin"), ("japanese", "Japanese"), ("other", "Other")),
       why="Decides when translation tools or guided options are suggested."),

    # ---------------- p8: Assistant behaviour (more carried-over questions) ----------------
    _q("q121", "p8", "How much explanation do you want with each recommendation?", "single",
       options=_o(("brief", "Brief - just the recommendation"), ("short_reason", "A one-line reason"),
                  ("full", "Full reasoning and alternatives")),
       vec=_ord("explanation_detail", {"brief": .2, "short_reason": .55, "full": 1.0}),
       why="Sets the verbosity of recommendation explanations."),
]

# --------------------------------------------------------------------------------------
# Questions that already existed in questionnaire.py but were never rendered in the UI.
# They are carried into Level 3 so they finally get asked. {qid: (section, extras)}
# --------------------------------------------------------------------------------------
CARRYOVER: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "q10": ("p5", {"exclusive": "no_concerns", "sensitive": True, "privacy": "health_travel_needs",
                   "why": "Allergy triggers become hard safety constraints for food, activities and packing."}),
    "q11": ("p5", {"sensitive": True, "privacy": "health_travel_needs",
                   "why": "Decides carry-on rules, document reminders and refrigeration needs."}),
    "q30": ("p7", {"why": "Chooses whether packing lists optimise for weight, weather, activities or health."}),
    "q38": ("p7", {"why": "Sets when and how often reminders are sent."}),
    "q39": ("p7", {"why": "Personal checklist items the assistant always includes."}),
    "q6":  ("p8", {"why": "Tells the assistant which parts of planning to take off your hands."}),
    "q42": ("p8", {"vec": _ord("proactivity", {"only_when_asked": .1, "relevant_suggestions": .35, "notify_opportunities": .6,
                                               "alert_immediately": 1.0, "adapt_situation": .5}),
                   "why": "How often the agent may act without being asked (its exploration budget)."}),
    "q43": ("p8", {"exclusive": "urgent_only", "why": "Defines which events may trigger unsolicited alerts."}),
    "q44": ("p8", {"why": "How the assistant behaves when its data is uncertain."}),
    "q45": ("p8", {"why": "How the agent treats a rejected recommendation, which is its learning signal."}),
    "q46": ("p8", {"vec": _ord("update_frequency", {"only_important": .1, "before_activity": .4, "morning_briefing": .6, "periodic_day": 1.0}),
                   "why": "Sets the notification cadence during a trip."}),
    "q47": ("p8", {"why": "Controls which categories of your answers are actually saved. This is enforced when you save."}),
    "q49": ("p8", {"why": "Tells the assistant what to show alongside a recommendation."}),
    "q50": ("p8", {"why": "Anything listed here is something you do not want remembered."}),
    "q51": ("p8", {"why": "Whether the app should surface edit/delete controls for saved data."}),
    "q54": ("p8", {"why": "Open-ended: reveals needs the fixed questions missed."}),
    "q55": ("p8", {"why": "Open-ended: becomes the user's top failure cases to avoid."}),
    "q56": ("p8", {"why": "Open-ended catch-all."}),
}

# --------------------------------------------------------------------------------------
# Assemble the bank (ordered by section so feature order is deterministic)
# --------------------------------------------------------------------------------------
def _build_bank() -> Dict[str, Dict[str, Any]]:
    bank: Dict[str, Dict[str, Any]] = {}
    for sec in PRECISION_SECTIONS:
        sid = sec["id"]
        for qid, (csec, extras) in CARRYOVER.items():
            if csec == sid:
                q = copy.deepcopy(BASE_QUESTIONS[qid])
                q.update({"section": sid, "tier": "precision", "carried_over": True})
                q.update(copy.deepcopy(extras))
                bank[qid] = q
        for q in NEW_QUESTIONS:
            if q["section"] == sid:
                bank[q["id"]] = q
    return bank

PRECISION_QUESTIONS: Dict[str, Dict[str, Any]] = _build_bank()
PRIVACY_CATEGORIES = ["interests_hobbies", "travel_prefs", "dietary_needs", "accessibility_needs",
                      "env_sensitivities", "budget_prefs", "health_travel_needs", "trip_feedback"]

# Level 1/2 answers (stored under different field names) that show_if rules may refer to, by question id
CONTEXT_QIDS = ["q3", "q5", "q14", "q20", "q22"]

def build_context_answers(base: Dict[str, Any], detailed: Dict[str, Any]) -> Dict[str, Any]:
    """Maps stored Level 1/2 answers to question ids so show_if rules can use them."""
    ctx: Dict[str, Any] = {}
    if base.get("companions"):
        ctx["q3"] = base["companions"]
    if base.get("travel_goals"):
        ctx["q5"] = list(base["travel_goals"])
    if base.get("place_interests"):
        ctx["q14"] = list(base["place_interests"])
    if base.get("dietary"):
        ctx["q20"] = list(base["dietary"])
    if detailed.get("meal_management"):
        ctx["q22"] = detailed["meal_management"]
    return ctx

def public_bank() -> Dict[str, Any]:
    """What the frontend receives: no internal vectorisation specs."""
    hidden = {"vec", "privacy"}
    questions = {qid: {k: v for k, v in q.items() if k not in hidden} for qid, q in PRECISION_QUESTIONS.items()}
    return {"sections": PRECISION_SECTIONS, "questions": questions, "total": len(questions),
            "new_count": len(NEW_QUESTIONS), "carried_over_count": len(CARRYOVER)}

# --------------------------------------------------------------------------------------
# Conditional visibility
# --------------------------------------------------------------------------------------
def _as_list(v: Any) -> List[Any]:
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple, set)) else [v]

def _cond_true(cond: Dict[str, Any], answers: Dict[str, Any]) -> bool:
    if "any" in cond:
        return any(_cond_true(c, answers) for c in cond["any"])
    if "all" in cond:
        return all(_cond_true(c, answers) for c in cond["all"])
    src = cond["q"]
    if src in PRECISION_QUESTIONS and not is_visible(src, answers):
        return False  # a follow-up of a hidden question is hidden too
    return any(x in cond["includes_any"] for x in _as_list(answers.get(src)))

def is_visible(qid: str, answers: Dict[str, Any]) -> bool:
    cond = PRECISION_QUESTIONS[qid].get("show_if")
    return True if not cond else _cond_true(cond, answers)

def _is_answered(v: Any) -> bool:
    return not (v is None or v == "" or v == [] or v == {})

# --------------------------------------------------------------------------------------
# Validation, sanitising, privacy
# --------------------------------------------------------------------------------------
def validate_answers(raw: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[Dict[str, Any], List[str]]:
    """Returns (clean_answers, errors). Unanswered values are dropped. Answers to hidden questions are dropped."""
    errors: List[str] = []
    clean: Dict[str, Any] = {}
    for qid, val in (raw or {}).items():
        q = PRECISION_QUESTIONS.get(qid)
        if q is None:
            errors.append(f"{qid}: unknown question")
            continue
        if not _is_answered(val):
            continue
        t = q["type"]
        ids = [o["id"] for o in q.get("options", [])]
        if t == "single":
            if not isinstance(val, str) or val not in ids:
                errors.append(f"{qid}: invalid option")
                continue
        elif t == "multi":
            if not isinstance(val, list) or any(not isinstance(x, str) or x not in ids for x in val) or len(set(val)) != len(val):
                errors.append(f"{qid}: invalid options")
                continue
            if q.get("max") and len(val) > q["max"]:
                errors.append(f"{qid}: choose at most {q['max']}")
                continue
            if q.get("exclusive") and q["exclusive"] in val and len(val) > 1:
                errors.append(f"{qid}: '{q['exclusive']}' cannot be combined with other options")
                continue
        elif t == "scale":
            if isinstance(val, bool) or not isinstance(val, int) or not 1 <= val <= 5:
                errors.append(f"{qid}: scale answer must be an integer 1-5")
                continue
        elif t == "number":
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not q["min"] <= val <= q["max"]:
                errors.append(f"{qid}: number must be between {q['min']} and {q['max']}")
                continue
        elif t == "text":
            if not isinstance(val, str):
                errors.append(f"{qid}: text expected")
                continue
            val = val.strip()[:500]
            if not val:
                continue
        clean[qid] = val

    full = {**(context or {}), **clean}
    clean = {qid: v for qid, v in clean.items() if is_visible(qid, full)}  # drop stale answers to hidden questions
    return clean, errors

def apply_privacy_filter(answers: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """If the user answered Q47 ('what may be saved'), drop answers in categories they did not allow."""
    allowed = answers.get("q47")
    if not allowed:
        return dict(answers), []
    kept, dropped = {}, []
    for qid, v in answers.items():
        cat = PRECISION_QUESTIONS[qid].get("privacy")
        if cat and cat in PRIVACY_CATEGORIES and cat not in allowed:
            dropped.append(qid)
        else:
            kept[qid] = v
    return kept, dropped

# --------------------------------------------------------------------------------------
# Vectorisation
# --------------------------------------------------------------------------------------
def get_precision_feature_names() -> List[str]:
    names: List[str] = []
    for q in PRECISION_QUESTIONS.values():
        spec = q.get("vec")
        if not spec:
            continue
        if spec["type"] == "flags":
            names.extend(f"{spec['prefix']}_{o}" for o in spec["options"])
        else:
            names.append(spec["name"])
    names.append("precision_coverage")
    return names

def coverage(answers: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[int, int]:
    full = {**(context or {}), **answers}
    visible = [qid for qid in PRECISION_QUESTIONS if is_visible(qid, full)]
    answered = [qid for qid in visible if _is_answered(answers.get(qid))]
    return len(answered), len(visible)

def build_precision_vector(answers: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[List[float], List[str]]:
    """
    Encoding rules (all features in [0, 1]):
      - question hidden by show_if         -> 0.0 (not applicable; conditional ordinals never use 0.0 as a real value)
      - question visible but unanswered    -> 0.5 neutral for scales/numbers/ordinals, 0.0 for flags/counts
      - scale 1-5                          -> (v-1)/4
      - number                             -> (v-min)/(max-min)
      - ordinal single choice              -> value from the question's "map"
      - flags                              -> one 0/1 dimension per listed option (allergens etc.)
      - count                              -> number selected / max
      - last dimension 'precision_coverage' = answered / applicable questions, so the agent knows how reliable the state is
    """
    full = {**(context or {}), **answers}
    vec: List[float] = []
    for qid, q in PRECISION_QUESTIONS.items():
        spec = q.get("vec")
        if not spec:
            continue
        visible = is_visible(qid, full)
        val = answers.get(qid) if visible else None
        answered = visible and _is_answered(val)
        t = spec["type"]
        if t == "flags":
            chosen = set(_as_list(val)) if answered else set()
            vec.extend(1.0 if o in chosen else 0.0 for o in spec["options"])
        elif t == "count":
            n = len([x for x in _as_list(val) if x not in spec.get("exclude", [])]) if answered else 0
            vec.append(min(n / spec["max"], 1.0))
        elif not visible:
            vec.append(0.0)
        elif not answered:
            vec.append(0.5)
        elif t == "scale":
            vec.append((val - 1) / 4)
        elif t == "number":
            lo, hi = q["min"], q["max"]
            vec.append((min(max(val, lo), hi) - lo) / (hi - lo))
        elif t == "ordinal":
            vec.append(spec["map"][val])
    n_ans, n_vis = coverage(answers, context)
    vec.append(round(n_ans / n_vis, 4) if n_vis else 0.0)
    return [round(v, 4) for v in vec], get_precision_feature_names()

# --------------------------------------------------------------------------------------
# Insights: readable planner rules derived from the answers
# --------------------------------------------------------------------------------------
def _label(qid: str, opt_id: str) -> str:
    for o in PRECISION_QUESTIONS[qid].get("options", []):
        if o["id"] == opt_id:
            return o["label"]
    return opt_id

def derive_insights(answers: Dict[str, Any], context: Dict[str, Any] = None) -> List[Dict[str, str]]:
    a = {**(context or {}), **answers}
    out: List[Dict[str, str]] = []

    def add(kind, text):
        out.append({"kind": kind, "text": text})

    def sel(qid):
        return _as_list(a.get(qid))

    def low(qid, n=2):
        return isinstance(a.get(qid), int) and a[qid] <= n

    allergens = sel("q95")
    if allergens:
        names = ", ".join(_label("q95", x).lower() for x in allergens)
        add("constraint", f"Hard food-safety constraint: never recommend anything containing {names}.")
        if a.get("q96") == "severe":
            add("reminder", "Severe allergy: remind about emergency medication in cabin baggage and look up the local emergency number on arrival.")
    if low("q78") or low("q80"):
        add("rule", f"Cold/wind-sensitive: packing adds a windproof outer layer and an insulating mid-layer whenever the forecast is below {COLD_C}\u00b0C or gusts exceed {WIND_KMH} km/h.")
    if a.get("q60") in ("hot_humid", "hot_dry") and isinstance(a.get("q78"), int) and a["q78"] <= 3:
        add("rule", "Big home-vs-destination climate gap risk: warn before booking if the destination is much colder than home, so you don't have to buy clothing on arrival.")
    if low("q81"):
        add("rule", "Rain-averse: every outdoor plan gets an indoor fallback, and the hourly forecast is checked the evening before.")
    if low("q79") or low("q82"):
        add("rule", "Heat/humidity-sensitive: outdoor activities are scheduled early morning or late afternoon, with hydration and sun-protection reminders.")
    if a.get("q61") == "carry_on":
        add("rule", "Carry-on only: packing list is capped to cabin-bag size, with a liquids-limit reminder for flights.")
    meds = set(sel("q103"))
    if meds & {"fridge", "documents", "dosing_schedule", "controlled"}:
        add("reminder", "Medication logistics: keep medication in cabin baggage, carry a doctor's letter/prescription copy, and plan refrigeration or time-zone dosing where relevant.")
    if a.get("q114") in ("expiring", "applying", "none") and a.get("q58") in ("regional", "long_haul"):
        add("reminder", "Passport needs attention before any international booking (many countries require 6+ months of validity).")
    if isinstance(a.get("q73"), (int, float)) and a["q73"] <= 4 or a.get("q74") == "m10" or (isinstance(a.get("q71"), int) and a["q71"] >= 4):
        km = f"about {a['q73']:g} km/day" if isinstance(a.get("q73"), (int, float)) else "short distances"
        add("rule", f"Limited walking/stamina: routes are capped at {km} and pass seating or cafe stops.")
    if a.get("q69") == "late" or a.get("q70") in ("late", "very_late"):
        add("rule", "Late rhythm: no activities before 09:30 and evening plans may run past 22:00.")
    elif a.get("q69") in ("very_early", "early") and a.get("q70") == "early_eve":
        add("rule", "Early rhythm: day starts by 07:00 and finishes before 20:00.")
    if a.get("q64") in ("infant", "toddler"):
        add("rule", "Young child: nap windows, stroller-friendly routes and child-safe food are built into every day.")
    if low("q88"):
        add("rule", "Low night-time comfort: evening transport is pre-booked and well-lit areas are favoured.")
    if a.get("q93") == "strict":
        add("rule", "Strict diet: only venues with verified menus are recommended. The assistant never guesses.")
    if a.get("q77") == "very":
        add("rule", "Sleep-sensitive: accommodation ranking prioritises quiet rooms and bed-quality reviews.")
    if a.get("q106") in ("enthusiast", "serious"):
        add("rule", "Photography focus: activities are timed for golden hour and gear weight is counted in the packing list.")
    if a.get("q116") == "cash":
        add("rule", "Cash-reliant: includes ATM/exchange guidance and favours venues that accept cash.")
    if a.get("q117") == "constant":
        add("reminder", "High data need: suggests an eSIM or roaming plan before departure.")
    elif a.get("q117") == "minimal":
        add("reminder", "Low data need: suggests downloading offline maps before departure.")
    return out

def summarize_precision(answers: Dict[str, Any], context: Dict[str, Any] = None) -> str:
    n_ans, n_vis = coverage(answers, context)
    insights = derive_insights(answers, context)
    constraints = sum(1 for i in insights if i["kind"] == "constraint")
    pct = round(100 * n_ans / n_vis) if n_vis else 0
    return f"Precision profile: {n_ans}/{n_vis} applicable questions answered ({pct}%), {constraints} hard constraints, {len(insights)} planner rules active."
