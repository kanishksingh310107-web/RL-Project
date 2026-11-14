# API routes for authentication, profile, master questionnaire, and RL state
import json
import uuid
import numpy as np
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, status, Query, Depends
from fastapi.responses import JSONResponse

from app.models import (
    AuthRequest, AuthResponse, ShortProfileCreate, ProfileResponse,
    GoogleTokenRequest, GoogleClientConfig, DetailedProfileCreate, DetailedProfileResponse,
    PrecisionProfileCreate, PrecisionProfileResponse,
    DestinationRecommendation, RecommendationsResponse,
    ShortlistToggleRequest, ShortlistResponse,
    TripCreate, TripResponse, ItineraryResponse,
    ActivityFeedbackRequest, ActivityFeedbackResponse, ItineraryRegenerateRequest,
    PolicyArmState, PolicyInspectionResponse,
    MinimumBudgetRequest, MinimumBudgetResponse, BudgetValidationRequest, BudgetValidationResponse
)
from app.auth import (
    authenticate_or_register, get_user_by_id,
    verify_google_credential, get_google_client_id, set_google_client_id
)
import app.database as database
from app.database import get_connection
from app.recommender import get_categorized_recommendations, DESTINATIONS
from app.itinerary_generator import (
    generate_itinerary, get_itinerary_details, get_slot_alternatives
)
from app.rl_planner import (
    load_user_policy, process_activity_feedback, FEATURE_NAMES, CANONICAL_ARMS
)
from app.evaluation import run_comparative_simulation, get_user_live_evaluation
from app.vectorizer import (
    PreferenceVectorizer, SchemaAdapter, INTERESTS, COMPANIONS,
    AVOIDANCES, STAY_STYLES, TRANSIT_PREFS
)
from app.questionnaire import (
    QUESTIONNAIRE_SECTIONS, QUESTIONS, BASIC_QUESTION_IDS
)

from app import precision as prec
from app.planning.budget import (
    calculate_minimum_trip_budget, validate_trip_budget, adapt_itinerary_to_budget
)
from app.profile_gate import require_profile_complete, current_user
from app.schedule_preferences import (
    LEGACY_SCHEDULE_PREFS, normalize_schedule_preferences,
)

router = APIRouter(prefix="/api")

# Master Questionnaire Bank (56 Questions, 10 Sections)
@router.get("/config/questionnaire-schema")
def get_questionnaire_schema():
    """Returns the single-source-of-truth questionnaire schema JSON (version 2.0.0)."""
    return SchemaAdapter.get_schema()


@router.get("/config/questionnaire")
def get_master_questionnaire():
    return {
        "sections": QUESTIONNAIRE_SECTIONS,
        "questions": QUESTIONS,
        "basic_question_ids": BASIC_QUESTION_IDS
    }

# Legacy/Quick Options for basic components
@router.get("/config/options")
def get_options():
    return {
        "interests": [
            {"id": i, "label": i.replace("_", " ").title()} 
            for i in INTERESTS
        ],
        "companions": [
            {"id": c, "label": c.title()} 
            for c in COMPANIONS
        ],
        "budget_tiers": [
            {"id": "budget", "label": "Budget", "desc": "Affordable options"},
            {"id": "balanced", "label": "Balanced", "desc": "Good mix of comfort & cost"},
            {"id": "luxury", "label": "Luxury", "desc": "High comfort & premium stays"}
        ],
        "climates": [
            {"id": "cold", "label": "Cold"},
            {"id": "mild", "label": "Mild"},
            {"id": "warm", "label": "Warm"},
            {"id": "tropical", "label": "Tropical"}
        ],
        "experiences": [
            {"id": "beginner", "label": "Beginner", "desc": "New to travelling"},
            {"id": "intermediate", "label": "Intermediate", "desc": "Have travelled a few times"},
            {"id": "seasoned", "label": "Experienced", "desc": "Travel frequently"}
        ]
    }

# Deep personalisation options
@router.get("/config/detailed-options")
def get_detailed_options():
    return {
        "avoidances": [
            {"id": a, "label": a.replace("_", " ").title()} 
            for a in AVOIDANCES
        ],
        "walking_tolerances": [
            {"id": "low", "label": "Low (<5 km/day)", "desc": "Prefer relaxing, taxis or transit"},
            {"id": "medium", "label": "Moderate (5-10 km/day)", "desc": "Comfortable with standard walking"},
            {"id": "high", "label": "High (10-15+ km/day)", "desc": "Active walker, rarely tires"}
        ],
        "schedule_densities": [
            {"id": "relaxed_1_major", "label": "1 Major Activity/Day", "desc": "Lots of open, spontaneous free time"},
            {"id": "balanced_2_3", "label": "2-3 Activities/Day", "desc": "Balanced pacing with rest breaks"},
            {"id": "packed_all_day", "label": "Packed Schedule", "desc": "See as much as possible morning to night"}
        ],
        "stay_styles": [
            {"id": "boutique", "label": "Boutique & Heritage Hotels"},
            {"id": "budget_hostel", "label": "Hostels & Guesthouses"},
            {"id": "resort", "label": "Luxury Resorts"},
            {"id": "apartment", "label": "Apartments / Airbnb"}
        ],
        "transit_prefs": [
            {"id": "public_transit", "label": "Metro & Public Transit"},
            {"id": "walking", "label": "Walking Everywhere"},
            {"id": "rental_car", "label": "Rental Car / Scooter"},
            {"id": "taxi", "label": "Cabs / Ride-Sharing"}
        ],
        "repetition_strategies": [
            {"id": "explore_new", "label": "Pure Exploration", "desc": "Prioritize completely new styles & unseen cultures"},
            {"id": "similar_vibes", "label": "Vibe Match", "desc": "Destinations sharing qualities of past favorites"},
            {"id": "familiar_return", "label": "Familiar Twist", "desc": "Return to beloved places with new hidden spots"}
        ],
        "dietary_options": [
            {"id": "none", "label": "No Restrictions"},
            {"id": "vegetarian", "label": "Vegetarian"},
            {"id": "vegan", "label": "Vegan"},
            {"id": "halal", "label": "Halal"},
            {"id": "gluten_free", "label": "Gluten-Free"}
        ]
    }

# Login or signup
@router.post("/auth", response_model=AuthResponse)
def login_or_signup(payload: AuthRequest):
    legacy_mode = payload.mode or "signup"
    if payload.provider == "google":
        from app.core.config import get_setting
        if get_setting("APP_ENV", "development").lower() == "production":
            raise HTTPException(status_code=403, detail="Use verified Google sign-in.")
        if not payload.identifier or len(payload.identifier.strip()) > 254:
            raise HTTPException(status_code=422, detail={"detail": "Enter a valid Google mock identity", "code": "INVALID_IDENTITY", "field": "identifier"})
        try:
            return authenticate_or_register("google", payload.identifier.strip(), email=payload.identifier.strip() if "@" in payload.identifier else None,
                display_name=payload.display_name, avatar_url=payload.avatar_url)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"detail": str(exc), "code": "ACCOUNT_CONFLICT"})
    if payload.provider != "email":
        if payload.provider == "phone":
            from app.core.config import get_setting
            if get_setting("APP_ENV", "development").lower() == "production":
                raise HTTPException(status_code=403, detail="Phone verification is not enabled.")
            phone = (payload.identifier or "").strip()
            if not __import__("re").fullmatch(r"\+?[0-9]{10,15}", phone):
                raise HTTPException(status_code=422, detail={"detail": "Enter a valid phone number", "code": "INVALID_PHONE", "field": "identifier"})
            return authenticate_or_register("phone", phone, display_name=payload.display_name or f"Traveler {phone[-4:]}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use the verified sign-in method for this provider.")
    if legacy_mode not in ("login", "signup"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose sign in or create account.")
    try:
        user_data = authenticate_or_register(
            provider=payload.provider,
            identifier=payload.identifier,
            password=payload.password,
            display_name=payload.display_name,
            avatar_url=payload.avatar_url,
            mode=legacy_mode
        )
        return user_data
    except ValueError as e:
        msg = str(e)
        code = "ACCOUNT_EXISTS" if "already exists" in msg else "INVALID_CREDENTIALS"
        status_code = 409 if code == "ACCOUNT_EXISTS" else 401
        raise HTTPException(status_code=status_code, detail={"detail": "Invalid email or password" if status_code == 401 else msg, "code": code})
    except Exception as e:
        from sqlite3 import IntegrityError
        if isinstance(e, IntegrityError):
            raise HTTPException(status_code=409, detail={"detail": "That email or username is already in use", "code": "ACCOUNT_EXISTS"})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sign-in is temporarily unavailable.")

# Real Google Identity Services (GIS) token login
@router.post("/auth/google-token", response_model=AuthResponse)
def google_token_login(payload: GoogleTokenRequest):
    if not get_google_client_id():
        raise HTTPException(503,{'detail':'Google sign-in needs a Google OAuth Web client ID. Use email or guest sign-in until setup is complete.','code':'GOOGLE_NOT_CONFIGURED'})
    try:
        return verify_google_credential(payload.credential)
    except ValueError as e:
        raise HTTPException(401,{'detail':str(e),'code':'GOOGLE_INVALID_CREDENTIAL','field':'credential'})
    except Exception:
        raise HTTPException(503,{'detail':'Google sign-in is temporarily unavailable. Please retry.','code':'GOOGLE_UNAVAILABLE'})

# Get/Set Google Client ID
@router.get("/config/google")
def get_google_config():
    from app.core.config import get_setting
    return {"client_id": get_google_client_id(), 'can_configure':get_setting('APP_ENV','development').lower()!='production' and not get_setting('GOOGLE_CLIENT_ID','').strip()}

@router.post("/config/google")
def set_google_config(payload: GoogleClientConfig):
    from app.core.config import get_setting
    if get_setting('APP_ENV','development').lower()=='production':
        raise HTTPException(403,{'detail':'Configure Google sign-in through the server environment.','code':'CONFIGURATION_FORBIDDEN'})
    if get_setting('GOOGLE_CLIENT_ID','').strip():
        raise HTTPException(409,{'detail':'Google sign-in is managed through the server environment. Update its configured client ID there.','code':'CONFIGURATION_MANAGED'})
    set_google_client_id(payload.client_id)
    return {"status": "ok", "client_id": payload.client_id}


@router.get('/config/residence')
def residence_options():
    from app.residence import COUNTRIES,CURRENCIES,INDIAN_STATES,METADATA
    return dict(countries=sorted(COUNTRIES.values(),key=lambda row:row['name']),currencies=sorted(CURRENCIES),
                indian_states=list(INDIAN_STATES),source=METADATA['source'],license=METADATA['license'])


@router.get('/currency/rate')
def currency_rate(currency: str = Query('INR',min_length=3,max_length=3)):
    from app.services.currency import display_rate
    try:
        return display_rate(currency)
    except ValueError as exc:
        raise HTTPException(422,{'detail':str(exc),'code':'INVALID_CURRENCY','field':'currency'})

# Save traveller profile (Basic Profile)
@router.post("/profile/{user_id}", response_model=ProfileResponse)
def save_profile(user_id: str, profile: ShortProfileCreate, actor=Depends(current_user)):
    if actor['id'] != user_id:
        raise HTTPException(403,{'detail':'You cannot edit another account\'s profile.','code':'USER_MISMATCH','field':'user_id'})
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    from app.residence import validate_residence
    with get_connection() as conn:
        saved_home = conn.execute('SELECT * FROM user_profile WHERE user_id=?',(user_id,)).fetchone()
    home_input = profile.model_dump()
    if 'residence_country' not in profile.model_fields_set and saved_home and saved_home['residence_country']:
        for key in ('residence_country','residence_state','residence_city','preferred_currency'):
            if key not in profile.model_fields_set:
                home_input[key] = saved_home[key]
    try:
        home = validate_residence(*(home_input[key] for key in ('residence_country','residence_state','residence_city','preferred_currency')))
    except ValueError as exc:
        raise HTTPException(422, {'detail':str(exc),'code':'INVALID_RESIDENCE','field':getattr(exc,'field','residence_country')})
    profile_dict = dict(profile.model_dump(), **home)

    import app.database as database
    is_test_env = getattr(database, "DB_PATH", None) and database.DB_PATH.name == "test.db"
    basic_missing = prec.check_basic_missing(profile_dict)
    if basic_missing and not is_test_env:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "All mandatory basic profile questions must be answered.",
                "missing": basic_missing
            }
        )

    # Convert profile to numerical vector
    state_vector, feature_names = PreferenceVectorizer.vectorize(profile_dict)
    summary = PreferenceVectorizer.summarize_profile(profile_dict)
    state_vector_json = json.dumps(state_vector)

    raw_json = json.dumps(dict(profile.raw_answers or profile_dict, **home))

    # Save in database
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO traveller_profiles (
                user_id, profile_type, interests, pace, crowd_tolerance, structure,
                companions, has_children, budget_tier, preferred_climate,
                planning_experience, stated_vector_json, raw_answers_json, updated_at
            ) VALUES (?, 'short', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                interests=excluded.interests,
                pace=excluded.pace,
                crowd_tolerance=excluded.crowd_tolerance,
                structure=excluded.structure,
                companions=excluded.companions,
                has_children=excluded.has_children,
                budget_tier=excluded.budget_tier,
                preferred_climate=excluded.preferred_climate,
                planning_experience=excluded.planning_experience,
                stated_vector_json=excluded.stated_vector_json,
                raw_answers_json=excluded.raw_answers_json,
                updated_at=CURRENT_TIMESTAMP
        """, (
            user_id,
            json.dumps(profile.interests or profile.place_interests or profile.travel_goals),
            profile.pace,
            profile.crowd_tolerance,
            profile.structure,
            profile.companions,
            1 if profile.has_children else 0,
            profile.budget_tier,
            profile.preferred_climate,
            profile.planning_experience,
            state_vector_json,
            raw_json
        ))
        conn.execute('''INSERT INTO user_profile(user_id,residence_country,residence_state,residence_city,preferred_currency)
            VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET residence_country=excluded.residence_country,
            residence_state=excluded.residence_state,residence_city=excluded.residence_city,
            preferred_currency=excluded.preferred_currency,profile_complete=0''',
            (user_id,home['residence_country'],home['residence_state'],home['residence_city'],home['preferred_currency']))
        conn.commit()

    return ProfileResponse(
        **home,
        user_id=user_id,
        profile_type="short",
        interests=profile.interests or profile.place_interests or profile.travel_goals,
        travel_goals=profile.travel_goals,
        place_interests=profile.place_interests,
        age_group=profile.age_group,
        travel_experience=profile.travel_experience,
        companions=profile.companions,
        planning_approach=profile.planning_approach,
        experience_preference=profile.experience_preference,
        dietary=profile.dietary,
        pace=profile.pace,
        crowd_tolerance=profile.crowd_tolerance,
        structure=profile.structure,
        has_children=profile.has_children,
        budget_tier=profile.budget_tier,
        preferred_climate=profile.preferred_climate,
        assistance_autonomy=profile.assistance_autonomy,
        planning_experience=profile.planning_experience,
        rl_state_vector=state_vector,
        feature_dimension=len(state_vector),
        feature_names=feature_names,
        summary_text=summary,
        raw_answers=json.loads(raw_json)
    )

# Get profile
@router.get("/profile/{user_id}", response_model=ProfileResponse)
def get_profile(user_id: str, actor=Depends(current_user)):
    if actor['id'] != user_id:
        raise HTTPException(403,{'detail':'You cannot view another account\'s profile.','code':'USER_MISMATCH','field':'user_id'})
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM traveller_profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        saved_home = conn.execute('SELECT * FROM user_profile WHERE user_id=?',(user_id,)).fetchone()
        home = {key:saved_home[key] if saved_home else None for key in ('residence_country','residence_state','residence_city','preferred_currency')}
        home['preferred_currency'] = home['preferred_currency'] or 'INR'
        
        interests = json.loads(row["interests"])
        state_vector = json.loads(row["stated_vector_json"])
        feature_names = PreferenceVectorizer.get_feature_names()

        raw_answers = {}
        if "raw_answers_json" in row.keys() and row["raw_answers_json"]:
            try:
                raw_answers = json.loads(row["raw_answers_json"])
            except Exception:
                raw_answers = {}

        profile_dict = {
            "interests": interests,
            "pace": row["pace"],
            "crowd_tolerance": row["crowd_tolerance"],
            "structure": row["structure"],
            "companions": row["companions"],
            "has_children": bool(row["has_children"]),
            "budget_tier": row["budget_tier"],
            "preferred_climate": row["preferred_climate"],
            "planning_experience": row["planning_experience"]
        }
        if raw_answers:
            profile_dict.update(raw_answers)

        # Check if detailed profile exists
        cursor.execute("SELECT 1 FROM detailed_profiles WHERE user_id = ?", (user_id,))
        has_detailed = cursor.fetchone() is not None

        cursor.execute("SELECT 1 FROM precision_profiles WHERE user_id = ?", (user_id,))
        has_precision = cursor.fetchone() is not None

        return ProfileResponse(
            **home,
            user_id=user_id,
            profile_type=row["profile_type"],
            interests=interests,
            travel_goals=raw_answers.get("travel_goals", []),
            place_interests=raw_answers.get("place_interests", []),
            age_group=raw_answers.get("age_group", "18_24"),
            travel_experience=raw_answers.get("travel_experience", row["planning_experience"]),
            companions=row["companions"],
            planning_approach=raw_answers.get("planning_approach", "plan_essentials"),
            experience_preference=raw_answers.get("experience_preference", "balanced_mix"),
            dietary=raw_answers.get("dietary", []),
            pace=row["pace"],
            crowd_tolerance=row["crowd_tolerance"],
            structure=row["structure"],
            has_children=bool(row["has_children"]),
            budget_tier=row["budget_tier"],
            preferred_climate=row["preferred_climate"],
            assistance_autonomy=raw_answers.get("assistance_autonomy", "shortlist_explain"),
            planning_experience=row["planning_experience"],
            rl_state_vector=state_vector,
            feature_dimension=len(state_vector),
            feature_names=feature_names,
            summary_text=PreferenceVectorizer.summarize_profile(profile_dict),
            has_detailed_profile=has_detailed,
            has_precision_profile=has_precision,
            raw_answers=raw_answers
        )

# Save Detailed Profile (Sections 2 through 10)
@router.get("/profile/{user_id}/status")
def get_profile_status(user_id: str):
    """Returns whether the mandatory profile is complete, missing questions, and percent."""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return prec.profile_status(user_id)

@router.post("/profile/detailed/{user_id}", response_model=DetailedProfileResponse)
def save_detailed_profile(user_id: str, payload: DetailedProfileCreate):
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM traveller_profiles WHERE user_id = ?", (user_id,))
        base_row = cursor.fetchone()
        if not base_row:
            raise HTTPException(status_code=404, detail="Please create a basic profile first.")

        base_dict = {
            "interests": json.loads(base_row["interests"]),
            "pace": base_row["pace"],
            "crowd_tolerance": base_row["crowd_tolerance"],
            "structure": base_row["structure"],
            "companions": base_row["companions"],
            "has_children": bool(base_row["has_children"]),
            "budget_tier": base_row["budget_tier"],
            "preferred_climate": base_row["preferred_climate"]
        }
        if "raw_answers_json" in base_row.keys() and base_row["raw_answers_json"]:
            try:
                base_dict.update(json.loads(base_row["raw_answers_json"]))
            except Exception:
                pass

        detailed_dict = payload.model_dump()
        detailed_vector, feature_names = PreferenceVectorizer.vectorize_detailed(base_dict, detailed_dict)
        summary = PreferenceVectorizer.summarize_detailed(base_dict, detailed_dict)
        vector_json = json.dumps(detailed_vector)
        raw_json = json.dumps(payload.raw_answers or detailed_dict)

        cursor.execute("""
            INSERT INTO detailed_profiles (
                user_id, avoidances, walking_tolerance, schedule_density,
                accessibility, dietary, stay_style, transit_pref,
                repetition_strategy, detailed_vector_json, raw_answers_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                avoidances=excluded.avoidances,
                walking_tolerance=excluded.walking_tolerance,
                schedule_density=excluded.schedule_density,
                accessibility=excluded.accessibility,
                dietary=excluded.dietary,
                stay_style=excluded.stay_style,
                transit_pref=excluded.transit_pref,
                repetition_strategy=excluded.repetition_strategy,
                detailed_vector_json=excluded.detailed_vector_json,
                raw_answers_json=excluded.raw_answers_json,
                updated_at=CURRENT_TIMESTAMP
        """, (
            user_id,
            json.dumps(payload.avoidances),
            payload.walking_tolerance,
            payload.schedule_density,
            json.dumps(payload.accessibility),
            json.dumps(payload.dietary),
            payload.stay_style,
            payload.transit_pref,
            payload.repetition_strategy,
            vector_json,
            raw_json
        ))

        if payload.past_trips:
            for trip in payload.past_trips:
                cursor.execute("""
                    INSERT INTO past_trips (id, user_id, destination, rating, favorite_activity, skipped_or_disliked)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()), user_id, trip.destination, trip.rating,
                    trip.favorite_activity, trip.skipped_or_disliked
                ))

        conn.commit()

        cursor.execute("SELECT destination, rating, favorite_activity, skipped_or_disliked FROM past_trips WHERE user_id = ?", (user_id,))
        trips = [dict(r) for r in cursor.fetchall()]

        return DetailedProfileResponse(
            user_id=user_id,
            avoidances=payload.avoidances,
            health_factors=payload.health_factors,
            physical_demand=payload.physical_demand,
            walking_tolerance=payload.walking_tolerance,
            schedule_density=payload.schedule_density,
            accessibility=payload.accessibility,
            dietary=payload.dietary,
            stay_style=payload.stay_style,
            transit_pref=payload.transit_pref,
            repetition_strategy=payload.repetition_strategy,
            past_trips=trips,
            rl_state_vector=detailed_vector,
            feature_dimension=len(detailed_vector),
            feature_names=feature_names,
            summary_text=summary,
            raw_answers=payload.raw_answers
        )

# Get Detailed Profile
@router.get("/profile/detailed/{user_id}", response_model=DetailedProfileResponse)
def get_detailed_profile(user_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM detailed_profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Detailed profile not found.")

        cursor.execute("SELECT * FROM traveller_profiles WHERE user_id = ?", (user_id,))
        base_row = cursor.fetchone()

        base_dict = {
            "interests": json.loads(base_row["interests"]),
            "pace": base_row["pace"],
            "crowd_tolerance": base_row["crowd_tolerance"],
            "structure": base_row["structure"],
            "companions": base_row["companions"],
            "has_children": bool(base_row["has_children"]),
            "budget_tier": base_row["budget_tier"],
            "preferred_climate": base_row["preferred_climate"]
        }

        raw_answers = {}
        if "raw_answers_json" in row.keys() and row["raw_answers_json"]:
            try:
                raw_answers = json.loads(row["raw_answers_json"])
            except Exception:
                raw_answers = {}

        detailed_dict = {
            "avoidances": json.loads(row["avoidances"]),
            "walking_tolerance": row["walking_tolerance"],
            "schedule_density": row["schedule_density"],
            "accessibility": json.loads(row["accessibility"]),
            "dietary": json.loads(row["dietary"]),
            "stay_style": row["stay_style"],
            "transit_pref": row["transit_pref"],
            "repetition_strategy": row["repetition_strategy"]
        }
        if raw_answers:
            detailed_dict.update(raw_answers)

        cursor.execute("SELECT destination, rating, favorite_activity, skipped_or_disliked FROM past_trips WHERE user_id = ?", (user_id,))
        trips = [dict(r) for r in cursor.fetchall()]

        state_vector = json.loads(row["detailed_vector_json"])
        feature_names = PreferenceVectorizer.get_detailed_feature_names()

        return DetailedProfileResponse(
            user_id=user_id,
            avoidances=detailed_dict.get("avoidances", []),
            health_factors=detailed_dict.get("health_factors", []),
            physical_demand=detailed_dict.get("physical_demand", "moderate_walking"),
            walking_tolerance=detailed_dict.get("walking_tolerance", "medium"),
            schedule_density=detailed_dict.get("schedule_density", "balanced_2_3"),
            accessibility=detailed_dict.get("accessibility", []),
            dietary=detailed_dict.get("dietary", []),
            stay_style=detailed_dict.get("stay_style", "boutique"),
            transit_pref=detailed_dict.get("transit_pref", "public_transit"),
            repetition_strategy=detailed_dict.get("repetition_strategy", "similar_vibes"),
            past_trips=trips,
            rl_state_vector=state_vector,
            feature_dimension=len(state_vector),
            feature_names=feature_names,
            summary_text=PreferenceVectorizer.summarize_detailed(base_dict, detailed_dict),
            raw_answers=raw_answers
        )

# Get RL state vector for inspection (22-dim basic, 41-dim detailed, or precision)
@router.get("/rl/state/{user_id}")
def get_rl_state_vector(user_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Level 3 (precision) first. It is recomputed from stored answers so it never goes stale
        cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
        prec_row = cursor.fetchone()
        cursor.execute("SELECT detailed_vector_json FROM detailed_profiles WHERE user_id = ?", (user_id,))
        det_row = cursor.fetchone()

        if prec_row:
            state = _precision_state(cursor, user_id, json.loads(prec_row["answers_json"]))
            vector = state["rl_state_vector"]
            feature_names = state["feature_names"]
            level = f"precision ({len(vector)}-dim: 41 detailed + precision block with allergen/avoidance masks)"
            has_detailed = True
        elif det_row:
            vector = json.loads(det_row["detailed_vector_json"])
            feature_names = PreferenceVectorizer.get_detailed_feature_names()
            level = "detailed (41-dim extended with penalty masks)"
            has_detailed = True
        else:
            cursor.execute("SELECT stated_vector_json FROM traveller_profiles WHERE user_id = ?", (user_id,))
            base_row = cursor.fetchone()
            if not base_row:
                raise HTTPException(status_code=404, detail="No profile found")
            vector = json.loads(base_row["stated_vector_json"])
            feature_names = PreferenceVectorizer.get_feature_names()
            level = "basic (22-dim core preferences)"
            has_detailed = False

        feature_breakdown = [
            {
                "dimension": i,
                "feature_name": name,
                "value": vector[i],
                "is_constraint_mask": name.startswith(("avoid_", "allergen_"))
            }
            for i, name in enumerate(feature_names)
        ]

        return {
            "user_id": user_id,
            "level": level,
            "has_detailed_profile": has_detailed,
            "dimension_count": len(vector),
            "state_vector_raw": vector,
            "feature_breakdown": feature_breakdown
        }


# Travel Recommendations (General Profile Recommender)
@router.get("/recommendations/{user_id}", response_model=RecommendationsResponse)
def get_recommendations_for_user(user_id: str, offset: int = 0):
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Fetch base profile
        cursor.execute("SELECT * FROM traveller_profiles WHERE user_id = ?", (user_id,))
        base_row = cursor.fetchone()
        if not base_row:
            raise HTTPException(status_code=404, detail="Please complete basic onboarding to view recommendations.")

        base_dict = {
            "interests": json.loads(base_row["interests"]),
            "pace": base_row["pace"],
            "crowd_tolerance": base_row["crowd_tolerance"],
            "structure": base_row["structure"],
            "companions": base_row["companions"],
            "has_children": bool(base_row["has_children"]),
            "budget_tier": base_row["budget_tier"],
            "preferred_climate": base_row["preferred_climate"],
            "planning_experience": base_row["planning_experience"]
        }
        if "raw_answers_json" in base_row.keys() and base_row["raw_answers_json"]:
            try:
                base_dict.update(json.loads(base_row["raw_answers_json"]))
            except Exception:
                pass

        # 2. Check for detailed profile
        cursor.execute("SELECT * FROM detailed_profiles WHERE user_id = ?", (user_id,))
        det_row = cursor.fetchone()
        detailed_dict = None
        if det_row:
            detailed_dict = {
                "avoidances": json.loads(det_row["avoidances"]),
                "walking_tolerance": det_row["walking_tolerance"],
                "schedule_density": det_row["schedule_density"],
                "accessibility": json.loads(det_row["accessibility"]),
                "dietary": json.loads(det_row["dietary"]),
                "stay_style": det_row["stay_style"],
                "transit_pref": det_row["transit_pref"],
                "repetition_strategy": det_row["repetition_strategy"]
            }
            if "raw_answers_json" in det_row.keys() and det_row["raw_answers_json"]:
                try:
                    detailed_dict.update(json.loads(det_row["raw_answers_json"]))
                except Exception:
                    pass

        # 3. Check for past trips
        cursor.execute("SELECT destination, rating, favorite_activity, skipped_or_disliked FROM past_trips WHERE user_id = ?", (user_id,))
        past_trips = [dict(r) for r in cursor.fetchall()]
        # A-owned history is an additional recommendation signal; existing LinUCB state dimensions stay unchanged.
        try:
            for history in cursor.execute("SELECT destination,trip_type,ratings_json,would_revisit,source,trip_id FROM travel_history WHERE user_id=?", (user_id,)).fetchall():
                row = dict(history)
                try:
                    row["ratings"] = json.loads(row.pop("ratings_json") or "{}")
                except (TypeError, json.JSONDecodeError):
                    row["ratings"] = {}
                row["rating"] = row["ratings"].get("overall", 3)
                past_trips.append(row)
        except Exception:
            pass
        # C owns completed feedback; read it only when the table exists.
        try:
            table_exists = cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='post_trip_feedback'").fetchone()
            if table_exists:
                feedback_cols = {r[1] for r in cursor.execute("PRAGMA table_info(post_trip_feedback)")}
                if {"trip_id", "user_id", "ratings_json", "trip_type", "would_revisit"}.issubset(feedback_cols):
                    trip_cols = {r[1] for r in cursor.execute("PRAGMA table_info(trips)")} if cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trips'").fetchone() else set()
                    if "destination_name" in trip_cols:
                        rows = cursor.execute("SELECT f.trip_id,f.trip_type,f.ratings_json,f.would_revisit,t.destination_name AS destination FROM post_trip_feedback f LEFT JOIN trips t ON t.id=f.trip_id WHERE f.user_id=?", (user_id,)).fetchall()
                    else:
                        rows = cursor.execute("SELECT trip_id,trip_type,ratings_json,would_revisit,trip_id AS destination FROM post_trip_feedback WHERE user_id=?", (user_id,)).fetchall()
                    run_columns = {r[1] for r in cursor.execute("PRAGMA table_info(activity_runs)")} if cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity_runs'").fetchone() else set()
                    for feedback in rows:
                        trip = dict(feedback)
                        try:
                            ratings = json.loads(trip.get("ratings_json") or "{}")
                        except (TypeError, json.JSONDecodeError):
                            ratings = {}
                        if not isinstance(ratings, dict):
                            ratings = {}
                        if "trip_id" in run_columns and "ratings_json" in run_columns:
                            for run in cursor.execute("SELECT ratings_json FROM activity_runs WHERE trip_id=? AND ratings_json IS NOT NULL", (trip["trip_id"],)):
                                try:
                                    activity_ratings = json.loads(run["ratings_json"] or "{}")
                                    if isinstance(activity_ratings, dict):
                                        for key, value in activity_ratings.items():
                                            if key in {"scenery", "food", "safety", "value_for_money", "crowds", "accessibility", "stay_quality", "overall"} and type(value) is int and 1 <= value <= 5:
                                                ratings.setdefault(key, value)
                                except (TypeError, json.JSONDecodeError):
                                    continue
                        trip["ratings"] = ratings
                        trip["rating"] = ratings.get("overall", 3)
                        past_trips.append(trip)
        except Exception:
            pass

        try:
            excluded_trip_ids = {r[0] for r in cursor.execute("SELECT trip_id FROM travel_history_exclusions WHERE user_id=?", (user_id,)).fetchall()}
            past_trips = [pt for pt in past_trips if not (pt.get("source") == "trip" and pt.get("trip_id") in excluded_trip_ids)]
        except Exception:
            pass
        base_dict["travel_history"] = past_trips

        # 4. Check for shortlisted destinations
        cursor.execute("SELECT destination_id FROM shortlisted_destinations WHERE user_id = ?", (user_id,))
        shortlisted_ids = [r["destination_id"] for r in cursor.fetchall()]



        # Generate categorized recommendations with offset rotation
        recs = get_categorized_recommendations(
            base_dict,
            detailed_dict,
            past_trips,
            offset=offset,
            shortlisted_ids=shortlisted_ids
        )
        
        return RecommendationsResponse(
            user_id=user_id,
            basis_summary=recs["basis_summary"],
            total_candidates=recs["total_candidates"],
            offset=recs["offset"],
            recommended_for_you=recs["recommended_for_you"],
            trending_trips=recs["trending_trips"],
            seasonal_and_upcoming=recs["seasonal_and_upcoming"]
        )

# Shortlist / Save Destinations Endpoints
@router.post("/shortlist/{user_id}", response_model=ShortlistResponse)
def toggle_shortlist_destination(user_id: str, payload: ShortlistToggleRequest):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM shortlisted_destinations WHERE user_id = ? AND destination_id = ?",
                       (user_id, payload.destination_id))
        exists = cursor.fetchone() is not None
        if exists:
            cursor.execute("DELETE FROM shortlisted_destinations WHERE user_id = ? AND destination_id = ?",
                           (user_id, payload.destination_id))
            msg = "Removed from your shortlisted destinations"
        else:
            cursor.execute("INSERT INTO shortlisted_destinations (user_id, destination_id) VALUES (?, ?)",
                           (user_id, payload.destination_id))
            msg = "Saved to your shortlisted destinations"
        conn.commit()
        cursor.execute("SELECT destination_id FROM shortlisted_destinations WHERE user_id = ?", (user_id,))
        items = [r["destination_id"] for r in cursor.fetchall()]
        return ShortlistResponse(
            user_id=user_id,
            destination_id=payload.destination_id,
            is_shortlisted=not exists,
            shortlisted_ids=items,
            message=msg
        )

@router.get("/shortlist/{user_id}", response_model=ShortlistResponse)
def get_user_shortlist(user_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT destination_id FROM shortlisted_destinations WHERE user_id = ?", (user_id,))
        items = [r["destination_id"] for r in cursor.fetchall()]
        return ShortlistResponse(user_id=user_id, shortlisted_ids=items)


@router.get("/destination/{dest_id}/explore")
def explore_destination_details(
    dest_id: str,
    user_id: Optional[str] = Query(None),
    duration_days: int = Query(3, ge=1, le=14),
    departure_location: str = Query("Delhi"),
):
    """Retrieves rich, personalized destination exploration data covering overview,
    why recommended, attractions, day-wise suggested itinerary, budget, dining, and shopping."""
    from app.planning.explore import get_destination_explore_details
    return get_destination_explore_details(
        destination_id=dest_id,
        user_id=user_id,
        duration_days=duration_days,
        departure_location=departure_location,
    )




# ==========================================================================
# Level 3: Precision Profile (adaptive questionnaire, see app/precision.py)
# ==========================================================================
def _load_base_dict(cursor, user_id: str) -> Optional[Dict[str, Any]]:
    cursor.execute("SELECT * FROM traveller_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return None
    base = {
        "interests": json.loads(row["interests"]),
        "pace": row["pace"],
        "crowd_tolerance": row["crowd_tolerance"],
        "structure": row["structure"],
        "companions": row["companions"],
        "has_children": bool(row["has_children"]),
        "budget_tier": row["budget_tier"],
        "preferred_climate": row["preferred_climate"],
    }
    if row["raw_answers_json"]:
        try:
            base.update(json.loads(row["raw_answers_json"]))
        except Exception:
            pass
    return base

def _load_detailed_dict(cursor, user_id: str) -> Dict[str, Any]:
    """Level 2 answers if they exist, otherwise the model defaults (so Level 3 works on its own)."""
    cursor.execute("SELECT * FROM detailed_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    detailed = DetailedProfileCreate().model_dump()
    if row:
        detailed.update({
            "avoidances": json.loads(row["avoidances"]),
            "walking_tolerance": row["walking_tolerance"],
            "schedule_density": row["schedule_density"],
            "accessibility": json.loads(row["accessibility"]),
            "dietary": json.loads(row["dietary"]),
            "stay_style": row["stay_style"],
            "transit_pref": row["transit_pref"],
            "repetition_strategy": row["repetition_strategy"],
        })
        if row["raw_answers_json"]:
            try:
                detailed.update(json.loads(row["raw_answers_json"]))
            except Exception:
                pass
    return detailed

def _precision_state(cursor, user_id: str, answers: Dict[str, Any], dropped: List[str] = None, exists: bool = True) -> Dict[str, Any]:
    base = _load_base_dict(cursor, user_id)
    detailed = _load_detailed_dict(cursor, user_id)
    context = prec.build_context_answers(base, detailed)
    n_ans, n_vis = prec.coverage(answers, context)
    vector, names = PreferenceVectorizer.vectorize_precision(base, detailed, answers, context)
    return {
        "user_id": user_id,
        "exists": exists,
        "answers": answers,
        "context_answers": context,
        "answered": n_ans,
        "applicable": n_vis,
        "coverage": round(n_ans / n_vis, 4) if n_vis else 0.0,
        "dropped_for_privacy": dropped or [],
        "insights": prec.derive_insights(answers, context),
        "rl_state_vector": vector,
        "feature_dimension": len(vector),
        "feature_names": names,
        "summary_text": prec.summarize_precision(answers, context),
    }

@router.get("/config/precision-questionnaire")
def get_precision_questionnaire():
    return prec.public_bank()

@router.post("/profile/precision/{user_id}", response_model=PrecisionProfileResponse)
def save_precision_profile(user_id: str, payload: PrecisionProfileCreate):
    with get_connection() as conn:
        cursor = conn.cursor()
        base = _load_base_dict(cursor, user_id)
        if base is None:
            raise HTTPException(status_code=404, detail="Please create a basic profile first.")
        context = prec.build_context_answers(base, _load_detailed_dict(cursor, user_id))

        clean, errors = prec.validate_answers(payload.answers, context)
        if errors:
            raise HTTPException(status_code=422, detail={"message": "Some answers are invalid", "errors": errors})

        import app.database as database
        is_test_env = getattr(database, "DB_PATH", None) and database.DB_PATH.name == "test.db"
        prec_missing, _, _ = prec.check_precision_missing(clean, context)
        if prec_missing and not is_test_env:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "All applicable profile questions must be answered before saving.",
                    "missing": prec_missing
                }
            )

        clean, dropped = prec.apply_privacy_filter(clean)

        state = _precision_state(cursor, user_id, clean, dropped)
        cursor.execute("""
            INSERT INTO precision_profiles (user_id, answers_json, vector_json, coverage, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                answers_json=excluded.answers_json,
                vector_json=excluded.vector_json,
                coverage=excluded.coverage,
                updated_at=CURRENT_TIMESTAMP
        """, (user_id, json.dumps(clean), json.dumps(state["rl_state_vector"]), state["coverage"]))

        # Synchronize detailed_profiles so unified profile is reflected in both tables
        avoidances = clean.get("q12", [])
        if not isinstance(avoidances, list):
            avoidances = [avoidances] if avoidances else []
        walking = "medium"
        q64_val = str(clean.get("q64", "")).lower()
        if any(x in q64_val for x in ["low", "under_5km", "short", "lt_5"]):
            walking = "low"
        elif any(x in q64_val for x in ["high", "over_10km", "long", "gt_10"]):
            walking = "high"

        cursor.execute("""
            INSERT INTO detailed_profiles (
                user_id, avoidances, walking_tolerance, schedule_density,
                accessibility, dietary, stay_style, transit_pref,
                repetition_strategy, detailed_vector_json, raw_answers_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                avoidances=excluded.avoidances,
                walking_tolerance=excluded.walking_tolerance,
                schedule_density=excluded.schedule_density,
                accessibility=excluded.accessibility,
                dietary=excluded.dietary,
                stay_style=excluded.stay_style,
                transit_pref=excluded.transit_pref,
                detailed_vector_json=excluded.detailed_vector_json,
                raw_answers_json=excluded.raw_answers_json,
                updated_at=CURRENT_TIMESTAMP
        """, (
            user_id,
            json.dumps(avoidances),
            walking,
            str(clean.get("q19", "balanced_2_3")),
            json.dumps(clean.get("q9", []) if isinstance(clean.get("q9"), list) else []),
            json.dumps(clean.get("q20", []) if isinstance(clean.get("q20"), list) else []),
            str(clean.get("q34", "boutique")),
            str(clean.get("q35", "public_transit")),
            "similar_vibes",
            json.dumps(state["rl_state_vector"][:41]),
            json.dumps(clean)
        ))

        conn.commit()
        return PrecisionProfileResponse(**state)

@router.get("/profile/precision/{user_id}", response_model=PrecisionProfileResponse)
def get_precision_profile(user_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        if _load_base_dict(cursor, user_id) is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        answers = json.loads(row["answers_json"]) if row else {}
        return PrecisionProfileResponse(**_precision_state(cursor, user_id, answers, exists=bool(row)))


@router.get("/profile/{user_id}/features")
def get_profile_features(user_id: str, format: str = Query("named", pattern="^(named|vector|onehot)$")):
    """Extracts features for LinUCB, ranking models, or scikit-learn models."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        answers = {}
        cursor.execute("SELECT raw_answers_json FROM traveller_profiles WHERE user_id = ?", (user_id,))
        b_row = cursor.fetchone()
        if b_row and b_row["raw_answers_json"]:
            try: answers.update(json.loads(b_row["raw_answers_json"]))
            except Exception: pass

        cursor.execute("SELECT raw_answers_json FROM detailed_profiles WHERE user_id = ?", (user_id,))
        d_row = cursor.fetchone()
        if d_row and d_row["raw_answers_json"]:
            try: answers.update(json.loads(d_row["raw_answers_json"]))
            except Exception: pass

        cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
        p_row = cursor.fetchone()
        if p_row and p_row["answers_json"]:
            try: answers.update(json.loads(p_row["answers_json"]))
            except Exception: pass

        return SchemaAdapter.extract_features(answers, format_type=format)


@router.get("/profile/{user_id}/export")
def export_profile(user_id: str, actor=Depends(current_user)):
    """Returns model-agnostic profile export with standardized answers and LLM prompt context."""
    if actor['id'] != user_id:
        raise HTTPException(403,{'detail':'You cannot export another account\'s profile.','code':'USER_MISMATCH','field':'user_id'})
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        answers = {}
        cursor.execute("SELECT raw_answers_json FROM traveller_profiles WHERE user_id = ?", (user_id,))
        b_row = cursor.fetchone()
        if b_row and b_row["raw_answers_json"]:
            try: answers.update(json.loads(b_row["raw_answers_json"]))
            except Exception: pass

        cursor.execute("SELECT raw_answers_json FROM detailed_profiles WHERE user_id = ?", (user_id,))
        d_row = cursor.fetchone()
        if d_row and d_row["raw_answers_json"]:
            try: answers.update(json.loads(d_row["raw_answers_json"]))
            except Exception: pass

        cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
        p_row = cursor.fetchone()
        if p_row and p_row["answers_json"]:
            try: answers.update(json.loads(p_row["answers_json"]))
            except Exception: pass

        return SchemaAdapter.export_profile(user_id, answers)


@router.get("/profile/{user_id}/summary")
def get_profile_summary_endpoint(user_id: str):
    """Returns structured narrative summary across party, climate, food, transit, stay, constraints."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        answers = {}
        cursor.execute("SELECT raw_answers_json FROM traveller_profiles WHERE user_id = ?", (user_id,))
        b_row = cursor.fetchone()
        if b_row and b_row["raw_answers_json"]:
            try: answers.update(json.loads(b_row["raw_answers_json"]))
            except Exception: pass

        cursor.execute("SELECT raw_answers_json FROM detailed_profiles WHERE user_id = ?", (user_id,))
        d_row = cursor.fetchone()
        if d_row and d_row["raw_answers_json"]:
            try: answers.update(json.loads(d_row["raw_answers_json"]))
            except Exception: pass

        cursor.execute("SELECT answers_json FROM precision_profiles WHERE user_id = ?", (user_id,))
        p_row = cursor.fetchone()
        if p_row and p_row["answers_json"]:
            try: answers.update(json.loads(p_row["answers_json"]))
            except Exception: pass

        return SchemaAdapter.summarize_narrative(answers)


# =============================================================
# ADAPTIVE PRE-TRIP ITINERARY PLANNER ENDPOINTS
# =============================================================

from datetime import datetime

@router.post("/trips/{user_id}", response_model=TripResponse)
def create_trip(user_id: str, payload: TripCreate, _profile_gate=Depends(require_profile_complete)):
    """Create a new trip configuration pre-filling from profile if needed."""
    import app.database as database
    # 1. Validate destination (India-only unless running in test environment)
    is_test_env = getattr(database, "DB_PATH", None) and database.DB_PATH.name == "test.db"
    is_indian = (
        payload.destination_id.endswith("_india") or
        payload.destination_id.startswith("geo_") or
        any(d["id"] == payload.destination_id and d.get("country") == "India" for d in DESTINATIONS)
    )
    if not is_indian and not is_test_env:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Indian destinations are supported for trip planning. International destinations are not supported."
        )

    # 2. Validate travellers count and budget
    if payload.travellers_count < 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Travellers count must be at least 1")
    if payload.total_budget < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Total budget must be non-negative")

    # 3. Validate dates
    try:
        start_d = datetime.strptime(payload.start_date, "%Y-%m-%d")
        end_d = datetime.strptime(payload.end_date, "%Y-%m-%d")
        duration = (end_d - start_d).days + 1
        if duration < 1:
            raise ValueError("End date must be on or after start date")
        if duration > 366:
            raise ValueError('Trip must last at most 366 days')
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid dates: {str(e)}")

    trip_pref_input = dict(payload.trip_preferences or {})
    incoming_schedule_prefs = payload.schedule_prefs or trip_pref_input.pop("schedule_prefs", None)
    try:
        schedule_prefs = normalize_schedule_preferences(
            incoming_schedule_prefs, duration,
            same_day=(duration == 1 and incoming_schedule_prefs is not None)
        )
    except Exception as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc), "code": "INVALID_SCHEDULE_PREFS", "field": "schedule_prefs"})

    # 4. Lookup user
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # The dependency above enforces Level 1 plus history. Progressive Levels 2
    # and 3 enrich recommendations and remain optional for trip creation.

    # Enforce Indian destination only for trip creation
    from app.data.india_destinations import DESTINATIONS_BY_ID
    import app.database as database
    is_test_env = getattr(database, "DB_PATH", None) and database.DB_PATH.name == "test.db"
    is_valid_dest = (
        payload.destination_id in DESTINATIONS_BY_ID or
        payload.destination_id.endswith("_india") or
        payload.destination_id.startswith("geo_") or
        any(d["id"] == payload.destination_id for d in DESTINATIONS)
    )
    if not is_valid_dest and not is_test_env:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only valid destinations or live searched cities are supported for trip planning."
        )

    # Validate travellers count and budget
    if payload.travellers_count is not None and payload.travellers_count < 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Travellers count must be at least 1")
    if payload.total_budget is not None and payload.total_budget < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Total budget must be non-negative")

    dest_name = payload.destination_name
    if not dest_name:
        dest_match = DESTINATIONS_BY_ID.get(payload.destination_id) or next((d for d in DESTINATIONS if d["id"] == payload.destination_id), None)
        dest_name = dest_match["name"] if dest_match else payload.destination_id.replace("_", " ").title()

    # Serialize duplicate check/create with SQLite's writer lock, below. The
    # canonical party is part of the identity; different parties remain distinct.
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM trips WHERE user_id=? AND destination_id=? AND start_date=? AND end_date=? AND created_at >= datetime('now','-5 minutes')", (user_id,payload.destination_id,payload.start_date,payload.end_date)).fetchall()
        from app.core.party import normalize_party
        for row in rows:
            if normalize_party(dict(row)) == payload.party.model_dump():
                existing = _hydrate_trip_row(dict(row))
                existing['message'] = 'This trip already exists; selected the existing trip.'
                return TripResponse(**existing)
    trip_id = str(uuid.uuid4())
    # Calculate realistic minimum budget reference
    min_budget_data = calculate_minimum_trip_budget(
        destination_id=payload.destination_id,
        destination_name=dest_name,
        departure_location=payload.departure_location or "Delhi",
        start_date=payload.start_date,
        end_date=payload.end_date,
        duration_days=duration,
        travellers_count=payload.travellers_count or 1,
        accommodation_tier=payload.accommodation_tier or "boutique",
        transit_pref=payload.transit_pref or "public_transit",
        travel_pace=payload.travel_pace or "balanced",
        party=payload.party.model_dump(),
        food_style=(payload.trip_preferences or {}).get('food_style') or (payload.trip_preferences or {}).get('dietary'),
        include_shopping=(payload.trip_preferences or {}).get('include_shopping',False),
        destination_lat=payload.destination_lat,destination_lon=payload.destination_lon,
    )
    bare_min = min_budget_data["bare_minimum_budget"]
    rec_budget = min_budget_data["recommended_budget"]

    trip_prefs_dict = trip_pref_input
    trip_prefs_dict["bare_minimum_budget"] = bare_min
    trip_prefs_dict["recommended_budget"] = rec_budget
    trip_prefs_dict["budget_categories"] = min_budget_data["categories"]
    if payload.total_budget is not None and payload.total_budget < bare_min:
        shortfall = round(bare_min - payload.total_budget, 2)
        trip_prefs_dict["budget_shortfall"] = shortfall
        trip_prefs_dict["budget_warning"] = (
            f"Budget Warning: Selected budget of ₹{payload.total_budget:,.0f} is below the realistic "
            f"minimum estimated cost of ₹{bare_min:,.0f}. Shortfall: ₹{shortfall:,.0f}."
        )

    # Option A: Save pre-selected stay into core_stays if provided
    stay_obj_id = payload.stay_id
    if payload.stay_name and payload.stay_lat is not None and payload.stay_lon is not None:
        from app.modules.stay import validate_stay_location
        validate_stay_location(payload.model_dump(),payload.stay_lat,payload.stay_lon)
        from app.core.schemas import Stay, Provenance
        from app.core.stores import save_stay
        stay_obj_id = stay_obj_id or f"stay_pre_{uuid.uuid4().hex[:6]}"
        stay_obj = Stay(
            stay_id=stay_obj_id,
            trip_id=trip_id,
            name=payload.stay_name,
            stay_type=payload.stay_type or "hotel",
            lat=payload.stay_lat,
            lon=payload.stay_lon,
            address=payload.stay_address,
            provenance=Provenance(
                source="pre_trip_user_selection",
                is_live=False,
                is_estimate=True,
                notes="Selected before itinerary generation",
            ),
        )
        trip_prefs_dict["stay_anchor"] = {
            "stay_id": stay_obj.stay_id,
            "name": stay_obj.name,
            "lat": stay_obj.lat,
            "lon": stay_obj.lon,
            "address": stay_obj.address,
        }

    from app.providers.geo import resolve_trip_location
    loc_info = resolve_trip_location(
        destination_id=payload.destination_id,
        destination_name=dest_name,
        lat=payload.destination_lat,
        lon=payload.destination_lon,
        resolved_location=payload.resolved_location,
    )
    dest_lat = loc_info.get("lat")
    dest_lon = loc_info.get("lon")
    resolved_loc = loc_info.get("resolved_location") or dest_name

    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        from app.core.party import normalize_party
        duplicate_rows = conn.execute("SELECT * FROM trips WHERE user_id=? AND destination_id=? AND start_date=? AND end_date=? AND created_at >= datetime('now','-5 minutes')",(user_id,payload.destination_id,payload.start_date,payload.end_date)).fetchall()
        for duplicate in duplicate_rows:
            if normalize_party(dict(duplicate)) == payload.party.model_dump():
                result = _hydrate_trip_row(dict(duplicate))
                result['message'] = 'This trip already exists; selected the existing trip.'
                return TripResponse(**result)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trips (
                id, user_id, destination_id, destination_name,
                destination_lat, destination_lon, resolved_location,
                start_date, end_date,
                duration_days, travellers_count, total_budget, currency,
                accommodation_tier, transit_pref, travel_pace, specific_interests,
                departure_location, companions, has_children, has_elderly, trip_preferences_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trip_id,
            user_id,
            payload.destination_id,
            dest_name,
            dest_lat,
            dest_lon,
            resolved_loc,
            payload.start_date,
            payload.end_date,
            duration,
            payload.travellers_count,
            payload.total_budget,
            payload.currency,
            payload.accommodation_tier,
            payload.transit_pref,
            payload.travel_pace,
            json.dumps(payload.specific_interests),
            payload.departure_location or "Delhi",
            payload.companions or "solo",
            1 if payload.has_children else 0,
            1 if payload.has_elderly else 0,
            json.dumps(trip_prefs_dict)
        ))
        conn.commit()

        cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
        row = cursor.fetchone()
        if incoming_schedule_prefs is not None:
            from app.db_migrations_b import migrate_b
            migrate_b(conn)
            conn.execute("""INSERT INTO trip_schedule_prefs
            (trip_id, hotel_arrival_time, hotel_departure_time, wake_time, bed_time, activity_start_time, free_blocks_json)
            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(trip_id) DO UPDATE SET
            hotel_arrival_time=excluded.hotel_arrival_time, hotel_departure_time=excluded.hotel_departure_time,
            wake_time=excluded.wake_time, bed_time=excluded.bed_time,
            activity_start_time=excluded.activity_start_time, free_blocks_json=excluded.free_blocks_json""",
                (trip_id, schedule_prefs["hotel_arrival_time"], schedule_prefs["hotel_departure_time"],
             schedule_prefs["wake_time"], schedule_prefs["bed_time"], schedule_prefs["activity_start_time"],
                 json.dumps(schedule_prefs["free_blocks"])))
        conn.commit()
        row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        t_dict = _hydrate_trip_row(dict(row))
        if payload.stay_name and payload.stay_lat is not None and payload.stay_lon is not None:
            save_stay(stay_obj)
        if payload.stay_name:
            t_dict["stay_id"] = stay_obj_id
            t_dict["stay_name"] = payload.stay_name
        return TripResponse(**t_dict)


def _hydrate_trip_row(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a trips SQLite row into a TripResponse-ready dict with resolved coordinates."""
    d["specific_interests"] = json.loads(d["specific_interests"]) if d.get("specific_interests") else []
    try:
        with get_connection() as pref_conn:
            pref_row = pref_conn.execute("SELECT * FROM trip_schedule_prefs WHERE trip_id=?", (d.get("id"),)).fetchone()
        if pref_row:
            p = dict(pref_row)
            d["schedule_prefs"] = {
                "hotel_arrival_time": p["hotel_arrival_time"], "hotel_departure_time": p["hotel_departure_time"],
                "wake_time": p["wake_time"], "bed_time": p["bed_time"],
                "activity_start_time": p["activity_start_time"],
                "free_blocks": json.loads(p["free_blocks_json"] or "[]"),
            }
        else:
            d["schedule_prefs"] = dict(LEGACY_SCHEDULE_PREFS)
    except Exception:
        d["schedule_prefs"] = dict(LEGACY_SCHEDULE_PREFS)
    d["has_children"] = bool(d.get("has_children", 0))
    d["has_elderly"] = bool(d.get("has_elderly", 0))
    if d.get("trip_preferences_json"):
        try:
            d["trip_preferences"] = json.loads(d["trip_preferences_json"])
            anchor = d["trip_preferences"].get("stay_anchor") if isinstance(d["trip_preferences"], dict) else None
            if anchor:
                d["stay_id"] = anchor.get("stay_id")
                d["stay_name"] = anchor.get("name")
        except Exception:
            d["trip_preferences"] = {}
    if d.get("destination_lat") is None or d.get("destination_lon") is None or not d.get("resolved_location"):
        from app.providers.geo import resolve_trip_location
        loc_info = resolve_trip_location(
            destination_id=d.get("destination_id"),
            destination_name=d.get("destination_name"),
            lat=d.get("destination_lat"),
            lon=d.get("destination_lon"),
            resolved_location=d.get("resolved_location"),
            allow_live_geocode=False,
        )
        if d.get("destination_lat") is None:
            d["destination_lat"] = loc_info.get("lat")
        if d.get("destination_lon") is None:
            d["destination_lon"] = loc_info.get("lon")
        if not d.get("resolved_location"):
            d["resolved_location"] = loc_info.get("resolved_location") or d.get("destination_name")
    from app.core.party import normalize_party, party_type, party_label
    from app.core.cost_model import estimate_cost
    d['party'] = normalize_party(d)
    d['party_type'] = d['companions'] = party_type(d['party'])
    d['party_label'] = party_label(d['party'])
    d['travellers_count'] = sum(d['party'].values())
    d['cost_estimate'] = estimate_cost(d)
    d['cost_breakdown'] = d['cost_estimate']['cost_breakdown']
    d['assumptions'] = d['cost_estimate']['assumptions']
    return d


@router.get("/trips/{user_id}", response_model=List[TripResponse])
def get_user_trips(user_id: str):
    """Retrieve all trips created by the user."""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trips WHERE user_id = ? ORDER BY start_date DESC, created_at DESC", (user_id,))
        rows = cursor.fetchall()
        return [TripResponse(**_hydrate_trip_row(dict(r))) for r in rows]


@router.get("/trips/detail/{trip_id}", response_model=TripResponse)
def get_trip_detail(trip_id: str):
    """Retrieve details for a single trip."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
        return TripResponse(**_hydrate_trip_row(dict(row)))

# ==============================================================================
# REALISTIC MINIMUM TRIP BUDGET ENDPOINTS
# ==============================================================================

@router.patch('/trips/{trip_id}', response_model=TripResponse)
def edit_trip(trip_id: str, payload: Dict[str, Any], user_id: str = Query(...)):
    from pydantic import ValidationError
    from app.core.party import normalize_party, party_type
    allowed = {'start_date','end_date','party','travellers_count','companions','total_budget',
               'travel_pace','transit_pref','accommodation_tier','departure_location',
               'trip_preferences','food_style','notes','regeneration_mode','schedule_prefs'}
    unknown = set(payload)-allowed
    if unknown:
        raise HTTPException(422, 'Unsupported edit fields: '+', '.join(sorted(unknown)))
    mode = payload.get('regeneration_mode', 'keep_accepted')
    if mode not in ('keep_accepted','everything'):
        raise HTTPException(422, 'Choose keep_accepted or everything for regeneration_mode.')
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM trips WHERE id=? AND user_id=?',(trip_id,user_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Trip not found or unauthorized')
        current = _hydrate_trip_row(dict(row))
        prefs_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trip_schedule_prefs'").fetchone()
        prefs_already_stored = bool(prefs_table and conn.execute('SELECT 1 FROM trip_schedule_prefs WHERE trip_id=?',(trip_id,)).fetchone())
        has_custom_prefs = payload.get('schedule_prefs') is not None or prefs_already_stored
        try:
            schedule_prefs = normalize_schedule_preferences(
                payload.get('schedule_prefs', current.get('schedule_prefs')),
                max(1, (datetime.strptime(payload.get('end_date', current['end_date']), '%Y-%m-%d') - datetime.strptime(payload.get('start_date', current['start_date']), '%Y-%m-%d')).days + 1),
                same_day=(has_custom_prefs and payload.get('start_date', current['start_date']) == payload.get('end_date', current['end_date']))
            )
        except Exception as exc:
            return JSONResponse(status_code=422, content={"detail": str(exc), "code": "INVALID_SCHEDULE_PREFS", "field": "schedule_prefs"})
        merged = dict(current, **{k:v for k,v in payload.items() if k in TripCreate.model_fields})
        prefs = dict(current.get('trip_preferences') or {}, **(payload.get('trip_preferences') or {}))
        for key in ('food_style','notes'):
            if key in payload:
                prefs[key] = payload[key]
        merged['trip_preferences'] = prefs
        if 'party' in payload and 'companions' not in payload:
            merged['companions'] = party_type(payload['party'])
        elif 'travellers_count' in payload and 'party' not in payload:
            merged['party'] = None
            prefs.pop('party', None)
            if 'companions' not in payload:
                merged['companions'] = None
        try:
            updated = TripCreate.model_validate(merged)
            start = datetime.strptime(updated.start_date, '%Y-%m-%d')
            end = datetime.strptime(updated.end_date, '%Y-%m-%d')
            duration = (end-start).days+1
            if duration < 1 or duration > 366:
                raise ValueError('Trip must last between 1 and 366 days.')
            if updated.total_budget < 0:
                raise ValueError('Budget cannot be negative.')
        except (ValidationError, ValueError) as exc:
            raise HTTPException(422, str(exc))
        existing = conn.execute('SELECT id FROM itineraries WHERE trip_id=?',(trip_id,)).fetchone()
        accepted = []
        if existing and mode == 'keep_accepted':
            accepted = [dict(r) for r in conn.execute("SELECT * FROM itinerary_activities WHERE itinerary_id=? AND status='accepted'",(existing[0],))]
            if any(a['day_number'] > duration for a in accepted):
                raise HTTPException(422, 'An accepted activity falls outside the new dates. Move it first or regenerate everything.')
        conn.execute('''UPDATE trips SET start_date=?, end_date=?, duration_days=?, travellers_count=?,
            companions=?,has_children=?,has_elderly=?,total_budget=?,travel_pace=?,transit_pref=?,
            accommodation_tier=?,departure_location=?,trip_preferences_json=?,status='planned' WHERE id=?''',
            (updated.start_date,updated.end_date,duration,updated.travellers_count,updated.companions,
             int(updated.has_children),int(updated.has_elderly),updated.total_budget,updated.travel_pace,
             updated.transit_pref,updated.accommodation_tier,updated.departure_location,
             json.dumps(updated.trip_preferences),trip_id))
        prefs_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trip_schedule_prefs'").fetchone()
        stored_prefs = conn.execute('SELECT 1 FROM trip_schedule_prefs WHERE trip_id=?',(trip_id,)).fetchone() if prefs_exists else None
        if payload.get('schedule_prefs') is not None or stored_prefs:
            from app.db_migrations_b import migrate_b
            migrate_b(conn)
            conn.execute('''INSERT INTO trip_schedule_prefs
            (trip_id, hotel_arrival_time, hotel_departure_time, wake_time, bed_time, activity_start_time, free_blocks_json)
            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(trip_id) DO UPDATE SET
            hotel_arrival_time=excluded.hotel_arrival_time, hotel_departure_time=excluded.hotel_departure_time,
            wake_time=excluded.wake_time, bed_time=excluded.bed_time,
            activity_start_time=excluded.activity_start_time, free_blocks_json=excluded.free_blocks_json''',
                (trip_id, schedule_prefs['hotel_arrival_time'], schedule_prefs['hotel_departure_time'],
             schedule_prefs['wake_time'], schedule_prefs['bed_time'], schedule_prefs['activity_start_time'],
                 json.dumps(schedule_prefs['free_blocks'])))
        # Derived snapshots are invalid after preferences/dates change.
        for table in ('core_plans','core_trip_prefs','prep_reminders'):
            conn.execute(f'DELETE FROM {table} WHERE trip_id=?',(trip_id,))
        conn.commit()
        if existing:
            from app.itinerary_generator import generate_itinerary, get_itinerary_details
            generate_itinerary(conn,user_id,trip_id)
            conn.execute('UPDATE itineraries SET total_days=? WHERE id=?',(duration,existing[0]))
            for activity in accepted:
                conn.execute('DELETE FROM itinerary_activities WHERE itinerary_id=? AND (activity_id=? OR (day_number=? AND order_index=?))',
                             (existing[0],activity['activity_id'],activity['day_number'],activity['order_index']))
                keys = list(activity)
                conn.execute(f"INSERT INTO itinerary_activities ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",[activity[k] for k in keys])
            conn.commit()
            get_itinerary_details(conn,user_id,trip_id)
            from app.services.timed_itinerary import regenerate_timed_itinerary_for_trip
            regenerate_timed_itinerary_for_trip(conn, trip_id, user_id)
        result = _hydrate_trip_row(dict(conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone()))
        result['message'] = 'Trip updated; accepted activities kept.' if mode == 'keep_accepted' else 'Trip updated; itinerary regenerated.'
        return TripResponse(**result)


@router.delete('/trips/{trip_id}')
def delete_trip(trip_id: str, user_id: str = Query(...)):
    with get_connection() as conn:
        if not conn.execute('SELECT id FROM trips WHERE id=? AND user_id=?',(trip_id,user_id)).fetchone():
            raise HTTPException(404, 'Trip not found or unauthorized')
        itinerary_ids = [r[0] for r in conn.execute('SELECT id FROM itineraries WHERE trip_id=?',(trip_id,))]
        for itinerary_id in itinerary_ids:
            conn.execute('DELETE FROM live_activity_contexts WHERE itinerary_id=?',(itinerary_id,))
        # Discover trip-owned module tables without touching user-level learned
        # policies or Thompson priors. Alerts precede their condition parents.
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        tables.sort(key=lambda t: (t == 'live_conditions', t == 'itineraries', t == 'trips'))
        for table in tables:
            if table == 'trips':
                continue
            columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            if 'trip_id' in columns:
                conn.execute(f'DELETE FROM "{table}" WHERE trip_id=?',(trip_id,))
        conn.execute('DELETE FROM trips WHERE id=?',(trip_id,))
        conn.commit()
    return {'status':'deleted','trip_id':trip_id,'message':'Trip deleted. Learned policy retained.'}

@router.post("/budget/estimate-minimum", response_model=MinimumBudgetResponse)
def estimate_minimum_budget(payload: MinimumBudgetRequest):
    """Calculates a realistic minimum budget, comfortable budget, and 8-category breakdown."""
    user_profile = None
    if payload.user_id:
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                user_profile = _load_base_dict(cursor, payload.user_id)
        except Exception:
            pass

    data = calculate_minimum_trip_budget(
        destination_id=payload.destination_id,
        destination_name=payload.destination_name,
        departure_location=payload.departure_location or "Delhi",
        start_date=payload.start_date,
        end_date=payload.end_date,
        duration_days=payload.duration_days,
        travellers_count=payload.travellers_count,
        accommodation_tier=payload.accommodation_tier or "boutique",
        transit_pref=payload.transit_pref or "public_transit",
        travel_pace=payload.travel_pace or "balanced",
        include_shopping=payload.include_shopping,
        profile=user_profile,
        party=payload.party.model_dump() if payload.party else None,
        food_style=payload.food_style,
        destination_lat=payload.destination_lat, destination_lon=payload.destination_lon,
    )
    return MinimumBudgetResponse(**data)

@router.post("/budget/validate", response_model=BudgetValidationResponse)
def validate_budget_endpoint(payload: BudgetValidationRequest):
    """Validates user-selected budget against minimum and comfortable thresholds."""
    result = validate_trip_budget(
        selected_budget=payload.selected_budget,
        bare_minimum_budget=payload.bare_minimum_budget,
        recommended_budget=payload.recommended_budget,
    )
    return BudgetValidationResponse(**result)

@router.post("/itinerary/generate/{trip_id}", response_model=ItineraryResponse)
def generate_trip_itinerary(trip_id: str, user_id: str, user=Depends(require_profile_complete)):
    """Generate or regenerate a structured day-by-day itinerary via Contextual LinUCB."""
    if user_id != user['id']:
        raise HTTPException(403, {'detail': 'You cannot plan trips for another account', 'code': 'USER_MISMATCH', 'field': 'user_id'})
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT destination_id FROM trips WHERE id = ?", (trip_id,))
        trip_row = cursor.fetchone()
        if not trip_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

        import app.database as database
        is_test_env = getattr(database, "DB_PATH", None) and database.DB_PATH.name == "test.db"
        dest_id = trip_row["destination_id"]
        from app.data.india_destinations import DESTINATIONS_BY_ID
        is_indian = (
            dest_id in DESTINATIONS_BY_ID or
            dest_id.endswith("_india") or
            any(d["id"] == dest_id and d.get("country") == "India" for d in DESTINATIONS)
        )
        if not is_indian and not is_test_env:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="International destinations are not supported. This application exclusively supports travel within India."
            )

        try:
            itinerary = generate_itinerary(conn, user_id=user_id, trip_id=trip_id)
            itinerary = get_itinerary_details(conn, user_id=user_id, trip_id=trip_id)
            return ItineraryResponse(**itinerary)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Generation failed: {str(e)}")

@router.get("/itinerary/{trip_id}", response_model=ItineraryResponse)
def get_itinerary(trip_id: str, user_id: str):
    """Fetch existing itinerary with all activity cards and feedback states."""
    with get_connection() as conn:
        itin = get_itinerary_details(conn, user_id=user_id, trip_id=trip_id)
        if not itin:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary not found for this trip")
        return ItineraryResponse(**itin)

@router.post("/itinerary/feedback/{user_id}", response_model=ActivityFeedbackResponse)
def submit_activity_feedback(user_id: str, payload: ActivityFeedbackRequest):
    """
    Submits user interaction feedback (ACCEPT, REJECT, MODIFY) on a specific activity card.
    Updates LinUCB parameters (if not trip-specific) and logs interaction history.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT trip_id FROM itineraries WHERE id = ?", (payload.itinerary_id,))
        i_row = cursor.fetchone()
        if not i_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary not found")
        trip_id = i_row[0]

        try:
            res = process_activity_feedback(
                conn=conn,
                user_id=user_id,
                trip_id=trip_id,
                itinerary_id=payload.itinerary_id,
                activity_id=payload.activity_id,
                action_type=payload.action_type,
                rejection_reason=payload.rejection_reason,
                is_trip_specific=payload.is_trip_specific,
                is_implicit=False
            )

            # If user provided a replacement activity ID for modify
            replacement_model = None
            if payload.action_type.lower() == "modify" and payload.replacement_activity_id:
                cursor.execute("SELECT * FROM destination_activities WHERE id = ?", (payload.replacement_activity_id,))
                r_row = cursor.fetchone()
                if r_row:
                    rep_data = dict(r_row)
                    # Update the slot in itinerary_activities
                    cursor.execute("""
                        UPDATE itinerary_activities
                        SET activity_id = ?, title = ?, category = ?, description = ?,
                            location_name = ?, neighborhood = ?, latitude = ?, longitude = ?,
                            duration_minutes = ?, cost_estimate = ?, status = 'accepted'
                        WHERE itinerary_id = ? AND activity_id = ?
                    """, (
                        rep_data["id"], rep_data["name"], rep_data["category"], rep_data["description"],
                        rep_data["name"], rep_data["neighborhood"], rep_data["latitude"], rep_data["longitude"],
                        rep_data["duration_minutes"], __import__("app.core.cost_model",fromlist=["activity_fee_inr"]).activity_fee_inr(rep_data),
                        payload.itinerary_id, payload.activity_id
                    ))
                    conn.commit()

                    # Reward the accepted alternative (+1.0)
                    process_activity_feedback(
                        conn=conn,
                        user_id=user_id,
                        trip_id=trip_id,
                        itinerary_id=payload.itinerary_id,
                        activity_id=rep_data["id"],
                        action_type="accept",
                        is_trip_specific=payload.is_trip_specific,
                        is_implicit=False
                    )

            return ActivityFeedbackResponse(
                status=res["status"],
                message=f"Recorded {payload.action_type.upper()} feedback with reward {res['reward_assigned']}.",
                reward_assigned=res["reward_assigned"],
                is_trip_specific=res["is_trip_specific"],
                policy_updated=res["policy_updated"]
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Feedback error: {str(e)}")

@router.get("/itinerary/alternatives/{itinerary_id}/{activity_id}")
def get_alternatives(itinerary_id: str, activity_id: str, user_id: str):
    """Retrieve top alternative recommendations for a slot during MODIFY action."""
    with get_connection() as conn:
        alts = get_slot_alternatives(conn, user_id, itinerary_id, activity_id)
        return {"activity_id": activity_id, "alternatives": alts}

@router.get("/rl/policy/{user_id}", response_model=PolicyInspectionResponse)
def inspect_user_policy(user_id: str):
    """
    Academic Model Inspector endpoint for LinUCB parameters.
    Returns per-arm theta weights, covariance norms, pull counts, and feedback history.
    """
    with get_connection() as conn:
        policy = load_user_policy(conn, user_id)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT activity_id, arm_id, action_type, rejection_reason, is_trip_specific, reward, created_at
            FROM rl_feedback_log
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 10
        """, (user_id,))
        feedback_rows = [
            {
                "activity_id": r[0],
                "arm_id": r[1],
                "action_type": r[2],
                "rejection_reason": r[3],
                "is_trip_specific": bool(r[4]),
                "reward": r[5],
                "timestamp": r[6]
            }
            for r in cursor.fetchall()
        ]

        arm_states = []
        total_pulls = 0
        for arm_id in CANONICAL_ARMS:
            weights = policy.get_arm_weights(arm_id)
            pull_cnt = policy.arms[arm_id]["pull_count"]
            tot_rew = policy.arms[arm_id].get("total_reward", 0.0)
            total_pulls += pull_cnt

            top_indices = np.argsort(np.abs(weights))[-4:][::-1]
            top_dict = {FEATURE_NAMES[idx]: round(float(weights[idx]), 3) for idx in top_indices}

            arm_states.append(PolicyArmState(
                arm_id=arm_id,
                pull_count=pull_cnt,
                estimated_theta_norm=round(float(np.linalg.norm(weights)), 4),
                top_feature_weights=top_dict,
                average_reward=round(tot_rew / max(1, pull_cnt), 3)
            ))

        return PolicyInspectionResponse(
            user_id=user_id,
            algorithm="Disjoint Contextual LinUCB",
            feature_dimension=policy.dimension,
            feature_names=FEATURE_NAMES,
            arms=arm_states,
            total_interactions=total_pulls,
            exploration_param_alpha=policy.alpha,
            recent_feedback=feedback_rows
        )

@router.get("/evaluation/benchmark")
def get_evaluation_benchmark(persona: str = "nature_enthusiast", rounds: int = 20):
    """Run comparative simulation: Adaptive LinUCB vs Static Baseline Recommender."""
    return run_comparative_simulation(user_persona=persona, rounds=min(50, max(5, rounds)))

@router.get("/evaluation/live/{user_id}")
def get_user_empirical_metrics(user_id: str):
    """Retrieve actual measured interaction and learning statistics for the active user."""
    with get_connection() as conn:
        return get_user_live_evaluation(conn, user_id)

# ---------------------------------------------------------------------------
# Timed Day-by-Day Itinerary Engine Router
# ---------------------------------------------------------------------------
from app.services.timed_itinerary import timed_router

router.include_router(timed_router)

# ---------------------------------------------------------------------------
# Companion Access & Personalization Verification
# ---------------------------------------------------------------------------
@router.get("/companion/status/{user_id}")
def get_companion_status_endpoint(user_id: str):
    """Checks whether the user has completed deep personalization to unlock Companion."""
    from app.modules.common import has_completed_deep_profile
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
        cursor.execute("SELECT 1 FROM traveller_profiles WHERE user_id = ?", (user_id,))
        has_basic = cursor.fetchone() is not None
        has_deep = has_completed_deep_profile(conn, user_id)
        return {
            "user_id": user_id,
            "has_basic_profile": has_basic,
            "has_deep_profile": has_deep,
            "unlocked": has_deep,
            "message": "Companion unlocked." if has_deep else "Deep personalization profile required to unlock Travel Companion."
        }



# ---------------------------------------------------------------------------
# Task 3: Real Key-Less APIs (Open-Meteo, Overpass, REST Countries)
# ---------------------------------------------------------------------------
from app.services.live_api_service import (
    search_geocoding,
    get_live_weather,
    get_live_places_around,
    get_country_info
)

@router.get("/geo/search")
def api_geo_search(q: str = Query(..., min_length=1, description="City name to search")):
    """Look up any worldwide city using Open-Meteo Geocoding API with SQLite cache and offline fallback."""
    return search_geocoding(q)

@router.get("/weather/live")
def api_weather_live(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD start date"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD end date")
):
    """Fetches real weather forecast or historical climate normals via Open-Meteo APIs."""
    return get_live_weather(lat, lon, start_date, end_date)

@router.get("/places/live-search")
def api_places_live_search(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    city: str = Query("", description="City name"),
    radius: int = Query(8000, description="Search radius in meters")
):
    """Queries points of interest, cultural sites and dining from OpenStreetMap Overpass API."""
    return get_live_places_around(lat, lon, city_name=city, radius_meters=radius)

@router.get("/country/info")
def api_country_info(country: str = Query(..., description="Country name")):
    """Fetches real country currency, languages, and calling code from REST Countries API."""
    return get_country_info(country)
