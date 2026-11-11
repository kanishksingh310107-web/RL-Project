"""Credit guard and rate limiter for external API providers.

Prevents exceeding free-tier allowances (2,500 calls/day on Geoapify)
and enforces a maximum call limit per user interaction request.
"""
from datetime import datetime, timezone
import threading

from app.database import get_connection
from app.core.stores import ensure_core_tables
from app.core.assumptions import GEOAPIFY_DAILY_CREDIT_LIMIT, GEOAPIFY_MAX_CALLS_PER_REQUEST

_local = threading.local()


def get_request_call_count() -> int:
    """Get number of external API calls made in the current thread/request."""
    return getattr(_local, "call_count", 0)


def reset_request_counter() -> None:
    """Reset the thread-local request call counter."""
    _local.call_count = 0


def get_daily_usage(service: str = "geoapify") -> int:
    """Get the total recorded calls for today (UTC) for a given service."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with get_connection() as conn:
            ensure_core_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT call_count FROM core_api_usage WHERE date_str = ? AND service = ?",
                (today_str, service)
            )
            row = cursor.fetchone()
            return int(row["call_count"]) if row else 0
    except Exception:
        return 0


def can_call_geoapify() -> bool:
    """Check whether a Geoapify call is permitted under daily and request ceilings."""
    # 1. Check request limit
    req_count = get_request_call_count()
    if req_count >= GEOAPIFY_MAX_CALLS_PER_REQUEST:
        return False

    # 2. Check daily credit limit
    daily_count = get_daily_usage("geoapify")
    if daily_count >= GEOAPIFY_DAILY_CREDIT_LIMIT:
        return False

    return True


def record_geoapify_call() -> None:
    """Record an executed Geoapify call against daily and request limits."""
    _local.call_count = get_request_call_count() + 1
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with get_connection() as conn:
            ensure_core_tables(conn)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO core_api_usage (date_str, service, call_count)
                VALUES (?, 'geoapify', 1)
                ON CONFLICT(date_str, service) DO UPDATE SET
                    call_count = call_count + 1
            """, (today_str,))
            conn.commit()
    except Exception:
        pass
