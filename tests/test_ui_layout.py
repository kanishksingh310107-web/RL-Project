"""Responsive geometry and permission checks for the shared app shell."""
from pathlib import Path
import re
import pytest

expect = pytest.importorskip('playwright.sync_api').expect
from test_e_browser import experience
from test_ui_upgrade_browser import static_url


def test_full_width_cards_have_separate_action_and_feedback_rows(experience):
    page,_,_,_,_=experience
    page.set_viewport_size({'width':1600,'height':1000})
    page.evaluate("""() => {
      updateNavUser();
      document.getElementById('dashWelcomeName').textContent='Welcome back, traveller';
      document.getElementById('dashSummaryText').textContent='Your preferences are ready. Find somewhere worth exploring.';
      document.getElementById('personalProfileBanner').classList.add('hidden');
      document.getElementById('personalProfileSummaryCard').classList.remove('hidden');
      const grid=document.getElementById('recommendedGrid');grid.replaceChildren();
      for(const [id,name] of [['hampi_india','Hampi'],['udaipur_mewar_india','Udaipur'],['jaipur_jodhpur_india','Jaipur']]) {
        grid.append(renderRecommendationCard({id,name,country:'India',duration:'3–5 days',budget_tier:'mid_range',tags:['Heritage','Culture','Photography'],
          image_url:'/static/images/destination-placeholder.svg',because_you_said:'Because you said prefer Cool_Hillstation climate (Q26) and travel with solo (Q3) and budget aligns with premium luxury (Q32).'},'recommended'));
      }
      document.querySelector('.ex-more-destinations').open=true;
    }""")
    expect(page.locator('#headerPlanTripBtn')).to_be_visible()
    expect(page.locator('#recommendedGrid .destination-card')).to_have_count(3)
    assert page.locator('#recommendedGrid').bounding_box()['width']>1450
    first=page.locator('#recommendedGrid .destination-card').first
    assert first.bounding_box()['height']<700
    assert first.locator('.destination-card-actions .ex-feedback-actions').count()==0
    expect(first.locator('.destination-card-feedback')).to_contain_text('Interested')
    expect(first).not_to_contain_text('(Q26)')
    expect(first).not_to_contain_text('Cool_Hillstation')
    first.locator('.ex-feedback-more summary').click()
    assert first.bounding_box()['height']<850
    assert first.get_by_role('button',name='Explore Details',exact=True).bounding_box()['width']>120
    page.evaluate('window.scrollTo(0,0)')
    output=Path('.worktrees/itinerary-completion');output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'layout-desktop.png'),full_page=True)
    for width in [2560,1024,768,390,320]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
        expect(page.locator('#headerPlanTripBtn')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(output/'layout-mobile.png'),full_page=True)


def test_header_planning_uses_existing_deep_gate_and_hides_when_signed_out(experience):
    page,_,_,_,_=experience
    page.evaluate("state.profileStatus={complete:false};window.openPersonalProfileModal=()=>{window.deepPrompted=true;};updateNavUser();")
    page.locator('#headerPlanTripBtn').click()
    page.wait_for_function('window.deepPrompted===true')
    assert page.evaluate('location.hash')!='#/trips/new'
    page.evaluate('state.profileStatus={complete:true}')
    page.locator('#headerPlanTripBtn').click()
    expect(page).to_have_url(re.compile(r'#/trips/new$'))
    expect(page.locator('#tripFormModal')).to_be_visible()
    page.evaluate("state.currentUser=null;updateNavUser();showView('auth');")
    expect(page.locator('#headerTripActions')).to_be_hidden()
    assert page.locator('#authView').bounding_box()['width']<=448
