# Atharva's Bug Log (External Issues Discovered During Verification)

This file documents functional, UI, and lifecycle issues discovered in files owned by teammates (Kanishk: `static/*`, Karan: `app/api.py`, `app/database.py`, `main.py`).

---

### Bug 1: Companion Modal Does Not Preserve Active Trip Selection on Refresh
- **Owner:** Kanishk
- **Location:** `static/modules/loader.js:25-31`
- **Steps to Reproduce:**
  1. Sign in as a user with multiple planned trips (e.g., Trip 1 and Trip 2).
  2. Open Companion modal and select Trip 2 from the `#companionTrip` dropdown.
  3. Refresh the browser page or navigate back and re-open Companion.
- **Expected Behavior:**
  The Companion modal should remember the user's previously selected `tripId` (e.g. from `localStorage.getItem("companion_active_trip")`) instead of resetting to the first trip in the array.
- **Actual Behavior:**
  Lines 26-29 always default to `trips[0]`:
  ```javascript
  tripId = sel.value || null;
  ```
  Forcing the user to re-select their trip each time they refresh or switch tabs.

---

### Bug 2: Academic Model Inspector Benchmark Panel Lacks Confidence Interval Display
- **Owner:** Kanishk
- **Location:** `static/app.js:1613-1616`, `static/index.html:935-965`
- **Steps to Reproduce:**
  1. Open Academic Model Inspector modal.
  2. Switch to the Benchmark tab.
  3. Click "Run Simulation Benchmark".
- **Expected Behavior:**
  The UI should display the sample size ($N=100$ seeds) and the 95% Confidence Intervals now returned by `/api/evaluation/benchmark` (e.g. `±0.71` reward, `±1.8%` acceptance), as well as the explanation string.
- **Actual Behavior:**
  `static/app.js` only updates scalar text:
  ```javascript
  document.getElementById("benchLinucbAcc").textContent = `${(data.adaptive_linucb.acceptance_rate * 100).toFixed(1)}% (Cumulative: ${data.adaptive_linucb.cumulative_reward > 0 ? '+' : ''}${data.adaptive_linucb.cumulative_reward})`;
  ```
  The 95% confidence intervals and evaluation summary in the API response are ignored.

---

### Bug 3: Deprecated FastAPI Startup Event Handler
- **Owner:** Karan
- **Location:** `main.py:31`
- **Steps to Reproduce:**
  Run `pytest tests/` with Python 3.12+.
- **Expected Behavior:**
  FastAPI application should use the modern `lifespan` context manager (`@asynccontextmanager async def lifespan(app: FastAPI)`).
- **Actual Behavior:**
  Throws `DeprecationWarning: on_event is deprecated, use lifespan event handlers instead`.
