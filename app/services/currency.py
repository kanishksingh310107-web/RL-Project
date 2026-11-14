"""Cached reference rates for optional display conversion; budgets remain INR."""
import math
from datetime import datetime, timedelta, timezone
import requests
from app.database import get_connection
from app.residence import CURRENCIES


def display_rate(currency):
    code = currency.strip().upper()
    if code not in CURRENCIES:
        raise ValueError('Choose a supported display currency.')
    if code == 'INR':
        return dict(base='INR',currency=code,rate=1,available=True,as_of=None,stale=False)
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        cached = conn.execute('SELECT * FROM a_currency_rates WHERE currency=?',(code,)).fetchone()
    if cached and now-datetime.fromisoformat(cached['fetched_at']) < timedelta(hours=6):
        return dict(base='INR',currency=code,rate=cached['rate'],as_of=cached['as_of'],available=True,stale=False,source='Frankfurter reference rate')
    try:
        response = requests.get('https://api.frankfurter.dev/v2/rate/inr/'+code.lower(),timeout=4)
        response.raise_for_status()
        data = response.json()
        rate = float(data['rate'])
        as_of = datetime.fromisoformat(data['date']).date()
        if not math.isfinite(rate) or rate <= 0 or as_of > now.date() or (now.date()-as_of).days > 7:
            raise ValueError('Invalid or outdated reference rate')
        with get_connection() as conn:
            conn.execute('''INSERT INTO a_currency_rates(currency,rate,as_of,fetched_at) VALUES(?,?,?,?)
                ON CONFLICT(currency) DO UPDATE SET rate=excluded.rate,as_of=excluded.as_of,fetched_at=excluded.fetched_at''',
                (code,rate,as_of.isoformat(),now.isoformat()))
        return dict(base='INR',currency=code,rate=rate,as_of=as_of.isoformat(),available=True,stale=False,source='Frankfurter reference rate')
    except (requests.RequestException,ValueError,KeyError,TypeError):
        if cached and (now.date()-datetime.fromisoformat(cached['as_of']).date()).days <= 7:
            return dict(base='INR',currency=code,rate=cached['rate'],as_of=cached['as_of'],available=True,stale=True,source='Cached Frankfurter reference rate')
        return dict(base='INR',currency=code,rate=None,as_of=None,available=False,stale=False,
                    message='Currency conversion is unavailable. Prices are shown in INR; your selected currency has been kept.')
