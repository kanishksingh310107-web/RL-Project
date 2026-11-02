# Verified project status (audit of the latest code, 2 Nov 2026)

Verified by actually running `python run_tests.py` (all pass) and reading the code. Nothing below is assumed.

## Implemented and working
| Area | Where | Notes |
|---|---|---|
| Auth (Google/email/phone/guest) | `app/auth.py` | Google token check is real only if a client ID is configured; chooser/guest are demo paths |
| Basic profile -> 22-dim vector, deep profile -> 41-dim, precision profile -> 126-dim | `app/vectorizer.py`, `app/precision.py` | Questionnaire is adaptive (show_if), privacy filter on server |
| Destination recommender (16 curated destinations; Recommended / Trending / Seasonal) | `app/recommender.py` | Weighted score, explainable. **Trending and Seasonal are hard-coded flags, not live data** |
| Trips, day-by-day itinerary generator | `app/itinerary_generator.py`, `app/activity_data.py` | Curated catalogue, hours/cost/proximity constraints |
| **LinUCB** bandit (the teammate's "LUCB") | `app/rl_planner.py` | Disjoint LinUCB (Li et al. 2010). **Arm = activity category** (7 arms). Context = 24-dim vector built from the user profile + trip + slot + activity. One (A, b) per user per arm in SQLite |
| Feedback loop (accept +1 / reject -1 / modify -0.4 & +1 / implicit +0.2) | `app/api.py` `/itinerary/feedback` | Trip-specific rejections do not change the permanent policy |
| Model Inspector UI, benchmark vs static baseline | `static/app.js`, `app/evaluation.py` | See problem 4 below |

## What is NOT there (do not claim in the demo)
1. **Packing list, weather, document checklist, timed reminders** – no endpoint, no table. The only "reminders" are text rules produced by `precision.derive_insights()` and shown on the profile card.
2. **During-trip support** (today's plan, alerts, replanning) – absent.
3. **Post-trip feedback / preference learning** – absent (only per-activity accept/reject before the trip).
4. **Seasonal / "best right now" ranking with timestamped sources** (handoff section 4) – only static `is_seasonal` flags.
5. **Churn prediction** – absent. Treat as *future work* only.

## Problems found
- **Benchmark shows LinUCB 73.3% acceptance vs static baseline 80.0%.** We cannot claim the RL policy beats the baseline. Needs a proper experiment (more rounds, several seeds/personas, report mean +- std) and an honest write-up either way.
- `ATTRIBUTION.md` says the agent is "Q-learning"; the code is LinUCB. Fix before submission.
- `ATTRIBUTION.md` says "I built ..." but large parts (precision profile, itinerary/LinUCB, tests) were AI-assisted. The instructor expects disclosure. Rewrite honestly.
- `HANDOFF.md` (teammate's) says "100% complete" for everything and has a Windows path; do not reuse its claims in the PPT.
- `run_tests.py` writes to the real `travel_guide.db` (interaction counts keep growing). New tests use `tests/conftest.py` with a temp DB instead.
- All results are from *simulated* users. There is no real interaction dataset. Say so.

## Architecture for the 3-way split
`app/modules/<id>.py` (backend, auto-loaded) + `static/modules/<id>.js` (UI tab in the "Companion" button) + `tests/test_<id>.py` + `docs/<id>.md`.
Nobody edits `api.py`, `app.js`, `index.html`, `database.py`, `models.py`, `rl_planner.py`.
