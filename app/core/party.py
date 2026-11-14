"""Canonical party composition, including compatibility with saved trips."""
import json


def party_type(party):
    if party['children'] or party['seniors']:
        return 'family'
    return {1: 'solo', 2: 'partner'}.get(party['adults'], 'friends')


def trip_type(trip, party=None):
    """Canonical relationship type, preserving explicit adult-only family."""
    explicit = trip.get('trip_type')
    if explicit in ('solo', 'couple', 'friends', 'family'):
        return explicit
    companion = (trip.get('companions') or '').strip().lower()
    aliases = {'partner': 'couple', 'couple': 'couple', 'alone': 'solo',
               'solo': 'solo', 'friends': 'friends', 'family': 'family',
               'family_with_children': 'family', 'family_with_elders': 'family'}
    if companion in aliases:
        return aliases[companion]
    party = party or normalize_party(trip)
    if party['children'] or party['seniors']:
        return 'family'
    if party['adults'] == 1:
        return 'solo'
    if party['adults'] == 2:
        return 'couple'
    return 'friends'


def normalize_party(trip):
    prefs = trip.get('trip_preferences') or trip.get('trip_preferences_json') or {}
    if isinstance(prefs, str):
        prefs = json.loads(prefs)
    party = trip.get('party') or prefs.get('party')
    if hasattr(party, 'model_dump'):
        party = party.model_dump()
    if not party:
        total = max(1, int(trip.get('travellers_count') or 1))
        children = int(bool(trip.get('has_children')) and total > 1)
        seniors = int(bool(trip.get('has_elderly')) and total - children > 1)
        party = dict(adults=total - children - seniors, children=children, seniors=seniors)
    party = {key: int(party.get(key, 0)) for key in ('adults', 'children', 'seniors')}
    if party['adults'] < 1 or min(party.values()) < 0:
        raise ValueError('Party requires at least one adult; counts cannot be negative.')
    return party


def party_label(party):
    if sum(party.values()) == 1:
        return 'Solo'
    return ' - '.join(f"{n} {singular if n == 1 else plural}" for key, singular, plural in
                      [('adults', 'adult', 'adults'), ('children', 'child', 'children'),
                       ('seniors', 'senior', 'seniors')] if (n := party[key]))
