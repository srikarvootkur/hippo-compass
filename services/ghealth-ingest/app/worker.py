from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

from app.schema import INITIAL_TYPES, REQUIRED_OPERATIONS, expected_rows_key


UTC = timezone.utc
GHEALTH = os.getenv("GHEALTH_BIN", "ghealth")
DATABASE_URL = os.getenv("DATABASE_URL", "")
TIMEZONE = os.getenv("GHEALTH_TIMEZONE", "America/New_York")
BACKFILL_DAYS = int(os.getenv("GHEALTH_BACKFILL_DAYS", "90"))
BACKFILL_WINDOW_DAYS = int(os.getenv("GHEALTH_BACKFILL_WINDOW_DAYS", "7"))
OVERLAP_HOURS = int(os.getenv("GHEALTH_OVERLAP_HOURS", "24"))
SYNC_INTERVAL_SECONDS = int(os.getenv("GHEALTH_SYNC_INTERVAL_SECONDS", str(4 * 60 * 60)))


class GHealthError(RuntimeError):
    pass


def command(*args: str, timeout: int = 180) -> dict[str, Any]:
    """Run ghealth without logging command output (it can contain health data)."""
    result = subprocess.run(
        [GHEALTH, *args], text=True, capture_output=True, check=False, timeout=timeout
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "ghealth command failed"
        raise GHealthError(message[:1000])
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GHealthError("ghealth returned non-JSON output") from exc
    if not isinstance(value, dict):
        raise GHealthError("ghealth returned an unexpected JSON envelope")
    return value


def command_text(*args: str) -> str:
    result = subprocess.run([GHEALTH, *args], text=True, capture_output=True, check=False, timeout=60)
    if result.returncode:
        raise GHealthError((result.stderr.strip() or result.stdout.strip() or "ghealth command failed")[:1000])
    return result.stdout


def nested(point: dict[str, Any], *keys: str) -> Any:
    value: Any = point
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def civil_date(value: Any) -> date | None:
    if not isinstance(value, dict):
        return None
    try:
        return date(int(value["year"]), int(value["month"]), int(value["day"]))
    except (KeyError, TypeError, ValueError):
        return None


def source_of(point: dict[str, Any]) -> str:
    data_source = point.get("dataSource") or {}
    device = data_source.get("device") or {}
    application = data_source.get("application") or {}
    return str(device.get("displayName") or application.get("packageName") or data_source.get("platform") or "unknown")


def point_identity(data_type: str, point: dict[str, Any]) -> str:
    name = point.get("name")
    if isinstance(name, str) and name:
        return name
    digest = hashlib.sha256(json.dumps(point, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"ghealth:{data_type}:{digest}"


def point_coordinates(data_type: str, point: dict[str, Any]) -> tuple[datetime | None, date | None]:
    if data_type in {"heart-rate", "weight"}:
        key = "heartRate" if data_type == "heart-rate" else "weight"
        return parse_time(nested(point, key, "sampleTime", "physicalTime")), None
    if data_type in {"sleep", "exercise"}:
        key = data_type
        return parse_time(nested(point, key, "interval", "startTime")), None
    if data_type == "steps":
        return None, civil_date(nested(point, "civilStartTime", "date"))
    return None, None


async def save_schema(pool: asyncpg.Pool, name: str, value: dict[str, Any]) -> None:
    version = command_text("--version").strip() or "unknown"
    await pool.execute(
        """INSERT INTO ghealth_schema_snapshots (cli_version, schema_name, schema_json)
           VALUES ($1, $2, $3::jsonb)
           ON CONFLICT (cli_version, schema_name) DO UPDATE SET schema_json = excluded.schema_json, captured_at = now()""",
        version, name, json.dumps(value),
    )


async def schema_preflight(pool: asyncpg.Pool) -> None:
    """Use CLI discovery as the contract, then persist only schema metadata."""
    type_catalog = command("schema", "types")
    available = {row.get("id"): set(row.get("operations") or []) for row in type_catalog.get("dataTypes", [])}
    for data_type, needed in REQUIRED_OPERATIONS.items():
        if not needed.issubset(available.get(data_type, set())):
            raise GHealthError(f"ghealth schema does not support required operation for {data_type}")
    await save_schema(pool, "types", type_catalog)
    for data_type, operation in INITIAL_TYPES.items():
        detail = command("schema", "type", data_type)
        if operation not in set(detail.get("operations") or []):
            raise GHealthError(f"ghealth schema type {data_type} does not support {operation}")
        await save_schema(pool, f"type:{data_type}", detail)
        # Ensure the documented command remains available without retaining help output.
        command_text("data", data_type, operation, "--help")


def assert_readonly_auth() -> None:
    status = command("auth", "status", "--validate")
    serialized = json.dumps(status).lower()
    if "cloud-platform" in serialized:
        raise GHealthError("ghealth health-data profile contains disallowed cloud-platform scope")
    if not status.get("authenticated", False):
        raise GHealthError("ghealth authentication is not valid; run auth login --scopes-preset readonly")


def fetch_page(data_type: str, operation: str, start: date, end: date, page_token: str | None) -> dict[str, Any]:
    args = ["--raw", "data", data_type, operation, "--from", start.isoformat(), "--to", end.isoformat()]
    if operation == "list":
        args.extend(["--limit", "10000"])
    if page_token and operation == "list":
        args.extend(["--page-token", page_token])
    response = command(*args, timeout=300)
    rows_key = expected_rows_key(operation)
    rows = response.get(rows_key)
    # Google Health can represent a no-data list as {"dataPoints": null}.
    # Normalize that explicit empty value before applying the schema gate.
    if rows is None and rows_key in response and response[rows_key] is None:
        response[rows_key] = []
        rows = response[rows_key]
    # The CLI preserves normal raw envelopes, but an API no-data response can
    # be normalized to {} (or hints only). Treat only that narrow shape as an
    # empty page; any real, unfamiliar payload remains a schema error.
    if rows is None and (not response or set(response).issubset({"_hints"})):
        response[rows_key] = []
        rows = response[rows_key]
    if not isinstance(rows, list):
        raise GHealthError(f"ghealth {data_type} {operation} response lacks {rows_key}")
    if "nextPageToken" in response and not isinstance(response["nextPageToken"], str):
        raise GHealthError("ghealth returned an invalid nextPageToken")
    return response


async def insert_point(pool: asyncpg.Pool, run_id: int, data_type: str, operation: str, point: dict[str, Any]) -> None:
    raw_payload = json.dumps(point, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(raw_payload.encode()).hexdigest()
    external_id = point_identity(data_type, point)
    point_time, point_date = point_coordinates(data_type, point)
    raw_id = await pool.fetchval(
        """INSERT INTO ghealth_raw_points
             (data_type, operation, source, point_time, point_date, external_id, payload_hash, payload, sync_run_id)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
           ON CONFLICT (data_type, operation, external_id, payload_hash)
           DO UPDATE SET updated_at = now(), sync_run_id = excluded.sync_run_id
           RETURNING id""",
        data_type, operation, source_of(point), point_time, point_date, external_id, payload_hash, raw_payload, run_id,
    )
    await project_typed_point(pool, raw_id, data_type, external_id, point)


async def project_typed_point(pool: asyncpg.Pool, raw_id: int, data_type: str, external_id: str, point: dict[str, Any]) -> None:
    source = source_of(point)
    if data_type == "heart-rate":
        measured_at = parse_time(nested(point, "heartRate", "sampleTime", "physicalTime"))
        bpm = nested(point, "heartRate", "beatsPerMinute")
        if measured_at is None or bpm is None:
            return
        await pool.execute("""INSERT INTO ghealth_heart_rate_points (source, measured_at, beats_per_minute, raw_point_id)
          VALUES ($1,$2,$3,$4) ON CONFLICT (source, measured_at) DO UPDATE
          SET beats_per_minute=excluded.beats_per_minute, raw_point_id=excluded.raw_point_id""", source, measured_at, float(bpm), raw_id)
    elif data_type == "steps":
        summary_date = civil_date(nested(point, "civilStartTime", "date"))
        count = nested(point, "steps", "countSum")
        if summary_date is None or count is None:
            return
        await pool.execute("""INSERT INTO ghealth_daily_steps (summary_date, step_count, raw_point_id) VALUES ($1,$2,$3)
          ON CONFLICT (summary_date) DO UPDATE SET step_count=excluded.step_count, raw_point_id=excluded.raw_point_id""", summary_date, int(count), raw_id)
    elif data_type == "sleep":
        start, end = parse_time(nested(point, "sleep", "interval", "startTime")), parse_time(nested(point, "sleep", "interval", "endTime"))
        if start is None or end is None:
            return
        summary = nested(point, "sleep", "summary") or {}
        await pool.execute("""INSERT INTO ghealth_sleep_sessions
          (external_id,start_time,end_time,minutes_asleep,minutes_awake,total_minutes,source,sleep_type,raw_point_id)
          VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (external_id) DO UPDATE SET
          start_time=excluded.start_time,end_time=excluded.end_time,minutes_asleep=excluded.minutes_asleep,
          minutes_awake=excluded.minutes_awake,total_minutes=excluded.total_minutes,source=excluded.source,
          sleep_type=excluded.sleep_type,raw_point_id=excluded.raw_point_id""", external_id, start, end,
          summary.get("minutesAsleep"), summary.get("minutesAwake"), summary.get("minutesInSleepPeriod"), source,
          nested(point, "sleep", "type"), raw_id)
    elif data_type == "exercise":
        start, end = parse_time(nested(point, "exercise", "interval", "startTime")), parse_time(nested(point, "exercise", "interval", "endTime"))
        if start is None or end is None:
            return
        exercise = point.get("exercise") or {}
        metrics = exercise.get("metricsSummary") or {}
        await pool.execute("""INSERT INTO ghealth_exercise_sessions
          (external_id,start_time,end_time,source,exercise_type,title,metrics,raw_point_id)
          VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8) ON CONFLICT (external_id) DO UPDATE SET
          start_time=excluded.start_time,end_time=excluded.end_time,source=excluded.source,exercise_type=excluded.exercise_type,
          title=excluded.title,metrics=excluded.metrics,raw_point_id=excluded.raw_point_id""", external_id, start, end, source,
          exercise.get("exerciseType"), exercise.get("title") or exercise.get("displayName"), json.dumps(metrics), raw_id)
    elif data_type == "weight":
        measured_at = parse_time(nested(point, "weight", "sampleTime", "physicalTime"))
        grams = nested(point, "weight", "weightGrams")
        if measured_at is None or grams is None:
            return
        await pool.execute("""INSERT INTO ghealth_weight_points (source, measured_at, weight_grams, raw_point_id)
          VALUES ($1,$2,$3,$4) ON CONFLICT (source, measured_at) DO UPDATE
          SET weight_grams=excluded.weight_grams, raw_point_id=excluded.raw_point_id""", source, measured_at, float(grams), raw_id)


async def sync_window(pool: asyncpg.Pool, sync_kind: str, start: date, end: date) -> bool:
    succeeded = True
    for data_type, operation in INITIAL_TYPES.items():
        run_id = await pool.fetchval("""INSERT INTO ghealth_sync_runs (sync_kind,data_type,operation,from_date,to_date)
          VALUES ($1,$2,$3,$4,$5) RETURNING id""", sync_kind, data_type, operation, start, end)
        pages = rows_loaded = 0
        try:
            token: str | None = None
            while True:
                response = fetch_page(data_type, operation, start, end, token)
                pages += 1
                for point in response[expected_rows_key(operation)]:
                    if not isinstance(point, dict):
                        raise GHealthError("ghealth returned a non-object data point")
                    await insert_point(pool, run_id, data_type, operation, point)
                    rows_loaded += 1
                token = response.get("nextPageToken") or None
                if token and operation == "daily-rollup":
                    # ghealth follows daily-rollup POST pages internally. If its
                    # safety cap is ever reached, this CLI version has no
                    # --page-token flag for this command, so fail visibly.
                    raise GHealthError("daily-rollup exceeded ghealth pagination safety cap; narrow the sync window")
                if token is None:
                    break
            await pool.execute("UPDATE ghealth_sync_runs SET status='success',finished_at=now(),page_count=$2,rows_loaded=$3 WHERE id=$1", run_id, pages, rows_loaded)
        except Exception as exc:
            succeeded = False
            await pool.execute("UPDATE ghealth_sync_runs SET status='failed',finished_at=now(),page_count=$2,rows_loaded=$3,error=$4 WHERE id=$1", run_id, pages, rows_loaded, str(exc)[:2000])
            print(json.dumps({"event": "ghealth_sync_failed", "data_type": data_type, "error": str(exc)[:300]}), flush=True)
    return succeeded


async def initial_backfill_needed(pool: asyncpg.Pool) -> bool:
    return not bool(await pool.fetchval("SELECT 1 FROM ghealth_ingestion_state WHERE state_key='backfill_complete'"))


async def run_once() -> None:
    import asyncpg

    if not DATABASE_URL:
        raise GHealthError("DATABASE_URL is required")
    assert_readonly_auth()
    async with asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3) as pool:
        await schema_preflight(pool)
        today = datetime.now().date()
        if await initial_backfill_needed(pool):
            start = today - timedelta(days=BACKFILL_DAYS)
            completed = True
            while start < today:
                end = min(start + timedelta(days=BACKFILL_WINDOW_DAYS - 1), today)
                completed = await sync_window(pool, "backfill", start, end) and completed
                start = end + timedelta(days=1)
            if completed:
                await pool.execute("""INSERT INTO ghealth_ingestion_state (state_key, state_value)
                  VALUES ('backfill_complete', jsonb_build_object('completed_at', now()))
                  ON CONFLICT (state_key) DO UPDATE SET state_value=excluded.state_value, updated_at=now()""")
        await sync_window(pool, "overlap", today - timedelta(hours=OVERLAP_HOURS), today)


async def main() -> None:
    while True:
        try:
            await run_once()
        except Exception as exc:
            print(json.dumps({"event": "ghealth_ingest_unavailable", "error": str(exc)[:300]}), flush=True)
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
