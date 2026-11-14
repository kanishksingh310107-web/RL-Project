"""Validation and normalization for Person B's per-trip schedule preferences."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _minute(value: str) -> int:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("Use a valid 24-hour time in HH:MM format.")
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError("Use a valid 24-hour time in HH:MM format.") from exc
    if parsed.strftime("%H:%M") != value:
        raise ValueError("Use a valid 24-hour time in HH:MM format.")
    return parsed.hour * 60 + parsed.minute


class FreeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    day: Optional[int] = Field(default=None, ge=1)
    start: str
    end: str
    label: str = Field(min_length=1, max_length=60)

    @field_validator("start", "end")
    @classmethod
    def valid_time(cls, value: str) -> str:
        _minute(value)
        return value

    @field_validator("label")
    @classmethod
    def nonblank_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Label cannot be empty.")
        return value.strip()

    @model_validator(mode="after")
    def valid_span(self):
        start, end = _minute(self.start), _minute(self.end)
        if end == start:
            raise ValueError("Free block start and end must be different.")
        if end < start:
            end += 1440
        if end - start > 1440:
            raise ValueError("A free block cannot exceed 24 hours.")
        return self


class SchedulePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    hotel_arrival_time: str = "14:00"
    hotel_departure_time: str = "11:00"
    wake_time: str = "07:00"
    bed_time: str = "21:00"
    activity_start_time: str = "09:00"
    free_blocks: List[FreeBlock] = Field(default_factory=list, max_length=10)

    @field_validator("hotel_arrival_time", "hotel_departure_time", "wake_time", "bed_time", "activity_start_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        _minute(value)
        return value

    @model_validator(mode="after")
    def valid_window_and_blocks(self):
        start = _minute(self.activity_start_time)
        if _minute(self.wake_time) > start:
            raise ValueError('Activity start time must be at or after wake time.')
        bed = _minute(self.bed_time)
        if bed <= start:
            bed += 1440
        if bed - start < 60:
            raise ValueError("The activity window must allow at least 60 minutes for one activity.")
        if bed - start > 18 * 60:
            raise ValueError("The daily activity window cannot exceed 18 hours.")
        ordered = []
        for block in self.free_blocks:
            bs, be = _minute(block.start), _minute(block.end)
            if be == bs:
                raise ValueError("Free block start and end must be different.")
            if be < bs:
                be += 1440
            # Times after midnight are interpreted relative to the activity start.
            while bs < start:
                bs += 1440
                be += 1440
            if bs < start or be > bed:
                raise ValueError("Free blocks must fall inside the daily activity window.")
            ordered.append((block.day, bs, be))
        for index, (day_a, start_a, end_a) in enumerate(ordered):
            for day_b, start_b, end_b in ordered[index + 1:]:
                if (day_a is None or day_b is None or day_a == day_b) and start_a < end_b and start_b < end_a:
                    raise ValueError("Free time blocks cannot overlap.")
        return self


DEFAULT_SCHEDULE_PREFS = {
    "hotel_arrival_time": "14:00", "hotel_departure_time": "11:00",
    "wake_time": "07:00", "bed_time": "21:00", "activity_start_time": "09:00",
    "free_blocks": [],
}
LEGACY_SCHEDULE_PREFS = {
    "hotel_arrival_time": "14:00", "hotel_departure_time": "11:00",
    "wake_time": "07:00", "bed_time": "21:00", "activity_start_time": "09:00",
    "free_blocks": [], "legacy_defaults": True,
}


def normalize_schedule_preferences(value: Optional[Dict[str, Any]], duration_days: int,
                                    start_date: Optional[str] = None, end_date: Optional[str] = None,
                                    same_day: bool = False) -> Dict[str, Any]:
    custom = value is not None and not value.get('legacy_defaults', False)
    raw = dict(value or DEFAULT_SCHEDULE_PREFS)
    raw.pop("legacy_defaults", None)
    prefs = SchedulePreferences.model_validate(raw).model_dump()
    if len(prefs["free_blocks"]) > 10:
        raise ValueError("No more than 10 free time blocks are allowed.")
    for block in prefs["free_blocks"]:
        day = block.get("day")
        if day is not None and not 1 <= day <= duration_days:
            raise ValueError("Free block day must be within the trip dates.")
    start = _minute(prefs["activity_start_time"])
    bed = _minute(prefs["bed_time"])
    if bed <= start:
        bed += 1440
    if bed - start > 18 * 60:
        raise ValueError("The daily activity window cannot exceed 18 hours.")
    for day_num in range(1, duration_days + 1):
        window_start, window_end = schedule_window(prefs, day_num, duration_days, custom)
        occupied = []
        for block in prefs["free_blocks"]:
            if block.get("day") not in (None, day_num):
                continue
            bs, be = _minute(block["start"]), _minute(block["end"])
            if be <= bs:
                be += 1440
            while bs < start:
                bs += 1440
                be += 1440
            if bs < window_end and be > window_start:
                occupied.append((max(window_start, bs), min(window_end, be)))
        occupied.sort()
        cursor = window_start
        largest_gap = 0
        for bs, be in occupied:
            largest_gap = max(largest_gap, bs - cursor)
            cursor = max(cursor, be)
        largest_gap = max(largest_gap, window_end - cursor)
        if largest_gap < 60:
            raise ValueError(f"Hotel buffers and free blocks on day {day_num} leave no 60-minute activity window.")
    if same_day and _minute(prefs["hotel_arrival_time"]) >= _minute(prefs["hotel_departure_time"]):
        raise ValueError("Hotel arrival must be before hotel departure on a same-day trip.")
    if same_day:
        first_activity = max(start, _minute(prefs["hotel_arrival_time"]) + 60)
        last_activity_end = _minute(prefs["hotel_departure_time"]) - 60
        if last_activity_end - first_activity < 60:
            raise ValueError("Hotel departure must leave at least one 60-minute activity after the transfer buffers.")
    if start_date and end_date and date.fromisoformat(end_date) < date.fromisoformat(start_date):
        raise ValueError("End date must be on or after start date.")
    return prefs


def minute_of_day(value: str) -> int:
    return _minute(value)


def schedule_window(prefs, day, total_days, custom=True):
    start = _minute(prefs['activity_start_time'])
    end = _minute(prefs['bed_time'])
    overnight = end <= start
    if overnight:
        end += 1440
    if custom and day == 1:
        start = max(start, _minute(prefs['hotel_arrival_time']) + 60)
        if prefs.get('destination_arrival_time'):
            arrival = _minute(prefs['destination_arrival_time']) + int(prefs.get('arrival_journey_minutes',45))
            start = max(start, arrival)
    if custom and day == total_days:
        if prefs.get('final_day_activities') is False:
            return start, start
        if prefs.get('transport_departure_time'):
            departure = _minute(prefs['transport_departure_time'])
            buffer = (int(prefs.get('terminal_arrival_buffer_minutes',120))
                      if prefs.get('departure_transport_mode') == 'flight' else
                      int(prefs.get('station_arrival_buffer_minutes',45))
                      if prefs.get('departure_transport_mode') == 'train' else 30)
            end = min(end, departure - int(prefs.get('terminal_journey_minutes',0)) - buffer)
        elif not prefs.get('final_day_activities'):
            departure = _minute(prefs['hotel_departure_time'])
            if overnight and departure <= _minute(prefs['bed_time']):
                departure += 1440
            end = min(end, departure - 60)
    return start, end
