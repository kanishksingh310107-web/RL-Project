<USER_REQUEST>
# RL TRAVEL GUIDE â€” IMPLEMENTATION MASTER PROMPT

## 1. Project Context and Overall Objective

I am developing a project called **RL Travel Guide**, an adaptive, personalised travel recommendation and travel assistance system that uses Reinforcement Learning (RL) as a major component.

The most important feature of this project is NOT simply generating travel itineraries.

**Our main objective is to understand each traveller as deeply as reasonably possible, learn from their preferences and actual experiences, and use that understanding to provide increasingly personalised recommendations and assistance.**

The application should learn:
- What the traveller enjoys.
- What activities they dislike or want to avoid.
- What kind of travel experience they prefer.
- Their preferred pace, budget behaviour, comfort requirements, and interests.
- Which experiences they have already had and whether they enjoyed them.
- How their preferences change over time.
- How they respond to recommendations and itinerary changes.
- What they learn about their own preferences after trying new experiences.

The travel guide is the result of this understanding.

The intended lifecycle is:

**Basic Profile â†’ General Recommendations â†’ Optional Deep Personalisation â†’ Personalised Trip Recommendations â†’ Pre-Trip Preparation â†’ Live Trip Management â†’ Post-Trip Feedback â†’ Preference Learning and RL Updates â†’ Better Future Recommendations.**

I want you to examine the EXISTING project and implement these features within its current architecture wherever practical.

Do not unnecessarily rebuild the entire application, replace working features, or introduce a completely different technology stack.

First inspect the codebase, identify the current authentication system, frontend, backend, database, existing questionnaires, recommendation logic, and RL implementation. Then determine what needs to be implemented, modified, or fixed.

Do not stop after writing a plan. Implement the changes, run appropriate tests, and report what actually works.

---

# 2. FEATURE ONE: BASIC PROFILE DURING FIRST LOGIN

## Objective

When a new user signs up or logs in for the first time, the system should collect a small amount of useful information through a short onboarding questionnaire.

This questionnaire must be quick to complete.

It should collect enough information to provide useful GENERAL or LIGHTLY PERSONALISED travel recommendations without forcing the user to complete a long questionnaire.

The user should be able to access the application after completing this short profile.

Do not ask all deep-personalisation questions during basic onboarding.

## Basic Profile Questionnaire

Design the best practical short questionnaire for the following areas.

### A. Basic travel interests

Ask the user to select the kinds of experiences they generally enjoy.

Include options such as:
- Nature and scenic landscapes.
- Mountains and hiking.
- Beaches and coastal destinations.
- History and heritage.
- Culture and local traditions.
- Food and culinary experiences.
- Cafes and relaxed exploration.
- Adventure and outdoor activities.
- Photography and scenic locations.
- Shopping.
- Nightlife and entertainment.
- Museums, art, and architecture.
- Religious or spiritual experiences.
- Relaxation and wellness.
- Festivals, events, and unique local experiences.
- Hidden gems and places away from the main tourist crowds.

Allow multiple selections and, if appropriate, a way to indicate the user's strongest interests.

Do not force the user to select interests they do not have.

### B. General travel style

Ask a few questions to identify whether the user generally prefers:
- Relaxed trips or packed itineraries.
- Famous attractions or less-crowded places.
- Planned activities or spontaneous exploration.
- Comfort and convenience or budget-friendly travel.
- Staying in one place or exploring multiple locations.

Avoid asking every possible variation as a separate question. Use concise, well-designed options.

### C. Typical travel companions

Ask whether the user usually travels:
- Alone.
- With a partner.
- With friends.
- With family.
- With children.
- With a larger group.
- In different arrangements depending on the trip.

This information should establish a general pattern, not permanently determine how every future trip must be planned.

### D. Broad budget preference

Ask whether the user generally prefers:
- Budget travel.
- Balanced value for money.
- Comfort-focused travel.
- Premium experiences.
- A different budget depending on the trip.

Do not assume that the user's general budget preference is their budget for every trip.

### E. General climate preference

Ask whether the user generally prefers:
- Cold or snowy destinations.
- Cool weather.
- Mild weather.
- Warm weather.
- Hot or tropical destinations.
- No strong preference.

Allow the user to indicate if weather strongly affects their travel decisions.

### F. Travel experience

Optionally ask whether the user is:
- New to travelling.
- An occasional traveller.
- An experienced traveller.
- A frequent traveller.

Only retain this information if it is useful for recommendations or assistance.

## Basic Profile Design Requirements

1. Keep the questionnaire short and user-friendly.
2. Use selectable cards, multi-select chips, sliders, or other suitable UI components instead of a long plain-text form.
3. Make optional questions clearly optional.
4. Do not request unnecessary sensitive personal information.
5. Save the responses against the authenticated user's unique account ID.
6. Allow the user to edit the basic profile later.
7. Do not repeatedly show onboarding to a user whose profile has already been completed.
8. Allow a user to skip optional questions.
9. Make the interface responsive and visually consistent with the existing application.
10. Store the answers in a structured format that can be used by the recommendation engine.

After completing the basic profile, take the user to the main dashboard.

---

# 3. FEATURE TWO: GENERAL TRAVEL RECOMMENDER

The basic profile must immediately provide value.

After the user completes basic onboarding, display general or lightly personalised recommendations.

The recommender should consider:
- Broad travel interests.
- General travel style.
- Broad budget preference.
- Climate preference.
- Typical travel companions.
- Available destination and activity data.

The system should show multiple suitable options rather than only one destination.

Each recommendation should explain:
- Why the destination or trip might suit the user.
- What experiences are available.
- The likely travel style and atmosphere.
- A rough budget category or estimate when data supports it.
- The season or conditions that may make it attractive.
- Any relevant limitations or uncertainties.

Do not pretend the recommendations are deeply personalised when the system has only collected a few answers.

Separate the following concepts:

**Recommended For You:** Options informed by the user's profile and available travel history.

**Trending Trips:** Popular or timely options that are not necessarily personalised.

**Seasonal and Upcoming Experiences:** Destinations and activities relevant to a particular season or upcoming event, when appropriate data is available.

The system should eventually support more sophisticated recommendations as the user provides additional information.

---

# 4. FEATURE THREE: OPTIONAL DEEP PERSONALISATION

This is one of the most important features of the entire project.

After basic onboarding, provide a clear option such as:

**"Create My Personal Travel Profile"**

Supporting text could explain:

"Answer a few more questions so we can understand your travel preferences, previous experiences, comfort requirements, and interests. We will use this information to create more personalised trip recommendations and provide better assistance before, during, and after your trips."

The user must be able to choose whether to begin.

Do not make the deep questionnaire compulsory for basic access.

The deep-personalisation flow should build upon the existing basic profile rather than asking the same questions again.

Use branching logic so users only see questions relevant to their answers.

For example, if a user never travels with children, do not show detailed child-related questions unless a later trip involves children.

Organise the questionnaire into manageable sections with a progress indicator.

The objective is to collect useful information, not the maximum possible amount of information.

## Section A: Detailed Interests

Ask the user to identify:
- Their strongest travel interests.
- Activities they particularly enjoy.
- Activities they dislike.
- Activities they have never tried but would like to try.
- Experiences they would not normally choose.
- Whether they want recommendations that
then do these things in this project folder , read what has already been done from it
</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-10-26T08:55:05+05:30.
</ADDITIONAL_METADATA>