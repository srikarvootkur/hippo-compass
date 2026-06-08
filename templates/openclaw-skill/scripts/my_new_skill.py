import argparse
import json
import os
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    base_url = os.environ["HIPPO_COMPASS_API_URL"].rstrip("/")
    api_key = os.environ["HIPPO_COMPASS_API_KEY"]
    body = json.dumps({"input": args.input}).encode()
    request = urllib.request.Request(
        f"{base_url}/replace-with-real-endpoint",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Assistant-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(json.dumps(json.loads(response.read().decode()), indent=2))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        print(json.dumps({"status": "error", "code": exc.code, "detail": detail}, indent=2))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
