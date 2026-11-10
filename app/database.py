# Database connection and tables using sqlite3
import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, Any

DB_PATH = Path(__file__).resolve().parent.parent / "travel_guide.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Users table (supports google, email, phone, guest)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                auth_provider TEXT NOT NULL,
                identifier TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                display_name TEXT,
                avatar_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                google_sub TEXT UNIQUE
            )
        """)
        
        # Ensure google_sub column exists for older DBs
        cursor.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in cursor.fetchall()]
        if "google_sub" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")


        # Traveller profiles table (Basic starting profile)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traveller_profiles (
                user_id TEXT PRIMARY KEY,
                profile_type TEXT DEFAULT 'short',
                interests TEXT NOT NULL,
                pace REAL NOT NULL DEFAULT 0.5,
                crowd_tolerance REAL NOT NULL DEFAULT 0.5,
                structure REAL NOT NULL DEFAULT 0.5,
                companions TEXT NOT NULL DEFAULT 'solo',
                has_children INTEGER NOT NULL DEFAULT 0,
                budget_tier TEXT NOT NULL DEFAULT 'balanced',
                preferred_climate TEXT NOT NULL DEFAULT 'mild',
                planning_experience TEXT NOT NULL DEFAULT 'intermediate',
                stated_vector_json TEXT,
                raw_answers_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Detailed traveller profiles table (Deep Personalisation - Sections 2-10)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detailed_profiles (
                user_id TEXT PRIMARY KEY,
                avoidances TEXT NOT NULL DEFAULT '[]', -- JSON list of avoided activities
                walking_tolerance TEXT NOT NULL DEFAULT 'medium', -- 'low', 'medium', 'high'
                schedule_density TEXT NOT NULL DEFAULT 'balanced_2_3', -- 'relaxed_1_major', 'balanced_2_3', 'packed_all_day'
                accessibility TEXT NOT NULL DEFAULT '[]', -- JSON list of mobility needs
                dietary TEXT NOT NULL DEFAULT '[]', -- JSON list of dietary requirements
                stay_style TEXT NOT NULL DEFAULT 'boutique', -- 'boutique', 'budget_hostel', 'resort', 'apartment'
                transit_pref TEXT NOT NULL DEFAULT 'public_transit', -- 'public_transit', 'walking', 'rental_car', 'taxi'
                repetition_strategy TEXT NOT NULL DEFAULT 'similar_vibes', -- 'explore_new', 'similar_vibes', 'familiar_return'
                detailed_vector_json TEXT, -- extended RL state vector
                raw_answers_json TEXT, -- complete questionnaire response map
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Level 3 precision profile (adaptive questionnaire, see app/precision.py)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS precision_profiles (
                user_id TEXT PRIMARY KEY,
                answers_json TEXT NOT NULL,      -- validated answers keyed by question id
                vector_json TEXT,                -- snapshot of the extended state vector at save time
                coverage REAL DEFAULT 0,         -- answered / applicable questions
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Past trips record (Section 5.3)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS past_trips (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                destination TEXT NOT NULL,
                rating REAL DEFAULT 4.0,
                favorite_activity TEXT,
                skipped_or_disliked TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Shortlisted / Saved destinations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shortlisted_destinations (
                user_id TEXT NOT NULL,
                destination_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, destination_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------------------
        # ADAPTIVE PRE-TRIP ITINERARY PLANNER SCHEMA (6 NEW TABLES)
        # -------------------------------------------------------------

        # 1. Trips table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                destination_id TEXT NOT NULL,
                destination_name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                travellers_count INTEGER DEFAULT 1,
                total_budget REAL DEFAULT 0.0,
                currency TEXT DEFAULT 'USD',
                accommodation_tier TEXT DEFAULT 'balanced',
                transit_pref TEXT DEFAULT 'public_transit',
                travel_pace TEXT DEFAULT 'balanced',
                specific_interests TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_user_id ON trips(user_id)")

        # 2. Itineraries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS itineraries (
                id TEXT PRIMARY KEY,
                trip_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                total_days INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                total_estimated_cost REAL DEFAULT 0.0,
                summary_notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_itineraries_trip_id ON itineraries(trip_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_itineraries_user_id ON itineraries(user_id)")

        # 3. Itinerary Activities table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS itinerary_activities (
                id TEXT PRIMARY KEY,
                itinerary_id TEXT NOT NULL,
                day_number INTEGER NOT NULL,
                time_slot TEXT NOT NULL, -- 'morning', 'afternoon', 'evening', 'meal'
                activity_id TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                location_name TEXT,
                neighborhood TEXT,
                latitude REAL,
                longitude REAL,
                duration_minutes INTEGER DEFAULT 90,
                cost_estimate REAL DEFAULT 0.0,
                transit_suggestion TEXT,
                transit_duration_minutes INTEGER DEFAULT 15,
                why_it_suits TEXT,
                status TEXT DEFAULT 'proposed', -- 'proposed', 'accepted', 'rejected', 'modified'
                rejection_reason TEXT,
                order_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_itin_act_itin_day ON itinerary_activities(itinerary_id, day_number)")

        # 4. Destination Activities catalog table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS destination_activities (
                id TEXT PRIMARY KEY,
                destination_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL, -- 'culture_history', 'nature_outdoors', 'food_dining', 'adventure', 'relaxation', 'shopping_local'
                neighborhood TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                duration_minutes INTEGER NOT NULL,
                cost_tier TEXT NOT NULL, -- 'free', 'budget', 'moderate', 'luxury'
                cost_amount REAL NOT NULL,
                physical_intensity TEXT NOT NULL, -- 'low', 'moderate', 'high'
                crowd_level TEXT NOT NULL, -- 'low', 'moderate', 'high'
                opening_time TEXT DEFAULT '09:00',
                closing_time TEXT DEFAULT '18:00',
                tags TEXT NOT NULL, -- JSON array of tags
                avoidance_triggers TEXT NOT NULL, -- JSON array of avoidance strings
                description TEXT NOT NULL,
                photo_url TEXT,
                data_source TEXT DEFAULT 'curated', -- 'curated', 'estimated', 'unavailable'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dest_act_dest_cat ON destination_activities(destination_id, category)")

        # 5. RL User Policies table (per-user, per-arm LinUCB parameters)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rl_user_policies (
                user_id TEXT NOT NULL,
                arm_id TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                matrix_a_json TEXT NOT NULL,
                vector_b_json TEXT NOT NULL,
                pull_count INTEGER DEFAULT 0,
                total_reward REAL DEFAULT 0.0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, arm_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 6. RL Feedback Log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rl_feedback_log (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                trip_id TEXT NOT NULL,
                itinerary_id TEXT NOT NULL,
                activity_id TEXT NOT NULL,
                arm_id TEXT NOT NULL,
                action_type TEXT NOT NULL, -- 'accept', 'reject', 'modify'
                rejection_reason TEXT,
                is_trip_specific INTEGER DEFAULT 0, -- 1 if trip-specific, 0 if general preference
                is_implicit INTEGER DEFAULT 0, -- 1 if implicit (e.g. itinerary saved), 0 if explicit click
                reward REAL NOT NULL,
                context_vector_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
                FOREIGN KEY (itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rl_feedback_user ON rl_feedback_log(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rl_feedback_itin ON rl_feedback_log(itinerary_id)")


        # Lightweight schema migrations for existing SQLite databases
        cursor.execute("PRAGMA table_info(traveller_profiles)")
        t_cols = [r[1] for r in cursor.fetchall()]
        if "raw_answers_json" not in t_cols:
            cursor.execute("ALTER TABLE traveller_profiles ADD COLUMN raw_answers_json TEXT")

        cursor.execute("PRAGMA table_info(detailed_profiles)")
        d_cols = [r[1] for r in cursor.fetchall()]
        if "raw_answers_json" not in d_cols:
            cursor.execute("ALTER TABLE detailed_profiles ADD COLUMN raw_answers_json TEXT")

        cursor.execute("PRAGMA table_info(rl_user_policies)")
        p_cols = [r[1] for r in cursor.fetchall()]
        if "total_reward" not in p_cols:
            cursor.execute("ALTER TABLE rl_user_policies ADD COLUMN total_reward REAL DEFAULT 0.0")

                # API Response Cache table (Open-Meteo, Overpass, REST Countries)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                source TEXT DEFAULT 'api',
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ttl_seconds INTEGER DEFAULT 86400
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_cache_key ON api_cache(cache_key)")

        conn.commit()

        # Seed curated activities catalog
        try:
            from app.activity_data import seed_curated_activities
            seed_curated_activities(conn)
        except Exception as e:
            print("Notice: activity seeding skipped:", e)

if __name__ == "__main__":
    init_db()
    print("Database ready:", DB_PATH)
