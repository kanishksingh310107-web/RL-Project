PROJECT: "RL-Based Proactive Travel Guide" - a student project (B.Tech CSE, AI/ML), due tomorrow (3 Nov 2026). It is a FastAPI + SQLite + vanilla-JS web app that personalises travel using a contextual LinUCB bandit (arm = activity category). A teammate built the pre-trip part (profiles, destination recommender, itinerary generator, LinUCB feedback loop). We are three people finishing the remaining parts in parallel, each on our own git branch with our own files, then merging.

SETUP: clone the repo (or I will upload the zip), then `git checkout feat/prep`, `pip install -r requirements.txt -r requirements-dev.txt`, `python -m pytest tests -q` (must pass), `python main.py` -> http://localhost:8000.

READ FIRST, in this order: docs/STATUS.md (what really exists and what is missing), docs/CONTRACT.md (file ownership and rules - follow strictly), then my task file docs/TASK_A_prep.md. Look at app/modules/_template.py, app/modules/common.py, static/modules/loader.js and tests/conftest.py to see how a module plugs in (backend router + init_tables, a UI tab registered with TravelModules.register, pytest fixtures).

HARD RULES:
1. Only create/edit the files listed as mine in CONTRACT.md. Never edit api.py, app.js, index.html, database.py, models.py, rl_planner.py, main.py - import from them read-only.
2. No invented data, results, APIs or screenshots. Anything simulated or estimated must be labelled as such in the API response and in the UI.
3. Keep it simple, beginner-readable Python with short comments - I must be able to explain every line in a viva.
4. Write tests as you go, run them, and show me the real output.
5. Add an "AI assistance and external libraries/APIs used" section to my docs file.
6. Work in small steps: finish deliverable 1, test, commit, then the next. Stop adding features after about 5 hours; after that only polish, screenshots and docs.
7. After each step, explain briefly in plain language what you did.

MY ROLE: Person A - Pre-trip preparation (packing list, weather, documents checklist, reminders with a small bandit). My files: app/modules/prep.py, static/modules/prep.js, tests/test_prep.py, docs/prep.md
MY BRANCH: feat/prep
MY TASK FILE: docs/TASK_A_prep.md

Start by reading the three docs, then summarise back to me in 5 lines what you will build and in what order, then begin with deliverable 1.
