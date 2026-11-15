"""Single indicative INR model for estimates, itinerary ledgers and live alerts."""
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from app.core.assumptions import (STAY_RATES_INR, ROOM_OCCUPANCY, INTERCITY_RATES_INR,
    LOCAL_DAILY_INR, FOOD_DAILY_INR, FOOD_TIER_MULTIPLIER, INCIDENTALS_DAILY_INR,
    SHOPPING_INR, CONTINGENCY_RATE, CHILD_ENTRY_FACTOR, SENIOR_ENTRY_FACTOR,
    UNKNOWN_ENTRY_INR, LEGACY_USD_TO_INR, CIRCUITY_FACTOR, BUDGET_BAND_LABELS)
from app.core.party import normalize_party


def whole_inr(value):
    """Round an INR amount deterministically to the nearest whole rupee."""
    return int(Decimal(str(value or 0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def canonical_tier(value):
    value = (value or 'mid_range').lower()
    aliases = {'budget_hostel':'hostel','budget_hotel':'budget','budget_guesthouse':'budget',
        'balanced':'mid_range','boutique_hotel':'boutique','heritage':'boutique','resort':'luxury',
        'apartment':'mid_range','homestay':'budget'}
    value = aliases.get(value,value)
    return value if value in STAY_RATES_INR else 'mid_range'


def canonical_mode(value):
    return {'bus_metro': 'public_transit', 'train': 'public_transit', 'cab': 'taxi',
            'cab_rental': 'taxi', 'walk': 'walking', 'auto': 'public_transit'}.get(value, value) if value else 'public_transit'


def activity_fee_inr(activity):
    amount = activity.get('cost_estimate',activity.get('cost_amount'))
    if amount is None:
        return UNKNOWN_ENTRY_INR
    amount = max(0,float(amount))
    # Legacy curated ticket values <=50 were USD. New generated INR values
    # are converted before storage; positive converted values are >=83 INR.
    if activity.get('currency') != 'INR' and amount <= 50:
        amount *= LEGACY_USD_TO_INR
    return amount


def leg_cost_inr(distance_km, mode):
    from app.core.assumptions import LOCAL_LEG_RATE_INR, LOCAL_LEG_BASE_INR
    if mode=='walk': return 0
    return whole_inr(distance_km * LOCAL_LEG_RATE_INR.get(mode,LOCAL_LEG_RATE_INR['cab']) +
                     (LOCAL_LEG_BASE_INR if mode in ('auto','cab') else 0))


def estimate_cost(trip, activities=None, minimum=False):
    from app.providers.geo import haversine_distance_km, resolve_trip_location
    from app.planning.budget import MAJOR_INDIAN_HUBS
    prefs = trip.get('trip_preferences') or trip.get('trip_preferences_json') or {}
    if isinstance(prefs, str):
        prefs = json.loads(prefs)
    party = normalize_party(trip)
    people = sum(party.values())
    days = max(1, (date.fromisoformat(trip['end_date']) - date.fromisoformat(trip['start_date'])).days + 1) if trip.get('start_date') and trip.get('end_date') else max(1, int(trip.get('duration_days') or 4))
    nights = max(0, days - 1)
    rooms = math.ceil(people / ROOM_OCCUPANCY)
    tier = 'hostel' if minimum else canonical_tier(trip.get('accommodation_tier'))
    mode = 'public_transit' if minimum else canonical_mode(trip.get('transit_pref'))
    mode = mode if mode in INTERCITY_RATES_INR else 'public_transit'
    dest = resolve_trip_location(destination_id=trip.get('destination_id'), destination_name=trip.get('destination_name'), lat=trip.get('destination_lat'), lon=trip.get('destination_lon'), allow_live_geocode=False)
    if dest.get('lat') is None:
        name = (trip.get('destination_name') or '').lower()
        coords = next((v for k,v in MAJOR_INDIAN_HUBS.items() if k in name), None)
        if coords:
            dest['lat'],dest['lon'] = coords
    departure = (trip.get('departure_location') or 'Delhi').lower().strip()
    origin = next((v for k,v in MAJOR_INDIAN_HUBS.items() if k == departure), None)
    if origin is None:
        origin = next((v for k,v in MAJOR_INDIAN_HUBS.items() if k in departure), None)
    distance_known = bool(origin and dest.get('lat') is not None and dest.get('lon') is not None)
    distance = haversine_distance_km(*origin, dest['lat'], dest['lon']) * CIRCUITY_FACTOR if distance_known else 0
    rate, floor = INTERCITY_RATES_INR[mode]
    intercity = 0 if distance_known and distance < 5 else 2 * max(floor, distance * rate) * people
    food_style = 'street_food' if minimum else (trip.get('food_style') or prefs.get('food_style') or prefs.get('dietary') or 'all')
    food = FOOD_DAILY_INR.get(food_style, FOOD_DAILY_INR['all']) * FOOD_TIER_MULTIPLIER[tier]
    selected_mode = canonical_mode(trip.get('transit_pref'))
    local_daily = min(LOCAL_DAILY_INR[mode],LOCAL_DAILY_INR.get(selected_mode,LOCAL_DAILY_INR[mode])) if minimum else LOCAL_DAILY_INR[mode]
    if activities is None and trip.get('id'):
        from app.database import get_connection
        with get_connection() as conn:
            exists = conn.execute('SELECT id FROM itineraries WHERE trip_id=?',(trip['id'],)).fetchone()
            if exists and not minimum:
                from app.itinerary_generator import get_itinerary_details
                visible = get_itinerary_details(conn,trip['user_id'],trip['id'])
                if visible and visible.get('cost_estimate'): return visible['cost_estimate']
            if exists:
                activities = [dict(r) for r in conn.execute("SELECT * FROM itinerary_activities WHERE itinerary_id=? AND status != 'rejected'",(exists[0],))]
    if activities is None:
        from app.activity_data import CURATED_ACTIVITIES
        activities = [a for a in CURATED_ACTIVITIES if a['destination_id'] == trip.get('destination_id') and a['category'] != 'food_dining']
        count = days * (2 if trip.get('travel_pace') == 'relaxed' else 3)
        activities = sorted(activities, key=lambda a: a.get('cost_amount') or 0)[:count]
        if not activities:
            activities = [{'cost_amount': UNKNOWN_ENTRY_INR, 'currency': 'INR'}] * count
    tickets = 0
    for activity in activities:
        if activity.get('category') == 'food_dining':
            continue  # meals are already accounted for in the daily food allowance
        tickets += activity_fee_inr(activity)
    ticket_people = party['adults'] + party['children'] * CHILD_ENTRY_FACTOR + party['seniors'] * SENIOR_ENTRY_FACTOR
    # If the itinerary and a stay/destination anchor have coordinates, estimate
    # local transport from the actual day-by-day legs. Keep the existing daily
    # allowance as a disclosed fallback when route data is incomplete.
    route_local_total = None
    routed = [a for a in activities or [] if a.get('category') != 'food_dining' and a.get('status') != 'rejected']
    anchor_lat = trip.get('stay_lat') if trip.get('stay_lat') is not None else dest.get('lat')
    anchor_lon = trip.get('stay_lon') if trip.get('stay_lon') is not None else dest.get('lon')
    if routed and anchor_lat is not None and anchor_lon is not None and all(a.get('latitude') is not None and a.get('longitude') is not None for a in routed):
        from app.providers.geo import haversine_distance_km
        from app.core.assumptions import LOCAL_LEG_RATE_INR, LOCAL_LEG_BASE_INR
        local_mode = {'public_transit': 'bus_metro', 'train': 'bus_metro', 'bus': 'bus_metro',
                      'taxi': 'cab', 'cab': 'cab', 'walking': 'walk', 'walk': 'walk',
                      'rental_car': 'rental_car', 'scooter': 'scooter', 'auto': 'auto'}.get(selected_mode, 'cab')
        route_local_total = 0
        for day in range(1, days + 1):
            day_activities = sorted((a for a in routed if int(a.get('day_number') or 0) == day),
                                    key=lambda a: (int(a.get('order_index') or 0), str(a.get('id') or '')))
            previous = (anchor_lat, anchor_lon)
            for activity in day_activities:
                current = (activity['latitude'], activity['longitude'])
                distance = haversine_distance_km(previous[0], previous[1], current[0], current[1]) * CIRCUITY_FACTOR
                fare = distance * LOCAL_LEG_RATE_INR[local_mode]
                if local_mode in ('auto', 'cab'):
                    fare += LOCAL_LEG_BASE_INR
                if local_mode == 'bus_metro':
                    fare *= people
                route_local_total += whole_inr(fare)
                previous = current
            if day_activities:
                distance = haversine_distance_km(previous[0], previous[1], anchor_lat, anchor_lon) * CIRCUITY_FACTOR
                fare = distance * LOCAL_LEG_RATE_INR[local_mode]
                if local_mode in ('auto', 'cab'):
                    fare += LOCAL_LEG_BASE_INR
                if local_mode == 'bus_metro':
                    fare *= people
                route_local_total += whole_inr(fare)
    entered_stay = prefs.get('accommodation') if isinstance(prefs.get('accommodation'), dict) else {}
    stay_cost = nights * rooms * STAY_RATES_INR[tier][0 if minimum else 1]
    if not minimum and entered_stay.get('expected_total_cost_inr') is not None:
        stay_cost = whole_inr(entered_stay['expected_total_cost_inr'])
    if not minimum and prefs.get('intercity_cost_inr') is not None:
        intercity = whole_inr(prefs['intercity_cost_inr'])
    components = {'intercity_transit': intercity, 'local_transit': route_local_total if route_local_total is not None else local_daily * days * people,
                  'accommodation': stay_cost,
                  'food': food * days * people, 'activities': tickets * ticket_people,
                  'shopping': (SHOPPING_INR * (.25 if minimum else 1) * people) if prefs.get('include_shopping', trip.get('include_shopping', False)) else 0,
                  'necessary_extras': INCIDENTALS_DAILY_INR * days * people}
    components['contingency_buffer'] = sum(components.values()) * CONTINGENCY_RATE
    components = {k: whole_inr(v) for k,v in components.items()}
    total = sum(components.values())
    budget = whole_inr(trip.get('total_budget') or 0)
    return {'total': total, 'cost_breakdown': {k: {'per_party': v, 'per_person': round(v/people, 2)} for k,v in components.items()},
            'per_person': round(total/people, 2), 'per_person_per_day': round(total/people/days, 2),
            'rooms': rooms, 'nights': nights, 'days': days, 'travellers_count': people,
            'intercity_distance_km': round(distance, 2), 'confidence': 'indicative',
            'budget_difference': round(budget-total, 2),
            'budget_message': f"Selected budget is {'over' if budget >= total else 'under'} the indicative estimate by ₹{abs(budget-total):,.0f}.",
            'assumptions': {'label': 'Indicative assumptions — not live prices', 'tier': tier,
                'room_rate_inr': STAY_RATES_INR[tier][0 if minimum else 1], 'people_per_room': ROOM_OCCUPANCY,
                'intercity_mode': mode, 'intercity_inr_per_km': rate, 'intercity_one_way_floor': floor,
                'departure_coordinates_known': distance_known, 'distance_note': 'Road distance estimated from coordinates' if distance_known else 'Unknown departure/destination coordinates: fare floor only; confirm intercity fare',
                'food_style': food_style, 'food_daily_inr': food, 'local_daily_inr': local_daily,
                'local_transit_basis': 'estimated itinerary legs from the stay location' if route_local_total is not None and trip.get('stay_lat') is not None else 'estimated itinerary legs from the destination centre' if route_local_total is not None else 'daily allowance; route coordinates unavailable',
                'child_entry_factor': CHILD_ENTRY_FACTOR, 'senior_entry_factor': SENIOR_ENTRY_FACTOR,
                'legacy_catalogue_usd_to_inr': LEGACY_USD_TO_INR, 'contingency_rate': CONTINGENCY_RATE}}


def apply_itinerary_cost(conn, itinerary):
    trip = dict(conn.execute('SELECT * FROM trips WHERE id=?', (itinerary['trip_id'],)).fetchone())
    activities = [a for day in itinerary['days'] for a in day['activities'] if a.get('status') != 'rejected']
    cost = estimate_cost(trip, activities)
    itinerary.update(total_estimated_cost=cost['total'], cost_breakdown=cost['cost_breakdown'],
                     cost_estimate=cost, assumptions=cost['assumptions'], confidence='indicative')
    # Allocate shared expenses evenly; allocate entry fees on their actual day.
    shared = cost['total'] - cost['cost_breakdown']['activities']['per_party'] * (1 + CONTINGENCY_RATE)
    assigned = 0
    for index, day in enumerate(itinerary['days']):
        day_cost = estimate_cost(trip, [a for a in day['activities'] if a.get('status') != 'rejected'])
        amount = round(shared / len(itinerary['days']) + day_cost['cost_breakdown']['activities']['per_party'] * (1 + CONTINGENCY_RATE), 2)
        if index == len(itinerary['days']) - 1:
            amount = round(cost['total'] - assigned, 2)
        day['total_cost'] = amount
        assigned += amount
    conn.execute('UPDATE itineraries SET total_estimated_cost=? WHERE id=?', (cost['total'], itinerary['id']))
    conn.commit()
    return itinerary


def daily_transit_options(
    total_day_distance_km: float,
    number_of_trips: int,
):
    """Compares 3 daily transit styles: day rental with driver, cab per trip, public transit."""
    from app.core.assumptions import (LOCAL_LEG_RATE_INR as MODE_COST_PER_KM, RENTAL_DAY_INR,
        RENTAL_INCLUDED_KM, RENTAL_EXTRA_KM_INR,CAB_PICKUP_INR,PUBLIC_BOARDING_INR,PUBLIC_CONNECTOR_KM_INR)
    # 1. Day rental with dedicated driver (fixed daily rate + fuel estimate)
    # team assumption, not measured: typical full-day 8hr/80km sedan rental in urban India
    day_rental_cost = RENTAL_DAY_INR + max(0.0, total_day_distance_km - RENTAL_INCLUDED_KM) * RENTAL_EXTRA_KM_INR

    # 2. Point-to-point cabs (base fare + per km per trip)
    cab_cost = number_of_trips * CAB_PICKUP_INR + total_day_distance_km * MODE_COST_PER_KM["cab"]

    # 3. Public transit / auto mix
    public_cost = number_of_trips * PUBLIC_BOARDING_INR + total_day_distance_km * PUBLIC_CONNECTOR_KM_INR

    return {
        "day_rental_with_driver": {
            "style_name": "Full-day Chauffeur / Rental",
            "estimated_cost_inr": whole_inr(day_rental_cost),
            "convenience": "high",
            "description": "Vehicle reserved for the day; no wait times between stops.",
        },
        "cab_per_trip": {
            "style_name": "Point-to-Point Cabs",
            "estimated_cost_inr": whole_inr(cab_cost),
            "convenience": "moderate",
            "description": "Book a cab per leg; wait times depend on local availability.",
        },
        "public_and_auto": {
            "style_name": "Auto-Rickshaw & Public Transit",
            "estimated_cost_inr": whole_inr(public_cost),
            "convenience": "budget",
            "description": "Economical mix of local auto-rickshaws, metro, and short walks.",
        },
    }
