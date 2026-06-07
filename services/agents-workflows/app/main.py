import os
from datetime import date, datetime, timezone
from typing import Any

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
    date: str | None = None
    use_mock_data: bool = True
    goals: dict[str, Any] = Field(default_factory=dict)


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
