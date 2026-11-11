"""Core persistence store for shared contracts.

Manages SQLite tables for places cache, API credit usage tracking,
trip preferences, generated trip plans, stays, and post-trip feedback.
Uses lazy table initialization so no migrations or startup hooks are needed.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from app.database import get_connection
from app.core.schemas import TripPrefs, TripPlan, Stay

_TABLES_INITIALIZED = False


def ensure_core_tables(conn: sqlite3.Connection) -> None:
    """Lazily create core store tables if they do not exist."""
    global _TABLES_INITIALIZED
    if _TABLES_INITIALIZED:
        return

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_place_cache (
            cache_key TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            fetched_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_api_usage (
            date_str TEXT NOT NULL,
            service TEXT NOT NULL,
            call_count INTEGER DEFAULT 0,
            PRIMARY KEY (date_str, service)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_trip_prefs (
            trip_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            prefs_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_plans (
            trip_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_stays (
            stay_id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL,
            stay_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_trip_feedback (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            feedback_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    _TABLES_INITIALIZED = True


# --- Trip Preferences Helpers ---

def save_trip_prefs(prefs: TripPrefs) -> None:
    """Save or update trip preferences in core_trip_prefs."""
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO core_trip_prefs (trip_id, user_id, prefs_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trip_id) DO UPDATE SET
                user_id = excluded.user_id,
                prefs_json = excluded.prefs_json,
                updated_at = excluded.updated_at
        """, (prefs.trip_id, prefs.user_id, prefs.model_dump_json(), now))
        conn.commit()


def load_trip_prefs(trip_id: str) -> Optional[TripPrefs]:
    """Retrieve trip preferences by trip_id."""
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT prefs_json FROM core_trip_prefs WHERE trip_id = ?", (trip_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return TripPrefs.model_validate_json(row["prefs_json"])


# --- Trip Plans Helpers ---

def save_trip_plan(plan: TripPlan) -> None:
    """Save or update a full multi-day trip plan in core_plans."""
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO core_plans (trip_id, user_id, plan_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trip_id) DO UPDATE SET
                user_id = excluded.user_id,
                plan_json = excluded.plan_json,
                updated_at = excluded.updated_at
        """, (plan.trip_id, plan.user_id, plan.model_dump_json(), now))
        conn.commit()


def load_trip_plan(trip_id: str) -> Optional[TripPlan]:
    """Retrieve a trip plan by trip_id."""
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT plan_json FROM core_plans WHERE trip_id = ?", (trip_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return TripPlan.model_validate_json(row["plan_json"])


# --- Stays Helpers ---

def save_stay(stay: Stay) -> None:
    """Save or update a chosen stay accommodation anchor."""
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO core_stays (stay_id, trip_id, stay_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(stay_id) DO UPDATE SET
                trip_id = excluded.trip_id,
                stay_json = excluded.stay_json
        """, (stay.stay_id, stay.trip_id, stay.model_dump_json(), now))
        conn.commit()


def load_stay(trip_id: str) -> Optional[Stay]:
    """Retrieve the chosen stay anchor for a trip."""
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT stay_json FROM core_stays WHERE trip_id = ? ORDER BY created_at DESC LIMIT 1", (trip_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Stay.model_validate_json(row["stay_json"])


# --- Trip Feedback Helpers ---

def save_trip_feedback(trip_id: str, user_id: str, feedback: Dict[str, Any]) -> str:
    """Save post-trip feedback or activity evaluations."""
    feedback_id = str(uuid.uuid4())
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO core_trip_feedback (id, trip_id, user_id, feedback_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (feedback_id, trip_id, user_id, json.dumps(feedback), now))
        conn.commit()
    return feedback_id


def load_trip_feedback(trip_id: str) -> List[Dict[str, Any]]:
    """Retrieve all feedback entries recorded for a trip."""
    with get_connection() as conn:
        ensure_core_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT feedback_json FROM core_trip_feedback WHERE trip_id = ? ORDER BY created_at ASC", (trip_id,))
        rows = cursor.fetchall()
        return [json.loads(r["feedback_json"]) for r in rows]
