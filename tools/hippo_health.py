#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API_URL = os.getenv("HIPPO_COMPASS_API_URL", "http://localhost:8080")
DEFAULT_ENV_PATH = Path(".env")
ALL_DATA_TYPES = ["all"]


def request_json(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    base_url = os.getenv("HIPPO_COMPASS_API_URL", DEFAULT_API_URL).rstrip("/")
    api_key = os.getenv("HIPPO_COMPASS_API_KEY") or os.getenv("ASSISTANT_API_KEY", "change-me-local-dev")
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Assistant-API-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise SystemExit(f"{exc.code} {exc.reason}: {detail}") from exc


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def update_env(path: Path, values: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    lines: list[str] = []
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=", 1)[0]
                existing[key] = line
            else:
                lines.append(line)
    merged = {**{key: value for key, value in existing.items()}, **{key: f"{key}={value}" for key, value in values.items()}}
    kept_keys = {line.split("=", 1)[0] for line in lines if "=" in line and not line.strip().startswith("#")}
    output = [line for line in lines if not (line.split("=", 1)[0] in values if "=" in line else False)]
    for key, line in merged.items():
        if key not in kept_keys:
            output.append(line)
    path.write_text("\n".join(output).strip() + "\n")


def setup(args: argparse.Namespace) -> None:
    print("Google Cloud setup:")
    print("1. Create/select a Google Cloud project.")
    print("2. Enable Google Health API.")
    print("3. Configure OAuth consent screen and add yourself as a test user.")
    print("4. Create OAuth client: Web application.")
    print("5. Authorized JavaScript origin: http://localhost:8080")
    print("6. Authorized redirect URI: http://localhost:8080/connectors/google-health/oauth/callback")
    print("7. Add Google Health readonly scopes. For all data, use the generated GOOGLE_HEALTH_SCOPES value.")
    client_id = args.client_id or input("GOOGLE_HEALTH_CLIENT_ID: ").strip()
    client_secret = args.client_secret or input("GOOGLE_HEALTH_CLIENT_SECRET: ").strip()
    redirect_uri = args.redirect_uri or input("GOOGLE_HEALTH_REDIRECT_URI [http://localhost:8080/connectors/google-health/oauth/callback]: ").strip()
    redirect_uri = redirect_uri or "http://localhost:8080/connectors/google-health/oauth/callback"
    catalog = request_json("GET", "/connectors/google-health/catalog")
    scopes = " ".join(sorted(set(item["scope"] for item in catalog["data_types"])))
    values = {
        "GOOGLE_HEALTH_CLIENT_ID": client_id,
        "GOOGLE_HEALTH_CLIENT_SECRET": client_secret,
        "GOOGLE_HEALTH_REDIRECT_URI": redirect_uri,
        "GOOGLE_HEALTH_SCOPES": scopes,
    }
    if args.database_url:
        values["DATABASE_URL"] = args.database_url
    update_env(Path(args.env_file), values)
    print(f"Updated {args.env_file}. Restart assistant-api after changing env values.")


def google_connect(_: argparse.Namespace) -> None:
    payload = request_json("GET", "/connectors/google-health/oauth/start")
    print_json(payload)
    print("\nOpen authorization_url in your browser, then run `hippo-health google status`.")


def google_status(_: argparse.Namespace) -> None:
    print_json(request_json("GET", "/connectors/google-health/status"))


def google_catalog(_: argparse.Namespace) -> None:
    print_json(request_json("GET", "/connectors/google-health/catalog"))


def configure(args: argparse.Namespace) -> None:
    selected = args.data_types
    if not selected or selected == ALL_DATA_TYPES:
        catalog = request_json("GET", "/connectors/google-health/catalog")
        selected = [item["data_type"] for item in catalog["data_types"]]
    print_json(
        request_json(
            "POST",
            "/connectors/google-health/configure",
            {
                "selected_data_types": selected,
                "sync_schedule": args.schedule,
            },
        )
    )


def sync(args: argparse.Namespace) -> None:
    body: dict[str, Any] = {"lookback_days": args.lookback_days}
    if args.data_types and args.data_types != ALL_DATA_TYPES:
        body["data_types"] = args.data_types
    print_json(request_json("POST", "/connectors/google-health/sync", body))


def schedule(args: argparse.Namespace) -> None:
    status = request_json("GET", "/connectors/google-health/status")
    selected = status.get("selected_data_types") or []
    print_json(
        request_json(
            "POST",
            "/connectors/google-health/configure",
            {
                "selected_data_types": selected,
                "sync_schedule": args.frequency,
            },
        )
    )


def import_csv(args: argparse.Namespace) -> None:
    print_json(
        request_json(
            "POST",
            "/connectors/csv/import",
            {"source": args.source, "file_path": args.file},
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="hippo-health")
    sub = parser.add_subparsers(required=True)

    setup_parser = sub.add_parser("setup")
    setup_parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    setup_parser.add_argument("--client-id")
    setup_parser.add_argument("--client-secret")
    setup_parser.add_argument("--redirect-uri")
    setup_parser.add_argument("--database-url")
    setup_parser.set_defaults(func=setup)

    google_parser = sub.add_parser("google")
    google_sub = google_parser.add_subparsers(required=True)
    google_sub.add_parser("connect").set_defaults(func=google_connect)
    google_sub.add_parser("status").set_defaults(func=google_status)
    google_sub.add_parser("catalog").set_defaults(func=google_catalog)
    configure_parser = google_sub.add_parser("configure")
    configure_parser.add_argument("--data-types", nargs="+", default=["all"])
    configure_parser.add_argument("--schedule", choices=["manual", "daily", "weekly", "off"], default="manual")
    configure_parser.set_defaults(func=configure)

    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument("--data-types", nargs="+", default=["all"])
    sync_parser.add_argument("--lookback-days", type=int, default=30)
    sync_parser.set_defaults(func=sync)

    schedule_parser = sub.add_parser("schedule")
    schedule_parser.add_argument("frequency", choices=["daily", "weekly", "manual", "off"])
    schedule_parser.set_defaults(func=schedule)

    csv_parser = sub.add_parser("import-csv")
    csv_parser.add_argument("--source", choices=["hevy", "cronometer"], required=True)
    csv_parser.add_argument("--file", required=True)
    csv_parser.set_defaults(func=import_csv)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
