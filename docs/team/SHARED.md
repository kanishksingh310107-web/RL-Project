# SHARED TEAM GUIDELINES: RL-Based Proactive Travel Guide

FastAPI + SQLite + vanilla-JS app, contextual LinUCB bandit (arm = activity category).
Three people work in parallel, one AI coding agent each.
Editing is strictly restricted to each team member's assigned file list (Section 5).
Correctness and honesty come first.

---

## 0. Behavioral Ground Rules
1. **Work on ONE numbered mini-task at a time, in order.** After each: run tests, show REAL output, git commit, explain in plain language what was done, then continue to the next.
2. **STOP-AND-ASK RULE.** If a task needs an API key or credential, an account, a package install, a file outside your list, a decision not in notes, or network access that fails: STOP and ask. Never skip silently, never fake results, never invent placeholder data.
3. **KEY GATE.** At the start of every session run `python scripts/check_keys.py`. It prints only "set / not set" per key, never the value.
4. **NO INVENTED DATA.** Every number shown in UI/API/docs must come from code that ran. Anything static, simulated, estimated or assumed must be labelled (fields: source, fetched_at, is_live, is_estimate). Unknown means `None` / "not available", NEVER zero or a made-up value.
5. **Centralized Assumptions:** All numeric assumptions (speeds, durations, budget shares, weights, thresholds) live in `app/core/assumptions.py`, each with a one-line note and the label "team assumption, not measured". Never scatter magic numbers.
6. **Code Style:** Beginner-readable Python (undergraduate ML/RL level), short comments, small functions. Must be explainable in a viva.
7. **Tests:** pytest, temp DB (`tests/conftest.py` fixtures). NO test may call the real network: mock HTTP functions. Do not claim a feature in docs unless a test covers it.
8. **Disclosure:** Every docs file you own ends with a section "AI assistance and external libraries/APIs used".
9. **Verify before rely:** Check Geoapify and Open-Meteo documentation for exact endpoint names, parameters, categories, and response fields.
10. **Privacy:** Send external services ONLY place text and coordinates. Never user ids, names, emails, health, allergy, or profile data.

---

## 1. External Keys and Services
- **Geoapify** (REQUIRED for live places, geocoding, accommodation): Free tier, 3,000 credits/day. Attribution required: "Powered by Geoapify | © OpenStreetMap contributors". Key in `.env` (`GEOAPIFY_API_KEY`). Daily credit guard stops live calls at 2,500/day.
- **Open-Meteo** (Weather forecast + historical climate): NO key needed. Free fair use under 10,000 calls/day. Attribution: "Weather data by Open-Meteo.com" (CC BY 4.0).
- **No hotel price API exists for free:** NEVER show hotel prices; only show budget bands and external search links.

---

## 2. Core Architecture
- **DATA (What exists):** `app/providers/` (Geoapify, Open-Meteo, cache, credit guard, offline catalogue fallback).
- **RECOMMEND (What to suggest):** LinUCB per category (7 arms) + destination ranking.
- **SCHEDULE (How it fits):** Rule-based time-budget scheduler, transport modes, meals, shopping, budget, stay anchor. (This is rule-based, NOT RL; stated clearly in docs).
- Safety fields = hard filters; comfort fields = score penalties; taste fields = LinUCB features.
- Live venues: show "cannot verify, check with the venue" for diet/allergens, never "safe".

---

## 3. Contracts and Data Flow
- `app/core/config.py` (reads env/.env), `app/core/assumptions.py`, `app/core/schemas.py`, `app/core/profile.py`, `app/core/stores.py`, `app/providers/*`.
- **Data flow:**
  - Person A WRITES `core_trip_prefs` and `core_plans`.
  - Person B WRITES `core_stays` and `core_trip_feedback`.
  - Person C reads all.
  - A reads `core_stays` (stay anchor).
  - Nobody imports another person's module code.
  - Nobody edits another person's files.
- **Module IDs and Tabs:**
  - `ranking` (Person C)
  - `plan` (Person A)
  - `stay` (Person B)
  - `prep` (Person B)
  - `live` (Person B)

---

## 4. File Ownership
- **Person C:** `app/core/*`, `app/providers/*`, `app/modules/ranking.py`, `static/modules/ranking.js`, `scripts/*`, `tests/fixtures/*`, `tests/test_core*.py`, `tests/test_providers*.py`, `tests/test_ranking*.py`, `docs/team/*`, `docs/ranking.md`, `docs/evaluation.md`, `docs/data_audit.*`, `docs/report/*`, `ATTRIBUTION.md`, `README.md`, `STATUS.md`, `CONTRACT.md`, `run_tests.py`, `.env.example`, `.gitignore`, `requirements*.txt`.
- **Person A:** `app/modules/plan.py`, `app/planning/*`, `static/modules/plan.js`, `tests/test_plan*.py`, `docs/plan.md`.
- **Person B:** `app/modules/stay.py`, `app/modules/prep.py`, `app/modules/live.py`, `app/stay/*`, `app/prep/*`, `app/live/*`, `static/modules/{stay,prep,live}.js`, `tests/test_stay*.py`, `tests/test_prep*.py`, `tests/test_live*.py`, `docs/{stay,prep,live}.md`.
- **Read-only for everyone:** `rl_planner.py`, `recommender.py`, `activity_data.py`, `itinerary_generator.py`, `models.py`, `api.py`, `app/modules/common.py`.

---

## AI assistance and external libraries/APIs used
- Created collaboratively by team members following project specifications.
