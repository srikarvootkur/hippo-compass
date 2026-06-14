import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


UTC = timezone.utc
STATE_FILE = Path(os.getenv("HEALTH_SYNC_STATE_FILE", "/tmp/hippo_health_last_sync.txt"))


def seconds_for_schedule(schedule: str) -> int | None:
    if schedule == "daily":
        return 24 * 60 * 60
    if schedule == "weekly":
        return 7 * 24 * 60 * 60
    return None


def should_run(schedule: str) -> bool:
    interval = seconds_for_schedule(schedule)
    if interval is None:
        return False
    if not STATE_FILE.exists():
        return True
    try:
        last = datetime.fromisoformat(STATE_FILE.read_text().strip())
    except ValueError:
        return True
    return (datetime.now(UTC) - last).total_seconds() >= interval


def maybe_sync_google_health() -> None:
    api_url = os.getenv("HIPPO_COMPASS_API_URL", "http://assistant-api:8080").rstrip("/")
    api_key = os.getenv("HIPPO_COMPASS_API_KEY") or os.getenv("ASSISTANT_API_KEY", "")
    if not api_key:
        return
    headers = {"X-Assistant-API-Key": api_key}
    try:
        status = httpx.get(f"{api_url}/connectors/google-health/status", headers=headers, timeout=30).json()
        schedule = status.get("sync_schedule", "manual")
        if should_run(schedule):
            response = httpx.post(
                f"{api_url}/connectors/google-health/sync",
                headers={**headers, "Content-Type": "application/json"},
                json={"lookback_days": 30},
                timeout=300,
            )
            response.raise_for_status()
            STATE_FILE.write_text(datetime.now(UTC).isoformat())
            print({"service": "personal-assistant-worker", "event": "google_health_sync", "result": response.json()}, flush=True)
    except Exception as exc:
        print({"service": "personal-assistant-worker", "event": "google_health_sync_error", "error": str(exc)}, flush=True)


def main() -> None:
    interval_seconds = int(os.getenv("WORKER_HEARTBEAT_SECONDS", "300"))
    while True:
        print(
            {
                "service": "personal-assistant-worker",
                "status": "idle",
                "time": datetime.now(UTC).isoformat(),
            },
            flush=True,
        )
        maybe_sync_google_health()
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
