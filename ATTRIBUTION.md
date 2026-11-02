# Project Sources & Attribution

## 1. Overview
This project is an RL-based Travel Intelligence System. I built the application logic, user authentication, master questionnaire bank, 2-tier progressive profile setup, database storage, and preference vectorizer myself. I used standard Python libraries for the backend and Tailwind CSS for styling.

---

## 2. Outside Libraries & Tools Used

| Library / Tool | Purpose | Source |
| :--- | :--- | :--- |
| **FastAPI** | Backend API routing and documentation | https://fastapi.tiangolo.com/ |
| **Uvicorn** | Local server runner | https://www.uvicorn.org/ |
| **Pydantic** | Request data validation | https://docs.pydantic.dev/ |
| **SQLite3** | Database storage (Python built-in) | Python Standard Library |
| **Tailwind CSS** | Clean CSS styling via CDN | https://tailwindcss.com/ |
| **Font Awesome** | Icons for categories (travel, food, transit, etc.) | https://fontawesome.com/ |

---

## 3. Code Written by Me

- **`app/questionnaire.py`**: The complete Master Question Bank containing 56 questions across 10 sections:
  - *Section 1*: Personal and Travel Background (Q1–Q6)
  - *Section 2*: Health, Mobility and Personal Comfort (Q7–Q13)
  - *Section 3*: Interests, Hobbies and Activities (Q14–Q19)
  - *Section 4*: Food, Diet and Daily Lifestyle (Q20–Q25)
  - *Section 5*: Weather, Clothing and Environmental Preferences (Q26–Q31)
  - *Section 6*: Budget, Accommodation and Transport (Q32–Q36)
  - *Section 7*: Travel Documents, Essentials and Preparedness (Q37–Q39)
  - *Section 8*: Behaviour, Decision-Making and Proactive Assistance (Q40–Q46)
  - *Section 9*: Trust, Privacy and Personalization Boundaries (Q47–Q51)
  - *Section 10*: Final Personalization Questions (Q52–Q56)
- **`app/database.py`**: SQLite database setup and tables (`users`, `traveller_profiles`, `detailed_profiles`, `past_trips`) with JSON storage for raw questionnaire answers.
- **`app/auth.py`**: User authentication logic (salted password hashing, Google Identity Services, email, and phone login flows).
- **`app/vectorizer.py`**: Feature extraction logic:
  - Base profile: 22-dimensional normalized vector $s_{pref} \in [0, 1]^{22}$ derived from core questions (Q1–Q5, Q14, Q17, Q20, Q26, Q32, Q41).
  - Detailed profile: 41-dimensional vector $s_{pref} \in [0, 1]^{41}$ adding avoidance penalty masks (Q12), walking capacity (Q8), schedule density (Q19), stay style (Q34), transit preference (Q35), and exploration vs exploitation balance (Q48).
- **`app/models.py`**: Pydantic schemas for auth, basic profile, detailed profile, and past trips.
- **`app/api.py`**: REST API routes (`/api/auth`, `/api/config/questionnaire`, `/api/profile`, `/api/profile/detailed`, `/api/rl/state`).
- **`static/index.html` & `static/app.js`**:
  - Fast 30–60 second basic onboarding form (3 steps).
  - Dashboard with summary statistics.
  - Comprehensive 6-tab Deep Personalisation modal covering Sections 2 to 10.
  - Interactive feature vector inspector.

---

## 4. Quick Viva / Teacher Questions

- **Q: Why have a 2-tier profile (Quick setup vs Deep Personalisation)?**  
  **A:** Per research recommendations, asking 56 questions upfront leads to user fatigue and abandonment. The 2-tier design collects 11 essential questions in 30–45 seconds to bootstrap the RL state space ($s_t \in \mathbb{R}^{22}$). Power users or travelers with specific constraints (health, dietary, walking limits) can expand to the comprehensive master question bank anytime to reach 41 features.

- **Q: How does this questionnaire connect to Reinforcement Learning?**  
  **A:** The questionnaire provides the initial state $s_t$:
  - **State Space**: $s_t = [s_{pref}, s_{context}, s_{history}]$, where user interests, budget, and climate form the base state, and avoidances act as negative penalty masks.
  - **Action Space**: Recommending an attraction, suggesting a restaurant, issuing a weather/packing alert, or selecting transit.
  - **Reward Function**: $R(s, a) = R_{interest}(s, a) - \sum \lambda_i \cdot \text{Penalty}_i(s, a)$. If an action violates a hard constraint (e.g. steep stairs when user selected walking difficulty in Q7/Q12), a heavy penalty $\lambda$ is subtracted.
  - **Policy Learning**: The Q-learning agent gradually learns to maximize user enjoyment while ensuring constraint violations stay at zero.

- **Q: Why use SQLite?**  
  **A:** It is lightweight, built into the Python Standard Library, requires zero cloud or credential setup, and persists data across sessions in `travel_guide.db`.

---

## 5. Level 3 Precision Profile (developed with AI assistance)

The Level 3 Precision Profile (`app/precision.py`, the `/api/profile/precision` and `/api/config/precision-questionnaire` routes, the `precision_profiles` table, `PreferenceVectorizer.vectorize_precision`, the precision modal in `static/index.html` and the `Level 3` section of `static/app.js`) was written with the help of Claude (Anthropic), working from this project's existing code. The question content, scoring maps and insight rules are design choices that should be reviewed and adjusted by me before submission.

- **What it adds:** 65 new questions + 18 existing master-bank questions that were not previously shown in the UI, conditional follow-ups (`show_if`), server-side validation, a privacy filter driven by Q47, an 85-dimension precision block (126-dim total state), and human-readable planner insights.
- **Also fixed:** Q12 avoidance ids that never reached the penalty mask, two hidden default avoidances sent for every user, missing `google-auth`/`requests` in `requirements.txt`, and tests that required a pre-existing database file.

