"""Run existing live assertions unchanged using the current signup contract.

The upstream shared fixture omits the now-required auth mode. These local
fixtures adapt setup only; every original test body/assertion is reused.
"""
import importlib.util
from pathlib import Path
import pytest
from app.database import get_connection


@pytest.fixture
def demo_user(client):
    from app.db_migrations_a import migrate_a
    migrate_a()
    response=client.post('/api/account/guest',json={'guest_id':'person_c_legacy_test_identity'})
    assert response.status_code==200,response.text
    user=response.json()['user_id']
    client.headers['Authorization']='Bearer '+response.json()['token']
    profile=client.post('/api/profile/'+user,json={'travel_goals':['nature','culture'],
        'residence_country':'IN','residence_state':'Tamil Nadu','residence_city':'Tirunelveli',
        'place_interests':['mountains','historic'],'preferred_climate':'cool','budget_tier':'mid_range','companions':'partner'})
    assert profile.status_code==200,profile.text
    # This fixture exercises C's legacy assertions, independently of A's
    # questionnaire tests. The merged create route now requires the gate.
    history=client.post('/api/profile/history/choice',json={'choice':'none'})
    assert history.status_code==200,history.text
    return user


@pytest.fixture
def demo_trip(client,demo_user):
    response=client.post('/api/trips/'+demo_user,json={'destination_id':'kyoto_japan','destination_name':'Kyoto',
        'start_date':'2026-11-10','end_date':'2026-11-14','travellers_count':2,'total_budget':1200,
        'specific_interests':['culture_history','food_dining']})
    assert response.status_code==200,response.text
    trip=response.json()['id']
    generated=client.post(f'/api/itinerary/generate/{trip}?user_id={demo_user}')
    assert generated.status_code==200,generated.text
    return demo_user,trip


spec=importlib.util.spec_from_file_location('c_original_live_tests',Path(__file__).with_name('test_live.py'))
original=importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
for name,value in vars(original).items():
    if name.startswith('test_') and callable(value):
        globals()['test_c_legacy_'+name[5:]]=value
