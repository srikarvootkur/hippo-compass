from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M", "%m/%d/%y %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def stable_external_id(source_name: str, row: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:32]
    return f"{source_name}:csv:{digest}"


def first_present(row: dict[str, Any], names: list[str]) -> Any:
    lowered = {key.lower().strip(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered and lowered[name.lower()] not in (None, ""):
            return lowered[name.lower()]
    return None


def ensure_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def source_record_to_typed_rows(record: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_name = record["source_name"]
    normalized = ensure_dict(record.get("normalized_payload"))
    record_type = normalized.get("record_type") or record.get("record_type")
    data_type = normalized.get("data_type") or record.get("record_type")
    external_id = record["external_id"]
    category = normalized.get("category") or "other"
    source_record_id = record.get("id")

    if record_type in {"session", "food", "workout", "exercise_set"} or data_type in {"exercise", "sleep", "electrocardiogram"}:
        return None, {
            "source_record_id": source_record_id,
            "source_name": source_name,
            "data_type": data_type,
            "external_id": external_id,
            "category": category,
            "session_type": normalized.get("exercise_type") or normalized.get("session_type") or normalized.get("type"),
            "title": normalized.get("display_name") or normalized.get("title") or normalized.get("exercise_name"),
            "start_time": parse_datetime(normalized.get("start_time") or normalized.get("observed_at")),
            "end_time": parse_datetime(normalized.get("end_time")),
            "metrics": normalized,
        }

    numeric_summary = normalized.get("numeric_summary") or {}
    value_numeric = None
    unit = None
    if numeric_summary:
        key, value_numeric = next(iter(numeric_summary.items()))
        unit = key
    return {
        "source_record_id": source_record_id,
        "source_name": source_name,
        "data_type": data_type,
        "external_id": external_id,
        "category": category,
        "observed_at": parse_datetime(normalized.get("observed_at") or normalized.get("sample_time") or normalized.get("start_time")),
        "start_time": parse_datetime(normalized.get("start_time")),
        "end_time": parse_datetime(normalized.get("end_time")),
        "value_numeric": value_numeric,
        "value_text": normalized.get("value_text"),
        "unit": unit,
        "summary": normalized,
    }, None


def daily_summary_key(normalized: dict[str, Any], fallback: datetime | None = None) -> str | None:
    if normalized.get("civil_date"):
        return normalized["civil_date"]
    observed = parse_datetime(normalized.get("observed_at") or normalized.get("start_time") or normalized.get("sample_time"))
    if observed:
        return observed.date().isoformat()
    if fallback:
        return fallback.date().isoformat()
    return None


def empty_health_summary(period_days: int) -> dict[str, Any]:
    return {
        "period_days": period_days,
        "data_sources": [],
        "daily_summary_count": 0,
        "categories": {},
        "activity": {},
        "sleep": {},
        "heart": {},
        "nutrition": {},
        "strength": {},
        "missing": ["No typed health summaries were found for the selected period."],
    }


def build_health_summary(
    daily_summaries: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    period_days: int,
) -> dict[str, Any]:
    if not daily_summaries and not sessions:
        return empty_health_summary(period_days)

    sources = sorted({row["source_name"] for row in daily_summaries} | {row["source_name"] for row in sessions})
    categories: dict[str, dict[str, Any]] = {}
    for row in daily_summaries:
        category = row["category"]
        metrics = row.get("metrics") or {}
        bucket = categories.setdefault(category, {"days": 0, "metrics": {}})
        bucket["days"] += 1
        for key, value in metrics.items():
            number = parse_number(value)
            if number is not None:
                bucket["metrics"][key] = round(bucket["metrics"].get(key, 0.0) + number, 2)

    strength_sessions = [row for row in sessions if row["source_name"] == "hevy" or row.get("category") == "strength"]
    sleep_sessions = [row for row in sessions if row.get("category") == "sleep" or row.get("data_type") == "sleep"]
    activity_sessions = [row for row in sessions if row.get("category") == "activity"]

    strength_volume = 0.0
    top_exercises: dict[str, float] = {}
    for session in strength_sessions:
        metrics = session.get("metrics") or {}
        volume = parse_number(metrics.get("volume")) or 0.0
        strength_volume += volume
        name = metrics.get("exercise_name") or session.get("title") or "Unknown"
        top_exercises[name] = top_exercises.get(name, 0.0) + volume

    sleep_minutes = 0.0
    for session in sleep_sessions:
        metrics = session.get("metrics") or {}
        sleep_minutes += parse_number(metrics.get("minutes_asleep") or metrics.get("minutes_in_sleep_period")) or 0.0

    return {
        "period_days": period_days,
        "data_sources": sources,
        "daily_summary_count": len(daily_summaries),
        "categories": categories,
        "activity": {
            "session_count": len(activity_sessions),
            "daily_metrics": categories.get("activity", {}).get("metrics", {}),
        },
        "sleep": {
            "session_count": len(sleep_sessions),
            "total_minutes_asleep": round(sleep_minutes, 1),
            "average_minutes_asleep": round(sleep_minutes / max(len(sleep_sessions), 1), 1) if sleep_sessions else 0,
            "daily_metrics": categories.get("sleep", {}).get("metrics", {}),
        },
        "heart": {
            "daily_metrics": categories.get("heart", {}).get("metrics", {}),
            "recovery_metrics": categories.get("recovery", {}).get("metrics", {}),
        },
        "nutrition": {
            "daily_metrics": categories.get("nutrition", {}).get("metrics", {}),
        },
        "strength": {
            "session_count": len(strength_sessions),
            "total_volume": round(strength_volume, 1),
            "top_exercises_by_volume": dict(sorted(top_exercises.items(), key=lambda item: item[1], reverse=True)[:8]),
        },
        "missing": missing_categories(categories, sessions),
    }


def missing_categories(categories: dict[str, Any], sessions: list[dict[str, Any]]) -> list[str]:
    present = set(categories)
    present.update(row.get("category") for row in sessions)
    expected = {"activity", "sleep", "heart", "recovery", "nutrition", "body"}
    return [category for category in sorted(expected - present) if category]


def summarize_normalized_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        normalized = ensure_dict(record.get("normalized_payload"))
        day = daily_summary_key(normalized, record.get("occurred_at"))
        if not day:
            continue
        key = (record["source_name"], day, normalized.get("category") or "other")
        bucket = buckets.setdefault(
            key,
            {
                "source_name": record["source_name"],
                "summary_date": day,
                "category": normalized.get("category") or "other",
                "metrics": {"record_count": 0},
            },
        )
        bucket["metrics"]["record_count"] += 1
        for metric, value in (normalized.get("numeric_summary") or {}).items():
            number = parse_number(value)
            if number is not None:
                bucket["metrics"][metric] = round(bucket["metrics"].get(metric, 0.0) + number, 2)
    return list(buckets.values())


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as csvfile:
        return list(csv.DictReader(csvfile))


def normalize_hevy_row(row: dict[str, Any]) -> dict[str, Any]:
    started_at = parse_datetime(first_present(row, ["start_time", "started_at", "date", "workout date"]))
    exercise_name = first_present(row, ["exercise_title", "exercise", "exercise name", "title"])
    weight = parse_number(first_present(row, ["weight_kg", "weight", "weight (kg)", "lbs"]))
    reps = parse_number(first_present(row, ["reps", "repetitions"]))
    volume = (weight or 0) * (reps or 0)
    return {
        "data_type": "exercise_set",
        "record_type": "exercise_set",
        "category": "strength",
        "start_time": started_at.isoformat() if started_at else None,
        "observed_at": started_at.isoformat() if started_at else None,
        "exercise_name": exercise_name,
        "workout_title": first_present(row, ["workout_title", "workout", "routine"]),
        "set_index": first_present(row, ["set_index", "set", "set number"]),
        "set_type": first_present(row, ["set_type", "type"]),
        "weight": weight,
        "reps": reps,
        "volume": volume,
        "distance": parse_number(first_present(row, ["distance", "distance_km"])),
        "duration_seconds": parse_number(first_present(row, ["duration_seconds", "seconds", "duration"])),
        "notes": first_present(row, ["notes", "note"]),
        "numeric_summary": {"volume": volume, "reps": reps or 0, "weight": weight or 0},
    }


def normalize_cronometer_row(row: dict[str, Any]) -> dict[str, Any]:
    observed_at = parse_datetime(first_present(row, ["date", "day", "timestamp"]))
    calories = parse_number(first_present(row, ["energy (kcal)", "calories", "kcal"]))
    protein = parse_number(first_present(row, ["protein (g)", "protein", "protein_g"]))
    carbs = parse_number(first_present(row, ["carbs (g)", "carbohydrates (g)", "carbs"]))
    fat = parse_number(first_present(row, ["fat (g)", "fat"]))
    fiber = parse_number(first_present(row, ["fiber (g)", "fiber"]))
    return {
        "data_type": "nutrition_log",
        "record_type": "sample",
        "category": "nutrition",
        "observed_at": observed_at.isoformat() if observed_at else None,
        "civil_date": observed_at.date().isoformat() if observed_at else None,
        "food_name": first_present(row, ["food", "food name", "name"]),
        "meal": first_present(row, ["meal", "group"]),
        "calories": calories,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        "fiber_g": fiber,
        "numeric_summary": {
            "calories": calories or 0,
            "protein_g": protein or 0,
            "carbs_g": carbs or 0,
            "fat_g": fat or 0,
            "fiber_g": fiber or 0,
        },
    }


def normalize_csv_row(source: str, row: dict[str, Any]) -> dict[str, Any]:
    if source == "hevy":
        return normalize_hevy_row(row)
    if source == "cronometer":
        return normalize_cronometer_row(row)
    raise ValueError(f"Unsupported CSV source: {source}")
