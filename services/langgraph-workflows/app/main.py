from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - keeps health/mock paths usable if deps drift.
    END = None
    START = None
    StateGraph = None


APP_NAME = "hippo-compass-langgraph-workflows"
AGENTS_WORKFLOWS_URL = os.getenv("AGENTS_WORKFLOWS_URL", "http://agents-workflows:8090")
UTC = timezone.utc

app = FastAPI(title=APP_NAME, version="0.1.0")


class CronometerReviewRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
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


class DailyReviewState(TypedDict, total=False):
    request: dict[str, Any]
    nutrition_review: dict[str, Any]
    approval_required: bool
    recommendation: dict[str, Any]
    memory_candidates: list[dict[str, Any]]


class HealthCoachState(TypedDict, total=False):
    request: dict[str, Any]
    evidence_pack: list[dict[str, str]]
    coach_review: dict[str, Any]
    recommendation: dict[str, Any]
    memory_candidates: list[dict[str, Any]]
    safety_level: str


EVIDENCE_PACK = [
    {
        "title": "CDC Adult Activity Guidelines",
        "url": "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html",
        "summary": "Adults generally benefit from 150 minutes of moderate-intensity activity weekly plus muscle-strengthening activity.",
    },
    {
        "title": "American Heart Association Physical Activity Recommendations",
        "url": "https://www.heart.org/en/healthy-living/fitness/fitness-basics/aha-recs-for-physical-activity-in-adults",
        "summary": "AHA emphasizes regular aerobic activity, resistance training, and reducing sedentary time.",
    },
    {
        "title": "Google Health API Codelab",
        "url": "https://developers.google.com/health/codelabs/make-your-first-api-call",
        "summary": "Google Health API exposes user-authorized health data such as exercise data points through OAuth.",
    },
    {
        "title": "Google Fitbit Personal Health Coach Preview",
        "url": "https://blog.google/products/fitbit/fitbit-ai-personal-health-coach-preview",
        "summary": "Google describes a personal health coach that uses Fitbit data for fitness plans, sleep guidance, and health question answering.",
    },
    {
        "title": "Google Research Health AI",
        "url": "https://research.google/research-areas/health-ai/",
        "summary": "Google Research describes health AI work across public health, diagnostics, and healthcare challenges.",
    },
]


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "service": APP_NAME,
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "langgraph_available": str(StateGraph is not None).lower(),
    }


async def call_nutrition_specialist(state: DailyReviewState) -> DailyReviewState:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{AGENTS_WORKFLOWS_URL}/workflows/cronometer/daily-review",
            json=state["request"],
        )
        response.raise_for_status()
        state["nutrition_review"] = response.json()
    return state


def prepare_review_outputs(state: DailyReviewState) -> DailyReviewState:
    review = state["nutrition_review"]
    recommendations = review.get("recommendations") or []
    state["approval_required"] = False
    state["recommendation"] = {
        "title": "Review nutrition follow-up",
        "body": " ".join(recommendations) if recommendations else review.get("summary", ""),
        "reason": f"Generated from Cronometer daily review for {review.get('date')}.",
        "metadata": {
            "workflow": "cronometer_daily_review",
            "source": review.get("source"),
        },
    }
    state["memory_candidates"] = review.get("memory_candidates") or []
    return state


def build_cronometer_graph():
    graph = StateGraph(DailyReviewState)
    graph.add_node("call_nutrition_specialist", call_nutrition_specialist)
    graph.add_node("prepare_review_outputs", prepare_review_outputs)
    graph.add_edge(START, "call_nutrition_specialist")
    graph.add_edge("call_nutrition_specialist", "prepare_review_outputs")
    graph.add_edge("prepare_review_outputs", END)
    return graph.compile()


def attach_health_evidence(state: HealthCoachState) -> HealthCoachState:
    state["evidence_pack"] = EVIDENCE_PACK
    return state


async def call_health_specialist(state: HealthCoachState) -> HealthCoachState:
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{AGENTS_WORKFLOWS_URL}/workflows/health/coach-review",
            json={**state["request"], "evidence_pack": state["evidence_pack"]},
        )
        response.raise_for_status()
        state["coach_review"] = response.json()
    return state


def prepare_health_outputs(state: HealthCoachState) -> HealthCoachState:
    review = state["coach_review"]
    state["safety_level"] = review.get("safety_level", "wellness")
    next_actions = review.get("next_actions") or []
    state["recommendation"] = {
        "title": "Review health coach summary",
        "body": " ".join(next_actions) if next_actions else review.get("summary", ""),
        "reason": f"Generated from health data over {review.get('period_days')} day(s).",
        "metadata": {
            "workflow": review.get("workflow", "health_coach_review"),
            "data_sources": review.get("data_sources", ["google_health"]),
            "safety_level": state["safety_level"],
            "citations": review.get("citations") or [],
        },
    }
    state["memory_candidates"] = review.get("memory_candidates") or []
    return state


def build_google_health_coach_graph():
    graph = StateGraph(HealthCoachState)
    graph.add_node("attach_health_evidence", attach_health_evidence)
    graph.add_node("call_health_specialist", call_health_specialist)
    graph.add_node("prepare_health_outputs", prepare_health_outputs)
    graph.add_edge(START, "attach_health_evidence")
    graph.add_edge("attach_health_evidence", "call_health_specialist")
    graph.add_edge("call_health_specialist", "prepare_health_outputs")
    graph.add_edge("prepare_health_outputs", END)
    return graph.compile()


@app.post("/workflows/cronometer/daily-review")
async def cronometer_daily_review(request: CronometerReviewRequest) -> dict[str, Any]:
    initial_state: DailyReviewState = {"request": request.model_dump()}
    if StateGraph is None:
        state = await call_nutrition_specialist(initial_state)
        state = prepare_review_outputs(state)
    else:
        graph = build_cronometer_graph()
        state = await graph.ainvoke(initial_state)
    return {
        "workflow_engine": "langgraph",
        "workflow": "cronometer_daily_review",
        "nutrition_review": state["nutrition_review"],
        "recommendation": state["recommendation"],
        "memory_candidates": state["memory_candidates"],
        "approval_required": state["approval_required"],
    }


@app.post("/workflows/google-health/coach-review")
async def google_health_coach_review(request: GoogleHealthCoachReviewRequest) -> dict[str, Any]:
    return await health_coach_review(request)


@app.post("/workflows/health/coach-review")
async def health_coach_review(request: GoogleHealthCoachReviewRequest) -> dict[str, Any]:
    initial_state: HealthCoachState = {"request": request.model_dump()}
    if StateGraph is None:
        state = attach_health_evidence(initial_state)
        state = await call_health_specialist(state)
        state = prepare_health_outputs(state)
    else:
        graph = build_google_health_coach_graph()
        state = await graph.ainvoke(initial_state)
    review = state["coach_review"]
    return {
        "workflow_engine": "langgraph",
        "workflow": review.get("workflow", "health_coach_review"),
        "period_days": review.get("period_days", request.period_days),
        "data_sources": review.get("data_sources", ["google_health"]),
        "summary": review.get("summary", ""),
        "patterns": review.get("patterns", []),
        "evidence_based_guidance": review.get("evidence_based_guidance", []),
        "next_actions": review.get("next_actions", []),
        "questions_for_user": review.get("questions_for_user", []),
        "citations": review.get("citations", []),
        "safety_level": state["safety_level"],
        "activity_summary": request.activity_summary,
        "health_summary": request.health_summary,
        "recommendation": state["recommendation"],
        "memory_candidates": state["memory_candidates"],
    }
