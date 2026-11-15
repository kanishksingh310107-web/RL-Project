"""Merged dashboard/history UX against real authenticated app endpoints."""
from datetime import date,timedelta
import json
from pathlib import Path
import socket
import threading
import time

import pytest
import uvicorn


def test_merged_dashboard_history_and_modal_against_real_apis(client,demo_user):
    playwright=pytest.importorskip('playwright.sync_api')
    from app.database import get_connection
    from main import app
    bank=client.get('/api/config/precision-questionnaire').json()['questions']
    question=next(q for q in bank.values() if q['type']=='single' and not q.get('show_if') and q.get('options'))
    partial=client.post('/api/profile/precision/'+demo_user,json={'answers':{question['id']:question['options'][0]['id']}})
    assert partial.status_code==200,partial.text
    assert client.get('/api/profile/'+demo_user+'/status').json()['complete'] is False
    history=client.post('/api/profile/history',json={'destination':'Pune','city':'Pune',
        'visited_on':str(date.today()-timedelta(days=100)),'trip_type':'solo','would_revisit':True,
        'ratings':{key:4 for key in ('scenery','food','safety','value_for_money','crowds','accessibility','stay_quality','overall')}})
    assert history.status_code==201,history.text
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    assert server.started
    try:
        with playwright.sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome')
            page=browser.new_page(viewport={'width':1600,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('https://**',lambda route:route.abort())
            account={'user_id':demo_user,'display_name':'Integration traveller','has_profile':True,
                'token':client.headers['Authorization'].split(' ',1)[1]}
            page.add_init_script("localStorage.setItem('rl_travel_user',JSON.stringify("+json.dumps(account)+"));")
            page.goto(f'http://127.0.0.1:{port}/',wait_until='domcontentloaded')
            expect=playwright.expect
            expect(page.locator('#personalProfileBanner')).to_be_visible()
            expect(page.locator('#personalProfileSummaryCard')).to_be_hidden()
            expect(page.locator('#dashboardOverview')).to_have_attribute('data-panels','1')
            assert len(page.locator('#dashboardOverview').evaluate("e=>getComputedStyle(e).gridTemplateColumns.split(' ')") )==1
            page.wait_for_selector('#exRecommendationShelves .ex-destination-card',timeout=20000)
            expect(page.locator('#exRecommendationShelves .ex-destination-card').first).to_be_visible()
            expect(page.locator('#exSavedPlaces')).to_be_hidden()
            page.locator('#exRecommendationShelves .ex-destination-card').first.get_by_role('button',name='Save for later',exact=True).click()
            expect(page.locator('#exSavedPlaces')).to_be_visible()
            output=Path('.pytest_cache/ui-review');output.mkdir(parents=True,exist_ok=True)
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(output/'merged-desktop.png'),full_page=True)
            for width in (320,390,768,1024,1600,2560):
                page.set_viewport_size({'width':width,'height':1000})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
                expect(page.locator('#headerPlanTripBtn')).to_be_visible()
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(output/'merged-mobile.png'),full_page=True)
            page.locator('#exSavedPlaces').get_by_role('button',name='Saved · remove',exact=True).click()
            expect(page.locator('#exSavedPlaces')).to_be_hidden()
            page.locator('#headerTripActions a[href="#/trips"]').click()
            expect(page.locator('#teTripList')).to_contain_text('Pune')
            expect(page.locator('#personalProfileModal')).to_be_hidden()
            page.locator('#tripExperienceView .te-workspace-nav a[href="#/"]').click()
            expect(page.locator('#dashboardView')).to_be_visible()
            page.locator('#headerPlanTripBtn').click()
            modal=page.locator('#personalProfileModal')
            expect(modal).to_be_visible()
            modal.locator('.selectable-card').first.click()
            visible=page.evaluate('Object.fromEntries(precVisibleIds().map(id=>[id,state.precision.answers[id]]))')
            page.keyboard.press('Escape')
            expect(modal).to_be_hidden()
            expect(page.locator('#headerPlanTripBtn')).to_be_focused()
            assert client.get('/api/profile/'+demo_user+'/status').json()['complete'] is False
            page.locator('#headerPlanTripBtn').click()
            expect(modal).to_be_visible()
            assert page.evaluate('Object.fromEntries(precVisibleIds().map(id=>[id,state.precision.answers[id]]))')==visible
            modal.get_by_role('button',name='Close Deep Personalisation',exact=True).click()
            assert errors==[],errors
            with get_connection() as conn:
                assert conn.execute('SELECT count(*) FROM trips WHERE user_id=?',(demo_user,)).fetchone()[0]==0
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
