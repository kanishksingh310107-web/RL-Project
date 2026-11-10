# Backend & Database Bug Log - Karan (Person C)

## Verification Summary
- **F-010:** Fixed missing `travel_goals` and `place_interests` fields in `run_tests.py` profile payload. `run_tests.py` passes all 141 assertions.
- **F-004:** Destination validation, travellers count, budget, and date range checks moved before user lookup in `app/api.py:create_trip`. Verified 400 for international destinations on live DB, 422 for non-positive travellers or negative budget, and 422 for end date preceding start date.
- **F-015:** Verified module registry tests (`tests/test_places_api.py` and `tests/test_ranking.py`) and destination tests (`tests/test_trip_india_validation.py`). All 22 tests pass cleanly.
- **F-002:** Added `conn.execute("PRAGMA foreign_keys = ON")` to database connection factory in `app/database.py`. Re-verified both test runners (`run_tests.py` and `pytest tests/ -q` 76/76 passing). No foreign key constraint violations observed.
- **API Error Format:** Verified that validation and lookup failures return structured JSON errors (`detail` message) rather than stack traces.

## Cross-Owner Bug Observations
None found in backend API or database components.
