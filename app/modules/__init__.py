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
from fastapi import APIRouter

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
def list_modules():
    """Used by static/modules/loader.js to build the 'Companion' tabs."""
    return [m.MODULE for m in discover()]
