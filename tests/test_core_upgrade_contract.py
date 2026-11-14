"""Backend contract regressions. Deliberately not run in this implementation branch."""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError


def _trip_dates():
    start = date.today() + timedelta(days=2)
    return start.isoformat(), (start + timedelta(days=2)).isoformat()


def test_adult_only_family_is_kept_separate_from_party_counts():
    from app.models import TripCreate
    start, end = _trip_dates()
    trip = TripCreate.model_validate({
        'destination_id':'manali_spiti_india','start_date':start,'end_date':end,
        'party':{'adults':3,'children':0,'seniors':0},'trip_type':'family','total_budget':24000,
    })
    assert trip.party.model_dump() == {'adults':3,'children':0,'seniors':0}
    assert trip.trip_type == 'family'
    assert trip.companions == 'friends'  # backward-compatible count alias


def test_trip_budget_requires_whole_amount_and_same_day_is_valid():
    from app.models import TripCreate
    today = date.today().isoformat()
    trip = TripCreate.model_validate({'destination_id':'jaipur_rajasthan_india','start_date':today,
        'end_date':today,'trip_type':'solo','party':{'adults':1,'children':0,'seniors':0},'total_budget':10000})
    assert trip.start_date == trip.end_date
    with pytest.raises(ValidationError):
        TripCreate.model_validate({'destination_id':'jaipur_rajasthan_india','start_date':today,
            'end_date':today,'total_budget':10000.25})


def test_unverified_google_mock_identity_is_never_accepted(client):
    response=client.post('/api/auth',json={'provider':'google','identifier':'someone@example.com'})
    assert response.status_code==403
    assert response.json()['detail']['code']=='GOOGLE_VERIFICATION_REQUIRED'


def test_new_trip_date_gate_uses_india_local_day(client,demo_user):
    today=date.today()
    future=(today+timedelta(days=3)).isoformat()
    result=client.post(f'/api/trips/{demo_user}',json={'destination_id':'manali_spiti_india',
        'start_date':future,'end_date':future,'party':{'adults':2,'children':0,'seniors':0},
        'trip_type':'family','total_budget':22000})
    assert result.status_code==200,result.text
    assert result.json()['trip_type']=='family'
    yesterday=(today-timedelta(days=1)).isoformat()
    rejected=client.post(f'/api/trips/{demo_user}',json={'destination_id':'manali_spiti_india',
        'start_date':yesterday,'end_date':yesterday,'travellers_count':1,'total_budget':10000})
    assert rejected.status_code==422


def test_expenses_and_share_links_are_owner_only_and_revocable(client,demo_user):
    start,end=_trip_dates()
    trip=client.post(f'/api/trips/{demo_user}',json={'destination_id':'manali_spiti_india',
        'start_date':start,'end_date':end,'travellers_count':1,'total_budget':18000})
    assert trip.status_code==200,trip.text
    trip_id=trip.json()['id']
    expense=client.post(f'/api/trips/{trip_id}/expenses',json={'category':'shopping','amount_inr':1250,
        'note':'Local crafts','spent_on':start})
    assert expense.status_code==200,expense.text
    assert expense.json()['planned_vs_actual']['actual_by_category_inr']['shopping']==1250
    share=client.post(f'/api/trips/{trip_id}/share')
    assert share.status_code==200,share.text
    token=share.json()['token']
    public=client.get(share.json()['url_path'])
    assert public.status_code==200
    assert public.json()['read_only'] is True
    assert 'user_id' not in public.json()['trip']
    revoke=client.delete(f'/api/trips/{trip_id}/share')
    assert revoke.status_code==200
    assert client.get(share.json()['url_path']).status_code==404


def test_expense_amount_rejects_fractional_or_unknown_category(client,demo_user):
    start,end=_trip_dates()
    trip=client.post(f'/api/trips/{demo_user}',json={'destination_id':'manali_spiti_india',
        'start_date':start,'end_date':end,'travellers_count':1,'total_budget':18000}).json()
    invalid=client.post(f"/api/trips/{trip['id']}/expenses",json={'category':'shopping','amount_inr':1.5,'spent_on':start})
    assert invalid.status_code==422
    invalid_category=client.post(f"/api/trips/{trip['id']}/expenses",json={'category':'unknown','amount_inr':1,'spent_on':start})
    assert invalid_category.status_code==422
