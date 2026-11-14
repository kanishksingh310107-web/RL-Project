"""Backend regression coverage for D's discovery, finance and assistant APIs.

Per task instructions, this file is authored but deliberately not executed here.
"""
from datetime import date, timedelta


def _trip(client, user_id, *, days=3):
    start = date.today() + timedelta(days=10)
    end = start + timedelta(days=days - 1)
    response = client.post(f'/api/trips/{user_id}', json={
        'destination_id':'manali_spiti_india','destination_name':'Manali & Spiti Valley',
        'start_date':start.isoformat(),'end_date':end.isoformat(),
        'party':{'adults':2,'children':0,'seniors':0},'trip_type':'couple',
        'travellers_count':2,'total_budget':30000,'currency':'INR'})
    assert response.status_code == 200, response.text
    return response.json()


def test_discovery_needs_authenticated_completed_basic_profile(client, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    response = client.post('/api/discovery/suggestions', json={
        'duration_days':4,'comfortable_budget_inr':100000,'party_size':2,'trip_type':'couple'})
    assert response.status_code == 403
    assert response.json()['code'] == 'NOT_OWNER'


def test_home_area_filter_excludes_home_city_without_excluding_its_state():
    from app.residence import is_home_area
    profile={'residence_country':'IN','residence_state':'Tamil Nadu','residence_city':'Tirunelveli'}
    assert is_home_area({'id':'home','country':'India','state':'Tamil Nadu','name':'Tirunelveli'},profile)
    assert not is_home_area({'id':'nearby','country':'India','state':'Tamil Nadu','name':'Ooty'},profile)


def test_discovery_returns_three_feasible_options_with_flexible_dates_and_unavailable_travel_time(client, demo_user):
    response = client.post('/api/discovery/suggestions', json={
        'mode':'help_choose','origin':'Tirunelveli','duration_days':4,
        'comfortable_budget_inr':500000,'party_size':2,'trip_type':'couple',
        'interests':['nature','culture_history'],'max_travel_minutes':240})
    assert response.status_code == 200, response.text
    result = response.json()
    assert 1 <= len(result['recommendations']) <= 3
    assert result['date_basis'] == 'flexible_duration'
    assert 'max_travel_minutes' in result['filters_not_evaluable']
    for item in result['recommendations']:
        assert item['start_date'] is None and item['end_date'] is None
        assert item['travel_time_minutes'] is None
        assert item['estimated_total_cost_inr'] <= 500000
        assert item['why_recommended'] and item['trade_off']
    assert result['groups']['within_your_budget']


def test_discovery_feedback_deterministically_removes_not_for_me_and_saves_to_existing_shortlist(client, demo_user):
    payload = {'duration_days':3,'comfortable_budget_inr':500000,'party_size':2,'trip_type':'couple'}
    first = client.post('/api/discovery/suggestions', json=payload)
    assert first.status_code == 200, first.text
    destination = first.json()['recommendations'][0]['destination_id']
    feedback = client.post('/api/discovery/feedback', json={
        'destination_id':destination,'action':'save_for_later'})
    assert feedback.status_code == 200
    assert feedback.json()['saved'] is True
    saved = client.get(f'/api/shortlist/{demo_user}')
    assert saved.status_code == 200
    rejected = client.post('/api/discovery/feedback', json={
        'destination_id':destination,'action':'not_for_me','reason':'crowding'})
    assert rejected.status_code == 200
    second = client.post('/api/discovery/suggestions', json=payload)
    assert second.status_code == 200
    assert destination not in {item['destination_id'] for item in second.json()['recommendations']}


def test_budget_allocation_normalizes_room_night_and_person_day_and_rejects_overallocation(client, demo_user):
    trip = _trip(client, demo_user)
    response = client.put(f"/api/trips/{trip['id']}/budget", json={
        'total_budget_inr':30000,'allocations':{
            'accommodation':{'amount_inr':4000,'basis':'per_room_night','rooms':1},
            'food':{'amount_inr':500,'basis':'per_person_day'},
            'emergency_reserve':{'amount_inr':1000,'basis':'total'}}})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['planned_category_totals_inr']['accommodation'] == 8000
    assert result['planned_category_totals_inr']['food'] == 3000
    assert result['actual_total_inr'] is None
    assert result['actual_spending_status'] == 'not_recorded'
    invalid = client.put(f"/api/trips/{trip['id']}/budget", json={
        'total_budget_inr':1000,'allocations':{
            'food':{'amount_inr':1200,'basis':'total'},
            'emergency_reserve':{'amount_inr':500,'basis':'total'}}})
    assert invalid.status_code == 422
    assert invalid.json()['code'] == 'BUDGET_ALLOCATION_EXCEEDS_TOTAL'


def test_expense_partial_and_final_linked_payments_do_not_double_count(client, demo_user):
    trip = _trip(client, demo_user)
    client.put(f"/api/trips/{trip['id']}/budget", json={
        'total_budget_inr':30000,'allocations':{
            'accommodation':{'amount_inr':4000,'basis':'per_room_night','rooms':1},
            'food':{'amount_inr':500,'basis':'per_person_day'}}})
    spent_on = trip['start_date']
    first = client.post(f"/api/trips/{trip['id']}/expenses", json={
        'category':'stay','amount_inr':3000,'spent_on':spent_on,'note':'Deposit',
        'planned_cost_key':'accommodation','idempotency_key':'stay-deposit-001'})
    assert first.status_code == 200, first.text
    replay = client.post(f"/api/trips/{trip['id']}/expenses", json={
        'category':'stay','amount_inr':3000,'spent_on':spent_on,'note':'Deposit',
        'planned_cost_key':'accommodation','idempotency_key':'stay-deposit-001'})
    assert replay.status_code == 200
    assert replay.json()['expense']['id'] == first.json()['expense']['id']
    assert replay.json()['idempotent_replay'] is True
    second = client.post(f"/api/trips/{trip['id']}/expenses", json={
        'category':'stay','amount_inr':4500,'spent_on':spent_on,'note':'Balance',
        'planned_cost_key':'accommodation','is_final_for_planned_cost':True,
        'idempotency_key':'stay-balance-002'})
    assert second.status_code == 200, second.text
    budget = second.json()['budget']
    assert budget['actual_total_inr'] == 7500
    assert budget['estimated_remaining_by_category_inr']['accommodation'] == 0


def test_expense_edit_delete_recalculate_and_csv_formula_text_is_neutralized(client, demo_user):
    trip = _trip(client, demo_user)
    spent_on = trip['start_date']
    created = client.post(f"/api/trips/{trip['id']}/expenses", json={
        'category':'food','amount_inr':700,'spent_on':spent_on,'note':'=HYPERLINK("https://bad.example")',
        'idempotency_key':'formula-test-001'})
    assert created.status_code == 200, created.text
    expense_id = created.json()['expense']['id']
    export = client.get(f"/api/trips/{trip['id']}/expenses/export.csv")
    assert export.status_code == 200
    assert "'=HYPERLINK" in export.text
    edited = client.patch(f"/api/trips/{trip['id']}/expenses/{expense_id}", json={'amount_inr':900})
    assert edited.status_code == 200, edited.text
    assert edited.json()['budget']['actual_total_inr'] == 900
    deleted = client.delete(f"/api/trips/{trip['id']}/expenses/{expense_id}")
    assert deleted.status_code == 200
    assert deleted.json()['budget']['actual_total_inr'] is None


def test_budget_comparison_is_fair_bounded_and_does_not_mutate_saved_trip(client, demo_user):
    trip = _trip(client, demo_user)
    before = client.get(f"/api/trips/{trip['id']}/budget").json()
    options = client.post(f"/api/trips/{trip['id']}/budget-options", json={
        'max_additional_budget_inr':0,'priorities':['food_dining']})
    assert options.status_code == 200, options.text
    result = options.json()
    assert result['saved_trip_mutated'] is False
    assert all(option['additional_cost_inr'] <= 0 for option in result['options'])
    assert all(option['comparison_basis']['destination_id'] == trip['destination_id'] for option in result['options'])
    after = client.get(f"/api/trips/{trip['id']}/budget").json()
    assert before == after


def test_itinerary_check_requires_existing_itinerary_and_does_not_claim_guaranteed_safety(client, demo_user):
    trip = _trip(client, demo_user)
    missing = client.get(f"/api/trips/{trip['id']}/itinerary-check")
    assert missing.status_code == 404
    assert missing.json()['code'] == 'ITINERARY_NOT_FOUND'


def test_assistant_unavailable_without_server_model_configuration(client, demo_user, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    caps = client.get('/api/experience/capabilities')
    assert caps.status_code == 200
    assert caps.json()['assistant_chat'] is False
    assert caps.json()['assistant_actions'] is False
    response = client.post('/api/assistant/chat', json={'user_id':demo_user,'message':'Why was this place recommended?'})
    assert response.status_code == 503
    assert response.json()['code'] == 'ASSISTANT_UNAVAILABLE'


def test_expense_and_budget_endpoints_enforce_trip_ownership(client, demo_user):
    trip = _trip(client, demo_user)
    auth = client.post('/api/auth', json={'provider':'email','identifier':'second@example.com',
        'password':'SafePass123','display_name':'Second','mode':'signup'})
    assert auth.status_code == 200, auth.text
    client.headers['Authorization'] = 'Bearer ' + auth.json()['token']
    denied = client.get(f"/api/trips/{trip['id']}/budget")
    assert denied.status_code == 403
    assert denied.json()['code'] == 'NOT_OWNER'
