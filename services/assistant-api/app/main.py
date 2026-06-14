from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app import google_health
from app import health_ingest
from app import health_coach


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
    reason: Optional[str] = None


class JournalEntryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    title: Optional[str] = None
    source: str = "manual"
    entry_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    occurred_at: Optional[str] = None
    summary: Optional[str] = None


class RecommendationCreate(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolRunCreate(BaseModel):
    tool_name: str = Field(..., min_length=1)
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(..., examples=["success", "error"])


class CronometerReviewRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD. Defaults to today in workflow service.")
    use_mock_data: bool = True
    goals: dict[str, Any] = Field(default_factory=dict)


class GoogleHealthSyncRequest(BaseModel):
    data_type: Optional[str] = None
    data_types: list[str] = Field(default_factory=list)
    lookback_days: int = Field(default=30, ge=1, le=3650)


class GoogleHealthConfigureRequest(BaseModel):
    selected_data_types: list[str] = Field(default_factory=google_health.all_data_type_names)
    sync_schedule: str = Field(default="manual", pattern="^(manual|daily|weekly|off)$")


class CsvImportRequest(BaseModel):
    source: str = Field(..., pattern="^(hevy|cronometer)$")
    file_path: str


class GoogleHealthCoachReviewRequest(BaseModel):
    period_days: int = Field(default=7, ge=1, le=90)
    force_sync: bool = True
    question: str = Field(
        default="Review my recent Google Health data and tell me what to improve next.",
        min_length=1,
    )
    goals: dict[str, Any] = Field(default_factory=dict)


class UnifiedHealthCoachReviewRequest(BaseModel):
    period_days: int = Field(default=7, ge=1, le=90)
    force_sync: bool = True
    question: str = Field(
        default="Review my recent health data and tell me what to improve next.",
        min_length=1,
    )
    goals: dict[str, Any] = Field(default_factory=dict)


def require_api_key(x_assistant_api_key: Optional[str] = Header(default=None)) -> None:
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
    selected_data_types = existing_config.get("selected_data_types") or google_health.all_data_type_names()
    scopes = google_health.selected_scopes(selected_data_types)
    await db.upsert_source_connection(
        pool,
        google_health.SOURCE_NAME,
        "oauth_pending",
        {
            **existing_config,
            "oauth_state": state,
            "scopes": scopes,
            "redirect_uri": config["redirect_uri"],
            "selected_data_types": selected_data_types,
        },
    )
    return {
        "authorization_url": google_health.build_authorization_url(
            state,
            config={**config, "scopes": scopes},
            data_types=selected_data_types,
        ),
        "state": state,
        "redirect_uri": config["redirect_uri"],
        "scopes": scopes,
        "selected_data_types": selected_data_types,
    }


@app.get("/connectors/google-health/oauth/callback")
async def google_health_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
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


@app.get("/connectors/google-health/catalog", dependencies=[Depends(require_api_key)])
async def google_health_catalog() -> dict[str, Any]:
    return {
        "source_name": google_health.SOURCE_NAME,
        "data_types": google_health.catalog(),
        "readonly_scopes": google_health.READONLY_SCOPES,
    }


@app.post("/connectors/google-health/configure", dependencies=[Depends(require_api_key)])
async def google_health_configure(request: GoogleHealthConfigureRequest) -> dict[str, Any]:
    pool = require_db_pool()
    invalid = [name for name in request.selected_data_types if name not in google_health.DATA_TYPE_BY_NAME]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported Google Health data type(s): {', '.join(invalid)}")
    existing = await db.get_source_connection(pool, google_health.SOURCE_NAME)
    existing_config = (existing or {}).get("config") or {}
    scopes = google_health.selected_scopes(request.selected_data_types)
    connection = await db.upsert_source_connection(
        pool,
        google_health.SOURCE_NAME,
        (existing or {}).get("status") or "configured",
        {
            **existing_config,
            "selected_data_types": request.selected_data_types,
            "sync_schedule": request.sync_schedule,
            "scopes": scopes,
        },
    )
    return {
        "source_name": google_health.SOURCE_NAME,
        "status": connection["status"],
        "selected_data_types": request.selected_data_types,
        "sync_schedule": request.sync_schedule,
        "scopes": scopes,
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
        "selected_data_types": config.get("selected_data_types") or [google_health.RECORD_TYPE_EXERCISE],
        "sync_schedule": config.get("sync_schedule", "manual"),
        "has_refresh_token": bool(tokens.get("refresh_token")),
        "token_expires_at": tokens.get("expires_at"),
    }


@app.post("/connectors/google-health/sync", dependencies=[Depends(require_api_key)])
async def google_health_sync(request: GoogleHealthSyncRequest) -> dict[str, Any]:
    pool = require_db_pool()
    data_types = request.data_types or ([request.data_type] if request.data_type else None)
    result = await sync_google_health_data(pool, data_types=data_types, lookback_days=request.lookback_days)
    return result


def data_types_for_sync(connection: dict[str, Any], data_types: list[str] | None) -> list[str]:
    if data_types:
        selected = data_types
    else:
        config = connection.get("config") or {}
        selected = config.get("selected_data_types") or [google_health.RECORD_TYPE_EXERCISE]
    invalid = [name for name in selected if name not in google_health.DATA_TYPE_BY_NAME]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported Google Health data type(s): {', '.join(invalid)}")
    return selected


async def write_typed_health_rows(pool: Any, record: dict[str, Any]) -> None:
    observation, session = health_ingest.source_record_to_typed_rows(record)
    if observation:
        await db.upsert_health_observation(pool, observation)
    if session:
        await db.upsert_health_session(pool, session)


async def write_daily_summaries(pool: Any, records: list[dict[str, Any]]) -> int:
    count = 0
    for summary in health_ingest.summarize_normalized_records(records):
        await db.upsert_health_daily_summary(pool, summary)
        count += 1
    return count


async def sync_google_health_data(
    pool: Any,
    data_types: list[str] | None = None,
    lookback_days: int = 30,
) -> dict[str, Any]:
    connection = await db.get_source_connection(pool, google_health.SOURCE_NAME)
    if not connection or connection["status"] not in {"active", "configured", "oauth_pending"}:
        raise HTTPException(status_code=400, detail="Google Health connector is not active")
    selected_data_types = data_types_for_sync(connection, data_types)
    run = await db.create_source_sync_run(
        pool,
        google_health.SOURCE_NAME,
        selected_data_types,
        {"lookback_days": lookback_days},
    )
    imported_records: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    seen = 0
    try:
        config = connection.get("config") or {}
        tokens = config.get("tokens") or {}
        if google_health.is_token_expired(tokens):
            try:
                tokens = await google_health.refresh_access_token(tokens)
            except httpx.HTTPStatusError as exc:
                await db.finish_source_sync_run(
                    pool,
                    run["id"],
                    "failed",
                    0,
                    0,
                    error="Google Health token refresh failed; reauthorize the connector.",
                )
                raise HTTPException(
                    status_code=401,
                    detail="Google Health token refresh failed. Reauthorize Google Health, especially if you changed selected data types or scopes.",
                ) from exc
            except ValueError as exc:
                await db.finish_source_sync_run(
                    pool,
                    run["id"],
                    "failed",
                    0,
                    0,
                    error=str(exc),
                )
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            await db.upsert_source_connection(
                pool,
                google_health.SOURCE_NAME,
                "active",
                {**config, "tokens": tokens},
            )
        since = datetime.now(UTC) - timedelta(days=lookback_days)
        for data_type in selected_data_types:
            try:
                points = await google_health.list_data_points(tokens["access_token"], data_type, since=since)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                failures[data_type] = str(exc)
                continue
            seen += len(points)
            for point in points:
                normalized = google_health.normalize_data_point(data_type, point)
                external_id = normalized.get("name")
                if not external_id:
                    continue
                record = await db.upsert_source_record(
                    pool,
                    {
                        "source_name": google_health.SOURCE_NAME,
                        "external_id": external_id,
                        "record_type": data_type,
                        "occurred_at": google_health.occurred_at(normalized),
                        "raw_payload": point,
                        "normalized_payload": normalized,
                    },
                )
                imported_records.append(record)
                await write_typed_health_rows(pool, record)
        daily_summary_count = await write_daily_summaries(pool, imported_records)
        status = "partial" if failures else "success"
        await db.finish_source_sync_run(
            pool,
            run["id"],
            status,
            seen,
            len(imported_records),
            metadata={"failures": failures, "daily_summary_count": daily_summary_count},
        )
        return {
            "source_name": google_health.SOURCE_NAME,
            "status": status,
            "data_types": selected_data_types,
            "synced_count": len(imported_records),
            "records_seen": seen,
            "daily_summary_count": daily_summary_count,
            "failures": failures,
            "records": serialize_source_records(imported_records),
        }
    except Exception as exc:
        await db.finish_source_sync_run(pool, run["id"], "error", seen, len(imported_records), error=str(exc))
        raise


async def sync_google_health_records(pool: Any, data_type: str = google_health.RECORD_TYPE_EXERCISE) -> list[dict[str, Any]]:
    result = await sync_google_health_data(pool, data_types=[data_type])
    return result.get("records", [])


def serialize_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(record["id"]),
            "external_id": record["external_id"],
            "record_type": record.get("record_type"),
            "occurred_at": record["occurred_at"].isoformat() if record.get("occurred_at") else None,
            "normalized_payload": db.ensure_dict(record["normalized_payload"]),
        }
        for record in records
    ]


def serialize_google_health_sync(records: list[dict[str, Any]], data_type: str) -> dict[str, Any]:
    return {
        "source_name": google_health.SOURCE_NAME,
        "record_type": data_type,
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


@app.post("/workflows/google-health/coach-review", dependencies=[Depends(require_api_key)])
async def google_health_coach_review(request: GoogleHealthCoachReviewRequest) -> dict[str, Any]:
    pool = require_db_pool()
    if request.force_sync:
        await sync_google_health_records(pool)

    since = datetime.now(UTC) - timedelta(days=request.period_days)
    records = await db.list_source_records(
        pool,
        google_health.SOURCE_NAME,
        google_health.RECORD_TYPE_EXERCISE,
        since,
    )
    activity_summary = health_coach.summarize_exercise_records(records, request.period_days)
    memories = await db.search_memories(
        pool,
        "health fitness exercise workout recovery sleep goals consistency",
        8,
        {},
    )
    active_goals = await db.list_active_goals(pool, category="health", limit=10)
    workflow_request = {
        "period_days": request.period_days,
        "question": request.question,
        "goals": request.goals,
        "active_goals": [
            {
                "id": str(goal["id"]),
                "name": goal["name"],
                "category": goal["category"],
                "target": goal["target"],
                "notes": goal.get("notes"),
            }
            for goal in active_goals
        ],
        "relevant_memories": [
            {
                "id": str(memory["id"]),
                "kind": memory["kind"],
                "content": memory["content"],
                "source": memory["source"],
                "metadata": db.ensure_dict(memory.get("metadata")),
            }
            for memory in memories
        ],
        "activity_summary": activity_summary,
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{LANGGRAPH_WORKFLOWS_URL}/workflows/google-health/coach-review",
                json=workflow_request,
            )
            response.raise_for_status()
            review = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Google Health coach workflow failed: {exc}") from exc

    recommendation = review.get("recommendation") or {
        "title": "Review Google Health coach summary",
        "body": review.get("summary", ""),
        "reason": "Generated from Google Health coach review.",
        "metadata": {"workflow": "google_health_coach_review"},
    }
    created_recommendation = await db.insert_recommendation(pool, recommendation)
    created_memories = []
    for memory in review.get("memory_candidates") or []:
        if memory.get("content"):
            created_memories.append(
                await db.insert_memory(
                    pool,
                    {
                        "kind": memory.get("kind", "health_pattern"),
                        "content": memory["content"],
                        "source": memory.get("source", "google_health_coach_review"),
                        "metadata": memory.get("metadata") or {"period_days": request.period_days},
                    },
                )
            )

    return {
        **review,
        "created_recommendation_id": str(created_recommendation["id"]),
        "created_memory_ids": [str(memory["id"]) for memory in created_memories],
    }


@app.post("/connectors/csv/import", dependencies=[Depends(require_api_key)])
async def import_health_csv(request: CsvImportRequest) -> dict[str, Any]:
    pool = require_db_pool()
    rows = health_ingest.read_csv_rows(request.file_path)
    records = []
    for row in rows:
        normalized = health_ingest.normalize_csv_row(request.source, row)
        external_id = health_ingest.stable_external_id(request.source, row)
        record = await db.upsert_source_record(
            pool,
            {
                "source_name": request.source,
                "external_id": external_id,
                "record_type": normalized["data_type"],
                "occurred_at": health_ingest.parse_datetime(normalized.get("observed_at") or normalized.get("start_time")),
                "raw_payload": row,
                "normalized_payload": normalized,
            },
        )
        records.append(record)
        await write_typed_health_rows(pool, record)
    daily_summary_count = await write_daily_summaries(pool, records)
    return {
        "source_name": request.source,
        "imported_count": len(records),
        "daily_summary_count": daily_summary_count,
        "records": serialize_source_records(records),
    }


@app.post("/workflows/health/coach-review", dependencies=[Depends(require_api_key)])
async def unified_health_coach_review(request: UnifiedHealthCoachReviewRequest) -> dict[str, Any]:
    pool = require_db_pool()
    if request.force_sync:
        await sync_google_health_data(pool)

    since = datetime.now(UTC) - timedelta(days=request.period_days)
    since_date = since.date()
    daily_summaries = await db.list_health_daily_summaries(pool, since_date)
    sessions = await db.list_recent_health_sessions(pool, since)
    health_summary = health_ingest.build_health_summary(daily_summaries, sessions, request.period_days)
    memories = await db.search_memories(
        pool,
        "health fitness exercise workout recovery sleep nutrition goals consistency",
        8,
        {},
    )
    active_goals = await db.list_active_goals(pool, category="health", limit=10)
    workflow_request = {
        "period_days": request.period_days,
        "question": request.question,
        "goals": request.goals,
        "active_goals": [
            {
                "id": str(goal["id"]),
                "name": goal["name"],
                "category": goal["category"],
                "target": goal["target"],
                "notes": goal.get("notes"),
            }
            for goal in active_goals
        ],
        "relevant_memories": [
            {
                "id": str(memory["id"]),
                "kind": memory["kind"],
                "content": memory["content"],
                "source": memory["source"],
                "metadata": db.ensure_dict(memory.get("metadata")),
            }
            for memory in memories
        ],
        "health_summary": health_summary,
        "activity_summary": health_summary.get("activity", {}),
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{LANGGRAPH_WORKFLOWS_URL}/workflows/health/coach-review",
                json=workflow_request,
            )
            response.raise_for_status()
            review = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Health coach workflow failed: {exc}") from exc

    recommendation = review.get("recommendation") or {
        "title": "Review health coach summary",
        "body": review.get("summary", ""),
        "reason": "Generated from unified health coach review.",
        "metadata": {"workflow": "health_coach_review"},
    }
    created_recommendation = await db.insert_recommendation(pool, recommendation)
    created_memories = []
    for memory in review.get("memory_candidates") or []:
        if memory.get("content"):
            created_memories.append(
                await db.insert_memory(
                    pool,
                    {
                        "kind": memory.get("kind", "health_pattern"),
                        "content": memory["content"],
                        "source": memory.get("source", "health_coach_review"),
                        "metadata": memory.get("metadata") or {"period_days": request.period_days},
                    },
                )
            )

    return {
        **review,
        "health_summary": health_summary,
        "created_recommendation_id": str(created_recommendation["id"]),
        "created_memory_ids": [str(memory["id"]) for memory in created_memories],
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
