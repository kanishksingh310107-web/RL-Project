# Team Contract & Architecture Specification

**Project:** RL-Based Proactive Travel Guide  
**Architecture:** 3-layer decoupled multi-developer split (FastAPI + SQLite + Vanilla JS + Contextual LinUCB).

---

## 1. File Ownership Matrix

Strict boundary enforcement: **Nobody edits another teammate's files.**

| Teammate | Focus Area | Exclusive File Ownership |
| :--- | :--- | :--- |
| **Person C** (You) | **Foundation, Ranking, Providers, Eval & Reporting** | `app/core/*`<br>`app/providers/*`<br>`app/modules/ranking.py`<br>`static/modules/ranking.js`<br>`scripts/*`<br>`tests/fixtures/*`<br>`tests/test_core*.py`<br>`tests/test_providers*.py`<br>`tests/test_ranking*.py`<br>`docs/team/*`<br>`docs/ranking.md`<br>`docs/evaluation.md`<br>`docs/data_audit.*`<br>`docs/report/*`<br>`ATTRIBUTION.md`<br>`README.md`<br>`STATUS.md`<br>`docs/STATUS.md`<br>`CONTRACT.md`<br>`docs/CONTRACT.md`<br>`run_tests.py`<br>`.env.example`<br>`.gitignore`<br>`requirements*.txt` |
| **Person A** | **Plan Engine & Time Budgeting** | `app/modules/plan.py`<br>`app/planning/*`<br>`static/modules/plan.js`<br>`tests/test_plan*.py`<br>`docs/plan.md` |
| **Person B** | **Stay, Prep, Live & Post-Trip Feedback** | `app/modules/stay.py`<br>`app/modules/prep.py`<br>`app/modules/live.py`<br>`static/modules/stay.js`<br>`static/modules/prep.js`<br>`static/modules/live.js`<br>`tests/test_stay*.py`<br>`tests/test_prep*.py`<br>`tests/test_live*.py`<br>`docs/stay.md`<br>`docs/prep.md`<br>`docs/live.md` |

Shared files (`app/api.py`, `app/database.py`, `static/app.js`, `static/index.html`, etc.) are touched ONLY in Phase 0 initialization or via an explicit mutual Change Request.

---

## 2. Shared Data Stores & Contracts

All communication between Person A, Person B, and Person C occurs strictly through database tables managed in `app/core/stores.py` using Pydantic models defined in `app/core/schemas.py`:

```
                 +-------------------+
                 |    Person C       |
                 | (Core & Provider) |
                 +---------+---------+
                           |
       +-------------------+-------------------+
       |                                       |
       v (Writes preferences/plans)            v (Writes stays/feedback)
+-----------------------+              +-----------------------+
|  core_trip_prefs      |              |  core_stays           |
|  core_plans           |              |  core_trip_feedback   |
|  (Owned by Person A)  |              |  (Owned by Person B)  |
+-----------+-----------+              +-----------+-----------+
            |                                      |
            +------------------+-------------------+
                               |
                               v
                     +-------------------+
                     | Reads across all  |
                     | (Person C Ranking |
                     | & Evaluation)     |
                     +-------------------+
```

- **`core_place_cache`**: Caches geocoding, reverse geocoding, and venue lookups with 7-day TTL.
- **`core_api_usage`**: Tracks daily provider credit usage with hard cutoff at 2,500 calls/day.
- **`core_trip_prefs`**: Trip configuration and timing written by Person A (`TripPrefs`).
- **`core_plans`**: Multi-day generated itineraries with time-budgeted blocks written by Person A (`TripPlan`).
- **`core_stays`**: Hotel / neighborhood stay anchors written by Person B (`Stay`). Person A reads `core_stays` to anchor daily start/end locations.
- **`core_trip_feedback`**: Post-trip ratings (1–5) and category notes written by Person B. Person C reads feedback to personalize destination and activity rankings.

---

## 3. Ground Rules & Invariants

1. **Strict Key Gate:** External keys must only be loaded via `app/core/config.py` from `.env`. Run `python scripts/check_keys.py` to verify key presence. Never print, commit, or send keys in client frontend requests.
2. **Offline Resilience:** All provider functions in `app/providers/` must fail over cleanly to cached data or local seed catalogs (`app/activity_data.py`) whenever network or keys are absent.
3. **No Synthetic/Invented Data in Production:** All numbers must be measured or tagged with provenance (`source`, `fetched_at`, `is_live`, `is_estimate`). Unknown numeric quantities must be `None`, never fake `0.0`.
4. **All Constants in Centralized Assumptions:** Speeds, durations, weights, thresholds, and circuity factors reside exclusively in `app/core/assumptions.py`.
5. **Non-overlapping Test Suites:** Every test suite must run using temporary databases (`tests/conftest.py` fixtures or isolated `tempfile.TemporaryDirectory()`). Tests must NEVER make live external HTTP calls.

---

## AI assistance and external libraries/APIs used

- **AI Tools:** Development and contract formalization was assisted by **Google Antigravity** (architectural synthesis, database schema alignment, contract definitions, and documentation) and **Claude** (contract verification and cross-module boundary auditing).
- **External Libraries & APIs:**
  - `FastAPI` & `Starlette`: REST API router definitions and schema validation.
  - `Pydantic`: Typed data contracts and schema serialization.
  - `SQLite3`: ACID relational backing store for shared tables (`core_plans`, `core_stays`, `core_trip_prefs`, `core_trip_feedback`, `core_place_cache`, `core_api_usage`).

