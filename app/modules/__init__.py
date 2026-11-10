"""Plug-in loader. Every team member adds ONE file here (app/modules/<id>.py).

A module file must define:
    MODULE = {"id": "prep", "title": "Trip Prep", "icon": "fa-suitcase", "owner": "A"}
    router = APIRouter(prefix="/api/prep")      # its own routes
and may define:
    def init_tables(conn): ...                  # CREATE TABLE IF NOT EXISTS for its own tables

main.py auto-discovers them, so nobody needs to edit api.py / main.py.
A module that fails to import is skipped with a warning (one person's bug must not kill the demo).
"""
import importlib
import pkgutil
import traceback
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

_SKIP = {"common"}
_loaded = None

def discover():
    global _loaded
    if _loaded is not None:
        return _loaded
    mods = []
    for info in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if info.name.startswith("_") or info.name in _SKIP:
            continue
        try:
            m = importlib.import_module(f"app.modules.{info.name}")
        except Exception:
            print(f"[modules] WARNING: could not import app.modules.{info.name}")
            traceback.print_exc()
            continue
        if getattr(m, "MODULE", None) and getattr(m, "router", None):
            mods.append(m)
    _loaded = mods
    return mods

def init_module_tables():
    from app.database import get_connection
    with get_connection() as conn:
        for m in discover():
            fn = getattr(m, "init_tables", None)
            if fn:
                fn(conn)
        conn.commit()

registry_router = APIRouter(prefix="/api")

@registry_router.get("/modules")
def list_modules(user_id: Optional[str] = Query(None)):
    """Used by static/modules/loader.js to build the 'Companion' tabs.
    Enforces deep personalization requirement when user_id is provided.
    Removes the exposed 'ranking' tab from the Companion interface (kept internally).
    """
    if user_id:
        from app.database import get_connection
        from app.modules.common import has_completed_deep_profile
        with get_connection() as conn:
            if not has_completed_deep_profile(conn, user_id):
                raise HTTPException(
                    status_code=403,
                    detail="Deep personalization profile required to unlock Travel Companion."
                )

    # Exclude 'ranking' from visible Companion tabs per product requirements
    # Exclude standalone 'places' demo tab so places powers the core itinerary instead
    return [
        m.MODULE for m in discover()
        if getattr(m, "MODULE", {}).get("id") not in ("ranking", "places")
    ]
