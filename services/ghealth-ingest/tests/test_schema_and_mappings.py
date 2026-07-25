import json
from pathlib import Path

from app.schema import INITIAL_TYPES, expected_rows_key
from app.worker import civil_date, point_coordinates, point_identity, source_of


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
