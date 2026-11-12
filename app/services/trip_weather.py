"""Date-specific shared weather for every planner surface.

Forecasts through today +16 days; other days use +/-3 calendar-day
samples from the last ten completed years. All failures are explicit estimates.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math
from urllib.parse import urlencode
import requests
from app.providers.cache import get_cached, set_cached, TTL_WEATHER_SECONDS, TTL_PLACES_SECONDS
from app.core.assumptions import PROVIDER_HTTP_TIMEOUT_SECONDS


def today_india():
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()


def _daily(lat, lon, start, end, archive=False, transport=None):
    key = f"trip-weather:v1:{lat:.4f}:{lon:.4f}:{start}:{end}:{archive}"
    cached = get_cached(key)
    if cached is not None:
        return cached
    # Keyless Open-Meteo only: no Geoapify credits are consumed. Ten bounded
    # archive windows per trip, each cached for seven days; no unbounded retries.
    daily = 'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max'
    if not archive:
        daily += ',precipitation_probability_max,weather_code,sunrise,sunset'
    try:
        url = 'https://archive-api.open-meteo.com/v1/archive' if archive else 'https://api.open-meteo.com/v1/forecast'
        params = {'latitude':lat,'longitude':lon,'start_date':str(start),'end_date':str(end),
                  'daily':daily,'timezone':'Asia/Kolkata'}
        if transport:
            data = transport(url+'?'+urlencode(params)).get('daily') or {}
            # Some legacy adapters omit the daily date vector; infer only dates
            # requested by that adapter, never fabricate missing measurements.
            if not data.get('time') and data.get('temperature_2m_max'):
                data['time'] = [str(start+timedelta(days=i)) for i in range(len(data['temperature_2m_max']))]
        else:
            response = requests.get(url,params=params,timeout=PROVIDER_HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json().get('daily') or {}
        rows = []
        for i, day in enumerate(data.get('time', [])):
            row = {'date':day}
            for key2, values in data.items():
                if key2 != 'time':
                    row[key2] = values[i] if i < len(values) else None
            if row.get('temperature_2m_max') is not None and row.get('temperature_2m_min') is not None:
                rows.append(row)
    except (requests.RequestException, ValueError, TypeError, KeyError, OSError, RuntimeError):
        rows = []
    set_cached(key, rows, TTL_PLACES_SECONDS if archive else TTL_WEATHER_SECONDS)
    return rows


def _percentile(values, quantile):
    values = sorted(values)
    index = (len(values)-1)*quantile
    lo = math.floor(index)
    hi = math.ceil(index)
    return round(values[lo] + (values[hi]-values[lo])*(index-lo), 1)


def weather_for_dates(lat, lon, start_date, end_date, transport=None):
    from app.providers.weather import WMO_DESCRIPTIONS
    today = today_india()
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end-start).days > 365:
        raise ValueError('Weather requires a chronological trip of at most 366 days.')
    key = f"trip-weather:summary:v1:{lat:.4f}:{lon:.4f}:{start}:{end}:{today}"
    cached = get_cached(key)
    if cached is not None:
        return dict(cached, cached=True)
    dates = [start+timedelta(days=i) for i in range((end-start).days+1)]
    forecast_dates = [d for d in dates if today <= d <= today+timedelta(days=16)]
    forecasts = {r['date']:r for r in _daily(lat,lon,min(forecast_dates),max(forecast_dates),transport=transport)} if forecast_dates else {}
    climate_dates = [d for d in dates if d not in forecast_dates]
    samples = {d:[] for d in climate_dates}
    # Fetch one window per reference year, then select the seven-day samples
    # separately for each trip date (including New Year and leap-day crossings).
    for offset in range(1,11) if climate_dates else []:
        year = today.year-offset
        centres = {d:date(year,d.month,min(d.day,28) if d.month==2 and d.day==29 else d.day) for d in climate_dates}
        rows = _daily(lat,lon,min(centres.values())-timedelta(days=3),max(centres.values())+timedelta(days=3),True,transport=transport)
        if not rows:
            break  # outage: do not repeat nine more calls to the same failing provider
        for d, centre in centres.items():
            samples[d].extend(r for r in rows if abs((date.fromisoformat(r['date'])-centre).days) <= 3)
    days = []
    for d in dates:
        forecast = forecasts.get(str(d))
        if forecast:
            row = {'date':str(d),'source':'forecast','temp_min_c':forecast['temperature_2m_min'],
                'temp_max_c':forecast['temperature_2m_max'],'rain_probability_pct':forecast.get('precipitation_probability_max') or 0,
                'rain_sum_mm':forecast.get('precipitation_sum') or 0,'wind_kmh':forecast.get('wind_speed_10m_max') or 0,
                'condition':WMO_DESCRIPTIONS.get(forecast.get('weather_code'), 'Forecast'),
                'sunrise':forecast.get('sunrise'),'sunset':forecast.get('sunset')}
        elif samples.get(d):
            rs = samples[d]
            fields = {'temp_min_c':'temperature_2m_min','temp_max_c':'temperature_2m_max',
                      'rain_sum_mm':'precipitation_sum','wind_kmh':'wind_speed_10m_max'}
            row = {'date':str(d),'source':'climatology','condition':'Typical seasonal conditions','sample_count':len(rs),
                   'reference_period':f'{today.year-10}–{today.year-1}', 'ranges':{}}
            for name, field in fields.items():
                values = [r[field] for r in rs if r.get(field) is not None]
                row[name] = round(sum(values)/len(values),1) if values else 0
                row['ranges'][name] = {'p10':_percentile(values,.1),'p90':_percentile(values,.9)} if values else None
            rains = [r['precipitation_sum'] for r in rs if r.get('precipitation_sum') is not None]
            row['rain_probability_pct'] = round(100*sum(r>1 for r in rains)/len(rains)) if rains else 0
        else:
            # Latitude/season adjusted broad defaults; never labelled forecast.
            winter = d.month in (11,12,1,2)
            low, high = ((12,27) if winter else (23,34)) if lat >= 23 else ((21,30) if winter else (24,33))
            row = {'date':str(d),'source':'offline_estimate','condition':'Offline estimate',
                   'temp_min_c':low,'temp_max_c':high,'rain_probability_pct':10 if winter else 50,
                   'rain_sum_mm':0 if winter else 3,'wind_kmh':15}
        row['label'] = {'forecast':'Forecast','climatology':'10-year typical conditions','offline_estimate':'Offline estimate'}[row['source']]
        days.append(row)
    count = sum(r['source']=='forecast' for r in days)
    offline = sum(r['source']=='offline_estimate' for r in days)
    label = 'Live forecast (Open-Meteo)' if count == len(days) else 'Offline estimate – not a live forecast' if offline == len(days) else 'Forecast and typical conditions' if count else '10-year typical conditions'
    sentence = f'Forecast for {count} of {len(days)} days; '
    sentence += 'the rest show typical conditions for these dates over the last 10 years.' if not offline else f'{offline} day(s) use an Offline estimate because weather data could not be retrieved.'
    summary = {'temp_min_c':min(r['temp_min_c'] for r in days),'temp_max_c':max(r['temp_max_c'] for r in days),
               'wind_kmh':max(r['wind_kmh'] for r in days),'rain_expected':any(r['rain_probability_pct']>=40 or r['rain_sum_mm']>1 for r in days),
               'rain_probability':max(r['rain_probability_pct'] for r in days)}
    result = {'available':True,'daily':days,'daily_forecast':days,'summary':summary,**summary,
        'label':label,'message':sentence,'weather_description':label,'weather_type_label':label,
        'source':'offline-estimate' if offline==len(days) else 'open-meteo',
        'weather_type':'forecast' if count==len(days) else 'historical_climate_estimate' if not count else 'mixed',
        'coordinates':(lat,lon),'start_date':str(start),'end_date':str(end),
        'fetched_at':datetime.now(timezone.utc).isoformat(),
        'provenance':{'source':'open-meteo' if offline<len(days) else 'assumed','is_live':count>0,
                      'is_estimate':count<len(days),'notes':sentence+' Weather data by Open-Meteo.com (CC BY 4.0)'}}
    set_cached(key,result,TTL_WEATHER_SECONDS)
    return result


def weather_for_trip(trip):
    from app.providers.geo import resolve_trip_location
    location = resolve_trip_location(destination_id=trip.get('destination_id'), destination_name=trip.get('destination_name'),
        lat=trip.get('destination_lat'),lon=trip.get('destination_lon'),allow_live_geocode=False)
    if location.get('lat') is None or location.get('lon') is None:
        return {'available':False,'source':'unavailable','label':'Weather unavailable','summary':{},'daily':[]}
    return dict(weather_for_dates(location['lat'],location['lon'],trip['start_date'],trip['end_date']),
                resolved_location=location.get('resolved_location'), destination_id=trip.get('destination_id'))
