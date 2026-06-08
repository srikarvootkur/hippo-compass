from __future__ import annotations

import os
import json
from typing import Any

import asyncpg


def ensure_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


async def create_pool() -> asyncpg.Pool | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    return await asyncpg.create_pool(database_url, min_size=1, max_size=5)


async def insert_memory(pool: asyncpg.Pool, memory: dict[str, Any]) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO memories (kind, content, source, metadata)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING id, kind, content, source, metadata, created_at
        """,
        memory["kind"],
        memory["content"],
        memory["source"],
        json.dumps(memory["metadata"]),
    )
    return dict(row)


async def search_memories(
    pool: asyncpg.Pool,
    query: str,
    limit: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    kind = filters.get("kind")
    if kind:
        rows = await pool.fetch(
            """
            SELECT id, kind, content, source, confidence, metadata, created_at
            FROM memories
            WHERE kind = $1 AND content ILIKE '%' || $2 || '%'
            ORDER BY created_at DESC
            LIMIT $3
            """,
            kind,
            query,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, kind, content, source, confidence, metadata, created_at
            FROM memories
            WHERE content ILIKE '%' || $1 || '%'
            ORDER BY created_at DESC
            LIMIT $2
            """,
            query,
            limit,
        )
    return [dict(row) for row in rows]


async def list_active_goals(pool: asyncpg.Pool, category: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    if category:
        rows = await pool.fetch(
            """
            SELECT id, name, category, status, target, notes, created_at, updated_at
            FROM goals
            WHERE status = 'active' AND category = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            category,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, name, category, status, target, notes, created_at, updated_at
            FROM goals
            WHERE status = 'active'
            ORDER BY updated_at DESC
            LIMIT $1
            """,
            limit,
        )
    results = []
    for row in rows:
        result = dict(row)
        result["target"] = ensure_dict(result.get("target"))
        results.append(result)
    return results


async def insert_approval(pool: asyncpg.Pool, approval: dict[str, Any]) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO approvals (action_type, title, proposed_payload, reason)
        VALUES ($1, $2, $3::jsonb, $4)
        RETURNING id, action_type, title, status, proposed_payload, reason, created_at
        """,
        approval["action_type"],
        approval["title"],
        json.dumps(approval["proposed_payload"]),
        approval.get("reason"),
    )
    return dict(row)


async def insert_journal_entry(pool: asyncpg.Pool, journal: dict[str, Any]) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO journal_entries (entry_date, title, source, content, summary, occurred_at)
        VALUES (COALESCE($1::date, current_date), $2, $3, $4, $5, COALESCE($6::timestamptz, now()))
        RETURNING id, entry_date, title, source, content, summary, occurred_at, created_at
        """,
        journal.get("entry_date"),
        journal.get("title"),
        journal["source"],
        journal["content"],
        journal.get("summary"),
        journal.get("occurred_at"),
    )
    return dict(row)


async def insert_recommendation(pool: asyncpg.Pool, recommendation: dict[str, Any]) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO recommendations (title, body, reason, metadata)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING id, title, body, reason, status, metadata, created_at, updated_at
        """,
        recommendation["title"],
        recommendation["body"],
        recommendation.get("reason"),
        json.dumps(recommendation["metadata"]),
    )
    return dict(row)


async def list_recommendations(pool: asyncpg.Pool, status: str, limit: int) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT id, title, body, reason, status, metadata, created_at, updated_at
        FROM recommendations
        WHERE status = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        status,
        limit,
    )
    return [dict(row) for row in rows]


async def insert_tool_run(pool: asyncpg.Pool, tool_run: dict[str, Any]) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO tool_runs (tool_name, input_json, output_json, status)
        VALUES ($1, $2::jsonb, $3::jsonb, $4)
        RETURNING id, tool_name, input_json, output_json, status, created_at
        """,
        tool_run["tool_name"],
        json.dumps(tool_run.get("input_json") or {}),
        json.dumps(tool_run.get("output_json") or {}),
        tool_run["status"],
    )
    return dict(row)


async def upsert_source_connection(
    pool: asyncpg.Pool,
    source_name: str,
    status: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO source_connections (source_name, status, config)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (source_name)
        DO UPDATE SET status = excluded.status, config = excluded.config, updated_at = now()
        RETURNING id, source_name, status, config, created_at, updated_at
        """,
        source_name,
        status,
        json.dumps(config),
    )
    return dict(row)


async def get_source_connection(pool: asyncpg.Pool, source_name: str) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        """
        SELECT id, source_name, status, config, created_at, updated_at
        FROM source_connections
        WHERE source_name = $1
        """,
        source_name,
    )
    if not row:
        return None
    result = dict(row)
    result["config"] = ensure_dict(result.get("config"))
    return result


async def upsert_source_record(pool: asyncpg.Pool, record: dict[str, Any]) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO source_records (
            source_name,
            external_id,
            record_type,
            occurred_at,
            raw_payload,
            normalized_payload
        )
        VALUES ($1, $2, $3, $4::timestamptz, $5::jsonb, $6::jsonb)
        ON CONFLICT (source_name, external_id)
        DO UPDATE SET
            record_type = excluded.record_type,
            occurred_at = excluded.occurred_at,
            raw_payload = excluded.raw_payload,
            normalized_payload = excluded.normalized_payload,
            created_at = source_records.created_at
        RETURNING id, source_name, external_id, record_type, occurred_at, raw_payload, normalized_payload, created_at
        """,
        record["source_name"],
        record["external_id"],
        record["record_type"],
        record.get("occurred_at"),
        json.dumps(record["raw_payload"]),
        json.dumps(record["normalized_payload"]),
    )
    return dict(row)


async def list_source_records(
    pool: asyncpg.Pool,
    source_name: str,
    record_type: str,
    since: Any,
    limit: int = 500,
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT id, source_name, external_id, record_type, occurred_at, raw_payload, normalized_payload, created_at
        FROM source_records
        WHERE source_name = $1
          AND record_type = $2
          AND occurred_at >= $3::timestamptz
        ORDER BY occurred_at DESC
        LIMIT $4
        """,
        source_name,
        record_type,
        since,
        limit,
    )
    results = []
    for row in rows:
        result = dict(row)
        result["raw_payload"] = ensure_dict(result.get("raw_payload"))
        result["normalized_payload"] = ensure_dict(result.get("normalized_payload"))
        results.append(result)
    return results
