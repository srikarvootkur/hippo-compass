from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx


SOURCE_NAME = "google_health"
RECORD_TYPE_EXERCISE = "exercise"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE_URL = "https://health.googleapis.com/v4/users/me"
UTC = timezone.utc

SCOPE_BASE = "https://www.googleapis.com/auth/googlehealth"
READONLY_SCOPES = {
    "activity_and_fitness": f"{SCOPE_BASE}.activity_and_fitness.readonly",
    "ecg": f"{SCOPE_BASE}.ecg.readonly",
    "health_metrics_and_measurements": f"{SCOPE_BASE}.health_metrics_and_measurements.readonly",
    "irn": f"{SCOPE_BASE}.irn.readonly",
    "location": f"{SCOPE_BASE}.location.readonly",
    "nutrition": f"{SCOPE_BASE}.nutrition.readonly",
    "profile": f"{SCOPE_BASE}.profile.readonly",
    "settings": f"{SCOPE_BASE}.settings.readonly",
    "sleep": f"{SCOPE_BASE}.sleep.readonly",
}
DEFAULT_SCOPES = READONLY_SCOPES["activity_and_fitness"]
ALL_READONLY_SCOPES = " ".join(sorted(READONLY_SCOPES.values()))


@dataclass(frozen=True)
class GoogleHealthDataType:
    name: str
    data_type: str
    filter_name: str
    record_type: str
    operations: tuple[str, ...]
    scope_key: str
    category: str

    @property
    def scope(self) -> str:
        return READONLY_SCOPES[self.scope_key]

    @property
    def supports_list(self) -> bool:
        return "list" in self.operations

    @property
    def supports_reconcile(self) -> bool:
        return "reconcile" in self.operations

    @property
    def supports_daily_rollup(self) -> bool:
        return "dailyRollup" in self.operations


DATA_TYPES: tuple[GoogleHealthDataType, ...] = (
    GoogleHealthDataType("Active Energy Burned", "active-energy-burned", "active_energy_burned", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Active Minutes", "active-minutes", "active_minutes", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Active Zone Minutes", "active-zone-minutes", "active_zone_minutes", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Activity Level", "activity-level", "activity_level", "interval", ("list", "reconcile"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Altitude", "altitude", "altitude", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Blood Glucose", "blood-glucose", "blood_glucose", "sample", ("list", "get", "reconcile", "rollup", "dailyRollup"), "health_metrics_and_measurements", "health_metrics"),
    GoogleHealthDataType("Body Fat", "body-fat", "body_fat", "sample", ("list", "get", "reconcile", "rollup", "dailyRollup"), "health_metrics_and_measurements", "body"),
    GoogleHealthDataType("Calories In Heart Rate Zone", "calories-in-heart-rate-zone", "calories_in_heart_rate_zone", "interval", ("rollup", "dailyRollup"), "activity_and_fitness", "heart"),
    GoogleHealthDataType("Core Body Temperature", "core-body-temperature", "core_body_temperature", "sample", ("list", "get", "reconcile", "rollup", "dailyRollup"), "health_metrics_and_measurements", "health_metrics"),
    GoogleHealthDataType("Daily Heart Rate Variability", "daily-heart-rate-variability", "daily_heart_rate_variability", "daily", ("list", "reconcile"), "health_metrics_and_measurements", "recovery"),
    GoogleHealthDataType("Daily Heart Rate Zones", "daily-heart-rate-zones", "daily_heart_rate_zones", "daily", ("list", "reconcile"), "health_metrics_and_measurements", "heart"),
    GoogleHealthDataType("Daily Oxygen Saturation", "daily-oxygen-saturation", "daily_oxygen_saturation", "daily", ("list", "reconcile"), "health_metrics_and_measurements", "recovery"),
    GoogleHealthDataType("Daily Respiratory Rate", "daily-respiratory-rate", "daily_respiratory_rate", "daily", ("list", "reconcile"), "health_metrics_and_measurements", "recovery"),
    GoogleHealthDataType("Daily Resting Heart Rate", "daily-resting-heart-rate", "daily_resting_heart_rate", "daily", ("list", "reconcile"), "health_metrics_and_measurements", "heart"),
    GoogleHealthDataType("Daily Sleep Temperature Derivations", "daily-sleep-temperature-derivations", "daily_sleep_temperature_derivations", "daily", ("list", "reconcile"), "health_metrics_and_measurements", "sleep"),
    GoogleHealthDataType("Daily VO2 Max", "daily-vo2-max", "daily_vo2_max", "daily", ("list", "reconcile"), "activity_and_fitness", "cardio"),
    GoogleHealthDataType("Distance", "distance", "distance", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Electrocardiogram (ECG)", "electrocardiogram", "electrocardiogram", "session", ("list",), "ecg", "heart"),
    GoogleHealthDataType("Exercise", "exercise", "exercise", "session", ("list", "get", "reconcile"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Floors", "floors", "floors", "interval", ("reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Food", "food", "food", "food", ("list", "get"), "nutrition", "nutrition"),
    GoogleHealthDataType("Food Measurement Unit", "food-measurement-unit", "food_measurement_unit", "food", ("list", "get"), "nutrition", "nutrition"),
    GoogleHealthDataType("Heart Rate", "heart-rate", "heart_rate", "sample", ("list", "reconcile", "rollup", "dailyRollup"), "health_metrics_and_measurements", "heart"),
    GoogleHealthDataType("Heart Rate Variability", "heart-rate-variability", "heart_rate_variability", "sample", ("list", "reconcile"), "health_metrics_and_measurements", "recovery"),
    GoogleHealthDataType("Height", "height", "height", "sample", ("list", "get", "reconcile"), "health_metrics_and_measurements", "body"),
    GoogleHealthDataType("Hydration Log", "hydration-log", "hydration_log", "session", ("list", "get", "reconcile", "rollup", "dailyRollup"), "nutrition", "nutrition"),
    GoogleHealthDataType("Irregular Rhythm Notification", "irregular-rhythm-notification", "irregular_rhythm_notification", "session", ("list",), "irn", "heart"),
    GoogleHealthDataType("Nutrition Log", "nutrition-log", "nutrition_log", "sample", ("list", "get", "reconcile", "rollup", "dailyRollup"), "nutrition", "nutrition"),
    GoogleHealthDataType("Oxygen Saturation", "oxygen-saturation", "oxygen_saturation", "sample", ("list", "reconcile"), "health_metrics_and_measurements", "recovery"),
    GoogleHealthDataType("Respiratory Rate Sleep Summary", "respiratory-rate-sleep-summary", "respiratory_rate_sleep_summary", "sample", ("list", "reconcile"), "health_metrics_and_measurements", "sleep"),
    GoogleHealthDataType("Run VO2 Max", "run-vo2-max", "run_vo2_max", "sample", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "cardio"),
    GoogleHealthDataType("Sedentary Period", "sedentary-period", "sedentary_period", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Sleep", "sleep", "sleep", "session", ("list", "get", "reconcile"), "sleep", "sleep"),
    GoogleHealthDataType("Steps", "steps", "steps", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Swim Lengths Data", "swim-lengths-data", "swim_lengths_data", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("Time in Heart Rate Zone", "time-in-heart-rate-zone", "time_in_heart_rate_zone", "interval", ("list", "reconcile", "rollup", "dailyRollup"), "activity_and_fitness", "heart"),
    GoogleHealthDataType("Total Calories", "total-calories", "total_calories", "interval", ("rollup", "dailyRollup"), "activity_and_fitness", "activity"),
    GoogleHealthDataType("VO2 Max", "vo2-max", "vo2_max", "sample", ("list", "reconcile"), "activity_and_fitness", "cardio"),
    GoogleHealthDataType("Weight", "weight", "weight", "sample", ("list", "get", "reconcile", "rollup", "dailyRollup"), "health_metrics_and_measurements", "body"),
)
DATA_TYPE_BY_NAME = {item.data_type: item for item in DATA_TYPES}


def catalog() -> list[dict[str, Any]]:
    return [{**asdict(item), "scope": item.scope} for item in DATA_TYPES]


def all_data_type_names() -> list[str]:
    return [item.data_type for item in DATA_TYPES]


def selected_scopes(data_types: list[str] | None = None) -> str:
    selected = data_types or all_data_type_names()
    scopes = {DATA_TYPE_BY_NAME[name].scope for name in selected if name in DATA_TYPE_BY_NAME}
    return " ".join(sorted(scopes))


def settings() -> dict[str, str]:
    return {
        "client_id": os.getenv("GOOGLE_HEALTH_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_HEALTH_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv(
            "GOOGLE_HEALTH_REDIRECT_URI",
            "http://localhost:8080/connectors/google-health/oauth/callback",
        ),
        "scopes": os.getenv("GOOGLE_HEALTH_SCOPES", ALL_READONLY_SCOPES),
    }


def require_settings() -> dict[str, str]:
    config = settings()
    missing = [key for key in ("client_id", "client_secret", "redirect_uri") if not config[key]]
    if missing:
        raise ValueError(f"Missing Google Health OAuth setting(s): {', '.join(missing)}")
    return config


def build_authorization_url(state: str, config: dict[str, str] | None = None, data_types: list[str] | None = None) -> str:
    config = config or require_settings()
    scopes = selected_scopes(data_types) if data_types else config["scopes"]
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "scope": scopes,
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


def new_oauth_state() -> str:
    return uuid4().hex


def token_expires_at(expires_in: int | None) -> str:
    ttl = expires_in if expires_in is not None else 3600
    return (datetime.now(UTC) + timedelta(seconds=max(ttl - 60, 0))).isoformat()


def normalize_token_response(token_response: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    refresh_token = token_response.get("refresh_token") or existing.get("refresh_token")
    return {
        "access_token": token_response["access_token"],
        "refresh_token": refresh_token,
        "token_type": token_response.get("token_type", "Bearer"),
        "scope": token_response.get("scope", existing.get("scope")),
        "expires_at": token_expires_at(token_response.get("expires_in")),
        "refresh_token_expires_in": token_response.get("refresh_token_expires_in"),
    }


async def exchange_code_for_tokens(code: str, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    config = require_settings()
    close_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return normalize_token_response(response.json())
    finally:
        if close_client:
            await client.aclose()


async def refresh_access_token(tokens: dict[str, Any], client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    config = require_settings()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise ValueError("Google Health refresh token is missing; reauthorize the connector.")
    close_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return normalize_token_response(response.json(), existing=tokens)
    finally:
        if close_client:
            await client.aclose()


def is_token_expired(tokens: dict[str, Any]) -> bool:
    expires_at = tokens.get("expires_at")
    if not expires_at:
        return True
    return datetime.fromisoformat(expires_at) <= datetime.now(UTC)


def parse_google_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def camelize_data_type(data_type: str) -> str:
    parts = data_type.split("-")
    return parts[0] + "".join(part.title() for part in parts[1:])


def get_data_type(data_type: str) -> GoogleHealthDataType:
    if data_type not in DATA_TYPE_BY_NAME:
        raise ValueError(f"Unsupported Google Health data type: {data_type}")
    return DATA_TYPE_BY_NAME[data_type]


def list_url(data_type: str, reconcile: bool = False) -> str:
    suffix = ":reconcile" if reconcile else ""
    return f"{API_BASE_URL}/dataTypes/{data_type}/dataPoints{suffix}"


def filter_for_since(spec: GoogleHealthDataType, since: datetime | None) -> str | None:
    if since is None:
        return None
    timestamp = since.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if spec.record_type in {"interval", "session"}:
        return f'{spec.filter_name}.interval.start_time >= "{timestamp}"'
    if spec.record_type == "sample":
        return f'{spec.filter_name}.sample_time.physical_time >= "{timestamp}"'
    return None


async def list_data_points(
    access_token: str,
    data_type: str,
    *,
    since: datetime | None = None,
    page_size: int = 1000,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    spec = get_data_type(data_type)
    if not spec.supports_list and not spec.supports_reconcile:
        raise ValueError(f"{data_type} does not support list or reconcile reads.")
    close_client = client is None
    client = client or httpx.AsyncClient(timeout=60)
    try:
        points: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            filter_value = filter_for_since(spec, since)
            if filter_value:
                params["filter"] = filter_value
            response = await client.get(
                list_url(data_type, reconcile=not spec.supports_list),
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            payload = response.json()
            points.extend(payload.get("dataPoints", []))
            page_token = payload.get("nextPageToken") or None
            if not page_token:
                return points
    finally:
        if close_client:
            await client.aclose()


async def list_exercise_data_points(access_token: str, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    return await list_data_points(access_token, RECORD_TYPE_EXERCISE, client=client)


def first_datetime(values: list[Any]) -> str | None:
    for value in values:
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}T", value):
            return value
    return None


def civil_date_to_iso(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    date_value = value.get("date") or value
    try:
        return date(int(date_value["year"]), int(date_value["month"]), int(date_value["day"])).isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def nested_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        results: list[Any] = []
        for child in value.values():
            results.extend(nested_values(child))
        return results
    if isinstance(value, list):
        results = []
        for child in value:
            results.extend(nested_values(child))
        return results
    return [value]


def coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def numeric_summary(payload: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            continue
        number = coerce_number(value)
        if number is not None:
            result[key] = number
    return result


def point_content(data_type: str, data_point: dict[str, Any]) -> dict[str, Any]:
    return data_point.get(camelize_data_type(data_type)) or data_point.get(data_type.replace("-", "")) or {}


def external_id_for_point(data_type: str, data_point: dict[str, Any]) -> str:
    if data_point.get("name"):
        return str(data_point["name"])
    digest = hashlib.sha256(json.dumps(data_point, sort_keys=True).encode()).hexdigest()[:32]
    return f"google-health:{data_type}:{digest}"


def normalize_data_point(data_type: str, data_point: dict[str, Any]) -> dict[str, Any]:
    spec = get_data_type(data_type)
    content = point_content(data_type, data_point)
    interval = content.get("interval") or {}
    sample_time = content.get("sampleTime") or content.get("sample_time") or {}
    data_source = data_point.get("dataSource") or {}
    start_time = interval.get("startTime")
    end_time = interval.get("endTime")
    physical_time = sample_time.get("physicalTime")
    civil_day = (
        civil_date_to_iso(content.get("day"))
        or civil_date_to_iso(content.get("date"))
        or civil_date_to_iso(interval.get("civilStartTime"))
        or civil_date_to_iso(sample_time.get("civilTime"))
    )
    observed = first_datetime([physical_time, start_time, end_time, *nested_values(content)])
    summary = numeric_summary(content)
    normalized = {
        "name": external_id_for_point(data_type, data_point),
        "data_type": data_type,
        "filter_name": spec.filter_name,
        "record_type": spec.record_type,
        "category": spec.category,
        "platform": data_source.get("platform"),
        "recording_method": data_source.get("recordingMethod"),
        "device": data_source.get("device") or {},
        "application": data_source.get("application") or {},
        "start_time": start_time,
        "end_time": end_time,
        "sample_time": physical_time,
        "observed_at": observed,
        "civil_date": civil_day,
        "content": content,
        "numeric_summary": summary,
    }
    if data_type == RECORD_TYPE_EXERCISE:
        normalized.update(normalize_exercise_data_point(data_point))
    if data_type == "sleep":
        sleep_summary = content.get("summary") or {}
        normalized["sleep_summary"] = sleep_summary
        normalized["sleep_stages"] = content.get("stages") or []
        normalized["minutes_asleep"] = sleep_summary.get("minutesAsleep")
        normalized["minutes_awake"] = sleep_summary.get("minutesAwake")
        normalized["minutes_in_sleep_period"] = sleep_summary.get("minutesInSleepPeriod")
    return normalized


def normalize_exercise_data_point(data_point: dict[str, Any]) -> dict[str, Any]:
    exercise = data_point.get("exercise") or {}
    interval = exercise.get("interval") or {}
    metrics = exercise.get("metricsSummary") or {}
    data_source = data_point.get("dataSource") or {}
    return {
        "name": data_point.get("name") or external_id_for_point(RECORD_TYPE_EXERCISE, data_point),
        "platform": data_source.get("platform"),
        "recording_method": data_source.get("recordingMethod"),
        "exercise_type": exercise.get("exerciseType"),
        "display_name": exercise.get("displayName"),
        "start_time": interval.get("startTime"),
        "end_time": interval.get("endTime"),
        "active_duration": exercise.get("activeDuration"),
        "calories_kcal": metrics.get("caloriesKcal"),
        "distance_millimeters": metrics.get("distanceMillimiters"),
        "steps": metrics.get("steps"),
        "active_zone_minutes": metrics.get("activeZoneMinutes"),
    }


def occurred_at(normalized: dict[str, Any]) -> datetime | None:
    return parse_google_timestamp(
        normalized.get("observed_at")
        or normalized.get("start_time")
        or normalized.get("sample_time")
        or normalized.get("end_time")
    )
