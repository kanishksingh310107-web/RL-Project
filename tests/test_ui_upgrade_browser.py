"""Browser regressions for the merged frontend/backend contract.

Requires Playwright and its Chromium browser in the integration test environment.
Uses the real static app with mocked APIs; it never calls external travel services.
"""
import os
import re
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
            result = trip if request.method == 'POST' else [trip]
        elif path == "/api/itinerary/generate/trip-1":
            result = {"id": "itin-1", "trip_id": "trip-1", "destination_name": "Hampi", "total_days": 2, "days": []}
        elif path == "/api/trips/detail/trip-1":
            result = trip
        elif path == "/api/trips/trip-1/runtime":
            result = runtime
        elif path == "/api/itinerary/trip-1":
            result = {"id": "itin-1", "trip_id": "trip-1", "destination_name": "Hampi", "total_days": 2, "total_estimated_cost": 300, "days": [{"day_number": 1, "activities": [], "total_cost": 300}]}
        elif path == "/api/trip-actions/trip-1/timed-view":
            result = {"trip": trip, "itinerary": {"id": "itin-1"}, "days": [{"day_number": 1, "timeline": blocks, "formatted_date": "1 Jan 2099"}], "has_itinerary": True}
        elif path == "/api/recommendations/ui-user":
            result = {"recommended_for_you": [{"id": "hampi_india", "name": "Hampi", "image_url":"/static/images/destinations/hampi_karnataka_india.jpg", "image_source_url":"https://en.wikipedia.org/wiki/Hampi", "match_score": 51, "why_recommended": "You enjoy heritage walks."}], "trending_trips": [], "seasonal_and_upcoming": []}
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
        browser = p.chromium.launch(channel=os.environ.get('TRAVEL_TEST_BROWSER_CHANNEL') or None)
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
    playwright.expect(page.locator("#teTripType")).to_be_hidden()
    page.locator("#tripAdultsInput").fill("3")
    page.locator("#tripAdultsInput").dispatch_event("change")
    playwright.expect(page.locator("#teTripType")).to_have_value("friends")
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


def test_dashboard_destination_photo_loads_without_external_network(ui):
    page, _, _, _ = ui
    page.evaluate('loadRecommendations()')
    photo=page.locator('#recommendedGrid img').first
    playwright.expect(photo).to_have_attribute('src',re.compile(r'/static/images/destinations/hampi_karnataka_india.jpg$'))
    page.wait_for_function("document.querySelector('#recommendedGrid img')?.naturalWidth > 0")
    playwright.expect(page.locator('#recommendedGrid').get_by_role('link',name='Photo source')).to_have_attribute('href','https://en.wikipedia.org/wiki/Hampi')


@pytest.mark.parametrize('with_meal_override', [False, True])
def test_create_trip_submits_preferences_and_generates_itinerary(ui, with_meal_override):
    page, _, _, recorded = ui
    errors, dialogs = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page.locator('#headerPlanTripBtn').click()
    playwright.expect(page.locator('#teDestinationRecommendations')).to_contain_text('Hampi')
    page.locator('#teDestinationRecommendations button').click()
    page.locator('#tripStartDateInput').fill('2099-01-01')
    page.locator('#tripEndDateInput').fill('2099-01-02')
    page.locator('#tripBudgetInput').fill('25000')
    assert page.locator('#teJourneyMode option').evaluate_all('(options)=>options.map(option=>option.value)') == ['flight','train','bus','car']
    page.locator('#teJourneyMode').select_option('train')
    page.locator('#tripTransitSelect').select_option('cab_rental')
    playwright.expect(page.locator('#teTripType')).to_be_hidden()
    playwright.expect(page.locator('#teRestDuration')).to_be_hidden()
    playwright.expect(page.locator('#teShopping')).to_be_hidden()
    page.locator('#teCheckoutGapChoice').select_option('activity')
    page.locator('#tripNotesInput').fill('Keep my travel preferences')
    if with_meal_override:
        page.get_by_role('button', name='Add a per-day meal time', exact=True).click()
        page.locator('.teMealOverrideLunch').fill('13:30')
        page.get_by_role('link', name='Back to main menu').click()
        page.go_back()
        playwright.expect(page.locator('.teMealOverrideLunch')).to_have_value('13:30')
    page.locator('#generateItinerarySubmitBtn').click()
    playwright.expect(page).to_have_url(re.compile(r'#/trips/trip-1$'))
    bodies = [body for method, path, body in recorded if method == 'POST' and path == '/api/trips/ui-user']
    assert len(bodies) == 1
    assert bodies[0]['trip_type'] == 'couple'
    assert bodies[0]['trip_preferences']['intercity_transport_mode'] == 'train'
    assert bodies[0]['transit_pref'] == 'cab_rental'
    assert bodies[0]['trip_preferences']['notes'] == 'Keep my travel preferences'
    overrides = bodies[0]['trip_preferences']['meal_overrides']
    assert overrides.get('1', {}).get('lunch_start_time') == ('13:30' if with_meal_override else None)
    assert any(method == 'POST' and path == '/api/itinerary/generate/trip-1' for method, path, _ in recorded)
    first_key = bodies[0]['creation_request_id']
    assert re.fullmatch(r'[a-f0-9-]{36}', first_key)
    if not with_meal_override:
        page.locator('#headerPlanTripBtn').click()
        playwright.expect(page.locator('#tripFormModal')).to_be_visible()
        page.locator('#teDestinationRecommendations button').click()
        page.locator('#tripStartDateInput').fill('2099-01-01')
        page.locator('#tripEndDateInput').fill('2099-01-02')
        page.locator('#tripBudgetInput').fill('25000')
        page.locator('#teCheckoutGapChoice').select_option('activity')
        page.locator('#generateItinerarySubmitBtn').click()
        playwright.expect(page).to_have_url(re.compile(r'#/trips/trip-1$'))
        bodies = [body for method, path, body in recorded if method == 'POST' and path == '/api/trips/ui-user']
        assert len(bodies) == 2
        assert bodies[1]['creation_request_id'] != first_key
    assert errors == []
    assert dialogs == []


def test_changing_destination_clears_stale_manali_coordinates(ui):
    page, _, _, _ = ui
    page.locator('#headerPlanTripBtn').click()
    page.evaluate("async()=>{await handleFeaturedDestinationChange('manali_spiti_india');await handleFeaturedDestinationChange('udaipur_india');}")
    coords=page.evaluate('activeTripCoords')
    assert coords['destination_id']=='udaipur_india'
    assert coords['lat']==pytest.approx(24.5854,abs=.02)
    assert coords['lon']==pytest.approx(73.7125,abs=.02)
    page.evaluate("async()=>await handleFeaturedDestinationChange('unknown_destination')")
    assert page.evaluate('activeTripCoords') is None


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
    playwright.expect(page.locator('#workspacePostContainer select[name="trip_type"]')).to_have_count(0)
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
    page.locator('#teCheckoutGapChoice').select_option('activity')
    playwright.expect(page.locator('#teFinalActivities')).to_have_value('yes')


def test_timeline_includes_travel_and_accessible_reordering(ui):
    page, _, _, _ = ui
    open_trip(page)
    playwright.expect(page.locator("#workspaceEditorContainer")).to_contain_text("Travel to market")
    playwright.expect(page.get_by_role("button", name="Move Temple visit earlier")).to_be_enabled()
    assert page.locator("#workspaceEditorContainer [draggable=true]").count() == 2


def test_shopping_gap_is_visible_with_budget_label_and_no_activity_buttons(ui):
    page, _, _, _ = ui
    payload=page.evaluate("async()=> (await fetch('/api/trip-actions/trip-1/timed-view')).json()")
    payload['days'][0]['timeline'].append({'type':'shopping','id':None,'activity_id':None,
        'title':'Shopping time','time_range':'14:00 – 15:00','duration_minutes':60,
        'cost_estimate':0,'description':'Shopping near an existing stop.'})
    page.route('**/api/trip-actions/trip-1/timed-view?*',lambda route:route.fulfill(json=payload))
    open_trip(page)
    card=page.locator('#workspaceEditorContainer article').filter(has_text='Shopping time')
    playwright.expect(card).to_contain_text('Use your shopping budget')
    assert card.locator('button').count()==0


def test_per_day_meal_control_previews_and_retains_values_on_failure(ui):
    page, options, _, recorded=ui
    open_trip(page)
    page.get_by_role('button',name='Move meals for Day 1',exact=True).click()
    form=page.locator('[data-meal-form]')
    form.locator('[name=lunch_start_time]').fill('13:30')
    form.get_by_role('button',name='Preview meal times').click()
    playwright.expect(page.get_by_role('dialog')).to_contain_text('Review itinerary change')
    writes=[body for method,path,body in recorded if method=='POST' and path.endswith('/preview')]
    assert writes[-1]=={'operation':'meal_times','target_day':1,'preferences':{'lunch_start_time':'13:30','lunch_duration_minutes':60}}
    page.get_by_role('button',name='Cancel / close').click()
    options['preview_fails']=True
    page.get_by_role('button',name='Move meals for Day 1',exact=True).click()
    form=page.locator('[data-meal-form]')
    form.locator('[name=lunch_start_time]').fill('13:45')
    form.get_by_role('button',name='Preview meal times').click()
    playwright.expect(page.get_by_role('dialog')).to_contain_text('Preview unavailable')
    playwright.expect(form.locator('[name=lunch_start_time]')).to_have_value('13:45')


def test_fix_booking_asks_for_actual_cost_and_sends_confirmation(ui):
    page, _, _, recorded=ui
    open_trip(page)
    page.locator('[data-occurrence="occ-1"] [data-booking]').click()
    form=page.locator('[data-booking-form]')
    playwright.expect(form.locator('[name=cost]')).to_have_value('')
    form.locator('[name=confirmed]').check()
    form.locator('[name=start]').fill('10:00')
    form.locator('[name=end]').fill('11:00')
    form.locator('[name=cost]').fill('25')
    form.get_by_role('button',name='Preview fixed slot').click()
    playwright.expect(page.get_by_role('dialog')).to_contain_text('Review itinerary change')
    body=next(body for method,path,body in recorded if method=='POST' and path.endswith('/preview'))
    assert body['operation']=='fix_booking' and body['booking_cost_inr']==25
    assert body['booking_confirmed'] is True
    assert body['booking_start_time']=='10:00' and body['booking_end_time']=='11:00'
    assert not any(path.endswith('/confirm') for _,path,_ in recorded)


def test_deep_profile_gate_prevents_new_trip(ui):
    page, _, _, recorded = ui
    page.evaluate("state.profileStatus={complete:false};location.hash='/trips/new'")
    playwright.expect(page.locator("#tripExperienceView")).to_be_hidden()
    assert not any(method == "POST" and path == "/api/trips/ui-user" for method, path, _ in recorded)
