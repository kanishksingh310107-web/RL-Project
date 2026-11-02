# RL Travel Guide

A travel recommendation and planning project using Reinforcement Learning.

## Setup and Running

1. Install requirements:
```bash
pip install -r requirements.txt
```

2. Run the server:
```bash
python main.py
```

3. Open in browser:
- Web App: [http://localhost:8000](http://localhost:8000)
- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

4. Run tests:
```bash
python run_tests.py
```

## What is implemented so far:
- **Auth (Stage 1):** Login via Google, manual email/password, or phone number.
- **Profile (Stage 2):** 3-step onboarding collecting interests, pace, companions, and budget.
- **RL Feature Vector:** Automatically transforms user choices into a 22-dimensional numerical vector for the RL state representation.
- **Deep Personalisation (Level 2):** 6-tab wizard that extends the state to 41 dimensions (avoidance masks, walking capacity, stay and transit style).
- **Precision Profile (Level 3):** adaptive questionnaire of 83 questions (65 new + 18 from the master bank that were never shown before). Follow-up questions appear only when relevant, answers are validated and privacy-filtered on the server, and they extend the state to 126 dimensions. See `app/precision.py`.

## Attribution
See [ATTRIBUTION.md](ATTRIBUTION.md) for libraries used and what was built from scratch.
