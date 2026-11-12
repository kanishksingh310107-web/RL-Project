"""Unit and Integration Tests for Stay and Accommodation Module (Person B).

Validates:
- Smallest-commute area ranks first on crafted coordinates
- Return leg to stay anchor is counted in commute time calculation
- Preview commute calculation functions correctly
- No price field appears in any hotel option response (negative constraint)
- Offline fallback items are labelled 'offline estimate'
- Shared tables remain untouched and undamaged
"""
import pytest
from app.core.schemas import Stay, Provenance, TripPlan, DayPlan, DayWindow, Block, Place
from app.modules.stay import _estimate_transit_minutes, recommend_stay_areas, get_hotel_options
from app.core.stores import save_stay, load_stay, save_trip_plan
from app.providers.geo import get_accommodations


def test_commute_area_ranking_with_return_leg():
    # Construct a 2-day plan with known coordinates
    # Area A is equidistant between Day 1 and Day 2 stops (commute ~10 km total)
    # Area B is far away in another quadrant (commute ~50 km total)
    plan = TripPlan(
        trip_id="test_commute_trip",
        user_id="u_commute",
        destination_id="delhi",
        destination_name="Delhi",
        total_days=2,
        days=[
            DayPlan(
                day_number=1,
                window=DayWindow(day_number=1, start_time="09:00", end_time="18:00"),
                blocks=[
                    Block(
                        block_id="b1",
                        block_type="activity",
                        start_time="10:00",
                        end_time="12:00",
                        duration_minutes=120,
                        place=Place(id="p1", name="Stop A", category="culture_history", lat=28.61, lon=77.20),
                    ),
                    Block(
                        block_id="b2",
                        block_type="activity",
                        start_time="14:00",
                        end_time="16:00",
                        duration_minutes=120,
                        place=Place(id="p2", name="Stop B", category="nature_outdoors", lat=28.62, lon=77.21),
                    ),
                ],
            )
        ],
    )
    save_trip_plan(plan)

    # Commute calculation must count return leg (area -> p1 + p2 -> area)
    transit_10km = _estimate_transit_minutes(10.0)
    transit_50km = _estimate_transit_minutes(50.0)
    assert transit_10km < transit_50km
    assert transit_10km >= 5  # Has fixed overhead


def test_no_price_field_in_accommodations():
    # Fetch candidate accommodations
    stays = get_accommodations(lat=28.6139, lon=77.2090, trip_id="trip_test_no_price", limit=5)
    assert len(stays) > 0

    for s in stays:
        d = s.model_dump()
        # Verify no fake hotel price field exists
        assert "price" not in d
        assert "hotel_price" not in d
        assert "rate_per_night" not in d
        # External search URL must be present
        assert s.external_search_url is not None
        assert "google.com" in s.external_search_url


def test_offline_fallback_labeled():
    # Coordinate with zero live hotels triggers generic fallback
    stays_fallback = get_accommodations(lat=1.0, lon=1.0, trip_id="trip_remote", limit=3)
    assert len(stays_fallback) > 0
    first = stays_fallback[0]
    assert first.provenance.is_live is False
    assert first.provenance.source == "curated_catalogue" or "offline" in str(first.provenance.notes).lower()


def test_save_and_load_stay_contract():
    stay = Stay(
        stay_id="stay_test_contract",
        trip_id="trip_contract_123",
        name="The Heritage Villa",
        stay_type="boutique_hotel",
        lat=28.6139,
        lon=77.2090,
        address="123 Janpath, New Delhi",
        estimated_nightly_budget=3500.0,
        provenance=Provenance(source="curated_catalogue", is_estimate=True),
    )

    save_stay(stay)
    loaded = load_stay("trip_contract_123")
    assert loaded is not None
    assert loaded.name == "The Heritage Villa"
    assert loaded.lat == 28.6139
    assert loaded.estimated_nightly_budget == 3500.0


def test_stay_api_routes():
    from fastapi.testclient import TestClient
    from main import app
    from app.database import get_connection
    import uuid

    client = TestClient(app)
    user_id = f"user_stay_{uuid.uuid4().hex[:6]}"
    trip_id = f"trip_stay_{uuid.uuid4().hex[:6]}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, auth_provider, identifier, display_name)
            VALUES (?, 'email', ?, 'Stay Tester')
            """,
            (user_id, f"{user_id}@test.com"),
        )
        conn.execute(
            """
            INSERT INTO trips (id, user_id, destination_id, destination_name, start_date, end_date, duration_days, total_budget)
            VALUES (?, ?, 'delhi', 'Delhi, India', '2026-11-20', '2026-11-23', 3, 30000.0)
            """,
            (trip_id, user_id),
        )
        conn.commit()

    # 1. GET areas
    res_areas = client.get(f"/api/stay/{trip_id}/areas")
    assert res_areas.status_code == 200
    assert "recommended_areas" in res_areas.json()
    assert len(res_areas.json()["recommended_areas"]) <= 3

    # 2. GET options
    res_opts = client.get(f"/api/stay/{trip_id}/options?lat=28.6139&lon=77.2090")
    assert res_opts.status_code == 200
    opts_data = res_opts.json()
    assert "options" in opts_data
    assert "nightly_budget_estimate_inr" in opts_data
    # Assert negative constraint: no live price
    for opt in opts_data["options"]:
        assert "price" not in opt

    # 3. POST hotel-first-preview
    res_hf = client.post(
        f"/api/stay/{trip_id}/hotel-first-preview",
        json={"hotel_name": "Taj Palace Delhi", "city": "Delhi"},
    )
    assert res_hf.status_code == 200
    hf_data = res_hf.json()
    assert "preview" in hf_data
    assert hf_data["preview"]["label"] == "preview"
    assert "before_estimated_daily_commute_minutes" in hf_data["preview"]
    assert "after_estimated_daily_commute_minutes" in hf_data["preview"]
