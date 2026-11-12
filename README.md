# RL Travel Guide

A local travel-planning web app built with FastAPI, SQLite, vanilla JavaScript, and a contextual LinUCB recommendation policy. It was developed as a B.Tech CSE AI/ML project.

## Run locally

From the project folder:

```powershell
python main.py
```

Open [http://localhost:8000](http://localhost:8000). The API reference is at [http://localhost:8000/docs](http://localhost:8000/docs).

To install dependencies in a fresh environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

## What the app includes

- Email and password account creation and sign-in.
- Optional Google sign-in when a Google OAuth client ID is configured.
- A basic travel profile that powers destination recommendations.
- Deep personalization that unlocks trip planning and tailored daily schedules.
- Trip preparation, accommodation, live-trip, and post-trip feedback features.
- Contextual LinUCB activity recommendations that update from user feedback.
- India-focused destination and trip data with offline fallbacks for selected live lookups.

Phone sign-in is not enabled because the project has no SMS verification provider. Google sign-in requires `GOOGLE_CLIENT_ID`; email sign-in works without it. Optional settings are documented in `.env.example`.

## Development

Run the maintained test suite with:

```powershell
python -m pytest tests -v
```

`run_tests.py` is retained as a legacy integration runner. To regenerate the evaluation artifacts in `docs/`, run `python scripts/evaluate.py`.

## Project documentation

- [Attribution and AI disclosure](ATTRIBUTION.md)
- [Academic report](docs/report/REPORT.md)
- [Viva questions](docs/report/VIVA_QA.md)
- [Evaluation method](docs/evaluation.md)
- [Destination ranking](docs/ranking.md)
- [Plan engine](docs/plan.md)
- [Stay, preparation, and live-trip guides](docs/stay.md), [prep](docs/prep.md), [live](docs/live.md)
