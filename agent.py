import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]

# Pouze diagnostická hodnota.
# Agent zatím nic neposílá.
DRY_RUN = True


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


def format_time(timestamp):
    if not isinstance(timestamp, (int, float)):
        return "neuvedeno"

    return datetime.fromtimestamp(
        timestamp / 1000,
        tz=timezone.utc,
    ).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def get_current_deadline(state: dict):
    deadlines = state.get("deadlines")
    round_number = state.get("round")

    if not isinstance(deadlines, list):
        return None

    if not isinstance(round_number, int):
        return None

    deadline_index = round_number

    if deadline_index >= len(deadlines):
        return None

    deadline = deadlines[deadline_index]

    if not isinstance(deadline, (int, float)):
        return None

    return deadline


def print_round_info(state: dict) -> None:
    round_number = state.get("round")
    server_time = state.get("serverTime")
    deadline = get_current_deadline(state)

    print()
    print("===== ČAS KOLA =====")
    print(f"Aktuální kolo: {round_number}")
    print(f"Serverový čas: {server_time}")
    print(f"Serverový čas čitelně: {format_time(server_time)}")
    print(f"Uzávěrka: {deadline}")
    print(f"Uzávěrka čitelně: {format_time(deadline)}")

    if isinstance(server_time, (int, float)) and isinstance(
        deadline,
        (int, float),
    ):
        seconds_left = max(0, (deadline - server_time) / 1000)

        print(f"Zbývá sekund: {seconds_left:.0f}")
        print(f"Zbývá minut: {seconds_left / 60:.1f}")

        if seconds_left <= 60:
            print("REŽIM: jsme v poslední minutě před uzávěrkou.")
        else:
            print("REŽIM: ještě nejsme v poslední minutě.")


def print_auction_plan(state: dict) -> None:
    round_number = state.get("round")
    auctions = state.get("auctions", [])

    print()
    print("===== PLÁN AUKCÍ - DRY RUN =====")

    if not isinstance(auctions, list):
        print("Aukce nejsou ve formátu seznamu.")
        return

    open_auctions = [
        auction
        for auction in auctions
        if isinstance(auction, dict)
        and auction.get("round") == round_number
        and auction.get("status") == "open"
    ]

    if not open_auctions:
        print("V aktuálním kole nejsou otevřené aukce.")
        return

    for auction in open_auctions:
        auction_id = auction.get("id")
        current_bid = auction.get("bid")
        minimum_bid = auction.get("minBid")
        bidder = auction.get("bidder")
        closes_at = auction.get("closesAt")

        print()
        print(f"Aukce: {auction_id}")
        print(f"  Název: {auction.get('name')}")
        print(f"  Aktuální nabídka: {current_bid}")
        print(f"  Minimální další příhoz: {minimum_bid}")
        print(f"  Aktuální vedoucí: {bidder}")
        print(f"  Uzavírá se: {format_time(closes_at)}")

        if isinstance(minimum_bid, int):
            print(
                f"  DRY RUN: hypotetický příhoz by byl "
                f"{minimum_bid} zl."
            )
        else:
            print("  DRY RUN: nelze určit částku.")


def main() -> None:
    print(f"Testing room: {ROOM_CODE}")

    state = get_state()

    print_round_info(state)
    print_auction_plan(state)

    print()
    print(f"DRY_RUN={DRY_RUN}")
    print("Nebyla odeslána žádná herní akce.")


if __name__ == "__main__":
    main()
