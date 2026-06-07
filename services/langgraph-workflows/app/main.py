import os
from datetime import datetime, timezone
from typing import Any, TypedDict

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
    date: str | None = Field(default=None, description="YYYY-MM-DD")
    use_mock_data: bool = True
    goals: dict[str, Any] = Field(default_factory=dict)


class DailyReviewState(TypedDict, total=False):
    request: dict[str, Any]
    nutrition_review: dict[str, Any]
    approval_required: bool
    recommendation: dict[str, Any]
    memory_candidates: list[dict[str, Any]]


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
