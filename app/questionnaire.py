"""
Master Questionnaire Bank (India-Specific, Deduplicated, Model-Agnostic)
Single source of truth: app/data/questionnaire_schema.json (Schema v2.0.0)

Provides:
- QUESTIONNAIRE_SECTIONS: Combined section list for basic and deep tiers
- QUESTIONS: Dictionary of all 39 questions, indexed by canonical ID and legacy ID
- BASIC_QUESTION_IDS: 12 core onboarding question IDs
"""
import copy
import json
from pathlib import Path
from typing import Any, Dict, List

_SCHEMA_PATH = Path(__file__).resolve().parent / "data" / "questionnaire_schema.json"

with open(_SCHEMA_PATH, "r", encoding="utf-8") as _f:
    SCHEMA_DATA: Dict[str, Any] = json.load(_f)

# Sections: combine basic and deep sections
QUESTIONNAIRE_SECTIONS: List[Dict[str, Any]] = (
    list(SCHEMA_DATA.get("basic_sections", [])) + list(SCHEMA_DATA.get("deep_sections", []))
)

# Canonical question dictionary (keyed by question ID and legacy ID)
QUESTIONS: Dict[str, Dict[str, Any]] = {}

for _raw_q in SCHEMA_DATA.get("questions", []):
    q = copy.deepcopy(_raw_q)
    # Ensure frontend-compatible 'question' attribute
    if "question" not in q and "text" in q:
        q["question"] = q["text"]
    
    qid = q["id"]
    QUESTIONS[qid] = q

    # Index by legacy_id if present for backward compatibility
    leg_id = q.get("legacy_id")
    if leg_id and leg_id not in QUESTIONS:
        QUESTIONS[leg_id] = q

# Legacy Q4 (planning approach) compatibility for basic onboarding form
if "q4" not in QUESTIONS:
    QUESTIONS["q4"] = {
        "id": "q4",
        "legacy_id": "q4",
        "section": "b_sec_1",
        "tier": "basic",
        "question": "What is your usual approach to planning a trip?",
        "type": "single",
        "options": [
            {
                "id": "plan_advance",
                "label": "Detailed planner",
                "desc": "I book transport, accommodation, and activities well ahead."
            },
            {
                "id": "plan_essentials",
                "label": "Essential planner",
                "desc": "I book transport and accommodation, leaving daily activities flexible."
            },
            {
                "id": "spontaneous",
                "label": "Spontaneous",
                "desc": "I book only the first night or two and decide as I go."
            },
            {
                "id": "rely_agent",
                "label": "Agent-guided",
                "desc": "I rely on another person or a travel agent to organize."
            },
            {
                "id": "ai_guided",
                "label": "AI-guided",
                "desc": "I want an AI assistant to adapt and recommend dynamically."
            }
        ]
    }
    QUESTIONS["planning_approach"] = QUESTIONS["q4"]

# Core 12 Basic onboarding question IDs
BASIC_QUESTION_IDS: List[str] = [
    q["id"] for q in SCHEMA_DATA.get("questions", []) if q.get("tier") == "basic"
]

# Legacy IDs for backward compatibility
LEGACY_BASIC_QUESTION_IDS: List[str] = [
    q.get("legacy_id")
    for q in SCHEMA_DATA.get("questions", [])
    if q.get("tier") == "basic" and q.get("legacy_id")
]
