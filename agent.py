import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]


def post_json(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8")

    request = Request(
        url=url,
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

            try:
                return json.loads(raw)
            except json.JSONDecodeError as error:
                print("Server nevrátil platný JSON.", file=sys.stderr)
                print(raw[:4000], file=sys.stderr)
                raise error

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        print(f"HTTP {error.code} {path}", file=sys.stderr)
        print(body[:4000], file=sys.stderr)

        raise

    except URLError as error:
        print(f"Chyba připojení: {error}", file=sys.stderr)
        raise


def remove_sensitive_data(value):
    if isinstance(value, dict):
        sanitized = {}

        for key, item in value.items():
            key_lower = str(key).lower()

            if key_lower in {
                "token",
                "key",
                "secret",
                "password",
                "personalkey",
                "personaltoken",
            }:
                sanitized[key] = "<REDACTED>"
            else:
                sanitized[key] = remove_sensitive_data(item)

        return sanitized

    if isinstance(value, list):
        return [remove_sensitive_data(item) for item in value]

    return value


def main() -> None:
    print(f"Testing room: {ROOM_CODE}")

    response = post_json(
        "/api/state",
        {
            "code": ROOM_CODE,
            "token": TOKEN,
        },
    )

    if not isinstance(response, dict):
        raise RuntimeError("Odpověď serveru není JSON objekt.")

    sanitized_response = remove_sensitive_data(response)

    print("Top-level keys:")
    print(", ".join(sorted(response.keys())))

    print("Skutečná odpověď serveru:")
    print(
        json.dumps(
            sanitized_response,
            ensure_ascii=False,
            indent=2,
        )[:20000]
    )


if __name__ == "__main__":
    main()
