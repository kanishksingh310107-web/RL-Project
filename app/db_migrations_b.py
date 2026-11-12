"""Idempotent schema migration owned by Person B."""

import sqlite3


def migrate_b(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trip_schedule_prefs (
            trip_id TEXT PRIMARY KEY,
            hotel_arrival_time TEXT NOT NULL DEFAULT '14:00',
            hotel_departure_time TEXT NOT NULL DEFAULT '11:00',
            wake_time TEXT NOT NULL DEFAULT '07:00',
            bed_time TEXT NOT NULL DEFAULT '21:00',
            activity_start_time TEXT NOT NULL DEFAULT '09:00',
            free_blocks_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


def run_b_migration() -> None:
    from app.database import get_connection
    with get_connection() as conn:
        migrate_b(conn)
