import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]

CHECK_INTERVAL_SECONDS = 45

# 5 hodin a 50 minut.
RUN_DURATION_SECONDS = 5 * 60 * 60 + 50 * 60

MAX_BID_BY_TIER = {
    0: 60,
    1: 120,
    2: 200,
}

TARGET_AUCTION_ID = os.environ.get("TARGET_AUCTION_ID", "").strip()


def post_json(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8")

    request = Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zlodeji-agent-auction/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            print(f"HTTP {response.status} {path}", flush=True)
            return json.loads(raw)

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"HTTP {error.code} {path}", file=sys.stderr, flush=True)
        print(body[:4000], file=sys.stderr, flush=True)
        raise

    except URLError as error:
        print(f"Chyba připojení: {error}", file=sys.stderr, flush=True)
        raise


def get_state() -> dict:
    response = post_json(
        "/api/state",
        {
            "code": ROOM_CODE,
            "token": TOKEN,
        },
    )

    state = response.get("state")

    if not isinstance(state, dict):
        raise RuntimeError("Odpověď neobsahuje objekt state.")

    return state


def format_time(timestamp):
    if not isinstance(timestamp, (int, float)):
        return "neuvedeno"

    return datetime.fromtimestamp(
        timestamp / 1000,
        tz=timezone.utc,
    ).strftime("%Y-%m-%d %H:%M:%S UTC")


def choose_candidate(state: dict) -> dict | None:
    me = state.get("me")

    if not isinstance(me, dict):
        raise RuntimeError("Stav neobsahuje objekt me.")

    my_id = str(me.get("id"))
    available_gold = int(
        me.get(
            "availableGold",
            me.get("gold", 0),
        )
    )
    current_round = state.get("round")

    auctions = [
        auction
        for auction in state.get("auctions", [])
        if isinstance(auction, dict)
        and auction.get("round") == current_round
        and auction.get("status") == "open"
    ]

    auctions.sort(
        key=lambda auction: (
            auction.get("closesAt", float("inf")),
            auction.get("id", ""),
        )
    )

    for auction in auctions:
        if TARGET_AUCTION_ID and auction.get("id") != TARGET_AUCTION_ID:
            continue

        if str(auction.get("bidder")) == my_id:
            continue

        tier = auction.get("tier")
        limit = MAX_BID_BY_TIER.get(tier)
        minimum_bid = auction.get("minBid")

        if limit is None:
            continue

        if not isinstance(minimum_bid, int):
            continue

        if minimum_bid > limit:
            continue

        if minimum_bid > available_gold:
            continue

        return {
            **auction,
            "plannedBid": minimum_bid,
            "limit": limit,
        }

    return None


def send_bid(state: dict, auction: dict) -> dict:
    payload = {
        "code": ROOM_CODE,
        "token": TOKEN,
        "requestId": str(uuid.uuid4()),
        "action": {
            "type": "auction-bid",
            "id": auction["id"],
            "amount": auction["plannedBid"],
            "round": state["round"],
        },
    }

    print("===== ODESÍLÁNÍ PŘÍHOZU =====", flush=True)
    print(f"Aukce: {auction['id']}", flush=True)
    print(f"Částka: {auction['plannedBid']}", flush=True)
    print(f"Limit: {auction['limit']}", flush=True)
    print(
        f"Uzávěrka: {format_time(auction.get('closesAt'))}",
        flush=True,
    )

    return post_json("/api/action", payload)


def process_once() -> None:
    print(
        f"===== KONTROLA {datetime.now(timezone.utc).isoformat()} =====",
        flush=True,
    )

    state = get_state()
    candidate = choose_candidate(state)

    if candidate is None:
        print(
            "Žádná vhodná aukce.",
            flush=True,
        )
        return

    print(
        f"Vybraná aukce: {candidate['id']}",
        flush=True,
    )

    result = send_bid(state, candidate)

    print("Odpověď serveru:", flush=True)
    print(
        json.dumps(result, ensure_ascii=False, indent=2)[:4000],
        flush=True,
    )

    # Po úspěšném příhozu se další kontrola provede
    # až po 45 sekundách. Serverový stav se tím znovu ověří.
    print("Příhoz dokončen.", flush=True)


def main() -> None:
    print(f"Room: {ROOM_CODE}", flush=True)
    print(
        f"Kontrola každých {CHECK_INTERVAL_SECONDS} sekund.",
        flush=True,
    )
    print(
        f"Běh potrvá přibližně {RUN_DURATION_SECONDS // 60} minut.",
        flush=True,
    )

    started = time.monotonic()
    next_run = started

    while time.monotonic() - started < RUN_DURATION_SECONDS:
        now = time.monotonic()

        if now < next_run:
            time.sleep(min(next_run - now, 5))
            continue

        try:
            process_once()
        except Exception as error:
            print(
                f"Chyba během kontroly: {error}",
                file=sys.stderr,
                flush=True,
            )

        next_run += CHECK_INTERVAL_SECONDS

    print("Běh agenta skončil.", flush=True)


if __name__ == "__main__":
    main()
