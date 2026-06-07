import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app import google_health


APP_NAME = "personal-assistant-api"
API_KEY = os.getenv("ASSISTANT_API_KEY", "change-me-local-dev")
LANGGRAPH_WORKFLOWS_URL = os.getenv("LANGGRAPH_WORKFLOWS_URL", "http://localhost:8070")
UTC = timezone.utc

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


class GoogleHealthSyncRequest(BaseModel):
    data_type: str = Field(default="exercise", pattern="^exercise$")


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


def require_db_pool() -> Any:
    pool = getattr(app.state, "db_pool", None)
    if not pool:
        raise HTTPException(status_code=503, detail="database connection is required")
    return pool


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


@app.get("/connectors/google-health/oauth/start", dependencies=[Depends(require_api_key)])
async def google_health_oauth_start() -> dict[str, Any]:
    pool = require_db_pool()
    try:
        config = google_health.require_settings()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    state = google_health.new_oauth_state()
    existing = await db.get_source_connection(pool, google_health.SOURCE_NAME)
    existing_config = (existing or {}).get("config") or {}
    await db.upsert_source_connection(
        pool,
        google_health.SOURCE_NAME,
        "oauth_pending",
        {
            **existing_config,
            "oauth_state": state,
            "scopes": config["scopes"],
            "redirect_uri": config["redirect_uri"],
        },
    )
    return {
        "authorization_url": google_health.build_authorization_url(state, config=config),
        "state": state,
        "redirect_uri": config["redirect_uri"],
        "scopes": config["scopes"],
    }


@app.get("/connectors/google-health/oauth/callback")
async def google_health_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> dict[str, Any]:
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing OAuth code or state")
    pool = require_db_pool()
    connection = await db.get_source_connection(pool, google_health.SOURCE_NAME)
    config = (connection or {}).get("config") or {}
    if state != config.get("oauth_state"):
        raise HTTPException(status_code=400, detail="invalid OAuth state")
    try:
        tokens = await google_health.exchange_code_for_tokens(code)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Google token exchange failed: {exc}") from exc
    await db.upsert_source_connection(
        pool,
        google_health.SOURCE_NAME,
        "active",
        {
            **config,
            "oauth_state": None,
            "tokens": tokens,
        },
    )
    return {
        "status": "connected",
        "source_name": google_health.SOURCE_NAME,
        "scopes": tokens.get("scope"),
    }


@app.get("/connectors/google-health/status", dependencies=[Depends(require_api_key)])
async def google_health_status() -> dict[str, Any]:
    pool = require_db_pool()
    connection = await db.get_source_connection(pool, google_health.SOURCE_NAME)
    if not connection:
        return {"source_name": google_health.SOURCE_NAME, "status": "not_configured"}
    config = connection.get("config") or {}
    tokens = config.get("tokens") or {}
    return {
        "source_name": google_health.SOURCE_NAME,
        "status": connection["status"],
        "scopes": config.get("scopes") or tokens.get("scope"),
        "redirect_uri": config.get("redirect_uri"),
        "has_refresh_token": bool(tokens.get("refresh_token")),
        "token_expires_at": tokens.get("expires_at"),
    }


@app.post("/connectors/google-health/sync", dependencies=[Depends(require_api_key)])
async def google_health_sync(request: GoogleHealthSyncRequest) -> dict[str, Any]:
    pool = require_db_pool()
    connection = await db.get_source_connection(pool, google_health.SOURCE_NAME)
    if not connection or connection["status"] != "active":
        raise HTTPException(status_code=400, detail="Google Health connector is not active")
    config = connection.get("config") or {}
    tokens = config.get("tokens") or {}
    try:
        if google_health.is_token_expired(tokens):
            tokens = await google_health.refresh_access_token(tokens)
            await db.upsert_source_connection(
                pool,
                google_health.SOURCE_NAME,
                "active",
                {**config, "tokens": tokens},
            )
        data_points = await google_health.list_exercise_data_points(tokens["access_token"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Google Health sync failed: {exc}") from exc

    records = []
    for point in data_points:
        normalized = google_health.normalize_exercise_data_point(point)
        external_id = normalized.get("name")
        if not external_id:
            continue
        record = await db.upsert_source_record(
            pool,
            {
                "source_name": google_health.SOURCE_NAME,
                "external_id": external_id,
                "record_type": request.data_type,
                "occurred_at": google_health.parse_google_timestamp(normalized.get("start_time")),
                "raw_payload": point,
                "normalized_payload": normalized,
            },
        )
        records.append(record)
    return {
        "source_name": google_health.SOURCE_NAME,
        "record_type": request.data_type,
        "synced_count": len(records),
        "records": [
            {
                "id": str(record["id"]),
                "external_id": record["external_id"],
                "occurred_at": record["occurred_at"].isoformat() if record["occurred_at"] else None,
                "normalized_payload": db.ensure_dict(record["normalized_payload"]),
            }
            for record in records
        ],
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
