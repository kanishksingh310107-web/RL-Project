# Handoff: Karan, backend API, database, test suites
Read `FIX_PLAN.md` first (scope, rules, file ownership, git steps). Branch: `karan/audit-fixes`. You own `app/api.py`, `app/database.py`, `run_tests.py`, `tests/*` (except RL/evaluation tests).

## Git workflow (do this FIRST, before any fix)
1. **Pull the latest `main`:** `git checkout main && git pull origin main` (Step 0 is already done: `main` has the audit report, your handoff in `docs/fix_plan/`, the bug logs and the `.gitignore` update).
2. **Create your own branch from it:** `git checkout -b karan/audit-fixes`
3. **Fix the issues below on that branch only.** One commit per finding, e.g. `F-010: fix profile payload in run_tests`.
4. **Push after every fix, not only at the end:** `git push -u origin karan/audit-fixes` (the `-u` is needed only the first time; later just `git push`).
5. If `main` gets new commits while you work, bring them in with `git fetch origin && git merge origin/main`, fix any conflict, run the tests, then push.
6. Do **not** merge into `main` yourself. Kanishk merges all branches at the end, so your job ends with a pushed branch.

## Tasks
**1. F-010 `run_tests.py` crashes at line 81 (S).** The profile call (around line 76) sends a payload without the now-mandatory `travel_goals` and `place_interests`, so the endpoint returns 422 and `assert p_res.status_code == 200` fails.
Add valid values (use options returned by `/api/config/questionnaire` rather than guessing ids), then keep running: later blocks may fail for the same reason. Done when `python run_tests.py` exits 0. Do not delete or loosen assertions.
The audit also counted 35 informational prints next to 141 asserts; leave them unless a print hides a real check.

**2. F-004 destination is validated after the user lookup (S).** `create_trip` returns 404 "User not found" for an international destination sent with a non-existent user; the intended rule (India-only destinations) should return 400 first.
Move the destination check before the user check. Done when `tests/test_trip_india_validation.py::test_international_destination_rejection` passes and valid trips still work.

**3. F-015 two registry tests fail (M).** `tests/test_places_api.py::test_places_module_registered` and `tests/test_ranking.py::test_module_registered` expect `places` and `ranking` in `GET /api/modules`, which deliberately excludes them
(standalone tabs are hidden). Read `app/modules/__init__.py` to confirm the intent (it belongs to Atharva, do not edit it). Change the tests to check the module registry directly (or that the routes respond) instead of the public list.
Done when `python -m pytest tests/test_places_api.py tests/test_ranking.py -q` passes. Use `-k` while working; the full suite takes about 3.5 minutes.

**4. F-002 foreign keys are off (S, time-box 30 min).** In the connection factory in `app/database.py` run `PRAGMA foreign_keys = ON` on every connection. Then run both test runners. If tests fail because they insert rows whose parent does not exist,
fix the test data; if the app itself breaks, revert the change and write the reason in `docs/bugs/karan.md`. Done when both runners are green with the pragma on, or it is reverted with a note.

**5. Click-through of your area (3 units).** Create a trip (every field; India-only destination dropdown; invalid dates; end before start), generate itinerary, Accept, Reject (every reason), Modify with an alternative, Regenerate (accepted items kept?),
trip list, reload the page and check the itinerary is still there, two users on one browser (log out/in). Check API errors are clear JSON, not stack traces. At 1366 and 360 px. Bugs in `api.py` or `database.py` are yours; bugs in `static/*` go to Kanishk, in `app/modules/*`, `itinerary_generator.py` or `rl_planner.py` to Atharva (log them in `docs/bugs/karan.md` and message them).

## Done when
`python run_tests.py` exits 0, the three registry/destination pytest failures pass, the full `python -m pytest tests/ -q` is green (or any remaining failure is explained in your bug file), branch pushed.
