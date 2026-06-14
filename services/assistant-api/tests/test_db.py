from datetime import date

from app import db


def test_ensure_date_accepts_iso_date_string() -> None:
    assert db.ensure_date("2026-06-14") == date(2026, 6, 14)


def test_ensure_date_accepts_date() -> None:
    value = date(2026, 6, 14)
    assert db.ensure_date(value) is value
