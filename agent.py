import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]

def post_json(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8")

    request = Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zlodeji-agent-test/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            print(f"HTTP {response.status} {path}")
            return json.loads(raw)

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"HTTP {error.code} {path}", file=sys.stderr)
        print(body, file=sys.stderr)
        raise

    except URLError as error:
        print(f"Connection error: {error}", file=sys.stderr)
        raise


def main() -> None:
    print(f"Testing room: {ROOM_CODE}")

    response = post_json(
        "/api/view",
        {
            "code": ROOM_CODE,
            "token": TOKEN,
        },
    )

    if not isinstance(response, dict):
        raise RuntimeError("Odpověď není JSON objekt.")

    print("Načtení stavu proběhlo.")
    print(json.dumps(response, ensure_ascii=False, indent=2)[:12000])


if __name__ == "__main__":
    main()
