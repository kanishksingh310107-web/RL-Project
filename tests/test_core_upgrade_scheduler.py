"""Schedule-boundary regression cases for the timed itinerary engine."""
from app.schedule_preferences import schedule_window
from app.services.timed_itinerary import _custom_schedule


def test_flight_terminal_buffer_and_journey_bound_final_activity_window():
    prefs={'activity_start_time':'09:00','bed_time':'22:00','hotel_arrival_time':'08:00',
        'hotel_departure_time':'11:00','free_blocks':[],'final_day_activities':True,
        'transport_departure_time':'18:00','departure_transport_mode':'flight',
        'terminal_journey_minutes':60,'terminal_arrival_buffer_minutes':120}
    start,end=schedule_window(prefs,2,2)
    assert (start,end)==(540,900)


def test_meals_are_not_shifted_into_wrong_windows_when_day_starts_late():
    prefs={'activity_start_time':'15:00','bed_time':'22:00','hotel_arrival_time':'14:00',
        'hotel_departure_time':'11:00','free_blocks':[],'final_day_activities':True,
        'lunch_start_time':'12:00','lunch_end_time':'14:00','lunch_duration_minutes':60,
        'dinner_start_time':'19:00','dinner_end_time':'21:00','dinner_duration_minutes':60,
        'rest_preference':'short'}
    activities=[{'id':'a','name':'Late museum visit','category':'culture_history','duration_minutes':180}]
    day=_custom_schedule(activities,1,'relaxed',prefs)[0]
    meals=[slot for slot in day['slots'] if slot['slot_type']=='meal']
    assert not any(slot['title'].startswith('Lunch') for slot in meals)
    assert not any(slot['start_time']<'15:00' for slot in meals)


def test_repeated_catalogue_place_is_not_scheduled_on_multiple_days():
    prefs={'activity_start_time':'09:00','bed_time':'21:00','hotel_arrival_time':'08:00',
        'hotel_departure_time':'11:00','free_blocks':[],'final_day_activities':True,
        'dinner_start_time':'19:00','dinner_end_time':'21:00','dinner_duration_minutes':45}
    repeated={'id':'same-place','name':'Same place','category':'culture_history','duration_minutes':60}
    days=_custom_schedule([repeated],2,'relaxed',prefs,selected_by_day={1:[repeated],2:[repeated]})
    assert sum(slot.get('activity_id')=='same-place' for day in days for slot in day['slots'])==1
