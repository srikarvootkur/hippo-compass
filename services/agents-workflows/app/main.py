from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

try:
    from agents import Agent, Runner, function_tool
except Exception:  # pragma: no cover - lets mock mode run without SDK import surprises.
    Agent = None
    Runner = None
    function_tool = None


APP_NAME = "personal-assistant-agents-workflows"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
UTC = timezone.utc

app = FastAPI(title=APP_NAME, version="0.1.0")


class CronometerReviewRequest(BaseModel):
    date: Optional[str] = None
    use_mock_data: bool = True
    goals: dict[str, Any] = Field(default_factory=dict)


class GoogleHealthCoachReviewRequest(BaseModel):
    period_days: int = Field(default=7, ge=1, le=90)
    question: str
    goals: dict[str, Any] = Field(default_factory=dict)
    active_goals: list[dict[str, Any]] = Field(default_factory=list)
    relevant_memories: list[dict[str, Any]] = Field(default_factory=list)
    activity_summary: dict[str, Any] = Field(default_factory=dict)
    health_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_pack: list[dict[str, str]] = Field(default_factory=list)


MOCK_DAY = {
    "calories": 2380,
    "protein_g": 146,
    "carbs_g": 248,
    "fat_g": 78,
    "fiber_g": 22,
    "water_l": 2.1,
    "notes": [
        "Protein target was likely met.",
        "Fiber looks a little low for a general health target.",
        "Hydration may need attention if training hard.",
    ],
}

MEDICAL_TERMS = {
    "diagnose",
    "diagnosis",
    "medication",
    "medicine",
    "dose",
    "prescription",
    "heart problem",
    "chest pain",
    "injury",
    "blood pressure",
    "disease",
}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "service": APP_NAME,
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
    }


def deterministic_cronometer_review(request: CronometerReviewRequest) -> dict[str, Any]:
    target_date = request.date or date.today().isoformat()
    goals = request.goals or {"protein_g": 140, "fiber_g": 30, "water_l": 2.7}
    recommendations = []

    if MOCK_DAY["protein_g"] >= goals.get("protein_g", 140):
        recommendations.append("Keep protein roughly where it is; this supports training and satiety.")
    if MOCK_DAY["fiber_g"] < goals.get("fiber_g", 30):
        recommendations.append("Add one high-fiber food tomorrow, such as berries, lentils, oats, or vegetables.")
    if MOCK_DAY["water_l"] < goals.get("water_l", 2.7):
        recommendations.append("Set a hydration reminder earlier in the day instead of trying to catch up at night.")

    return {
        "date": target_date,
        "source": "mock_cronometer",
        "summary": "Nutrition was broadly on track, with fiber and hydration as the clearest improvement points.",
        "metrics": MOCK_DAY,
        "goals": goals,
        "recommendations": recommendations,
        "memory_candidates": [
            {
                "kind": "health_pattern",
                "content": f"On {target_date}, nutrition review suggested fiber and hydration as improvement points.",
                "source": "cronometer_daily_review",
            }
        ],
    }


def selected_citations(evidence_pack: list[dict[str, str]]) -> list[dict[str, str]]:
    keep_titles = {
        "CDC Adult Activity Guidelines",
        "American Heart Association Physical Activity Recommendations",
        "Google Health API Codelab",
        "Google Fitbit Personal Health Coach Preview",
    }
    return [
        {"title": item["title"], "url": item["url"]}
        for item in evidence_pack
        if item.get("title") in keep_titles
    ]


def is_sensitive_medical_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in MEDICAL_TERMS)


def deterministic_google_health_coach_review(request: GoogleHealthCoachReviewRequest) -> dict[str, Any]:
    health_summary = request.health_summary or {}
    activity = request.activity_summary or health_summary.get("activity") or {}
    period_days = request.period_days
    active_minutes = float(activity.get("total_active_minutes") or 0)
    target_minutes = float(activity.get("guideline_scaled_target_active_minutes") or 150 * (period_days / 7))
    active_days = int(activity.get("active_days") or 0)
    record_count = int(activity.get("record_count") or 0)
    top_types = list((activity.get("exercise_type_counts") or {}).keys())[:3]
    data_sources = health_summary.get("data_sources") or ["google_health"]
    sleep = health_summary.get("sleep") or {}
    heart = health_summary.get("heart") or {}
    nutrition = health_summary.get("nutrition") or {}
    strength = health_summary.get("strength") or {}
    missing = health_summary.get("missing") or []
    citations = selected_citations(request.evidence_pack)
    sensitive = is_sensitive_medical_question(request.question)

    if sensitive:
        return {
            "workflow": "health_coach_review",
            "period_days": period_days,
            "data_sources": data_sources,
            "summary": "I can review wellness patterns from your activity data, but I cannot diagnose symptoms, assess urgent risk, or advise on medication changes.",
            "patterns": [
                f"Hippo Compass has {record_count} activity record(s) plus typed health summaries for the last {period_days} day(s).",
                f"Recorded active time is about {round(active_minutes, 1)} minute(s) across {active_days} active day(s).",
            ],
            "evidence_based_guidance": [
                "For medical symptoms, diagnosis, medication, or treatment decisions, use a clinician or urgent care path instead of an AI coach.",
                "For general wellness, compare weekly activity consistency against public activity guidelines and your own recovery signals.",
            ],
            "next_actions": [
                "If this is about symptoms, pain, chest discomfort, fainting, or medication, contact a qualified clinician.",
                "For a wellness-only review, ask me about activity consistency, recovery, or workout planning.",
            ],
            "questions_for_user": ["Do you want a non-medical activity consistency review instead?"],
            "citations": citations,
            "memory_candidates": [],
            "safety_level": "medical_boundary",
        }

    if record_count == 0 and not health_summary.get("daily_summary_count") and not strength.get("session_count"):
        patterns = [f"No typed health records were found for the last {period_days} day(s)."]
        next_actions = [
            "Confirm your Google Health/Fitbit sync or CSV imports are working before drawing conclusions.",
            "After data appears, run this review again and compare activity, sleep, nutrition, and training patterns.",
        ]
    else:
        patterns = [
            f"You logged about {round(active_minutes, 1)} active minute(s) across {active_days} active day(s) in the last {period_days} day(s).",
            f"Your most common recorded activity type(s): {', '.join(top_types) if top_types else 'not enough labeled activity yet'}.",
            f"This is about {round((active_minutes / target_minutes) * 100, 1) if target_minutes else 0}% of the scaled 150-minute weekly activity guideline target.",
            f"Sleep records: {sleep.get('session_count', 0)} session(s), average asleep minutes: {sleep.get('average_minutes_asleep', 0)}.",
            f"Strength records: {strength.get('session_count', 0)} session/set rows, total volume: {strength.get('total_volume', 0)}.",
            f"Missing or sparse categories: {', '.join(missing) if missing else 'none obvious'}.",
        ]
        next_actions = [
            "Pick one consistency target for the next week, such as 3 active days or one short walk on non-lifting days.",
            "Use strength volume and exercise trends from imports as context, but avoid changing too many variables at once.",
            "Use soreness, sleep quality, and energy as guardrails; do not chase more volume when recovery is poor.",
        ]

    memory_content = (
        f"Health review over {period_days} day(s): sources {', '.join(data_sources)}, {round(active_minutes, 1)} active minutes "
        f"across {active_days} active day(s), strength volume {strength.get('total_volume', 0)}, "
        f"sleep sessions {sleep.get('session_count', 0)}."
    )
    return {
        "workflow": "health_coach_review",
        "period_days": period_days,
        "data_sources": data_sources,
        "summary": "Your recent health review is most useful as a consistency and recovery check, not a diagnosis. The main coaching lever is to use the data to make the next week easier to execute.",
        "patterns": patterns,
        "evidence_based_guidance": [
            "Use public activity guidelines as a baseline target, then personalize based on your goals and recovery.",
            "Wearable and app coaching is strongest when activity, sleep, nutrition, training, goals, and memory are reviewed together.",
            "This guidance is coach inference from your records plus cited public guidance, not medical advice.",
        ],
        "next_actions": next_actions,
        "questions_for_user": [
            "What is the main goal this week: fat loss, strength, basketball conditioning, sleep/recovery, or consistency?",
            "Were any workouts missing from Google Health?",
        ],
        "citations": citations,
        "memory_candidates": [
            {
                "kind": "health_pattern",
                "content": memory_content,
                "source": "health_coach_review",
                "metadata": {"period_days": period_days},
            }
        ],
        "safety_level": "wellness",
        "sections": {
            "activity": activity,
            "sleep_recovery": sleep,
            "heart_metrics": heart,
            "nutrition": nutrition,
            "strength_training": strength,
            "unknown_or_missing": missing,
        },
    }


@app.post("/workflows/cronometer/daily-review")
async def cronometer_daily_review(request: CronometerReviewRequest) -> dict[str, Any]:
    if request.use_mock_data or not os.getenv("OPENAI_API_KEY") or Agent is None:
        return deterministic_cronometer_review(request)

    @function_tool
    def get_cronometer_day() -> dict[str, Any]:
        """Return normalized Cronometer nutrition data for the requested date."""
        return MOCK_DAY

    agent = Agent(
        name="Cronometer Daily Review",
        model=MODEL,
        instructions=(
            "Review one day of nutrition data. Be concise, practical, and oriented toward "
            "behavior change. Return summary, recommendations, and memory candidates."
        ),
        tools=[get_cronometer_day],
    )
    result = await Runner.run(agent, f"Review this date with goals: {request.model_dump_json()}")
    return {
        "date": request.date or date.today().isoformat(),
        "source": "openai_agents_sdk",
        "summary": result.final_output,
        "metrics": MOCK_DAY,
        "goals": request.goals,
        "recommendations": [],
        "memory_candidates": [],
    }


@app.post("/workflows/google-health/coach-review")
async def google_health_coach_review(request: GoogleHealthCoachReviewRequest) -> dict[str, Any]:
    return await health_coach_review(request)


@app.post("/workflows/health/coach-review")
async def health_coach_review(request: GoogleHealthCoachReviewRequest) -> dict[str, Any]:
    review = deterministic_google_health_coach_review(request)
    if not os.getenv("OPENAI_API_KEY") or Agent is None:
        return review

    agent = Agent(
        name="Hippo Compass Health Coach",
        model=MODEL,
        instructions=(
            "You are a wellness coach, not a medical provider. Use the supplied health summary, "
            "goals, memories, and evidence pack. Separate activity, sleep/recovery, heart metrics, "
            "nutrition, strength training, and missing data. Do not diagnose, change medications, "
            "or provide treatment plans. Keep advice practical, cite the supplied sources by title, "
            "and clearly label inference."
        ),
    )
    prompt = json.dumps(
        {
            "question": request.question,
            "activity_summary": request.activity_summary,
            "health_summary": request.health_summary,
            "goals": request.goals,
            "active_goals": request.active_goals,
            "relevant_memories": request.relevant_memories,
            "evidence_pack": request.evidence_pack,
            "draft_review_to_improve": review,
        },
        indent=2,
    )
    result = await Runner.run(agent, prompt)
    return {
        **review,
        "summary": str(result.final_output),
        "source": "openai_agents_sdk_with_curated_evidence",
    }
