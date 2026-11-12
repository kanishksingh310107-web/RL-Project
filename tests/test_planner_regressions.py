"""Regression coverage for the seven planner repairs, without paid/live APIs."""
from datetime import date, timedelta
from itertools import combinations
from unittest.mock import Mock
import pytest
import requests
from app.providers.geo import haversine_distance_km


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError('test: offline')
    monkeypatch.setattr('requests.get', unavailable)
    monkeypatch.setattr('urllib.request.urlopen', unavailable)


def trip_payload(**overrides):
    return dict(destination_id='jaipur_jodhpur_india',destination_name='Jaipur & Jodhpur (Rajasthan)',
        start_date='2026-11-26',end_date='2026-11-30',total_budget=26000,
        accommodation_tier='boutique',transit_pref='public_transit',travel_pace='relaxed',**overrides)


def create(client, user, **overrides):
    response = client.post('/api/trips/'+user,json=trip_payload(**overrides))
    assert response.status_code == 200, response.text
    return response.json()


def test_offline_stays_are_real_areas_inside_radius(client):
    response = client.get('/api/stay/search?destination_id=jaipur_jodhpur_india&accommodation_tier=boutique')
    assert response.status_code == 200, response.text
    rows = response.json()['options']
    assert rows
    for row in rows:
        assert row['kind'] == 'area'
        assert row['label'] == 'Indicative - no live listings'
        assert row['distance_km'] <= 12
        assert row['tier_label'] == 'Boutique & Heritage'
        assert 'maps/search' in row['external_search_url']
        assert set(row['price_bands']) == {'hostel','budget','mid_range','boutique','luxury'}
        assert not any(word in row['name'].lower() for word in ('hotel','shrine','bamboo'))


def test_geoapify_stays_filter_country_category_distance_and_tier(monkeypatch):
    from app.providers import geo
    monkeypatch.setattr(geo,'is_geoapify_configured',lambda: True)
    monkeypatch.setattr(geo,'can_call_geoapify',lambda: True)
    properties = dict(name='Mock accommodation',lat=26.92,lon=75.79,country_code='in',
                      categories=['accommodation.hotel'],stars=4)
    rows = [properties,dict(properties,name='Attraction',categories=['tourism.attraction']),
            dict(properties,name='Foreign',country_code='jp'),
            dict(properties,name='Far hotel',lat=27.5),dict(properties,name='Wrong tier',stars=5)]
    response = Mock(ok=True)
    response.json.return_value = {'features':[{'properties':p} for p in rows]}
    http = Mock(return_value=response)
    monkeypatch.setattr(geo.requests,'get',http)
    stays = geo.get_accommodations(26.9124,75.7873,tier='boutique',trip_id='one')
    assert [s.name for s in stays] == ['Mock accommodation']
    assert stays[0].kind == 'accommodation'
    assert stays[0].distance_km <= 12
    assert 'circle:75.7873,26.9124,12000' == http.call_args.kwargs['params']['filter']
    assert geo.get_accommodations(26.9124,75.7873,tier='boutique',trip_id='two')[0].trip_id == 'two'
    assert http.call_count == 1


def test_all_indian_catalogue_destinations_have_curated_stay_areas():
    from app.data.stay_areas import AREA_NAMES
    from app.data.india_destinations import INDIAN_DESTINATIONS
    from app.recommender import DESTINATIONS
    ids = {d['id'] for d in INDIAN_DESTINATIONS+DESTINATIONS if d.get('country')=='India' or d['id'].endswith('_india')}
    assert ids <= set(AREA_NAMES)
    assert all(len(AREA_NAMES[key]) >= 3 for key in ids)


def test_cost_monotonic_components_and_shared_minimum():
    from app.core.cost_model import estimate_cost
    from app.core.assumptions import STAY_RATES_INR
    from app.planning.budget import calculate_minimum_trip_budget
    base = trip_payload()
    costs = []
    for tier in ('hostel','budget','mid_range','boutique','luxury'):
        trip = dict(base,accommodation_tier=tier)
        cost = estimate_cost(trip)
        costs.append(cost['total'])
        assert cost['total'] >= cost['nights']*STAY_RATES_INR[tier][0]
        assert cost['total'] == round(sum(v['per_party'] for v in cost['cost_breakdown'].values()),2)
    assert costs == sorted(set(costs))
    solo = estimate_cost(base)
    assert estimate_cost(dict(base,travellers_count=2))['total'] > solo['total']
    assert estimate_cost(dict(base,end_date='2026-12-01'))['total'] > solo['total']
    minimum = calculate_minimum_trip_budget(**{k:v for k,v in base.items() if k!='total_budget'})
    assert minimum['recommended_budget'] == solo['total']
    assert minimum['bare_minimum_budget'] == estimate_cost(base,minimum=True)['total']
    assert solo['cost_breakdown']['intercity_transit']['per_party'] > 0


def test_party_sync_legacy_and_solo_rejection(client,demo_user):
    r=client.post('/api/trips/'+demo_user,json=trip_payload(companions='solo',travellers_count=2))
    assert r.status_code == 422
    assert 'Solo requires exactly one adult' in r.text
    trip=create(client,demo_user,party={'adults':2,'children':1,'seniors':0})
    assert trip['travellers_count']==3 and trip['party_type']=='family'
    assert trip['party_label']=='2 adults - 1 child'
    from app.core.party import normalize_party,party_type
    assert party_type(normalize_party({'travellers_count':2,'companions':'solo'}))=='partner'


def test_trip_duplicate_edit_delete_ownership_and_policy(client,demo_user):
    from app.database import get_connection
    trip=create(client,demo_user)
    duplicate=create(client,demo_user)
    assert trip['id']==duplicate['id']
    assert 'already exists' in duplicate['message']
    tid=trip['id']
    r=client.post(f'/api/itinerary/generate/{tid}?user_id={demo_user}')
    assert r.status_code==200,r.text
    itinerary=r.json()
    assert round(sum(d['total_cost'] for d in itinerary['days']),2)==itinerary['total_estimated_cost']
    accepted_id = itinerary['days'][0]['activities'][0]['activity_id']
    feedback = client.post('/api/itinerary/feedback/'+demo_user, json={
        'itinerary_id':itinerary['id'],'activity_id':accepted_id,'action_type':'accept'})
    assert feedback.status_code == 200, feedback.text
    with get_connection() as conn:
        first=conn.execute('SELECT id FROM itinerary_activities WHERE itinerary_id=? LIMIT 1',(itinerary['id'],)).fetchone()
        assert first
        conn.execute("UPDATE itinerary_activities SET status='accepted' WHERE id=?",(first[0],));conn.commit()
        policy=conn.execute('SELECT * FROM rl_user_policies WHERE user_id=?',(demo_user,)).fetchall()
        assert policy
        conn.execute("INSERT INTO live_activity_contexts(itinerary_id,activity_id,context_vector_json) VALUES(?,?,'[]')",(itinerary['id'],accepted_id))
        conn.commit()
    assert client.patch(f'/api/trips/{tid}?user_id=wrong',json={'total_budget':30000}).status_code==404
    edited=client.patch(f'/api/trips/{tid}?user_id={demo_user}',json={
        'party':{'adults':2,'children':0,'seniors':0},'total_budget':30000,'regeneration_mode':'keep_accepted'})
    assert edited.status_code==200,edited.text
    assert edited.json()['party_type']=='partner'
    assert edited.json()['cost_estimate']['total']>trip['cost_estimate']['total']
    with get_connection() as conn:
        assert conn.execute('SELECT status FROM itinerary_activities WHERE id=?',(first[0],)).fetchone()[0]=='accepted'
    assert client.delete(f'/api/trips/{tid}?user_id=wrong').status_code==404
    deleted=client.delete(f'/api/trips/{tid}?user_id={demo_user}')
    assert deleted.status_code==200,deleted.text
    with get_connection() as conn:
        assert not conn.execute('SELECT id FROM itineraries WHERE trip_id=?',(tid,)).fetchone()
        assert not conn.execute('SELECT * FROM rl_feedback_log WHERE trip_id=?',(tid,)).fetchone()
        assert not conn.execute('SELECT * FROM live_activity_contexts WHERE itinerary_id=?',(itinerary['id'],)).fetchone()
        assert [tuple(r) for r in conn.execute('SELECT * FROM rl_user_policies WHERE user_id=?',(demo_user,))]==[tuple(r) for r in policy]


def test_strict_radius_regions_and_daily_clusters(client,demo_user):
    from app.providers.geo import discover_places_india
    from app.activity_data import CURATED_ACTIVITIES
    places=discover_places_india(26.9124,75.7873,radius_meters=5000)
    assert places
    assert all(haversine_distance_km(26.9124,75.7873,p.lat,p.lon)<=5 for p in places)
    for activity in CURATED_ACTIVITIES:
        assert activity['city'] and activity['area']
        if activity['id'] in ('agra_fatehpur_sikri_buland_darwaza','mathura_vrindavan_bankey_bihari'):
            assert activity['destination_id']=='agra_braj_india'
    trip=create(client,demo_user)
    r=client.post(f"/api/itinerary/generate/{trip['id']}?user_id={demo_user}")
    assert r.status_code==200,r.text
    for day in r.json()['days']:
        assert 'Central Jaipur & Jodhpur' not in day['theme']
        for a,b in combinations(day['activities'],2):
            assert haversine_distance_km(a['latitude'],a['longitude'],b['latitude'],b['longitude'])<=12


def mock_weather_http(url,params,timeout):
    start,end=date.fromisoformat(params['start_date']),date.fromisoformat(params['end_date'])
    times=[str(start+timedelta(days=i)) for i in range((end-start).days+1)]
    count=len(times)
    daily={'time':times,'temperature_2m_max':[29]*count,'temperature_2m_min':[14]*count,
        'precipitation_sum':[2]*count,'wind_speed_10m_max':[20]*count,
        'precipitation_probability_max':[60]*count,'weather_code':[61]*count}
    response=Mock(ok=True)
    response.json.return_value={'daily':daily}
    return response


def test_weather_mixed_window_climatology_and_packing_equality(client,demo_user,monkeypatch):
    from app.services import trip_weather
    monkeypatch.setattr(trip_weather,'today_india',lambda:date(2026,11,12))
    http=Mock(side_effect=mock_weather_http)
    monkeypatch.setattr(trip_weather.requests,'get',http)
    trip=create(client,demo_user)
    weather=client.get(f"/api/prep/{trip['id']}/weather").json()
    assert [r['source'] for r in weather['daily']]==['forecast']*3+['climatology']*2
    assert weather['daily'][-1]['sample_count']==70
    assert weather['daily'][-1]['rain_probability_pct']==100
    assert weather['daily'][-1]['ranges']['temp_max_c']=={'p10':29,'p90':29}
    packing=client.get(f"/api/prep/{trip['id']}/packing").json()
    assert packing['weather_summary']==weather['summary']
    assert http.call_count==11
    assert all(call.kwargs['params']['timezone']=='Asia/Kolkata' for call in http.call_args_list)


def test_weather_offline_and_past_paths(monkeypatch):
    from app.services import trip_weather
    monkeypatch.setattr(trip_weather,'today_india',lambda:date(2026,11,12))
    offline=trip_weather.weather_for_dates(26.9124,75.7873,'2026-11-26','2026-11-30')
    assert len(offline['daily'])==5
    assert {r['source'] for r in offline['daily']}=={'offline_estimate'}
    assert 'not a live forecast' in offline['label']
    monkeypatch.setattr(trip_weather.requests,'get',mock_weather_http)
    past=trip_weather.weather_for_dates(26.9124,75.7873,'2025-02-01','2025-02-02')
    assert {r['source'] for r in past['daily']}=={'climatology'}


def test_regenerate_everything_and_activity_cost_refresh(client,demo_user):
    trip=create(client,demo_user)
    tid=trip['id']
    itinerary=client.post(f'/api/itinerary/generate/{tid}?user_id={demo_user}').json()
    activity=next(a for d in itinerary['days'] for a in d['activities'] if a['cost_estimate']>0 and a['category']!='food_dining')
    removed=client.delete(f"/api/trip-actions/{tid}/activity/{activity['activity_id']}?user_id={demo_user}")
    assert removed.status_code==200
    updated=client.get(f'/api/itinerary/{tid}?user_id={demo_user}').json()
    assert updated['total_estimated_cost']<itinerary['total_estimated_cost']
    assert round(sum(d['total_cost'] for d in updated['days']),2)==updated['total_estimated_cost']
    packing=client.get(f'/api/prep/{tid}/packing').json()
    timed=client.get(f'/api/trip-actions/{tid}/timed-view').json()
    assert packing['cost_estimate']['total']==timed['cost_estimate']['total']==updated['total_estimated_cost']
    edited=client.patch(f'/api/trips/{tid}?user_id={demo_user}',json={
        'end_date':'2026-11-28','regeneration_mode':'everything','food_style':'street_food'})
    assert edited.status_code==200,edited.text
    assert edited.json()['duration_days']==3
    assert len(client.get(f'/api/itinerary/{tid}?user_id={demo_user}').json()['days'])==3


def test_outside_india_never_returns_stays():
    from app.providers.geo import get_accommodations
    assert get_accommodations(1,1)==[]


def test_stay_option_a_anchor_and_option_b_centroid(client,demo_user):
    trip=create(client,demo_user,stay_name='User chosen stay',stay_lat=26.931,stay_lon=75.789)
    assert trip['trip_preferences']['stay_anchor']['lat']==26.931
    r=client.post(f"/api/itinerary/generate/{trip['id']}?user_id={demo_user}")
    assert r.status_code==200,r.text
    assert any('User chosen stay' in (a['transit_suggestion'] or '') for d in r.json()['days'] for a in d['activities'])
    areas=client.get(f"/api/stay/{trip['id']}/areas").json()
    assert len(areas['recommended_areas'])==3
    distances=[a['distance_to_centroid_km'] for a in areas['recommended_areas']]
    assert distances==sorted(distances)
