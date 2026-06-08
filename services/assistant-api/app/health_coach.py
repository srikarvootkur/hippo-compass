from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_seconds(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("s"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def iso_day(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def summarize_exercise_records(records: list[dict[str, Any]], period_days: int) -> dict[str, Any]:
    total_steps = 0.0
    total_calories = 0.0
    total_active_seconds = 0.0
    exercise_types: dict[str, int] = {}
    platforms: dict[str, int] = {}
    active_days: set[str] = set()
    recent_records = []

    for record in records:
        payload = record.get("normalized_payload") or {}
        exercise_type = payload.get("exercise_type") or payload.get("display_name") or "UNKNOWN"
        platform = payload.get("platform") or "UNKNOWN"
        day = iso_day(payload.get("start_time") or record.get("occurred_at"))
        if day:
            active_days.add(day)
        exercise_types[exercise_type] = exercise_types.get(exercise_type, 0) + 1
        platforms[platform] = platforms.get(platform, 0) + 1
        total_steps += parse_number(payload.get("steps"))
        total_calories += parse_number(payload.get("calories_kcal"))
        total_active_seconds += parse_seconds(payload.get("active_duration"))
        if len(recent_records) < 12:
            recent_records.append(
                {
                    "occurred_at": record["occurred_at"].isoformat() if record.get("occurred_at") else None,
                    "display_name": payload.get("display_name"),
                    "exercise_type": payload.get("exercise_type"),
                    "platform": payload.get("platform"),
                    "active_minutes": round(parse_seconds(payload.get("active_duration")) / 60, 1),
                    "steps": payload.get("steps"),
                    "calories_kcal": payload.get("calories_kcal"),
                }
            )

    target_minutes = round(150 * (period_days / 7), 1)
    total_active_minutes = round(total_active_seconds / 60, 1)
    return {
        "period_days": period_days,
        "record_count": len(records),
        "active_days": len(active_days),
        "active_day_dates": sorted(active_days),
        "total_steps": int(total_steps),
        "total_calories_kcal": round(total_calories, 1),
        "total_active_minutes": total_active_minutes,
        "average_active_minutes_per_day": round(total_active_minutes / period_days, 1) if period_days else 0,
        "guideline_scaled_target_active_minutes": target_minutes,
        "guideline_progress_ratio": round(total_active_minutes / target_minutes, 2) if target_minutes else 0,
        "exercise_type_counts": dict(sorted(exercise_types.items(), key=lambda item: item[1], reverse=True)),
        "platform_counts": dict(sorted(platforms.items(), key=lambda item: item[1], reverse=True)),
        "recent_records": recent_records,
    }
