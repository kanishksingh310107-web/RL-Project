"""Dashboard refinement regressions. Run after frontend integration with Playwright installed."""
import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
from test_e_browser import experience


def test_dashboard_overview_tracks_visible_profile_panels_and_account(experience):
    page, _, _, _, _ = experience
    page.set_viewport_size({"width": 1600, "height": 1000})
    page.evaluate("""() => {
      state.currentUser={user_id:'owner',display_name:'Owner'};
      state.currentProfile={user_id:'owner',has_precision_profile:false,summary_text:'Basic profile summary'};
      state.precision.exists=false;
      updateNavUser();DashboardLayout.refresh();
    }""")
    overview = page.locator("#dashboardOverview")
    expect(overview).to_have_attribute("data-panels", "2")
    expect(page.locator("#dashBasicProfileCard .inline-flex")).to_contain_text("Basic profile complete")
    expect(page.locator("#personalProfileBanner")).to_be_visible()
    expect(page.locator("#personalProfileSummaryCard")).to_be_hidden()
    assert len(page.locator("#dashboardOverview").evaluate("el=>getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean)")) == 2

    page.evaluate("""() => {document.getElementById('dashBasicProfileCard').classList.add('hidden');DashboardLayout.refresh();}""")
    expect(overview).to_have_attribute("data-panels", "1")
    assert len(overview.evaluate("el=>getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean)")) == 1

    page.evaluate("""() => {
      state.currentProfile.has_precision_profile=true;state.precision.exists=true;
      document.getElementById('dashBasicProfileCard').classList.remove('hidden');DashboardLayout.refresh();
    }""")
    expect(page.locator("#personalProfileBanner")).to_be_hidden()
    expect(page.locator("#personalProfileSummaryCard")).to_be_visible()
    expect(page.locator("#personalProfileStatus")).to_contain_text("detailed answers")

    page.evaluate("""() => {
      state.currentUser={user_id:'another-account',display_name:'Another'};
      updateNavUser();DashboardLayout.refresh();
    }""")
    expect(overview).to_be_hidden()
    page.evaluate("""() => {
      state.currentProfile={user_id:'another-account',has_precision_profile:false,summary_text:'New account'};
      DashboardLayout.refresh();
    }""")
    expect(overview).to_have_attribute("data-panels", "2")
    expect(page.locator("#personalProfileBanner")).to_be_visible()
    expect(page.locator("#personalProfileSummaryCard")).to_be_hidden()
    expect(page.locator("#headerPlanTripBtn")).to_be_visible()


def test_saved_places_visibility_shortlist_state_and_account_isolation(experience):
    page, _, writes, _, _ = experience
    active_account = ["owner"]
    saved = {"owner": [], "another-account": []}
    hampi = {
        "id": "hampi_india", "name": "Hampi", "is_shortlisted": True,
        "estimated_total_inr": 22000, "reasons": ["You enjoy heritage walks."],
        "tradeoff": "Busy on weekends"
    }

    def saved_api(route):
        route.fulfill(status=200, json={"destinations": list(saved.get(active_account[0], []))})

    def shortlist_api(route):
        destination_id = route.request.post_data_json["destination_id"]
        values = saved.setdefault(active_account[0], [])
        exists = any(item["id"] == destination_id for item in values)
        if exists:
            values[:] = [item for item in values if item["id"] != destination_id]
        else:
            values.append(dict(hampi, id=destination_id))
        route.fulfill(status=200, json={"is_shortlisted": not exists, "shortlisted_ids": [item["id"] for item in values]})

    page.route("**/api/discovery/saved", saved_api)
    page.route("**/api/shortlist/**", shortlist_api)
    page.evaluate("RecommendationDiscovery.refresh()")
    page.wait_for_function("document.querySelector('#exSavedPlaces')?.hidden === true")
    expect(page.locator("#exSavedPlacesHeading")).to_have_count(0)
    expect(page.locator("#exSavedPlaces")).not_to_contain_text("Places you save")
    expect(page.locator("#exRecommendationShelves h3").first).to_have_text("Within your budget")

    page.locator("#exRecommendationShelves .ex-destination-card").first.get_by_role("button", name="Save for later", exact=True).click()
    expect(page.locator("#exSavedPlaces")).to_be_visible()
    expect(page.locator("#exSavedPlaces")).to_contain_text("Hampi")
    active_account[0] = "another-account"
    page.evaluate("""() => {
      state.currentUser={user_id:'another-account',display_name:'Another',token:'other-token'};
      localStorage.setItem('rl_travel_user',JSON.stringify(state.currentUser));updateNavUser();
      return RecommendationDiscovery.refresh();
    }""")
    page.wait_for_function("document.querySelector('#exSavedPlaces')?.hidden === true")
    expect(page.locator("#exSavedPlaces")).not_to_contain_text("Hampi")

    active_account[0] = "owner"
    page.evaluate("""() => {
      state.currentUser={user_id:'owner',display_name:'Owner',token:'test-token'};
      localStorage.setItem('rl_travel_user',JSON.stringify(state.currentUser));updateNavUser();
      return RecommendationDiscovery.refresh();
    }""")
    expect(page.locator("#exSavedPlaces")).to_be_visible()
    page.locator("#exSavedPlaces").get_by_role("button", name="Saved · remove", exact=True).click()
    expect(page.locator("#exSavedPlaces")).to_be_hidden()
    assert any(path == "shortlist/owner" for _, path, _, _ in writes)


def test_dashboard_has_no_horizontal_overflow_at_supported_widths(experience):
    page, _, _, _, _ = experience
    page.evaluate("""() => {
      state.currentProfile={user_id:'owner',has_precision_profile:false};
      state.precision.exists=false;DashboardLayout.refresh();
    }""")
    for width in (320, 390, 768, 1024, 1600, 2560):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
        expect(page.locator("#headerPlanTripBtn")).to_be_visible()
