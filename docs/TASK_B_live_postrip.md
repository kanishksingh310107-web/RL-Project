# Person B – During-trip support and post-trip learning
Module id `live`. Completes the lifecycle: pre-trip -> **during** -> **post-trip** -> learning.

## Deliverables (priority order)
1. **Live "Today" view** `GET /api/live/{trip_id}/today?date=YYYY-MM-DD` – the activities of that day from `get_itinerary()`, with next-up activity, simple status (done/skipped/pending) stored in `live_activity_status`. `POST /api/live/{trip_id}/activity/{activity_id}/status`.
2. **Conditions simulator + alerts.** There is no real live feed, so build an explicit, labelled **demo simulator**: `POST /api/live/{trip_id}/simulate` with `{condition: "heavy_rain" | "heat" | "closure" | "strike" | "fatigue", day: N}` creates a condition record (`live_conditions`). Clearly mark everything from it `source: "simulated"`. Optional (only if time): real weather via Open-Meteo, labelled `source: "open-meteo"`.
3. **Rule-based alert engine** that maps conditions + the user's profile to alerts (`live_alerts`): e.g. heavy_rain + outdoor activity -> warn and suggest an indoor alternative. Respect an **alert budget** (max alerts/day, cooldown, severity-first) – "avoid excessive alerts". Also respect the user's preferred response style if present in precision answers (warn / suggest alternative / ask before change).
4. **Replan suggestion** `GET /api/live/{trip_id}/replan?activity_id=...&reason=...` – reuse `get_slot_alternatives` from `app/itinerary_generator.py` (read-only import) and filter by the condition (indoor only for rain, low intensity for fatigue). User confirms -> call the existing feedback logic via `process_activity_feedback` (import from `app/rl_planner.py`) with `modify` and `is_trip_specific=True` so the permanent policy is not polluted by weather. Read how `/api/itinerary/feedback` in `app/api.py` does it and mirror it.
5. **Post-trip feedback** `POST /api/live/{trip_id}/postrip` – per activity rating 1–5 + enjoyed/not, overall rating, "what was missing", "what was irrelevant", "remember this / don't remember" toggles. Table `live_postrip`. Convert to rewards (rating 4–5 = +1, 3 = 0 (no update), 1–2 = -1) and update the LinUCB policy through `process_activity_feedback` (document the mapping). Respect "don't remember" (do not store/learn). Append to `past_trips` is optional.
6. `GET /api/live/{user_id}/learning-summary` – before/after: which arm (category) weights changed after post-trip feedback (use `load_user_policy`), shown as a small table in the UI.
7. UI tab `static/modules/live.js`: Today view, "Simulate condition" dropdown (labelled DEMO), alert list, replan confirm, post-trip form, learning summary.

## Tests (`tests/test_live.py`) – at least
- Simulated heavy rain on a day with outdoor activities -> alert created and alternative is indoor.
- Alert budget caps alerts per day.
- Trip-specific replan does not change permanent policy; post-trip rating does.
- "Don't remember" feedback is not learned.
- Rating->reward mapping unit test.

## Do NOT
Pretend simulated conditions are real data. Do not edit shared files (see CONTRACT.md).
