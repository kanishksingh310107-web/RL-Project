"""Prompt 2 regressions. Execute only after both feature branches are integrated."""
from datetime import date, timedelta

import pytest


def test_incomplete_profile_can_read_own_empty_history_and_trip_lists(client):
    account = client.post('/api/auth', json={
        'provider':'email', 'identifier':'history-reader@example.com',
        'password':'SafePass123', 'display_name':'History reader', 'mode':'signup',
    })
    assert account.status_code == 200, account.text
    user = account.json()
    client.headers['Authorization'] = 'Bearer ' + user['token']
    assert client.get('/api/profile/status').json()['profile_complete'] is False
    history = client.get('/api/profile/history')
    assert history.status_code == 200 and history.json()['entries'] == []
    for suffix in ['', '/feedback-pending', '/archive']:
        response = client.get('/api/trips/' + user['user_id'] + suffix)
        assert response.status_code == 200 and response.json() == [], response.text


def test_manual_history_is_available_without_deep_profile_and_reads_do_not_create_trips(client, demo_user):
    from app.database import get_connection
    payload = {'destination':'Pune', 'city':'Pune', 'visited_on':str(date.today()-timedelta(days=60)),
        'trip_type':'solo', 'ratings':{key:4 for key in ['scenery','food','safety','value_for_money','crowds','accessibility','stay_quality','overall']},
        'would_revisit':True, 'notes':'A past trip entered during the basic profile.'}
    created = client.post('/api/profile/history', json=payload)
    assert created.status_code == 201, created.text
    assert client.get('/api/profile/'+demo_user+'/status').json()['complete'] is False
    for _ in range(2):
        result = client.get('/api/profile/history')
        assert result.status_code == 200
        entries = result.json()['entries']
        assert len(entries) == 1 and entries[0]['source'] == 'manual'
        assert entries[0]['destination'] == 'Pune' and not entries[0].get('trip_id')
        assert client.get('/api/trips/'+demo_user).json() == []
    with get_connection() as conn:
        assert conn.execute('SELECT count(*) FROM trips WHERE user_id=?',(demo_user,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM travel_history WHERE user_id=?',(demo_user,)).fetchone()[0] == 1


def test_history_read_access_does_not_unlock_planning(client, demo_user):
    assert client.get('/api/profile/history').status_code == 200
    start = date.today()+timedelta(days=10)
    result = client.post('/api/trips/'+demo_user,json={'destination_id':'manali_spiti_india',
        'start_date':str(start),'end_date':str(start+timedelta(days=3)),
        'total_budget':40000,'travellers_count':1})
    assert result.status_code == 403
    assert result.json()['code'] == 'DEEP_PROFILE_INCOMPLETE'


def test_history_and_trip_reads_keep_ownership_checks(client, demo_user):
    for suffix in ['', '/feedback-pending', '/archive']:
        assert client.get('/api/trips/not-this-user'+suffix).status_code in (403,404)
    assert client.get('/api/trips/detail/unknown-trip').status_code in (403,404)
    client.headers.pop('Authorization')
    assert client.get('/api/profile/history').status_code in (401,403)
    assert client.get('/api/trips/'+demo_user).status_code in (401,403)


def test_history_query_cannot_select_another_account(client, demo_user):
    created = client.post('/api/profile/history',json={'destination':'Pune','visited_on':'2020-01-01',
        'trip_type':'solo','would_revisit':True,'ratings':{key:4 for key in ['scenery','food','safety','value_for_money','crowds','accessibility','stay_quality','overall']}})
    assert created.status_code == 201, created.text
    other = client.post('/api/auth',json={'provider':'email','identifier':'other-reader@example.com',
        'password':'SafePass123','display_name':'Other reader','mode':'signup'})
    assert other.status_code == 200, other.text
    client.headers['Authorization'] = 'Bearer ' + other.json()['token']
    response = client.get('/api/profile/history?user_id='+demo_user)
    assert response.status_code == 200 and response.json()['entries'] == []
    assert client.get('/api/trips/'+demo_user).status_code in (403,404)


@pytest.fixture
def history_ui(request):
    playwright = pytest.importorskip('playwright.sync_api')
    static_url = request.getfixturevalue('static_url')
    options = {'basic_complete':True,'fail_history':False,'history':[], 'trips':[],
        'pending':[], 'archived':[], 'precision_answers':{}, 'delay_precision':False}
    calls, held = [], []
    bank = {'sections':[{'id':'p1','title':'Travel style','purpose':'Your preferences'}],
        'questions':{qid:{'id':qid,'section':'p1','type':'single','text':title,
            'options':[{'id':'quiet','label':'Quiet places'},{'id':'busy','label':'Busy places'}]}
            for qid,title in [('style','What places do you enjoy?'),('pace','What pace do you prefer?')]}}

    def mock(route):
        path = route.request.url.split('?',1)[0].split('/api/',1)[1]
        method = route.request.method
        calls.append((method,path))
        data, status = {}, 200
        if path == 'config/google': data = {'client_id':''}
        elif path == 'profile/status': data = {'profile_complete':options['basic_complete']}
        elif path == 'config/precision-questionnaire': data = bank
        elif path == 'profile/precision/history-owner':
            if options['delay_precision']:
                held.append(route)
                return
            data = {'answers':options['precision_answers'],'context_answers':{},'exists':bool(options['precision_answers'])}
        elif path == 'profile/history':
            status = 503 if options['fail_history'] else 200
            data = {'detail':'History unavailable. Please retry.'} if options['fail_history'] else {'entries':options['history'],'history_choice':'none'}
        elif path == 'trips/history-owner': data = options['trips']
        elif path == 'trips/history-owner/feedback-pending': data = options['pending']
        elif path == 'trips/history-owner/archive': data = options['archived']
        elif path == 'trip-experience/capabilities': data = {'itinerary_preview':True,'schedule_preferences_v2':True}
        elif path == 'experience/capabilities': data = {'discovery':False,'assistant_chat':False}
        elif path.startswith('trips/') and path.endswith('/runtime'):
            trip_id = path.split('/')[1]
            completed = trip_id != 'active-trip'
            data = {'trip_id':trip_id,'status':'completed' if completed else 'draft',
                'runtime':{'current_day':1,'version':1},'closed_out':trip_id == 'archived-trip',
                'total_days':1,'runs':[],'schedule':[],'today':[],'rating_keys':['overall'],
                'post_feedback':{'notes':'Saved feedback'} if trip_id == 'archived-trip' else None}
        elif path.startswith('itinerary/'):
            trip_id = path.split('/')[1]
            data = {'id':'itinerary-'+trip_id,'trip_id':trip_id,'destination_name':'Saved destination',
                'total_days':1,'total_estimated_cost':1000,'days':[{'day_number':1,'activities':[]}]}
        elif path.startswith('trip-actions/') and path.endswith('/timed-view'):
            data = {'trip':{'destination_name':'Saved destination'},'days':[]}
        route.fulfill(status=status,json=data)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':1280,'height':900})
        errors = []
        page.on('pageerror', lambda error:errors.append(str(error)))
        page.route('**/api/**', mock)
        page.route('https://**', lambda route:route.abort())
        page.goto(static_url+'/static/index.html',wait_until='domcontentloaded')
        page.evaluate("""() => {
            state.currentUser={user_id:'history-owner',display_name:'History owner',auth_provider:'email'};
            state.currentProfile={residence_country:'IN',residence_city:'Pune'};
            state.profileStatus={complete:false};showView('dashboard');updateNavUser();
        }""")
        yield page, options, calls, held
        assert errors == [], errors
        browser.close()


# Reuse only the static-file server fixture, never an existing test function.
from test_ui_upgrade_browser import static_url


def open_history(page):
    page.locator('#headerTripActions a[href="#/trips"]').click()


def manual_entry():
    return {'id':'manual-1','source':'manual','destination':'Pune <img src=x onerror="window.historyInjected=true">',
        'visited_on':'2020-01-01','trip_type':'solo','ratings':{'overall':4},'would_revisit':True,
        'notes':'History notes <script>window.historyInjected=true</script>'}


def test_my_trips_displays_manual_history_without_questionnaire_or_planning(history_ui):
    from playwright.sync_api import expect
    page, options, calls, _ = history_ui
    options['basic_complete'] = False
    options['history'] = [manual_entry()]
    open_history(page)
    expect(page.locator('#teTripList')).to_contain_text('Travel history')
    expect(page.locator('#teTripList')).to_contain_text('Pune <img')
    expect(page.locator('#personalProfileModal')).to_be_hidden()
    expect(page.locator('#aHistoryPanel')).to_have_count(0)
    assert page.locator('#teTripList img,#teTripList script').count() == 0
    assert not page.evaluate('window.historyInjected===true')
    assert page.locator('#teTripList a[href^="#/trips/"]').count() == 0
    assert not any(method != 'GET' for method,_ in calls)
    page.reload(wait_until='domcontentloaded')
    page.evaluate("state.currentUser={user_id:'history-owner',display_name:'History owner'};state.currentProfile={residence_country:'IN'};state.profileStatus={complete:false};showView('dashboard');TripExperience.route();")
    expect(page.locator('#teTripList')).to_contain_text('Pune <img')


def test_empty_history_popup_is_dismissible_and_read_failures_are_not_empty(history_ui):
    from playwright.sync_api import expect
    page, options, _, _ = history_ui
    open_history(page)
    expect(page.locator('#teNoTripsDialog')).to_be_visible()
    expect(page.locator('#teNoTripsMessage')).to_have_text('no trips')
    page.locator('#teNoTripsDialog').get_by_role('button',name='Close',exact=True).click()
    expect(page.locator('#teNoTripsDialog')).to_have_count(0)
    options['fail_history'] = True
    open_history(page)
    expect(page.locator('#teTripList [role=alert]')).to_contain_text('History unavailable')
    expect(page.locator('#teNoTripsDialog')).to_have_count(0)
    options['fail_history'] = False
    options['history'] = [manual_entry()]
    page.get_by_role('button',name='Retry',exact=True).click()
    expect(page.locator('#teTripList')).to_contain_text('Travel history')


@pytest.mark.parametrize('dismiss',['close','escape','backdrop'])
def test_questionnaire_closes_without_submitting_and_resumes_draft(history_ui,dismiss):
    from playwright.sync_api import expect
    page, _, calls, _ = history_ui
    page.locator('#headerPlanTripBtn').click()
    modal = page.locator('#personalProfileModal')
    expect(modal).to_be_visible()
    modal.locator('.selectable-card').filter(has_text='Quiet places').first.click()
    modal.locator('#personalAdditionalInfo').fill('Keep this unsaved note')
    before = len(calls)
    if dismiss == 'close':
        modal.get_by_role('button',name='Close Deep Personalisation',exact=True).click()
    elif dismiss == 'escape':
        page.keyboard.press('Escape')
    else:
        modal.click(position={'x':3,'y':3})
    expect(modal).to_be_hidden()
    page.evaluate('ProfileGate.checkAndPrompt()')
    expect(modal).to_be_hidden()
    assert page.evaluate('state.profileStatus.complete') is False
    assert page.evaluate('document.body.style.overflow') != 'hidden'
    assert not any(method != 'GET' for method,_ in calls[before:])
    assert page.evaluate("document.activeElement.id") == 'headerPlanTripBtn'
    page.reload(wait_until='domcontentloaded')
    page.evaluate("state.currentUser={user_id:'history-owner',display_name:'History owner'};state.currentProfile={residence_country:'IN'};state.profileStatus={complete:false};showView('dashboard');updateNavUser();")
    page.locator('#headerPlanTripBtn').click()
    expect(modal).to_be_visible()
    assert page.evaluate('state.precision.answers.style') == 'quiet'
    expect(modal.locator('#personalAdditionalInfo')).to_have_value('Keep this unsaved note')


def test_my_trips_cancels_a_slow_questionnaire_open_and_has_no_bottom_launcher(history_ui):
    from playwright.sync_api import expect
    page, options, _, held = history_ui
    page.set_default_timeout(10000)
    options['delay_precision'] = True
    page.evaluate("() => { const openDeep=window.openPersonalProfileModal;window.openPersonalProfileModal=(...args)=>(window.pendingDeepOpen=openDeep(...args)); }")
    with page.expect_request('**/api/profile/precision/history-owner'):
        page.locator('#headerPlanTripBtn').click()
    open_history(page)
    expect(page.locator('#teNoTripsDialog')).to_be_visible()
    assert held
    for route in held:
        route.fulfill(status=200,json={'answers':{},'context_answers':{},'exists':False})
    page.evaluate("()=>Promise.race([window.pendingDeepOpen,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Questionnaire opening did not finish')),10000))])")
    expect(page.locator('#personalProfileModal')).to_be_hidden()
    assert page.locator('#dashboardView a.te-primary[href="#/trips/new"]').count() == 0
    expect(page.locator('#headerPlanTripBtn')).to_be_visible()


def test_questionnaire_draft_does_not_leak_to_another_account(history_ui):
    from playwright.sync_api import expect
    page, options, _, _ = history_ui
    options['history'] = [manual_entry()]
    page.locator('#headerPlanTripBtn').click()
    modal = page.locator('#personalProfileModal')
    expect(modal).to_be_visible()
    modal.locator('.selectable-card').filter(has_text='Quiet places').first.click()
    modal.get_by_role('button',name='Close Deep Personalisation',exact=True).click()
    open_history(page)
    expect(page.locator('#teTripList')).to_contain_text('Pune <img')
    page.evaluate("state.currentUser=null;showView('auth');updateNavUser();")
    expect(page.locator('#teTripList')).to_be_empty()
    page.evaluate("state.currentUser={user_id:'different-owner',display_name:'Different owner'};window.dispatchEvent(new Event('trip:context-cleared'));")
    assert page.evaluate("readPersonalProfileDraft('different-owner')") is None
    expect(modal).to_be_hidden()


def test_active_pending_and_archived_trips_remain_readable_and_back_navigation_works(history_ui):
    from playwright.sync_api import expect
    page, options, _, _ = history_ui
    base = {'destination_name':'Saved destination','start_date':'2099-01-01','end_date':'2099-01-03','status':'planned'}
    options['trips'] = [{**base,'id':'active-trip'}]
    options['pending'] = [{**base,'id':'pending-trip'}]
    options['archived'] = [{**base,'id':'archived-trip'}]
    open_history(page)
    expect(page.locator('#teTripList')).to_contain_text('Active trips')
    expect(page.locator('#teTripList')).to_contain_text('Feedback pending')
    expect(page.locator('#teTripList')).to_contain_text('Feedback saved')
    expect(page.locator('#teTripList a[href="#/trips/archived-trip"]')).to_have_count(1)
    page.locator('#teTripList a[href="#/trips/active-trip"]').click()
    expect(page.locator('#tripExperienceView')).to_be_visible()
    expect(page.locator('#personalProfileModal')).to_be_hidden()
    page.go_back()
    expect(page.locator('#teTripList')).to_be_visible()
    expect(page.locator('#teTripList')).to_contain_text('Feedback pending')
    page.locator('#teTripList a[href="#/trips/archived-trip"]').click()
    expect(page.locator('#workspacePostContainer')).to_contain_text('Trip closed out — feedback saved')
    expect(page.locator('#wsTabBtn-live')).to_be_disabled()
    expect(page.locator('#personalProfileModal')).to_be_hidden()
