import argparse
import json
import os
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    base_url = os.environ["HIPPO_COMPASS_API_URL"].rstrip("/")
    api_key = os.environ["HIPPO_COMPASS_API_KEY"]
    body = json.dumps({"query": args.query, "limit": args.limit}).encode()
    request = urllib.request.Request(
        f"{base_url}/memory/search",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Assistant-API-Key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.read().decode())


if __name__ == "__main__":
    main()
