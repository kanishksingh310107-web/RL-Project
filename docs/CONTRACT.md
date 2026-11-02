# Team contract (read before touching anything)

## Branches and ownership
| Person | Branch | You own ONLY these files |
|---|---|---|
| A – Pre-trip prep | `feat/prep` | `app/modules/prep.py`, `static/modules/prep.js`, `tests/test_prep.py`, `docs/prep.md` |
| B – Live trip + post-trip | `feat/live` | `app/modules/live.py`, `static/modules/live.js`, `tests/test_live.py`, `docs/live.md` |
| C – Ranking + evaluation + report/PPT | `feat/ranking-eval` | `app/modules/ranking.py`, `static/modules/ranking.js`, `tests/test_ranking.py`, `scripts/evaluate.py`, `docs/ranking.md`, `docs/evaluation.md`, `docs/report/*`, `ATTRIBUTION.md`, `README.md` |

Because file sets do not overlap, `git merge` of the three branches into `main` should have **zero conflicts**.

## Rules
1. Do not edit shared files: `app/api.py`, `app/database.py`, `app/models.py`, `app/rl_planner.py`, `app/recommender.py`, `app/itinerary_generator.py`, `static/app.js`, `static/index.html`, `main.py`. Import from them (read-only) instead. If you find a real bug in one, message the group and C makes the fix on `main` once.
2. Your tables are created in your module's `init_tables(conn)`, prefixed with your id (`prep_*`, `live_*`, `ranking_*`).
3. Pydantic request models live inside your module file.
4. Use the helpers in `app/modules/common.py` (`get_trip`, `get_user_context`, `get_itinerary`).
5. Tests use the `client`, `demo_user`, `demo_trip` fixtures (`tests/conftest.py`, temp DB). Run: `python -m pytest tests -q`.
6. Every number you show in the UI or docs must come from code you ran. No invented data, no invented API results. If an external API is used, it must have an offline fallback clearly labelled "offline estimate".
7. Disclose AI help: add a short section in your `docs/<id>.md`: "AI assistance and external libraries/APIs used".
8. Do not print/claim a feature is done in docs unless a test covers it.
9. Commit small, push often: `git pull --rebase origin main` before pushing.
10. Docs file format (C compiles these into the PPT/report): sections *What it does*, *How it works (method)*, *Files*, *Test table* (case / input / expected / actual / pass), *Limitations*, *Screenshots to take*, *AI assistance*.

## Time plan (deadline: 3 Nov)
- T+0 to T+3h: working backend endpoint + one passing test.
- T+3h to T+5h: UI tab + docs file.
- T+5h: push, tell C. C merges all three into `main`, runs `python -m pytest tests -q` and `python run_tests.py`, takes screenshots, finalises PPT.
- Stop adding features at T+5h. Polish and screenshots only.

## Merge procedure (C does this)
```
git checkout main && git pull
git merge --no-ff feat/prep
git merge --no-ff feat/live
git merge --no-ff feat/ranking-eval
python -m pytest tests -q && python run_tests.py
```
