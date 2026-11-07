# Handoff: Kanishk, front end (static/*), connection check, auth/profile click-through
Read `FIX_PLAN.md` first (scope, rules, file ownership, git steps). Branch: `kanishk/audit-fixes`. You own `static/*` and `.gitignore`.

## Git workflow (do this FIRST, before any fix)
1. **Pull the latest `main`:** `git checkout main && git pull origin main` (Step 0 is already done: `main` has the audit report, your handoff in `docs/fix_plan/`, the bug logs and the `.gitignore` update).
2. **Create your own branch from it:** `git checkout -b kanishk/audit-fixes`
3. **Fix the issues below on that branch only.** One commit per finding, e.g. `F-005: define saveGoogleClientId`.
4. **Push after every fix, not only at the end:** `git push -u origin kanishk/audit-fixes` (the `-u` is needed only the first time; later just `git push`).
5. If `main` gets new commits while you work, bring them in with `git fetch origin && git merge origin/main`, fix any conflict, run the tests, then push.
6. You are also the one who merges all three branches at the end (see the merge order in `FIX_PLAN.md`), so keep your own branch up to date too.

## Tasks
**1. F-005 `saveGoogleClientId` is not defined (S).** `index.html` has a Google config modal (`#googleConfigModal`) whose "Save & Enable" button calls
`saveGoogleClientId()`; the function does not exist in `app.js`. Reproduce (click it, read the console). Fix by defining the function: read the input, `POST /api/config/google`
(the route exists), close the modal, show a short success or error message (not an `alert` of an object). Done when the button works with a dummy ID and the console is clean.

**2. F-014 `[object Object]` error alerts (S).** FastAPI returns `detail` as a string, an object, or a list of `{loc, msg}` for 422. `app.js` does
`throw new Error(data.detail)` (around line 235 in the audit's copy). Write one helper `formatApiError(data)` that turns any of these into readable text
(for the profile endpoint it should list the missing questions by name), then replace **every** place that builds an error from `data.detail` or shows `err.message`
(`grep -n "detail" static/app.js`). Done when submitting the basic profile with nothing selected shows a readable list, and every other form error is readable too.

**3. F-008 Esc does not close modals (S).** Add one `keydown` listener: on Escape close the topmost visible modal (Model Inspector, plan trip, reject, modify, Google config,
destination details, any other `fixed inset-0` overlay). Reset any pending state those modals use (for example the pending feedback context). Done when every modal closes on Esc and Esc does nothing when none is open.

**4. Connection check (M).** The audit's table is unreliable (see `FIX_PLAN.md`). Write `docs/CONNECTION_CHECK.md`: for each of the 47 backend routes listed below, search **all files in `static/`**
(not only app.js) for the path and record `file:line` or "no UI calls this". Routes with no match in `app.js`: `/api/config/options`, `/api/config/detailed-options`, `/api/trips/detail/{trip_id}`,
`/api/evaluation/live/{user_id}`, `/api/companion/status/{user_id}`, `/api/places/live-search`, `/api/country/info`, all of `/api/live/*`, `/api/places/search|attractions|popular|plan-trip`,
`/api/prep/*`, `/api/ranking/{user_id}`, `/api/trip-actions/*`, `/api/modules`, `/api/template/{trip_id}`, `/destinations/india`, `/api/destinations/india`, `/places/live/{id}`, `/api/places/live/{id}`, `/itinerary/timed/*`.
Do **not** build new UI. List what is a real orphan (backend feature with no way to reach it from the UI) and tell the owner (Atharva for modules/services, Karan for api.py).

**5. Click-through of your area (3 units).** Auth (Google modal, email, phone, guest, quick demo, logout/login again), onboarding steps 1-3 (including the climate chips that made the audit's first
browser run time out: `#basicClimateGrid button` was "not visible"), detailed profile tabs, precision questionnaire, dashboard, recommendations (Refresh, shortlist). At 1366, 768 and 360 px; use Back and refresh in the middle of a flow.
Fix problems in `static/*`; log the others in `docs/bugs/kanishk.md`.

## Done when
Tasks 1-3 fixed with one commit each, `docs/CONNECTION_CHECK.md` written, click-through bugs fixed or logged, `python run_tests.py` passes, branch pushed.
