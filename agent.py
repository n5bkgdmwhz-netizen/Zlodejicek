import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]

# Bezpečnostní režim.
# True = agent pouze vypisuje plán.
# False = agent může podle další logiky odesílat akce.
DRY_RUN = True

# Maximální částky, které smí agent nabídnout podle tieru aukce.
# Tyto hodnoty si později upravíš.
MAX_BID_BY_TIER = {
    0: 60,
    1: 120,
    2: 200,
}


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


def current_auction_plan(state: dict) -> list[dict]:
    round_number = state.get("round")
    auctions = state.get("auctions", [])

    if not isinstance(auctions, list):
        return []

    return [
        auction
        for auction in auctions
        if isinstance(auction, dict)
        and auction.get("round") == round_number
        and auction.get("status") == "open"
    ]


def print_round_info(state: dict) -> None:
    round_number = state.get("round")
    server_time = state.get("serverTime")
    deadlines = state.get("deadlines", [])

    print()
    print("===== ČAS KOLA =====")
    print(f"Aktuální kolo: {round_number}")
    print(f"Serverový čas: {server_time}")
    print(f"Serverový čas čitelně: {format_time(server_time)}")

    if (
        isinstance(round_number, int)
        and isinstance(deadlines, list)
        and 0 <= round_number < len(deadlines)
    ):
        deadline = deadlines[round_number]

        print(f"Uzávěrka kola: {deadline}")
        print(f"Uzávěrka kola čitelně: {format_time(deadline)}")

        if isinstance(server_time, (int, float)):
            seconds_left = max(0, (deadline - server_time) / 1000)

            print(f"Zbývá sekund: {seconds_left:.0f}")
            print(f"Zbývá minut: {seconds_left / 60:.1f}")

            if seconds_left <= 60:
                print("REŽIM: poslední minuta před uzávěrkou kola.")
            else:
                print("REŽIM: nejsme v poslední minutě před uzávěrkou kola.")
    else:
        print("Uzávěrku aktuálního kola se nepodařilo určit.")


def print_auction_plan(state: dict) -> None:
    server_time = state.get("serverTime")
    auctions = current_auction_plan(state)

    print()
    print("===== PLÁN AUKCÍ - DRY RUN =====")

    if not auctions:
        print("V aktuálním kole nejsou otevřené aukce.")
        return

    for auction in auctions:
        auction_id = auction.get("id")
        tier = auction.get("tier")
        current_bid = auction.get("bid")
        minimum_bid = auction.get("minBid")
        bidder = auction.get("bidder")
        closes_at = auction.get("closesAt")
        hard_close = auction.get("hardClose")

        max_bid = MAX_BID_BY_TIER.get(tier)

        print()
        print(f"Aukce: {auction_id}")
        print(f"  Název: {auction.get('name')}")
        print(f"  Tier: {tier}")
        print(f"  Aktuální nabídka: {current_bid}")
        print(f"  Minimální další příhoz: {minimum_bid}")
        print(f"  Aktuální vedoucí: {bidder}")
        print(f"  Uzavírá se: {format_time(closes_at)}")
        print(f"  Tvrdá uzávěrka: {format_time(hard_close)}")
        print(f"  Můj maximální limit: {max_bid}")

        if isinstance(server_time, (int, float)) and isinstance(
            closes_at,
            (int, float),
        ):
            seconds_to_close = max(0, (closes_at - server_time) / 1000)
            print(f"  Do uzavření aukce zbývá: {seconds_to_close:.0f} sekund")

        if max_bid is None:
            print("  ROZHODNUTÍ: tier nemá nastavený limit.")
            continue

        if not isinstance(minimum_bid, int):
            print("  ROZHODNUTÍ: nelze určit minimální příhoz.")
            continue

        if minimum_bid <= max_bid:
            print(
                f"  ROZHODNUTÍ: hypoteticky přihodit {minimum_bid} zl."
            )
        else:
            print(
                "  ROZHODNUTÍ: nepřihazovat, "
                f"minimum {minimum_bid} > limit {max_bid}."
            )


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
