"""Idempotent schema for recommendation discovery and trip finance (D-owned)."""
import sqlite3


def migrate_d(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trip_budget_allocations (
            trip_id TEXT PRIMARY KEY REFERENCES trips(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            total_budget_inr INTEGER NOT NULL CHECK(total_budget_inr >= 0),
            allocations_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS discovery_feedback (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            destination_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS d_discovery_user_created ON discovery_feedback(user_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS assistant_request_limits (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            requested_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS d_assistant_rate_limit ON assistant_request_limits(user_id,requested_at);
        CREATE TABLE IF NOT EXISTS trip_expenses (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL CHECK(category IN ('shopping','transport','food','stay','activities','other')),
            amount_inr INTEGER NOT NULL CHECK(amount_inr >= 0),
            note TEXT NOT NULL DEFAULT '',
            spent_on TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cols = {r[1] for r in conn.execute('PRAGMA table_info(trip_expenses)')}
    additions = (
        ('idempotency_key', 'TEXT'),
        ('paid_by', 'TEXT'),
        ('planned_cost_key', 'TEXT'),
        ('is_final_for_planned_cost', 'INTEGER NOT NULL DEFAULT 0'),
        ('updated_at', 'TEXT'),
    )
    for name, declaration in additions:
        if name not in cols:
            conn.execute(f'ALTER TABLE trip_expenses ADD COLUMN {name} {declaration}')
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS d_expense_idempotency
        ON trip_expenses(trip_id,user_id,idempotency_key) WHERE idempotency_key IS NOT NULL""")
    conn.execute('CREATE INDEX IF NOT EXISTS d_expense_trip_date ON trip_expenses(trip_id,spent_on,id)')
    activity_cols = {r[1] for r in conn.execute('PRAGMA table_info(itinerary_activities)')}
    if 'planning_priority' not in activity_cols:
        conn.execute("ALTER TABLE itinerary_activities ADD COLUMN planning_priority TEXT NOT NULL DEFAULT 'nice_to_do'")
    conn.commit()

