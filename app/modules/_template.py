"""COPY THIS FILE to app/modules/<your_id>.py and rename. Files starting with '_' are ignored by the loader."""
from fastapi import APIRouter, HTTPException
from app.database import get_connection
from app.modules.common import get_trip, get_user_context, get_itinerary

MODULE = {"id": "template", "title": "Template", "icon": "fa-puzzle-piece", "owner": "-"}
router = APIRouter(prefix="/api/template", tags=["template"])

def init_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS template_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id TEXT NOT NULL, note TEXT)""")

@router.get("/{trip_id}")
def hello(trip_id: str):
    trip = get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "trip not found")
    return {"trip": trip["destination_name"], "has_itinerary": get_itinerary(trip_id) is not None}
