"""Prepared regression cases; execution is deferred until the user's push request."""
from unittest.mock import Mock
import pytest
import requests
from app.database import get_connection
from app.residence import validate_residence, is_home_area
from app.recommender import get_categorized_recommendations


@pytest.mark.parametrize('country,state,city,currency,field',[
    (None,None,None,None,'residence_country'),('XX',None,None,'USD','residence_country'),
    ('IN',None,None,'INR','residence_state'),('IN','Rajasthan','  ','INR','residence_city'),
    ('IN','Rajasthan','<script>x</script>','INR','residence_city'),('US',None,None,'ZZZ','preferred_currency'),
])
def test_residence_invalid_input_has_field(country,state,city,currency,field):
    with pytest.raises(ValueError) as error:
        validate_residence(country,state,city,currency)
    assert error.value.field==field


def test_foreign_country_skips_and_clears_indian_address():
    home=validate_residence('us','Rajasthan','Jaipur','usd')
    assert home==dict(residence_country='US',residence_state=None,residence_city=None,preferred_currency='USD')


def test_home_city_excluded_without_excluding_entire_state():
    profile=dict(residence_country='IN',residence_state='Rajasthan',residence_city='Jaipur',interests=['culture_history'])
    assert is_home_area({'name':'Jaipur & Jodhpur','state':'Rajasthan','country':'India'},profile)
    assert not is_home_area({'name':'Udaipur','state':'Rajasthan','country':'India'},profile)
    assert not is_home_area({'name':'Jaipur','state':'Assam','country':'India'},profile)
    result=get_categorized_recommendations(profile)
    for key in ('recommended_for_you','trending_trips','seasonal_and_upcoming'):
        assert not any('jaipur' in row['name'].casefold() for row in result[key])


def test_profile_residence_roundtrip_and_currency(client,demo_user):
    response=client.post('/api/profile/'+demo_user,json={'travel_goals':['nature','culture'],
        'place_interests':['mountains','historic'],'residence_country':'US','preferred_currency':'USD',
        'residence_state':'Rajasthan','residence_city':'Jaipur'})
    assert response.status_code==200,response.text
    saved=client.get('/api/profile/'+demo_user).json()
    assert saved['residence_country']=='US' and saved['preferred_currency']=='USD'
    assert saved['residence_state'] is None and saved['residence_city'] is None
    assert len(saved['rl_state_vector'])==22


def test_residence_cannot_be_read_by_another_account(client,demo_user):
    other=client.post('/api/account/guest',json={'guest_id':'another_residence_account_identity'}).json()
    for suffix in ('','/export'):
        response=client.get('/api/profile/'+demo_user+suffix,headers={'Authorization':'Bearer '+other['token']})
        assert response.status_code==403 and response.json()['code']=='USER_MISMATCH'


def test_reference_rate_cached_and_offline_fallback(client,monkeypatch):
    from app.services.currency import display_rate
    from datetime import datetime,timezone
    response=Mock()
    response.json.return_value={'rate':0.012,'date':datetime.now(timezone.utc).date().isoformat()}
    provider=Mock(return_value=response)
    monkeypatch.setattr(requests,'get',provider)
    first=display_rate('USD')
    assert first['available'] and first['rate']==0.012
    assert display_rate('USD')['rate']==0.012 and provider.call_count==1
    with get_connection() as conn:
        conn.execute("UPDATE a_currency_rates SET fetched_at='2000-01-01T00:00:00+00:00'")
    provider.side_effect=requests.ConnectionError('offline')
    cached=display_rate('USD')
    assert cached['stale'] and cached['available']
    missing=display_rate('EUR')
    assert not missing['available'] and missing['rate'] is None


def test_google_setup_survives_memory_reset(client,monkeypatch):
    from app import auth
    monkeypatch.setenv('GOOGLE_CLIENT_ID','')
    monkeypatch.setattr(auth,'GOOGLE_CLIENT_ID','')
    client_id='123456789-example.apps.googleusercontent.com'
    auth.set_google_client_id(client_id)
    monkeypatch.setattr(auth,'GOOGLE_CLIENT_ID','')
    assert auth.get_google_client_id()==client_id
