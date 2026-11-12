"""Person C's idempotent execution/review schema. No history/profile writes."""
from app.database import get_connection


def migrate_c(conn=None):
    if conn is None:
        with get_connection() as connection:
            migrate_c(connection)
            connection.commit()
        return
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trip_runtime (
            trip_id TEXT PRIMARY KEY REFERENCES trips(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','finalized','live','completed')),
            current_activity_id TEXT,
            started_at TEXT,
            ended_at TEXT,
            current_day INTEGER NOT NULL DEFAULT 1,
            day_ended INTEGER NOT NULL DEFAULT 0,
            pending_decision_json TEXT,
            preview_json TEXT,
            operation_in_flight INTEGER NOT NULL DEFAULT 0,
            operation_started_at TEXT,
            last_confirmation_token TEXT,
            version INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS activity_runs (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            activity_id TEXT NOT NULL,
            itinerary_activity_id TEXT NOT NULL,
            day_number INTEGER NOT NULL,
            started_at TEXT,
            ended_at TEXT,
            ratings_json TEXT,
            notes TEXT NOT NULL DEFAULT '',
            action TEXT CHECK(action IN ('keep','enhance','change')),
            outcome TEXT NOT NULL DEFAULT 'in_progress' CHECK(outcome IN ('in_progress','completed','early_ended','skipped','not_done')),
            context_json TEXT,
            learning_applied INTEGER NOT NULL DEFAULT 0,
            UNIQUE(trip_id,itinerary_activity_id)
        );
        CREATE TABLE IF NOT EXISTS post_trip_feedback (
            trip_id TEXT PRIMARY KEY REFERENCES trips(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            ratings_json TEXT NOT NULL DEFAULT '{}',
            trip_type TEXT CHECK(trip_type IN ('solo','couple','friends','family')),
            would_revisit TEXT CHECK(would_revisit IN ('yes','no','maybe')),
            liked TEXT NOT NULL DEFAULT '',
            disliked TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            per_place_ratings_json TEXT NOT NULL DEFAULT '[]',
            delivery_started_at TEXT,
            submitted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS c_runs_trip_day ON activity_runs(trip_id,day_number);
    """)
    columns = {row[1] for row in conn.execute('PRAGMA table_info(trip_runtime)')}
    if 'operation_started_at' not in columns:
        conn.execute('ALTER TABLE trip_runtime ADD COLUMN operation_started_at TEXT')
    feedback_columns = {row[1] for row in conn.execute('PRAGMA table_info(post_trip_feedback)')}
    if 'delivery_started_at' not in feedback_columns:
        conn.execute('ALTER TABLE post_trip_feedback ADD COLUMN delivery_started_at TEXT')
