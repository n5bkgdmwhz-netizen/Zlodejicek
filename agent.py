import json
import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]

DRY_RUN = False

MAX_BID_BY_TIER = {
    0: 60,
    1: 120,
    2: 200,
}

TARGET_AUCTION_ID = os.environ.get("TARGET_AUCTION_ID", "")


def post_json(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8")

    request = Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zlodeji-agent/1.0",
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


def get_me(state: dict) -> dict:
    me = state.get("me")

    if not isinstance(me, dict):
        raise RuntimeError("Stav neobsahuje objekt me.")

    return me


def get_open_auctions(state: dict) -> list[dict]:
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


def choose_candidate(state: dict) -> dict | None:
    me = get_me(state)
    my_id = me.get("id")
    available_gold = me.get("availableGold")

    if not isinstance(available_gold, (int, float)):
        available_gold = me.get("gold", 0)

    candidates = []

    for auction in get_open_auctions(state):
        auction_id = auction.get("id")
        bidder = auction.get("bidder")
        tier = auction.get("tier")
        minimum_bid = auction.get("minBid")
        max_bid = MAX_BID_BY_TIER.get(tier)

        if TARGET_AUCTION_ID and auction_id != TARGET_AUCTION_ID:
            continue

        if bidder == my_id:
            continue

        if not isinstance(minimum_bid, int):
            continue

        if max_bid is None:
            continue

        if minimum_bid > max_bid:
            continue

        if minimum_bid > available_gold:
            continue

        candidates.append(auction)

    candidates.sort(
        key=lambda auction: auction.get(
            "closesAt",
            float("inf"),
        )
    )

    if not candidates:
        return None

    selected = candidates[0]

    return {
        **selected,
        "plannedBid": selected["minBid"],
        "maxBid": MAX_BID_BY_TIER[selected["tier"]],
    }


def send_bid(state: dict, auction: dict) -> dict:
    request_id = str(uuid.uuid4())

    payload = {
        "code": ROOM_CODE,
        "token": TOKEN,
        "requestId": request_id,
        "action": {
            "type": "auction-bid",
            "id": auction["id"],
            "amount": auction["plannedBid"],
            "round": state["round"],
        },
    }

    print()
    print("===== ODESÍLÁNÍ PŘÍHOZU =====")
    print(f"Aukce: {auction['id']}")
    print(f"Částka: {auction['plannedBid']}")
    print(f"Request ID: {request_id}")
    print("Endpoint: /api/action")

    return post_json("/api/action", payload)


def verify_bid(auction_id: str, amount: int) -> None:
    state = get_state()
    auctions = state.get("auctions", [])

    auction = next(
        (
            item
            for item in auctions
            if isinstance(item, dict)
            and item.get("id") == auction_id
        ),
        None,
    )

    print()
    print("===== OVĚŘENÍ PŘÍHOZU =====")

    if auction is None:
        print("Aukce nebyla ve stavu nalezena.")
        return

    print(f"Status: {auction.get('status')}")
    print(f"Bid: {auction.get('bid')}")
    print(f"Bidder: {auction.get('bidder')}")
    print(f"Odeslaná částka: {amount}")


def main() -> None:
    print(f"Room: {ROOM_CODE}")
    print(f"DRY_RUN: {DRY_RUN}")
    print(f"TARGET_AUCTION_ID: {TARGET_AUCTION_ID or 'všechny'}")

    state = get_state()
    candidate = choose_candidate(state)

    if candidate is None:
        print()
        print("Aktuálně není žádná vhodná aukce.")
        print("Nebyl odeslán žádný zápisový request.")
        return

    print()
    print("===== KANDIDÁT PRO PŘÍHOZ =====")
    print(f"Aukce: {candidate['id']}")
    print(f"Název: {candidate.get('name')}")
    print(f"Tier: {candidate.get('tier')}")
    print(f"Aktuální bid: {candidate.get('bid')}")
    print(f"Vedoucí: {candidate.get('bidder')}")
    print(f"Plánovaný příhoz: {candidate['plannedBid']}")
    print(f"Limit: {candidate['maxBid']}")
    print(f"Uzávěrka: {format_time(candidate.get('closesAt'))}")

    if DRY_RUN:
        print("DRY_RUN=True – příhoz nebyl odeslán.")
        return

    result = send_bid(state, candidate)

    print()
    print("===== ODPOVĚĎ SERVERU =====")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])

    verify_bid(
        auction_id=candidate["id"],
        amount=candidate["plannedBid"],
    )


if __name__ == "__main__":
    main()
