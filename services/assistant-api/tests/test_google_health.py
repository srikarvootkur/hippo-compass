import os
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import google_health


def test_build_authorization_url_contains_required_google_health_params() -> None:
    url = google_health.build_authorization_url(
        "state-123",
        config={
            "client_id": "client-id",
            "client_secret": "secret",
            "redirect_uri": "http://localhost:8080/connectors/google-health/oauth/callback",
            "scopes": google_health.DEFAULT_SCOPES,
        },
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == ["http://localhost:8080/connectors/google-health/oauth/callback"]
    assert query["response_type"] == ["code"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["scope"] == [google_health.DEFAULT_SCOPES]
    assert query["state"] == ["state-123"]


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_uses_google_token_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv(
        "GOOGLE_HEALTH_REDIRECT_URI",
        "http://localhost:8080/connectors/google-health/oauth/callback",
    )
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        body = request.content.decode()
        assert "code=auth-code" in body
        assert "client_id=client-id" in body
        assert "client_secret=secret" in body
        assert "grant_type=authorization_code" in body
        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "scope": google_health.DEFAULT_SCOPES,
                "token_type": "Bearer",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tokens = await google_health.exchange_code_for_tokens("auth-code", client=client)

    assert seen["url"] == google_health.TOKEN_URL
    assert tokens["access_token"] == "access-token"
    assert tokens["refresh_token"] == "refresh-token"
    assert tokens["scope"] == google_health.DEFAULT_SCOPES
    assert tokens["token_type"] == "Bearer"
    assert tokens["expires_at"]


def test_normalize_exercise_data_point_from_codelab_shape() -> None:
    normalized = google_health.normalize_exercise_data_point(
        {
            "name": "users/123/dataTypes/exercise/dataPoints/abc",
            "dataSource": {
                "recordingMethod": "MANUAL",
                "platform": "FITBIT",
            },
            "exercise": {
                "interval": {
                    "startTime": "2026-02-23T13:10:00Z",
                    "endTime": "2026-02-23T13:25:00Z",
                },
                "exerciseType": "WALKING",
                "metricsSummary": {
                    "caloriesKcal": 16,
                    "distanceMillimiters": 1609344,
                    "steps": "2038",
                    "activeZoneMinutes": "0",
                },
                "displayName": "Walk",
                "activeDuration": "900s",
            },
        }
    )

    assert normalized == {
        "name": "users/123/dataTypes/exercise/dataPoints/abc",
        "platform": "FITBIT",
        "recording_method": "MANUAL",
        "exercise_type": "WALKING",
        "display_name": "Walk",
        "start_time": "2026-02-23T13:10:00Z",
        "end_time": "2026-02-23T13:25:00Z",
        "active_duration": "900s",
        "calories_kcal": 16,
        "distance_millimeters": 1609344,
        "steps": "2038",
        "active_zone_minutes": "0",
    }


def test_parse_google_timestamp() -> None:
    parsed = google_health.parse_google_timestamp("2026-06-06T03:55:04.257Z")

    assert parsed is not None
    assert parsed.isoformat() == "2026-06-06T03:55:04.257000+00:00"
