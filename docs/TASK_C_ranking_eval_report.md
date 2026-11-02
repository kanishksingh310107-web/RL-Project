# Person C – Seasonal ranking, honest RL evaluation, report/PPT, final integration
Module id `ranking`. C is also the integrator.

## Part 1 – Ranking module (`app/modules/ranking.py`)
Implements handoff section 4 properly. `GET /api/ranking/{user_id}?date=YYYY-MM-DD&budget=...`
- Score each of the 16 destinations (`DESTINATIONS` in `app/recommender.py`, read-only) with the baseline weights: 25% interest match, 20% weather/season, 15% popularity, 15% feasibility, 10% live conditions, 15% past feedback. Treat weights as *assumptions* (say so), keep them in a visible dict, and let the query override them.
- Keep four separate lists: **Trending now**, **Best this season**, **Best for you**, **Best feasible**.
- **Hard constraints are filters, not scores** (budget cap exceeded, closure flag, advisory flag -> excluded with a stated reason).
- Season suitability from `best_seasons` + the requested date (parse months). Popularity = a static, **labelled and dated** table you write (`source`, `as_of`) – never claim "popular right now" without evidence; say "static estimate as of <date>".
- Each result returns the per-component breakdown (explainability) and `data_freshness` notes.
- UI tab `ranking.js`: four lists + a breakdown bar per item.
- Tests: season changes ranking; hard constraint excludes; weights sum to 1; missing profile still works.

## Part 2 – Honest evaluation (`scripts/evaluate.py`, `docs/evaluation.md`)
Problem: current benchmark says LinUCB 73.3% vs static baseline 80.0%.
- Read `app/evaluation.py` and `app/rl_planner.py`. Find out why (very short horizon of 20 rounds? alpha=0.5? reward noise? baseline sees the true preference?). Fix the *experiment*, not the numbers: run >= 3 personas x >= 10 seeds x 100–200 rounds, with alpha swept (e.g. 0.1, 0.3, 0.5, 1.0), report mean +- std of acceptance rate and cumulative reward for LinUCB vs static vs random. Also a learning curve (acceptance per 10-round window). Save `docs/eval_results.csv` and `docs/eval_curve.png`.
- Report whatever the result is. If LinUCB does not win, say exactly under which conditions it does/doesn't and why. Do NOT tune until it "wins" and do NOT edit `rl_planner.py` unless you find a real bug – if so, tell the team first.
- State limitations: simulated users only, no real dataset, one synthetic reward model.
- Write `docs/evaluation.md` (setup, table, plot, interpretation, limitations).

## Part 3 – Report/PPT and disclosure
- Rewrite `ATTRIBUTION.md`: correct "Q-learning" -> "Contextual LinUCB (disjoint)", list libraries, and honestly list AI-assisted parts per file. Update `README.md` run/test commands (add pytest).
- RL framing slide/section: state, actions (arm = activity category, action = which activity to recommend), reward, policy, constraints (use handoff section 6 wording).
- Compile each person's `docs/<id>.md` into the PPT (8–10 slides, structure in the original handoff section 9) and a short report. Label clearly: **Implemented / Simulated / Future work** (churn prediction, real live data feeds, real user study).
- Prepare ~10 viva questions with answers (What is LinUCB? Why disjoint? What is an arm? What is the reward? Why simulated? What is the limitation?).

## Part 4 – Integration (at T+5h)
Follow the merge procedure in `docs/CONTRACT.md`, run both test suites, run the app (`python main.py`), click through every tab, take screenshots, fix only blocking bugs.
