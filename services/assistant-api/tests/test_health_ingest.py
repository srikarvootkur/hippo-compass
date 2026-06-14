import json
from datetime import datetime, timezone

from app import health_ingest


def test_source_record_to_typed_rows_creates_sleep_session() -> None:
    observation, session = health_ingest.source_record_to_typed_rows(
        {
            "id": "record-id",
            "source_name": "google_health",
            "external_id": "sleep-id",
            "record_type": "sleep",
            "normalized_payload": {
                "data_type": "sleep",
                "record_type": "session",
                "category": "sleep",
                "start_time": "2026-03-03T20:57:30Z",
                "end_time": "2026-03-04T04:41:30Z",
                "sleep_summary": {"minutesAsleep": "407"},
            },
        }
    )

    assert observation is None
    assert session is not None
    assert session["data_type"] == "sleep"
    assert session["category"] == "sleep"
    assert session["metrics"]["sleep_summary"] == {"minutesAsleep": "407"}


def test_source_record_to_typed_rows_accepts_json_string_payload() -> None:
    observation, session = health_ingest.source_record_to_typed_rows(
        {
            "id": "record-id",
            "source_name": "google_health",
            "external_id": "steps-id",
            "record_type": "steps",
            "normalized_payload": json.dumps(
                {
                    "data_type": "steps",
                    "record_type": "interval",
                    "category": "activity",
                    "start_time": "2026-06-06T12:00:00Z",
                    "numeric_summary": {"steps": 1200},
                }
            ),
        }
    )

    assert session is None
    assert observation is not None
    assert observation["data_type"] == "steps"
    assert observation["value_numeric"] == 1200


def test_summarize_normalized_records_groups_daily_metrics() -> None:
    summaries = health_ingest.summarize_normalized_records(
        [
            {
                "source_name": "google_health",
                "occurred_at": datetime(2026, 6, 6, tzinfo=timezone.utc),
                "normalized_payload": {
                    "category": "activity",
                    "civil_date": "2026-06-06",
                    "numeric_summary": {"steps": 1200},
                },
            },
            {
                "source_name": "google_health",
                "occurred_at": datetime(2026, 6, 6, tzinfo=timezone.utc),
                "normalized_payload": {
                    "category": "activity",
                    "civil_date": "2026-06-06",
                    "numeric_summary": {"steps": 800},
                },
            },
        ]
    )

    assert len(summaries) == 1
    assert summaries[0]["metrics"]["record_count"] == 2
    assert summaries[0]["metrics"]["steps"] == 2000


def test_summarize_normalized_records_accepts_json_string_payload() -> None:
    summaries = health_ingest.summarize_normalized_records(
        [
            {
                "source_name": "google_health",
                "occurred_at": datetime(2026, 6, 6, tzinfo=timezone.utc),
                "normalized_payload": json.dumps(
                    {
                        "category": "activity",
                        "civil_date": "2026-06-06",
                        "numeric_summary": {"steps": 1200},
                    }
                ),
            }
        ]
    )

    assert len(summaries) == 1
    assert summaries[0]["summary_date"] == "2026-06-06"
    assert summaries[0]["metrics"]["steps"] == 1200


def test_normalize_hevy_row_calculates_volume() -> None:
    normalized = health_ingest.normalize_hevy_row(
        {
            "Date": "2026-06-06",
            "Exercise": "Bench Press",
            "Weight": "135",
            "Reps": "8",
        }
    )

    assert normalized["data_type"] == "exercise_set"
    assert normalized["category"] == "strength"
    assert normalized["exercise_name"] == "Bench Press"
    assert normalized["volume"] == 1080


def test_normalize_cronometer_row_extracts_macros() -> None:
    normalized = health_ingest.normalize_cronometer_row(
        {
            "Date": "2026-06-06",
            "Food": "Greek yogurt",
            "Calories": "150",
            "Protein": "20",
        }
    )

    assert normalized["data_type"] == "nutrition_log"
    assert normalized["category"] == "nutrition"
    assert normalized["calories"] == 150
    assert normalized["protein_g"] == 20
