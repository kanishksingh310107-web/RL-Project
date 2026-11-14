"""Residence validation and home-area exclusions without changing policy vectors."""
import json
import re
import unicodedata
from pathlib import Path

METADATA = json.loads((Path(__file__).parent / 'data' / 'residence_countries.json').read_text(encoding='utf-8'))
COUNTRIES = {item['code']: item for item in METADATA['countries']}
CURRENCIES = {'INR', 'USD'} | {code for item in COUNTRIES.values() for code in item['currencies']}
INDIAN_STATES = (
    'Andaman and Nicobar Islands','Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chandigarh',
    'Chhattisgarh','Dadra and Nagar Haveli and Daman and Diu','Delhi','Goa','Gujarat','Haryana',
    'Himachal Pradesh','Jammu and Kashmir','Jharkhand','Karnataka','Kerala','Ladakh','Lakshadweep',
    'Madhya Pradesh','Maharashtra','Manipur','Meghalaya','Mizoram','Nagaland','Odisha','Puducherry',
    'Punjab','Rajasthan','Sikkim','Tamil Nadu','Telangana','Tripura','Uttar Pradesh','Uttarakhand','West Bengal')


class ResidenceError(ValueError):
    def __init__(self,message,field):
        super().__init__(message)
        self.field = field


def normalise_place(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    value = re.sub(r'[^\w\s]', ' ', value, flags=re.UNICODE)
    value = ' '.join(value.split())
    return {'bangalore':'bengaluru','bombay':'mumbai','calcutta':'kolkata','madras':'chennai',
            'gurgaon':'gurugram','new delhi':'delhi','banaras':'varanasi','cochin':'kochi'}.get(value,value)


def validate_residence(country, state, city, currency):
    if not isinstance(country,str) or country.strip().upper() not in COUNTRIES:
        raise ResidenceError('Choose your country of residence.','residence_country')
    country = country.strip().upper()
    if country == 'IN':
        states = {s.casefold():s for s in INDIAN_STATES}
        if not isinstance(state,str) or state.strip().casefold() not in states:
            raise ResidenceError('Choose your Indian state or union territory.','residence_state')
        state = states[state.strip().casefold()]
        if not isinstance(city,str) or not 2 <= len(city.strip()) <= 100 or not any(c.isalpha() for c in city):
            raise ResidenceError('Enter your town or city using 2–100 characters.','residence_city')
        city = ' '.join(city.split())
        if any(c in '<>' or unicodedata.category(c) in ('Cc','Cs') for c in city):
            raise ResidenceError('Enter a town or city name, without HTML or control characters.','residence_city')
        currency = 'INR'
    else:
        state, city = None, None
        currency = currency or next(iter(COUNTRIES[country]['currencies']), 'USD')
    if not isinstance(currency,str) or currency.strip().upper() not in CURRENCIES:
        raise ResidenceError('Choose a supported display currency.','preferred_currency')
    return dict(residence_country=country,residence_state=state,residence_city=city,preferred_currency=currency.strip().upper())


def residence_missing(profile):
    raw = profile.get('raw_answers') or profile
    values = {key:profile.get(key) or raw.get(key) for key in ('residence_country','residence_state','residence_city','preferred_currency')}
    try:
        validate_residence(values['residence_country'],values['residence_state'],values['residence_city'],values['preferred_currency'])
        return []
    except ValueError as exc:
        field = getattr(exc,'field','residence_country')
        return [dict(id=field,field=field,label=str(exc),question=str(exc),level='basic')]


def is_home_area(destination, profile):
    raw = profile.get('raw_answers') or {}
    country = profile.get('residence_country') or raw.get('residence_country')
    city = normalise_place(profile.get('residence_city') or raw.get('residence_city'))
    if country != 'IN' or not city or str(destination.get('country','India')).casefold() not in ('india','in'):
        return False
    state = normalise_place(profile.get('residence_state') or raw.get('residence_state'))
    from app.data.india_destinations import DESTINATIONS_BY_ID
    canonical = DESTINATIONS_BY_ID.get(destination.get('id'),{})
    dest_state = normalise_place(destination.get('state') or canonical.get('state'))
    if state and dest_state and state != dest_state and not re.search(r'(?<!\w)'+re.escape(state)+r'(?!\w)',dest_state):
        return False
    names = [destination.get('city'),destination.get('name'),destination.get('destination_name')]
    names += re.split(r'\s*(?:&|,|/|\band\b)\s*', str(destination.get('name') or ''))
    return any(re.search(r'(?<!\w)'+re.escape(city)+r'(?!\w)',normalise_place(name)) for name in names)
