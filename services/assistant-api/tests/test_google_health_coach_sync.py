from datetime import datetime, timezone

import pytest

from app import main


@pytest.mark.asyncio
async def test_sync_google_health_records_uses_data_type_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = object()

    async def fake_get_source_connection(pool_arg, source_name):
        return {
            "status": "active",
            "config": {
                "tokens": {
                    "access_token": "access-token",
                    "expires_at": (datetime.now(timezone.utc).isoformat()),
                }
            },
        }

    async def fake_create_source_sync_run(pool_arg, source_name, data_types, metadata=None):
        return {"id": "sync-run-id"}

    async def fake_finish_source_sync_run(*args, **kwargs):
        return {"id": "sync-run-id"}

    async def fake_list_data_points(access_token, data_type, since=None):
        return [
            {
                "name": "users/123/dataTypes/exercise/dataPoints/abc",
                "dataSource": {"platform": "FITBIT", "recordingMethod": "MANUAL"},
                "exercise": {
                    "interval": {
                        "startTime": "2026-06-06T12:00:00Z",
                        "endTime": "2026-06-06T12:30:00Z",
                    },
                    "exerciseType": "WALKING",
                    "metricsSummary": {"caloriesKcal": 100},
                },
            }
        ]

    async def fake_upsert_source_record(pool_arg, record):
        assert record["record_type"] == "exercise"
        assert record["external_id"] == "users/123/dataTypes/exercise/dataPoints/abc"
        return {
            "id": "record-id",
            "external_id": record["external_id"],
            "record_type": record["record_type"],
            "occurred_at": datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
            "normalized_payload": record["normalized_payload"],
        }

    async def fake_upsert_source_connection(*args, **kwargs):
        return {"id": "connection-id"}

    async def fake_write_typed_health_rows(*args, **kwargs):
        return None

    async def fake_write_daily_summaries(*args, **kwargs):
        return 1

    monkeypatch.setattr(main.db, "get_source_connection", fake_get_source_connection)
    monkeypatch.setattr(main.google_health, "is_token_expired", lambda tokens: False)
    monkeypatch.setattr(main.google_health, "list_data_points", fake_list_data_points)
    monkeypatch.setattr(main.db, "create_source_sync_run", fake_create_source_sync_run)
    monkeypatch.setattr(main.db, "finish_source_sync_run", fake_finish_source_sync_run)
    monkeypatch.setattr(main.db, "upsert_source_record", fake_upsert_source_record)
    monkeypatch.setattr(main.db, "upsert_source_connection", fake_upsert_source_connection)
    monkeypatch.setattr(main, "write_typed_health_rows", fake_write_typed_health_rows)
    monkeypatch.setattr(main, "write_daily_summaries", fake_write_daily_summaries)

    records = await main.sync_google_health_records(pool, "exercise")

    assert len(records) == 1
    assert records[0]["external_id"] == "users/123/dataTypes/exercise/dataPoints/abc"
