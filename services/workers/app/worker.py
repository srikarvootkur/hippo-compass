import os
import time
from datetime import UTC, datetime


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
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
