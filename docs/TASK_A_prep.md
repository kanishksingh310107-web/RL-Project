# Person A – Pre-trip preparation: packing, weather, documents, reminders
Module id `prep`. Closes the biggest gap vs the project idea (the "Scotland coat" example).

## Deliverables (priority order)
1. `GET /api/prep/{trip_id}/weather` – forecast/climate summary for the trip dates. Use **Open-Meteo** (free, no API key) via `httpx`, with a **clearly labelled offline fallback** (monthly climate table you write for the 16 destinations; lat/lon dict for each destination you add in your module). Return `source: "open-meteo" | "offline-estimate"` and `fetched_at`.
2. `GET /api/prep/{trip_id}/packing` – packing list built by transparent rules from: weather (temp, wind, rain), trip length, activities in the itinerary (hiking -> boots, etc.), the user's cold/heat sensitivity and packing preferences from `get_user_context()` (precision answers: carry-on only, allergens, medication...). Each item has `reason` (why it is on the list) and `category`. Cold-wind user + windy destination must add a windproof layer.
3. `GET /api/prep/{trip_id}/documents` – checklist: passport validity, visa/entry (generic: "check official source" – do NOT invent visa rules; only a small hand-written table of well-known facts, labelled with a "verify on the official site" note), insurance, tickets, adapters, SIM/eSIM, currency, medication-in-cabin.
4. Reminder schedule: table `prep_reminders` (trip_id, text, category, due_date = start_date minus N days, status pending/done/dismissed, shown_count). Endpoints: `POST /api/prep/{trip_id}/reminders/generate`, `GET .../reminders`, `POST .../reminders/{id}/feedback` with `useful | not_useful | done`.
5. **RL part (keep small and honest):** a per-user, per-reminder-category bandit (Thompson sampling with Beta priors, or reuse `LinUCBPolicy`) that learns which reminder categories this user finds useful and orders/limits them (alert-budget cap, e.g. max N shown per day). Reward: `useful`/`done` = +1, `not_useful` = -1 (dismiss without feedback = weak 0). Persist in `prep_bandit`.
6. UI tab `static/modules/prep.js`: weather card (with source label), packing list grouped by category with reasons and tick boxes, documents checklist, reminders with a 👍/👎 on each.

## Tests (`tests/test_prep.py`) – at least
- Packing list for cold+windy trip contains a windproof/insulating layer; hot trip does not.
- Same trip, user with "carry-on only" gets a shorter list with liquids reminder.
- Offline fallback works when network is unavailable (monkeypatch the HTTP call to raise).
- Reminder due dates are correct relative to `start_date`.
- Feedback changes the bandit state and changes ordering after enough feedback (seeded random).

## Do NOT
Invent visa rules, medical advice, or forecast data. Do not edit shared files (see CONTRACT.md).
