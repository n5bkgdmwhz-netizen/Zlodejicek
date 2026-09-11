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


def get_state() -> dict:
    response = post_json(
        "/api/state",
        {
            "code": ROOM_CODE,
            "token": TOKEN,
        },
    )

    if not isinstance(response, dict):
        raise RuntimeError("Odpověď serveru není JSON objekt.")

    state = response.get("state")

    if not isinstance(state, dict):
        raise RuntimeError(
            "Odpověď neobsahuje objekt state. "
            f"Obdržené klíče: {sorted(response.keys())}"
        )

    return state


def format_timestamp(timestamp):
    if not isinstance(timestamp, (int, float)):
        return "neuvedeno"

    return str(timestamp)


def print_summary(state: dict) -> None:
    round_number = state.get("round")
    server_time = state.get("serverTime")
    deadlines = state.get("deadlines")
    auctions = state.get("auctions", [])

    print()
    print("===== STAV HRY =====")
    print(f"Kolo: {round_number}")
    print(f"Server time: {server_time}")
    print(f"Počet deadline hodnot: {len(deadlines) if isinstance(deadlines, list) else 0}")
    print(f"Počet aukcí: {len(auctions) if isinstance(auctions, list) else 0}")

    print()
    print("===== AKTUÁLNÍ AUKCE =====")

    if not isinstance(auctions, list):
        print("Aukce nejsou ve formátu seznamu.")
        return

    current_auctions = [
        auction
        for auction in auctions
        if isinstance(auction, dict)
        and auction.get("round") == round_number
    ]

    if not current_auctions:
        print("Pro aktuální kolo nebyly nalezeny žádné aukce.")
        return

    for auction in current_auctions:
        print(
            " | ".join(
                [
                    f"ID={auction.get('id')}",
                    f"tier={auction.get('tier')}",
                    f"name={auction.get('name')}",
                    f"status={auction.get('status')}",
                    f"bid={auction.get('bid')}",
                    f"bidder={auction.get('bidder')}",
                    f"minBid={auction.get('minBid')}",
                    f"closesAt={format_timestamp(auction.get('closesAt'))}",
                    f"hardClose={format_timestamp(auction.get('hardClose'))}",
                ]
            )
        )

    print()
    print("===== DEADLINY =====")

    if isinstance(deadlines, list):
        for index, deadline in enumerate(deadlines):
            print(f"{index}: {deadline}")
    else:
        print("Deadliny nejsou ve formátu seznamu.")


def main() -> None:
    print(f"Testing room: {ROOM_CODE}")

    state = get_state()
    print_summary(state)

    print()
    print("Read-only test dokončen. Nebyla odeslána žádná herní akce.")


if __name__ == "__main__":
    main()
