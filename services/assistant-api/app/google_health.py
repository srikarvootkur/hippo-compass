from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx


SOURCE_NAME = "google_health"
RECORD_TYPE_EXERCISE = "exercise"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EXERCISE_POINTS_URL = "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints"
DEFAULT_SCOPES = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"
UTC = timezone.utc


def settings() -> dict[str, str]:
    return {
        "client_id": os.getenv("GOOGLE_HEALTH_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_HEALTH_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv(
            "GOOGLE_HEALTH_REDIRECT_URI",
            "http://localhost:8080/connectors/google-health/oauth/callback",
        ),
        "scopes": os.getenv("GOOGLE_HEALTH_SCOPES", DEFAULT_SCOPES),
    }


def require_settings() -> dict[str, str]:
    config = settings()
    missing = [key for key in ("client_id", "client_secret", "redirect_uri") if not config[key]]
    if missing:
        raise ValueError(f"Missing Google Health OAuth setting(s): {', '.join(missing)}")
    return config


def build_authorization_url(state: str, config: dict[str, str] | None = None) -> str:
    config = config or require_settings()
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "scope": config["scopes"],
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


async def list_exercise_data_points(access_token: str, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    close_client = client is None
    client = client or httpx.AsyncClient(timeout=60)
    try:
        response = await client.get(
            EXERCISE_POINTS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        return response.json().get("dataPoints", [])
    finally:
        if close_client:
            await client.aclose()


def normalize_exercise_data_point(data_point: dict[str, Any]) -> dict[str, Any]:
    exercise = data_point.get("exercise") or {}
    interval = exercise.get("interval") or {}
    metrics = exercise.get("metricsSummary") or {}
    data_source = data_point.get("dataSource") or {}
    return {
        "name": data_point.get("name"),
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
