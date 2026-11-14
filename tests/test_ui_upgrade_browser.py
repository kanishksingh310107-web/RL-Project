"""Browser regressions for the merged frontend/backend contract.

Requires Playwright and its Chromium browser in the integration test environment.
Uses the real static app with mocked APIs; it never calls external travel services.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def static_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def ui(static_url):
    trip = {"id": "trip-1", "user_id": "ui-user", "trip_type": "family", "companions": "family", "destination_id": "hampi_india", "destination_name": "Hampi", "start_date": "2099-01-01", "end_date": "2099-01-02", "duration_days": 2, "total_budget": 25000, "travellers_count": 2, "party": {"adults": 2, "children": 0, "seniors": 0}, "trip_preferences": {}}
    runtime = {"trip_id": "trip-1", "status": "draft", "phase": "draft", "runtime": {"current_day": 1}, "total_days": 2, "current_activity": None, "pending_review": None, "pending_decision": None, "runs": [], "schedule": [], "today": [], "closed_out": False, "rating_keys": ["overall"], "post_feedback": None}
    blocks = [{"id": "occ-1", "activity_id": "place-1", "type": "activity", "title": "Temple visit", "time_range": "10:00 – 11:00", "duration_minutes": 60, "cost_estimate": 100, "acceptance_status": "unreviewed"}, {"type": "travel", "title": "Travel to market", "time_range": "11:00 – 11:30", "duration_minutes": 30, "cost_estimate": 100}, {"id": "occ-2", "activity_id": "place-1", "type": "activity", "title": "Market visit", "time_range": "11:30 – 12:30", "duration_minutes": 60, "cost_estimate": 0, "acceptance_status": "unreviewed"}]
    recorded = []
    options = {"profile_complete": True, "preview_fails": False, "capabilities": True}

    def mock(route):
        request = route.request
        url = request.url.split("?", 1)[0]
        path = "/api/" + url.split("/api/", 1)[1]
        recorded.append((request.method, path, request.post_data_json if request.post_data else None))
        result = {}
        status = 200
        if path == "/api/config/google":
            result = {"client_id": "", "can_configure": True}
        elif path == "/api/profile/status":
            result = {"profile_complete": options["profile_complete"]}
        elif path == "/api/trip-experience/capabilities":
            result = {key: options["capabilities"] for key in ["schedule_preferences_v2", "explicit_trip_type", "occurrence_acceptance", "itinerary_preview", "custom_activities", "expenses", "readonly_sharing", "live_adjustments"]}
        elif path == "/api/trips/ui-user":
            result = [trip]
        elif path == "/api/trips/detail/trip-1":
            result = trip
        elif path == "/api/trips/trip-1/runtime":
            result = runtime
        elif path == "/api/itinerary/trip-1":
            result = {"id": "itin-1", "trip_id": "trip-1", "destination_name": "Hampi", "total_days": 2, "total_estimated_cost": 300, "days": [{"day_number": 1, "activities": [], "total_cost": 300}]}
        elif path == "/api/trip-actions/trip-1/timed-view":
            result = {"trip": trip, "itinerary": {"id": "itin-1"}, "days": [{"day_number": 1, "timeline": blocks, "formatted_date": "1 Jan 2099"}], "has_itinerary": True}
        elif path == "/api/recommendations/ui-user":
            result = {"recommended_for_you": [{"id": "hampi_india", "name": "Hampi", "match_score": 51, "why_recommended": "You enjoy heritage walks."}], "trending_trips": [], "seasonal_and_upcoming": []}
        elif path == "/api/trip-actions/trip-1/acceptance":
            body = request.post_data_json
            for block in blocks:
                if block.get("id") == body.get("itinerary_activity_id"):
                    block["acceptance_status"] = "accepted" if body["action"] == "accept" else "rejected"
            result = {"saved": True}
        elif path == "/api/trip-actions/trip-1/preview":
            if options["preview_fails"]:
                status, result = 503, {"detail": "Preview unavailable. Please retry.", "code": "DOWNSTREAM_UNAVAILABLE"}
            else:
                result = {"preview": {"token": "preview-1", "summary": "Move this activity earlier", "timeline": [{"time_range": "09:00 – 10:00", "title": "Temple visit"}]}}
        route.fulfill(status=status, json=result)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route("**/api/**", mock)
        page.route("https://**", lambda route: route.abort())
        page.goto(static_url + "/static/index.html", wait_until="domcontentloaded")
        page.add_style_tag(content=".hidden{display:none!important}")
        page.evaluate("state.currentUser={user_id:'ui-user',display_name:'UI User'};state.currentProfile={};state.profileStatus={complete:true};activeUserTrips=[];showView('dashboard');")
        yield page, options, runtime, recorded
        browser.close()


def open_trip(page):
    page.evaluate("location.hash='/trips/trip-1'")
    playwright.expect(page.locator("#workspaceEditorContainer")).to_contain_text("Temple visit")


def test_google_unconfigured_offers_fallback_without_setup(ui):
    page, _, _, _ = ui
    page.evaluate("initGoogleGIS()")
    playwright.expect(page.locator("#googleAuthStatus")).to_contain_text("email")
    assert page.locator("#googleConfigModal,#googleSetupLink").count() == 0


def test_new_trip_is_full_page_and_retains_draft(ui):
    page, _, _, _ = ui
    page.evaluate("location.hash='/trips/new'")
    playwright.expect(page.locator("#tripExperienceView")).to_be_visible()
    page.locator("#tripNotesInput").fill("Keep an afternoon free")
    page.locator("#teTripType").select_option("family")
    page.locator("#tripAdultsInput").fill("3")
    page.locator("#tripAdultsInput").dispatch_event("change")
    playwright.expect(page.locator("#teTripType")).to_have_value("family")
    page.get_by_role("link", name="Back to main menu").click()
    playwright.expect(page.locator("#dashboardView")).to_be_visible()
    page.go_back()
    playwright.expect(page.locator("#tripNotesInput")).to_have_value("Keep an afternoon free")


def test_recommendations_have_reasons_and_honest_match_label(ui):
    page, _, _, _ = ui
    page.evaluate("location.hash='/trips/new'")
    playwright.expect(page.locator("#teDestinationRecommendations")).to_contain_text("heritage walks")
    playwright.expect(page.locator("#teDestinationRecommendations")).not_to_contain_text("90%")
    assert page.locator("#tripDestSelect").is_hidden()


def test_single_accept_does_not_accept_same_place_on_other_occurrence(ui):
    page, _, _, recorded = ui
    open_trip(page)
    page.locator('[data-occurrence="occ-1"] [data-choice="accept"]').click()
    playwright.expect(page.locator("#workspaceEditorContainer")).to_contain_text("1 of 2 activities accepted")
    playwright.expect(page.locator('[data-occurrence="occ-2"]')).to_contain_text("Not reviewed")
    requests = [body for method, path, body in recorded if path.endswith("/acceptance")]
    assert requests == [{"itinerary_activity_id": "occ-1", "action": "accept"}]


def test_preview_cancel_and_failure_do_not_confirm(ui):
    page, options, _, recorded = ui
    open_trip(page)
    page.locator('[data-occurrence="occ-1"] [data-edit="earlier"]').click()
    playwright.expect(page.get_by_role("dialog")).to_contain_text("Move this activity earlier")
    page.get_by_role("button", name="Cancel / close").click()
    assert not any(path.endswith("/confirm") for _, path, _ in recorded)
    options["preview_fails"] = True
    page.locator('[data-occurrence="occ-1"] [data-edit="earlier"]').click()
    playwright.expect(page.locator("[data-status]")).to_contain_text("Preview unavailable")
    playwright.expect(page.locator('[data-occurrence="occ-1"]')).to_contain_text("10:00")


def test_phase_locks_and_post_type_prefill(ui):
    page, _, runtime, _ = ui
    open_trip(page)
    playwright.expect(page.locator("#wsTabBtn-live")).to_be_disabled()
    playwright.expect(page.locator("#wsTabBtn-post")).to_be_disabled()
    runtime.update(status="completed", phase="completed", feedback_required=True)
    page.evaluate("TripExperience.route()")
    playwright.expect(page.locator("#wsTabBtn-live")).to_be_disabled()
    playwright.expect(page.locator("#wsTabBtn-post")).to_be_enabled()
    playwright.expect(page.locator('#workspacePostContainer select[name="trip_type"]')).to_have_value("family")
    page.evaluate("switchWorkspaceMode('live')")
    playwright.expect(page.locator("#workspaceLiveTrip")).to_be_hidden()


def test_missing_capabilities_disable_unsupported_writes(ui):
    page, options, _, _ = ui
    options["capabilities"] = False
    open_trip(page)
    playwright.expect(page.locator('[data-occurrence="occ-1"] [data-choice="accept"]')).to_be_disabled()
    playwright.expect(page.locator('[data-custom]')).to_be_disabled()
    playwright.expect(page.locator('[data-share]')).to_be_disabled()


def test_past_trips_only_collected_in_basic_history(ui):
    page, _, _, _ = ui
    assert page.locator("#personalPastTripsSection").count() == 0


def test_invalid_dates_and_fractional_budget_keep_values(ui):
    page, _, _, recorded = ui
    page.evaluate("location.hash='/trips/new'")
    playwright.expect(page.locator("#teDestinationRecommendations")).to_contain_text("Hampi")
    page.locator("#teDestinationRecommendations button").click()
    page.locator("#tripStartDateInput").fill("2020-01-02")
    page.locator("#tripEndDateInput").fill("2020-01-01")
    page.locator("#tripBudgetInput").fill("25000.50")
    page.evaluate("document.getElementById('tripCreateForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
    playwright.expect(page.locator("#tripStartDateInputUiError")).to_contain_text("before today")
    playwright.expect(page.locator("#tripEndDateInputUiError")).to_contain_text("after departure")
    playwright.expect(page.locator("#tripBudgetInputUiError")).to_contain_text("whole-rupee")
    playwright.expect(page.locator("#tripBudgetInput")).to_have_value("25000.50")
    assert not any(method == "POST" and path == "/api/trips/ui-user" for method, path, _ in recorded)


def test_departure_buffers_and_lunch_inputs_are_separate_from_checkout(ui):
    page, _, _, _ = ui
    page.evaluate("location.hash='/trips/new'")
    playwright.expect(page.locator("#teDepartureMode")).to_be_enabled()
    page.locator("#teDepartureMode").select_option("flight")
    page.locator("#teTransportDeparture").fill("18:00")
    page.locator("#teTerminalTravel").fill("60")
    playwright.expect(page.locator("#teCheckinBuffer")).to_have_value("120")
    playwright.expect(page.locator("#teDepartureWindow")).to_contain_text("15:00")
    page.locator("#teDepartureMode").select_option("train")
    playwright.expect(page.locator("#teCheckinBuffer")).to_have_value("60")
    page.locator("#teLunchTime").fill("13:30")
    page.locator("#teLunchDuration").fill("45")
    prefs = page.evaluate("TripExperience.readExperience()")
    assert prefs["lunch_time"] == "13:30"
    assert prefs["lunch_duration_minutes"] == 45
    page.locator("#teFinalActivities").select_option("no")
    playwright.expect(page.locator("#teDepartureWindow")).to_contain_text("reserved for departure")


def test_timeline_includes_travel_and_accessible_reordering(ui):
    page, _, _, _ = ui
    open_trip(page)
    playwright.expect(page.locator("#workspaceEditorContainer")).to_contain_text("Travel to market")
    playwright.expect(page.get_by_role("button", name="Move Temple visit earlier")).to_be_enabled()
    assert page.locator("#workspaceEditorContainer [draggable=true]").count() == 2


def test_deep_profile_gate_prevents_new_trip(ui):
    page, _, _, recorded = ui
    page.evaluate("state.profileStatus={complete:false};location.hash='/trips/new'")
    playwright.expect(page.locator("#tripExperienceView")).to_be_hidden()
    assert not any(method == "POST" and path == "/api/trips/ui-user" for method, path, _ in recorded)
