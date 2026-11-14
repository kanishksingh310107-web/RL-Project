"""Redistribute existing proposed occurrences without replacing protected stops."""
import json

from app.schedule_preferences import LEGACY_SCHEDULE_PREFS, schedule_window
from app.services.timed_itinerary import _custom_schedule


def rebalance_days(conn, trip_id):
    trip=dict(conn.execute('SELECT * FROM trips WHERE id=?',(trip_id,)).fetchone())
    prefs=dict(LEGACY_SCHEDULE_PREFS)
    row=conn.execute('SELECT * FROM trip_schedule_prefs WHERE trip_id=?',(trip_id,)).fetchone()
    if row:
        prefs.update(dict(row));prefs['free_blocks']=json.loads(row['free_blocks_json'] or '[]')
    prefs.update(json.loads(trip.get('trip_preferences_json') or '{}'))
    if prefs.get('hotel_checkin_time'):prefs['hotel_arrival_time']=prefs['hotel_checkin_time']
    if prefs.get('hotel_checkout_time'):prefs['hotel_departure_time']=prefs['hotel_checkout_time']
    days=int(trip['duration_days']);pace=trip.get('travel_pace') or 'balanced'
    rows=[dict(r) for r in conn.execute('''SELECT ia.*,da.opening_time,da.closing_time FROM itinerary_activities ia
        JOIN itineraries i ON i.id=ia.itinerary_id LEFT JOIN destination_activities da ON da.id=ia.activity_id
        WHERE i.trip_id=? AND ia.status!='rejected' ORDER BY ia.day_number,ia.order_index,ia.id''',(trip_id,))]
    def protected(r):
        return r['status']!='proposed' or r.get('is_fixed_booking') or r.get('is_pinned') or r.get('must_visit') or r.get('planning_priority')=='must_do'
    groups={d:[dict(r,id=r['activity_id'],occurrence_id=r['id'],name=r['title']) for r in rows if r['day_number']==d and protected(r)] for d in range(1,days+1)}
    for row in sorted((r for r in rows if not protected(r)),key=lambda r:(-int(r['duration_minutes'] or 0),r['order_index'],r['id'])):
        candidate=dict(row,id=row['activity_id'],occurrence_id=row['id'],name=row['title'])
        choices=sorted(groups,key=lambda d:(len(groups[d]),sum(int(a['duration_minutes'] or 0) for a in groups[d]),d))
        placed=False
        for day in choices:
            start,end=schedule_window(prefs,day,days)
            if end<=start:continue
            from app.providers.geo import haversine_distance_km
            if candidate.get('latitude') is not None and candidate.get('longitude') is not None and any(a.get('latitude') is not None and a.get('longitude') is not None and
                haversine_distance_km(candidate['latitude'],candidate['longitude'],a['latitude'],a['longitude'])>12 for a in groups[day]):continue
            tentative=groups[day]+[candidate]
            schedule=_custom_schedule([],days,pace,prefs,{day:tentative})[day-1]
            scheduled={s['activity_id'] for s in schedule['slots'] if s['slot_type'] in ('activity','shopping')}
            if all(a['id'] in scheduled for a in tentative):
                groups[day].append(candidate);placed=True;break
        if not placed:groups[row['day_number']].append(candidate)
    for day,activities in groups.items():
        for index,activity in enumerate(activities):
            conn.execute('UPDATE itinerary_activities SET day_number=?,order_index=? WHERE id=?',(day,index,activity['occurrence_id']))
