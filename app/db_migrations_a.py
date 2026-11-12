"""Idempotent database changes owned by Person A (accounts and profile history)."""
import json
import sqlite3
from typing import Dict, Iterable, List

from app.database import get_connection


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, name: str, declaration: str) -> None:
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def _normalise(value: str) -> str:
    return (value or "").strip().casefold()


def _flag_conflicts(
    conn: sqlite3.Connection,
    kind: str,
    pairs: Iterable[tuple],
) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for raw, user_id in pairs:
        normal = _normalise(raw)
        if normal:
            grouped.setdefault(normal, []).append(str(user_id))
    conflicts = {key: ids for key, ids in grouped.items() if len(ids) > 1}
    for value, user_ids in conflicts.items():
        conn.execute(
            """INSERT INTO auth_identity_conflicts
               (conflict_type, normalized_value, user_ids_json)
               VALUES (?, ?, ?)
               ON CONFLICT(conflict_type, normalized_value) DO UPDATE SET
                 user_ids_json=excluded.user_ids_json""",
            (kind, value, json.dumps(sorted(user_ids))),
        )
    return conflicts


def _migrate_legacy_history(conn: sqlite3.Connection) -> None:
    """Copy old single-score trips without inventing dates or missing ratings."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "past_trips" not in tables:
        return
    columns = _columns(conn, "past_trips")
    if not {"id", "user_id", "destination"}.issubset(columns):
        return
    rows = conn.execute("SELECT * FROM past_trips").fetchall()
    for row in rows:
        data = dict(row)
        destination = str(data.get("destination") or "").strip()
        if not destination:
            continue
        ratings = {}
        try:
            score = float(data.get("rating"))
            if 1 <= score <= 5:
                ratings["overall"] = int(round(score))
        except (TypeError, ValueError):
            pass
        notes = "; ".join(
            part for part in (
                f"Enjoyed: {data.get('favorite_activity')}" if data.get("favorite_activity") else "",
                f"Disliked: {data.get('skipped_or_disliked')}" if data.get("skipped_or_disliked") else "",
            ) if part
        ) or None
        conn.execute(
            """INSERT OR IGNORE INTO travel_history
               (id, user_id, destination, city, visited_on, trip_type, ratings_json,
                would_revisit, notes, source, trip_id)
               VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, ?, 'manual', NULL)""",
            (f"legacy_{data['id']}", data["user_id"], destination, json.dumps(ratings), notes),
        )


def migrate_a() -> None:
    """Create A-owned tables and normalized auth indexes without discarding rows."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""CREATE TABLE IF NOT EXISTS auth_identity_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_type TEXT NOT NULL,
            normalized_value TEXT NOT NULL,
            user_ids_json TEXT NOT NULL,
            flagged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(conflict_type, normalized_value)
        )""")

        _add_column(conn, "users", "username", "TEXT")
        _add_column(conn, "users", "username_normalized", "TEXT")
        _add_column(conn, "users", "email", "TEXT")
        _add_column(conn, "users", "email_normalized", "TEXT")
        _add_column(conn, "users", "identifier_normalized", "TEXT")
        _add_column(conn, "users", "google_sub", "TEXT")

        conn.execute("""CREATE TABLE IF NOT EXISTS user_profile (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            history_choice TEXT CHECK(history_choice IN ('none', 'provided') OR history_choice IS NULL),
            profile_complete INTEGER NOT NULL DEFAULT 0 CHECK(profile_complete IN (0, 1)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS travel_history (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            destination TEXT NOT NULL,
            city TEXT,
            visited_on TEXT,
            trip_type TEXT CHECK(trip_type IN ('solo', 'couple', 'friends', 'family') OR trip_type IS NULL),
            ratings_json TEXT NOT NULL DEFAULT '{}',
            would_revisit INTEGER CHECK(would_revisit IN (0, 1) OR would_revisit IS NULL),
            notes TEXT,
            source TEXT NOT NULL CHECK(source IN ('manual', 'trip')),
            trip_id TEXT REFERENCES trips(id) ON DELETE SET NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS auth_login_attempts (
            login_key TEXT NOT NULL,
            ip_key TEXT NOT NULL,
            failed_count INTEGER NOT NULL DEFAULT 0,
            window_started_at TEXT NOT NULL,
            locked_until TEXT,
            PRIMARY KEY(login_key, ip_key)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS travel_history_exclusions (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            trip_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, trip_id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_history_user ON travel_history(user_id, visited_on DESC)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_travel_history_manual_place_date ON travel_history(user_id, lower(destination), visited_on) WHERE source='manual' AND visited_on IS NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_travel_history_trip ON travel_history(user_id, trip_id) WHERE source='trip' AND trip_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id)")

        # Import existing email identifiers and flag, never merge or delete,
        # case-variant duplicates from older databases.
        rows = conn.execute("SELECT id, auth_provider, identifier, email FROM users").fetchall()
        for row in rows:
            if row[1] == "email" and not row[3]:
                conn.execute("UPDATE users SET email=? WHERE id=?", (row[2], row[0]))
        rows = conn.execute("SELECT id, identifier, email FROM users").fetchall()
        identifier_conflicts = _flag_conflicts(conn, "identifier", ((r[1], r[0]) for r in rows))
        email_conflicts = _flag_conflicts(conn, "email", ((r[2], r[0]) for r in rows if r[2]))
        for row in rows:
            ident = _normalise(row[1])
            mail = _normalise(row[2])
            conn.execute(
                "UPDATE users SET identifier_normalized=?, email_normalized=? WHERE id=?",
                (None if ident in identifier_conflicts else ident or None,
                 None if mail in email_conflicts else mail or None,
                 row[0]),
            )

        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_users_identifier_normalized
                        ON users(identifier_normalized) WHERE identifier_normalized IS NOT NULL""")
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_normalized
                        ON users(email_normalized) WHERE email_normalized IS NOT NULL""")
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_normalized
                        ON users(username_normalized) WHERE username_normalized IS NOT NULL""")

        conn.execute("INSERT OR IGNORE INTO user_profile(user_id) SELECT id FROM users")
        _migrate_legacy_history(conn)
        conn.commit()
