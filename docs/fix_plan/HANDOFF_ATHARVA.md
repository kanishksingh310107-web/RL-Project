# Handoff: Atharva, RL evaluation, modules, documentation
Read `FIX_PLAN.md` first (scope, rules, file ownership, git steps). Branch: `atharva/audit-fixes`. You own `app/rl_planner.py`, `app/evaluation.py`, `app/itinerary_generator.py`, `app/modules/*`, `app/services/*`, `README.md`, `HANDOFF.md`, `ATTRIBUTION.md`, and RL/evaluation tests.

## Git workflow (do this FIRST, before any fix)
1. **Pull the latest `main`:** `git checkout main && git pull origin main` (Step 0 is already done: `main` has the audit report, your handoff in `docs/fix_plan/`, the bug logs and the `.gitignore` update).
2. **Create your own branch from it:** `git checkout -b atharva/audit-fixes`
3. **Fix the issues below on that branch only.** One commit per finding, e.g. `F-017: correct LinUCB docstring`.
4. **Push after every fix, not only at the end:** `git push -u origin atharva/audit-fixes` (the `-u` is needed only the first time; later just `git push`).
5. If `main` gets new commits while you work, bring them in with `git fetch origin && git merge origin/main`, fix any conflict, run the tests, then push.
6. Do **not** merge into `main` yourself. Kanishk merges all branches at the end, so your job ends with a pushed branch.

## Tasks
**1. F-016 the benchmark shows the baseline winning (M).** The audit ran `run_comparative_simulation` over 100 seeds x 20 rounds: cumulative reward LinUCB 9.18 +/- 0.83 vs static baseline 11.90 +/- 0.64 (95% CI).
(`AUDIT_EVIDENCE/benchmark_100_seeds.json`). Goal: report the truth and, if a legitimate improvement exists, show it.
 a. Write down in `docs/evaluation_results.md` BEFORE running anything new: the metric, the number of seeds (>= 100), and the one or two changes you will try (for example initialising `b` from the user's stated interests as a prior, a horizon of 50 rounds).
 b. Make the benchmark return mean and 95% CI over many seeds (use `np.random.default_rng(seed)` per seed, no global seed). Keep the response keys that `static/app.js` (around line 1737, `/api/evaluation/benchmark`) and the tests read; check usage before renaming anything.
 c. Run the pre-declared variants. Record **all** results, including ones where the baseline still wins. Do not tune until it looks good and hide the rest.
 d. Make the Model Inspector benchmark panel show what you found (tell Kanishk if a change in `static/*` is needed).
Done when `docs/evaluation_results.md` has the table with CIs and the command to reproduce it, and nothing in the app or docs claims LinUCB is better unless the table shows it.

**2. F-017 Sherman-Morrison claim (S).** The docstring in `LinUCBPolicy.update` says Sherman-Morrison; the code does `A += x x^T` and `np.linalg.inv(A)` in `predict_score`. Either correct the docstring, or store `A_inv` and update it with
`A_inv -= (A_inv x x^T A_inv) / (1 + x^T A_inv x)` and add a test that it equals `np.linalg.inv(A)`. Tell Kanishk which, so the docs match. Done when code and comments agree.

**3. Click-through of your area (4 units).** The audit never opened these: trip preparation (weather, packing, documents, reminders, reminder feedback), live trip (start, today, simulate, alerts and dismiss, replan, complete, post-trip, learning summary),
places (search, attractions, popular, plan-trip), trip actions (finalize, swap, delete activity, reschedule, switch days), ranking, timed itinerary, and the Model Inspector tabs. For each: does a UI control reach it (see Kanishk's `docs/CONNECTION_CHECK.md`),
does it show real data, what happens with a trip that has no activities or a destination with few activities, and does Back/refresh keep state. Fix bugs in your files; log the others in `docs/bugs/atharva.md` for the owner.

**4. F-009 documentation (S, do it LAST, after the other branches are merged).** Remove every "100% complete" and any mention of Q-learning or Sherman-Morrison that is not true.
Replace the scorecard with a three-column capability matrix: *verified by an automated test*, *verified by clicking through*, *exists but not verified*. Include the modules (live, prep, places, trip actions, ranking). List libraries and any AI assistance in `ATTRIBUTION.md`.

## Done when
Evaluation table with CIs committed, docstring/code agree, click-through bugs fixed or logged, docs updated last, branch pushed.
