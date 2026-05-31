import os
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import db


APP_NAME = "personal-assistant-api"
API_KEY = os.getenv("ASSISTANT_API_KEY", "change-me-local-dev")
LANGGRAPH_WORKFLOWS_URL = os.getenv("LANGGRAPH_WORKFLOWS_URL", "http://localhost:8070")

app = FastAPI(title=APP_NAME, version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    try:
        app.state.db_pool = await db.create_pool()
    except Exception as exc:
        app.state.db_pool = None
        print(f"database pool unavailable: {exc}", flush=True)


@app.on_event("shutdown")
async def shutdown() -> None:
    pool = getattr(app.state, "db_pool", None)
    if pool:
        await pool.close()


class ActionRisk(str, Enum):
    low = "low"
    sensitive = "sensitive"


class MemoryWrite(BaseModel):
    kind: str = Field(..., examples=["preference", "goal", "journal_summary"])
    content: str
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearch(BaseModel):
    query: str
    limit: int = Field(default=8, ge=1, le=25)
    filters: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    action_type: str = Field(..., examples=["send_text", "book_reservation"])
    title: str
    proposed_payload: dict[str, Any]
    risk: ActionRisk = ActionRisk.sensitive
    reason: str | None = None


class JournalEntryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    title: str | None = None
    source: str = "manual"
    entry_date: str | None = Field(default=None, description="YYYY-MM-DD")
    occurred_at: str | None = None
    summary: str | None = None


class RecommendationCreate(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolRunCreate(BaseModel):
    tool_name: str = Field(..., min_length=1)
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(..., examples=["success", "error"])


class CronometerReviewRequest(BaseModel):
    date: str | None = Field(default=None, description="YYYY-MM-DD. Defaults to today in workflow service.")
    use_mock_data: bool = True
    goals: dict[str, Any] = Field(default_factory=dict)


def require_api_key(x_assistant_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and x_assistant_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid assistant API key")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "service": APP_NAME,
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
    }


@app.post("/journal_entries", dependencies=[Depends(require_api_key)])
async def create_journal_entry(journal: JournalEntryCreate) -> dict[str, Any]:
    pool = getattr(app.state, "db_pool", None)
    summary = journal.summary or journal.content.strip().replace("\n", " ")[:240]
    if pool:
        record = await db.insert_journal_entry(pool, {**journal.model_dump(), "summary": summary})
        memory = await db.insert_memory(
            pool,
            {
                "kind": "journal_theme",
                "content": f"Journal theme from {journal.source}: {summary}",
                "source": "journal_entry",
                "metadata": {"journal_entry_id": str(record["id"])},
            },
        )
        recommendation = await db.insert_recommendation(
            pool,
            {
                "title": "Review new journal theme",
                "body": "Review this journal theme and decide whether it should become a goal, reminder, or weekly experiment.",
                "reason": f"Created from journal entry {record['id']}",
                "metadata": {"journal_entry_id": str(record["id"])},
            },
        )
        return {
            "id": str(record["id"]),
            "status": "persisted",
            "journal_entry": {
                **record,
                "id": str(record["id"]),
                "entry_date": record["entry_date"].isoformat(),
                "occurred_at": record["occurred_at"].isoformat(),
                "created_at": record["created_at"].isoformat(),
            },
            "created_memory_id": str(memory["id"]),
            "created_recommendation_id": str(recommendation["id"]),
        }
    return {
        "id": str(uuid4()),
        "status": "not_persisted_no_database",
        "summary": summary,
        "journal_entry": journal.model_dump(),
    }


@app.post("/memory/write", dependencies=[Depends(require_api_key)])
async def write_memory(memory: MemoryWrite) -> dict[str, Any]:
    pool = getattr(app.state, "db_pool", None)
    if pool:
        record = await db.insert_memory(pool, memory.model_dump())
        return {
            "id": str(record["id"]),
            "status": "persisted",
            "memory": {
                **record,
                "id": str(record["id"]),
                "created_at": record["created_at"].isoformat(),
            },
        }
    return {
        "id": str(uuid4()),
        "status": "not_persisted_no_database",
        "memory": memory.model_dump(),
        "time": datetime.now(UTC).isoformat(),
    }


@app.post("/memory/search", dependencies=[Depends(require_api_key)])
async def search_memory(search: MemorySearch) -> dict[str, Any]:
    pool = getattr(app.state, "db_pool", None)
    if pool:
        rows = await db.search_memories(pool, search.query, search.limit, search.filters)
        return {
            "query": search.query,
            "results": [
                {
                    **row,
                    "id": str(row["id"]),
                    "created_at": row["created_at"].isoformat(),
                }
                for row in rows
            ],
        }
    return {
        "query": search.query,
        "results": [],
        "note": "No database connection is available.",
    }


@app.post("/recommendations", dependencies=[Depends(require_api_key)])
async def create_recommendation(recommendation: RecommendationCreate) -> dict[str, Any]:
    pool = getattr(app.state, "db_pool", None)
    if pool:
        record = await db.insert_recommendation(pool, recommendation.model_dump())
        return {
            "id": str(record["id"]),
            "status": record["status"],
            "recommendation": {
                **record,
                "id": str(record["id"]),
                "created_at": record["created_at"].isoformat(),
                "updated_at": record["updated_at"].isoformat(),
            },
        }
    return {
        "id": str(uuid4()),
        "status": "not_persisted_no_database",
        "recommendation": recommendation.model_dump(),
    }


@app.get("/recommendations", dependencies=[Depends(require_api_key)])
async def list_recommendations(status: str = "pending", limit: int = 20) -> dict[str, Any]:
    pool = getattr(app.state, "db_pool", None)
    if pool:
        rows = await db.list_recommendations(pool, status, min(max(limit, 1), 100))
        return {
            "status": status,
            "results": [
                {
                    **row,
                    "id": str(row["id"]),
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                }
                for row in rows
            ],
        }
    return {
        "status": status,
        "results": [],
        "note": "No database connection is available.",
    }


@app.post("/approvals", dependencies=[Depends(require_api_key)])
async def create_approval(request: ApprovalRequest) -> dict[str, Any]:
    pool = getattr(app.state, "db_pool", None)
    if pool:
        record = await db.insert_approval(pool, request.model_dump())
        return {
            "id": str(record["id"]),
            "status": record["status"],
            "approval": {
                **record,
                "id": str(record["id"]),
                "created_at": record["created_at"].isoformat(),
            },
        }
    return {
        "id": str(uuid4()),
        "status": "pending_approval",
        "request": request.model_dump(),
        "time": datetime.now(UTC).isoformat(),
    }


@app.post("/tool_runs", dependencies=[Depends(require_api_key)])
async def create_tool_run(tool_run: ToolRunCreate) -> dict[str, Any]:
    pool = getattr(app.state, "db_pool", None)
    if pool:
        record = await db.insert_tool_run(pool, tool_run.model_dump())
        return {
            "id": str(record["id"]),
            "status": record["status"],
            "tool_run": {
                **record,
                "id": str(record["id"]),
                "created_at": record["created_at"].isoformat(),
            },
        }
    return {
        "id": str(uuid4()),
        "status": "not_persisted_no_database",
        "tool_run": tool_run.model_dump(),
    }


@app.post("/workflows/cronometer/daily-review", dependencies=[Depends(require_api_key)])
async def cronometer_daily_review(request: CronometerReviewRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{LANGGRAPH_WORKFLOWS_URL}/workflows/cronometer/daily-review",
            json=request.model_dump(),
        )
        response.raise_for_status()
        return response.json()
