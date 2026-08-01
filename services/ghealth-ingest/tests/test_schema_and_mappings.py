import json
from pathlib import Path

from app.schema import INITIAL_TYPES, expected_rows_key
from app import worker
from app.worker import civil_date, parse_integer, point_coordinates, point_identity, source_of


FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "ghealth_raw_responses.json").read_text())


def test_initial_operations_have_expected_envelopes() -> None:
    for data_type, operation in INITIAL_TYPES.items():
        assert expected_rows_key(operation) in FIXTURES[data_type]


def test_verified_raw_mappings() -> None:
    heart = FIXTURES["heart-rate"]["dataPoints"][0]
    steps = FIXTURES["steps"]["rollupDataPoints"][0]
    sleep = FIXTURES["sleep"]["dataPoints"][0]
    weight = FIXTURES["weight"]["dataPoints"][0]

    assert source_of(heart) == "FITBIT"
    assert point_coordinates("heart-rate", heart)[0].isoformat() == "2026-07-20T12:00:00+00:00"
    assert point_coordinates("steps", steps)[1].isoformat() == "2026-07-20"
    assert point_coordinates("sleep", sleep)[0].isoformat() == "2026-07-20T03:00:00+00:00"
    assert point_coordinates("weight", weight)[0].isoformat() == "2026-07-20T12:00:00+00:00"
    assert point_identity("heart-rate", heart).endswith("hr-1")
    assert civil_date(steps["civilStartTime"]["date"]).isoformat() == "2026-07-20"


def test_unknown_shape_can_still_have_a_stable_raw_identity() -> None:
    point = {"newGoogleField": {"value": 1}}
    assert point_identity("heart-rate", point).startswith("ghealth:heart-rate:")


def test_empty_cli_envelope_is_a_valid_zero_row_page(monkeypatch) -> None:
    monkeypatch.setattr(worker, "command", lambda *args, **kwargs: {})
    response = worker.fetch_page("sleep", "list", worker.date(2026, 7, 18), worker.date(2026, 7, 24), None)
    assert response == {"dataPoints": []}


def test_null_data_points_is_a_valid_zero_row_page(monkeypatch) -> None:
    monkeypatch.setattr(worker, "command", lambda *args, **kwargs: {"dataPoints": None})
    response = worker.fetch_page("sleep", "list", worker.date(2026, 5, 24), worker.date(2026, 5, 30), None)
    assert response == {"dataPoints": []}


def test_parse_integer_handles_google_string_numbers_and_missing_values() -> None:
    assert parse_integer("433") == 433
    assert parse_integer(433) == 433
    assert parse_integer(None) is None
    assert parse_integer("") is None
