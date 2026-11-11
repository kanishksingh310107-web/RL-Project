"""SQLite-backed cache for places, geocoding, and weather data.

Implements TTL-based caching using the core_place_cache table.
Never stores sensitive user data, emails, or profile answers.
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from app.database import get_connection
from app.core.stores import ensure_core_tables
from app.core.assumptions import CACHE_TTL_DAYS_PLACES, CACHE_TTL_HOURS_WEATHER

TTL_PLACES_SECONDS: int = CACHE_TTL_DAYS_PLACES * 86400
TTL_WEATHER_SECONDS: int = CACHE_TTL_HOURS_WEATHER * 3600


def get_cached(cache_key: str) -> Optional[Any]:
    """Retrieve non-expired cached object by key, or None if expired/missing."""
    try:
        with get_connection() as conn:
            ensure_core_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_json, expires_at FROM core_place_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            now = datetime.now(timezone.utc)
            expires_at = datetime.fromisoformat(row["expires_at"])
            if now > expires_at:
                # Expired: clean up lazily
                cursor.execute("DELETE FROM core_place_cache WHERE cache_key = ?", (cache_key,))
                conn.commit()
                return None

            return json.loads(row["data_json"])
    except Exception:
        return None


def set_cached(cache_key: str, data: Any, ttl_seconds: int = TTL_PLACES_SECONDS) -> None:
    """Store data in cache with specified TTL in seconds."""
    try:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        data_json = json.dumps(data)

        with get_connection() as conn:
            ensure_core_tables(conn)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO core_place_cache (cache_key, data_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    data_json = excluded.data_json,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
            """, (cache_key, data_json, now.isoformat(), expires_at.isoformat()))
            conn.commit()
    except Exception:
        pass
