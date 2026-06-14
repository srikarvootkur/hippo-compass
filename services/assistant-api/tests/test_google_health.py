import os
from datetime import datetime, timezone
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


def test_catalog_contains_sleep_and_readonly_scopes() -> None:
    names = {item["data_type"] for item in google_health.catalog()}

    assert "exercise" in names
    assert "sleep" in names
    assert "heart-rate" in names
    assert google_health.READONLY_SCOPES["sleep"].endswith(".sleep.readonly")


def test_selected_scopes_for_data_types() -> None:
    scopes = google_health.selected_scopes(["sleep", "heart-rate", "steps"])

    assert google_health.READONLY_SCOPES["sleep"] in scopes
    assert google_health.READONLY_SCOPES["health_metrics_and_measurements"] in scopes
    assert google_health.READONLY_SCOPES["activity_and_fitness"] in scopes


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


def test_filter_for_interval_uses_civil_start_time() -> None:
    spec = google_health.DATA_TYPE_BY_NAME["steps"]
    value = google_health.filter_for_since(spec, datetime(2026, 3, 4, tzinfo=timezone.utc))

    assert value == 'steps.interval.civil_start_time >= "2026-03-04T00:00:00"'


def test_filter_for_session_uses_civil_end_date() -> None:
    spec = google_health.DATA_TYPE_BY_NAME["sleep"]
    value = google_health.filter_for_since(spec, datetime(2026, 3, 4, tzinfo=timezone.utc))

    assert value == 'sleep.interval.civil_end_time >= "2026-03-04"'


@pytest.mark.asyncio
async def test_sleep_list_uses_reconcile_and_wearables_family() -> None:
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"dataPoints": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        points = await google_health.list_data_points(
            "access-token",
            "sleep",
            since=datetime(2026, 3, 4, tzinfo=timezone.utc),
            client=client,
        )

    assert points == []
    assert "/dataTypes/sleep/dataPoints:reconcile" in seen["url"]
    assert "dataSourceFamily=users%2Fme%2FdataSourceFamilies%2Fgoogle-wearables" in seen["url"]


def test_normalize_sleep_data_point() -> None:
    normalized = google_health.normalize_data_point(
        "sleep",
        {
            "name": "users/123/dataTypes/sleep/dataPoints/abc",
            "dataSource": {"platform": "FITBIT"},
            "sleep": {
                "interval": {
                    "startTime": "2026-03-03T20:57:30Z",
                    "endTime": "2026-03-04T04:41:30Z",
                },
                "summary": {"minutesAsleep": "407"},
                "stages": [{"type": "LIGHT", "minutes": "198"}],
            },
        },
    )

    assert normalized["data_type"] == "sleep"
    assert normalized["category"] == "sleep"
    assert normalized["start_time"] == "2026-03-03T20:57:30Z"
    assert normalized["sleep_summary"] == {"minutesAsleep": "407"}
    assert normalized["minutes_asleep"] == "407"
