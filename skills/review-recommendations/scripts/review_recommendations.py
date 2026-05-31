import argparse
import json
import os
import urllib.parse
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default="pending")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    base_url = os.environ["HIPPO_COMPASS_API_URL"].rstrip("/")
    api_key = os.environ["HIPPO_COMPASS_API_KEY"]
    query = urllib.parse.urlencode({"status": args.status, "limit": args.limit})
    request = urllib.request.Request(
        f"{base_url}/recommendations?{query}",
        headers={"X-Assistant-API-Key": api_key},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print(json.dumps(json.loads(response.read().decode()), indent=2))


if __name__ == "__main__":
    main()
