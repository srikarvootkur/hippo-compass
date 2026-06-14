from datetime import date, datetime, timezone

import pytest

from app import health_coach
from app import main


def test_summarize_exercise_records_aggregates_google_health_payloads() -> None:
    records = [
        {
            "occurred_at": datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
            "normalized_payload": {
                "platform": "FITBIT",
                "exercise_type": "WALKING",
                "display_name": "Walk",
                "start_time": "2026-06-06T12:00:00Z",
                "active_duration": "1800s",
                "steps": "2500",
                "calories_kcal": 140,
            },
        },
        {
            "occurred_at": datetime(2026, 6, 5, 12, tzinfo=timezone.utc),
            "normalized_payload": {
                "platform": "HEALTH_KIT",
                "exercise_type": "STRENGTH_TRAINING",
                "display_name": "Strength training",
                "start_time": "2026-06-05T12:00:00Z",
                "active_duration": "3600s",
                "steps": None,
                "calories_kcal": 300,
            },
        },
    ]

    summary = health_coach.summarize_exercise_records(records, period_days=7)

    assert summary["record_count"] == 2
    assert summary["active_days"] == 2
    assert summary["total_active_minutes"] == 90
    assert summary["total_steps"] == 2500
    assert summary["total_calories_kcal"] == 440
    assert summary["exercise_type_counts"] == {"WALKING": 1, "STRENGTH_TRAINING": 1}


@pytest.mark.asyncio
async def test_google_health_coach_endpoint_persists_workflow_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    main.app.state.db_pool = object()

    async def fake_sync(pool):
        return []

    async def fake_list_source_records(pool, source_name, record_type, since, limit=500):
        return []

    async def fake_search_memories(pool, query, limit, filters):
        return []

    async def fake_list_active_goals(pool, category=None, limit=20):
        return []

    async def fake_insert_recommendation(pool, recommendation):
        return {"id": "rec-id"}

    async def fake_insert_memory(pool, memory):
        return {"id": "mem-id"}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "workflow": "google_health_coach_review",
                "period_days": 7,
                "data_sources": ["google_health"],
                "summary": "Summary",
                "patterns": [],
                "next_actions": ["Do one easy walk."],
                "citations": [],
                "recommendation": {
                    "title": "Review Google Health coach summary",
                    "body": "Do one easy walk.",
                    "reason": "Test",
                    "metadata": {"workflow": "google_health_coach_review"},
                },
                "memory_candidates": [
                    {
                        "kind": "health_pattern",
                        "content": "Test pattern",
                        "source": "google_health_coach_review",
                    }
                ],
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            assert url.endswith("/workflows/google-health/coach-review")
            assert json["activity_summary"]["record_count"] == 0
            return FakeResponse()

    monkeypatch.setattr(main, "sync_google_health_records", fake_sync)
    monkeypatch.setattr(main.db, "list_source_records", fake_list_source_records)
    monkeypatch.setattr(main.db, "search_memories", fake_search_memories)
    monkeypatch.setattr(main.db, "list_active_goals", fake_list_active_goals)
    monkeypatch.setattr(main.db, "insert_recommendation", fake_insert_recommendation)
    monkeypatch.setattr(main.db, "insert_memory", fake_insert_memory)
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    response = await main.google_health_coach_review(
        main.GoogleHealthCoachReviewRequest(
            question="Review my week.",
            period_days=7,
            force_sync=True,
        )
    )

    assert response["created_recommendation_id"] == "rec-id"
    assert response["created_memory_ids"] == ["mem-id"]


@pytest.mark.asyncio
async def test_unified_health_coach_uses_date_for_daily_summary_query(monkeypatch: pytest.MonkeyPatch) -> None:
    main.app.state.db_pool = object()

    async def fake_list_health_daily_summaries(pool, since_date, limit=500):
        assert isinstance(since_date, date)
        return []

    async def fake_list_recent_health_sessions(pool, since, limit=200):
        return []

    async def fake_search_memories(pool, query, limit, filters):
        return []

    async def fake_list_active_goals(pool, category=None, limit=20):
        return []

    async def fake_insert_recommendation(pool, recommendation):
        return {"id": "rec-id"}

    async def fake_insert_memory(pool, memory):
        return {"id": "mem-id"}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "workflow": "health_coach_review",
                "period_days": 7,
                "data_sources": [],
                "summary": "Summary",
                "patterns": [],
                "next_actions": ["Pick one consistency target."],
                "citations": [],
                "recommendation": {
                    "title": "Review health coach summary",
                    "body": "Pick one consistency target.",
                    "reason": "Test",
                    "metadata": {"workflow": "health_coach_review"},
                },
                "memory_candidates": [],
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            assert url.endswith("/workflows/health/coach-review")
            return FakeResponse()

    monkeypatch.setattr(main.db, "list_health_daily_summaries", fake_list_health_daily_summaries)
    monkeypatch.setattr(main.db, "list_recent_health_sessions", fake_list_recent_health_sessions)
    monkeypatch.setattr(main.db, "search_memories", fake_search_memories)
    monkeypatch.setattr(main.db, "list_active_goals", fake_list_active_goals)
    monkeypatch.setattr(main.db, "insert_recommendation", fake_insert_recommendation)
    monkeypatch.setattr(main.db, "insert_memory", fake_insert_memory)
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    response = await main.unified_health_coach_review(
        main.UnifiedHealthCoachReviewRequest(
            question="Review my week.",
            period_days=7,
            force_sync=False,
        )
    )

    assert response["created_recommendation_id"] == "rec-id"
