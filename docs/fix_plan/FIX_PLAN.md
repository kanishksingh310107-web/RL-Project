# Fix plan after the audit (functional problems only)

Source: `AUDIT_REPORT.md` (17 findings). Scope decision: **no security or deployment work** (auth, passwords, OTP, IDOR, XSS/innerHTML,
SQL-string style, CDN bundling). Only things that stop the project from working, mislead the user, or make the demo or tests fail.

## What is dropped and why
| Finding | Why dropped |
|---|---|
| F-001 IDOR / no tokens, F-012 plaintext passwords, F-013 fixed OTP, F-003 SQL f-string, F-006 innerHTML | Security. Out of scope for now |
| F-007 CDN needed offline | Deployment concern. Mitigation for demo day: record a backup video, use a stable connection |
| F-011 negative/security tests | Nice to have. Only the validation checks inside the fixes below are required |

## Two corrections to the audit itself (verified by re-running its own script)
1. **Section 3 "Not Connected" table is wrong.** The audit compared route paths like `/api/trips/{user_id}` with JS strings like `` `/api/trips/${id}` ``
   by plain substring, so nearly every parameterised route was marked "Not Connected" (recommendations, shortlist, trips, itinerary, feedback,
   policy are all called in `app.js`). It also only printed the first 40 of 74 routes and scanned **only `static/app.js`**. Re-matched properly,
   27 routes are connected and 47 have no match in `app.js`; most of those are module routes (`live`, `prep`, `places`, `trip-actions`, `ranking`)
   whose UI may live in other JS files that were not scanned. Task K-4 re-checks this across all of `static/`.
2. **The browser coverage stopped early.** The audit's browser run ends at the dashboard/recommendations screen (11 screenshots). Trip creation,
   itinerary, Accept/Reject/Modify, Model Inspector, preparation, live trip, places and trip actions were **never clicked**, and the first
   browser run crashed at the onboarding climate chips (`#basicClimateGrid button` "not visible", 30 s timeout), which may be a real UI bug. So
   "17 findings" is a floor, not the full list. Each person below has a click-through task for their area.

## What is kept (functional)
| ID | Problem | Effort | Owner |
|---|---|---|---|
| F-005 | `saveGoogleClientId()` referenced in `index.html` but not defined: ReferenceError on the Google config "Save & Enable" button | S | Kanishk |
| F-014 | 422 validation errors show `Error: [object Object],...`; probably the same pattern elsewhere | S | Kanishk |
| F-008 | Modals cannot be closed with Esc | S | Kanishk |
| K-4 | Re-check frontend/backend connections across all of `static/`, list real orphans | M | Kanishk |
| F-010 | `run_tests.py` crashes at line 81 (profile payload lacks `travel_goals`, `place_interests`) | S | Karan |
| F-015 | 3 pytest failures (2 module-registry tests, 1 destination test) | M | Karan |
| F-004 | Destination checked after user lookup: 404 instead of 400 | S | Karan |
| F-002 | SQLite foreign keys are OFF (orphan rows). Time-boxed, revert if it breaks tests | S | Karan |
| F-016 | Over 100 seeds the static baseline beats LinUCB (cumulative reward 11.90 vs 9.18). Fix the evaluation honestly | M | Atharva |
| F-017 | Docstring claims Sherman-Morrison, code does `np.linalg.inv` | S | Atharva |
| F-009 | "100% complete" claims in docs | S | Atharva |
| Click-throughs | Each person clicks their whole area and logs bugs | 3 units each | all |

Rough load (S = 1, M = 2-3 units): Kanishk about 8, Karan about 9, Atharva about 9.

## File ownership (nobody edits files owned by someone else)
- **Kanishk:** `static/*` (app.js, index.html, style.css and any other front-end files), `.gitignore`
- **Karan:** `app/api.py`, `app/database.py`, `run_tests.py`, `tests/*` (except the RL/evaluation tests)
- **Atharva:** `app/rl_planner.py`, `app/evaluation.py`, `app/itinerary_generator.py`, `app/modules/*`, `app/services/*`, `README.md`, `HANDOFF.md`, `ATTRIBUTION.md`, RL/evaluation tests
- A bug found in someone else's file goes into **your own** `docs/bugs/<yourname>.md` with file:line, steps and expected/actual, then message the owner. (Separate files per person, so there are no merge conflicts.)

## Step 0: DONE (by Kanishk)
`main` already contains: this plan and the three handoffs in `docs/fix_plan/`, `docs/AUDIT_REPORT.md`, empty bug logs `docs/bugs/kanishk.md`, `karan.md`, `atharva.md`,
and `.gitignore` now ignores `AUDIT_EVIDENCE/`. Snapshot of the pre-fix code: tag `pre-audit-baseline`, branch `backup/pre-audit-fixes`.
Everyone starts here: `git checkout main && git pull origin main && git checkout -b <name>/audit-fixes`.

## Workflow in one line
Everyone: **pull latest `main` -> create `<name>/audit-fixes` -> fix -> push the branch (after each fix)**. Nobody merges into `main`; Kanishk merges all three at the end.

## Working rules
1. First **reproduce** each finding. If you cannot, write that in your bug file and skip it. The audit can be wrong.
2. One commit per finding: `F-005: define saveGoogleClientId`. Push after each one: `git push -u origin <name>/audit-fixes`.
3. Before every push: `python run_tests.py` must pass. Full `python -m pytest tests/ -q` (about 3.5 minutes) before the final push; use `-k` for quick checks.
4. Never weaken or delete an assertion to make a test pass. Fix the cause or ask.
5. Do not claim anything in docs or slides that you did not verify by running it.

## Merge order and final checks (Kanishk merges via pull requests)
Karan -> Kanishk -> Atharva. After each merge: `python run_tests.py && python -m pytest tests/ -q`, then start the app and open it once.
When all three are in, tag: `git tag -a post-audit-fixes -m "After audit fixes" && git push origin post-audit-fixes`.
To undo everything: `git checkout pre-audit-baseline`.

## Optional now: second audit for the flows the first one never reached
Paste into Antigravity (read-only, writes `AUDIT_REPORT_2.md`, evidence in an ignored folder). Run it on `main` while people fix, and add its findings to the plan.
```
Read-only audit, same rules as before (do not edit code; every finding needs evidence; mark VERIFIED/SUSPECTED). The previous audit never got past the dashboard. Using a browser, fresh database, and a fully profiled user, test ONLY these flows end to end at 1366px and 360px, and keep going after the first problem instead of stopping: (1) recommendations: Refresh, shortlist/unshortlist, open card details; (2) create a trip (India destinations), every field and invalid dates; (3) generate an itinerary, then Accept, Reject with each reason, Modify with an alternative, Regenerate, reload the page and check state is preserved; (4) Model Inspector tabs and the benchmark button; (5) trip preparation: weather, packing, documents, reminders and reminder feedback; (6) live trip: start, today view, simulate, alerts and dismiss, replan, complete, post-trip; (7) places search, attractions, popular, plan-trip; (8) trip actions: finalize, swap, delete activity, reschedule, switch days; (9) ranking. For each screen record: buttons that do nothing, console errors, failed network calls, wrong or empty data, confusing steps, anything that loses input or breaks when pressing Back or refreshing. Also list every route in app/ that no file under static/ calls (search ALL files in static/, not only app.js, and match parameterised paths properly). Write AUDIT_REPORT_2.md in the same findings format.
```
