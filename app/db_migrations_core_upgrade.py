"""Idempotent core-upgrade tables for actual expenses, sharing and edit undo."""
from app.database import get_connection


def migrate_core_upgrade(conn=None):
    if conn is None:
        with get_connection() as connection:
            migrate_core_upgrade(connection)
            connection.commit()
        return
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trip_expenses (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('shopping','transport','food','stay','activities','other')),
            amount_inr INTEGER NOT NULL CHECK(amount_inr >= 0),
            note TEXT NOT NULL DEFAULT '',
            spent_on TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS core_expenses_trip_date ON trip_expenses(trip_id,spent_on,id);
        CREATE TABLE IF NOT EXISTS trip_share_links (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT
        );
        CREATE INDEX IF NOT EXISTS core_shares_trip ON trip_share_links(trip_id,revoked_at);
        CREATE TABLE IF NOT EXISTS trip_edit_history (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            undone_at TEXT
        );
        CREATE INDEX IF NOT EXISTS core_edits_trip_time ON trip_edit_history(trip_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS trip_edit_previews (
            token TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL, fingerprint TEXT NOT NULL, payload_json TEXT NOT NULL,
            preview_json TEXT NOT NULL, confirmed_at TEXT
        );
    """)
    activity_columns = {row[1] for row in conn.execute('PRAGMA table_info(itinerary_activities)')}
    for name, declaration in (
        ('is_pinned', 'INTEGER NOT NULL DEFAULT 0'),
        ('must_visit', 'INTEGER NOT NULL DEFAULT 0'),
        ('is_fixed_booking', 'INTEGER NOT NULL DEFAULT 0'),
        ('booking_start_time', 'TEXT'),
        ('booking_end_time', 'TEXT'),
        ('booking_label', 'TEXT'),
    ):
        if name not in activity_columns:
            conn.execute(f'ALTER TABLE itinerary_activities ADD COLUMN {name} {declaration}')
    conn.commit()
