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
            print(f"HTTP {response.status} {path}")
            return json.loads(raw)

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

    print("===== ODESÍLÁNÍ PŘÍHOZU =====")
    print(f"Aukce: {auction['id']}")
    print(f"Částka: {auction['plannedBid']}")
    print(f"Limit: {auction['limit']}")
    print(f"Uzávěrka: {format_time(auction.get('closesAt'))}")

    return post_json("/api/action", payload)


def main() -> None:
    print(f"Room: {ROOM_CODE}")
    print("Jednorázová kontrola aukcí.")

    state = get_state()
    candidate = choose_candidate(state)

    if candidate is None:
        print("Žádná vhodná aukce.")
        return

    print("Vybraná aukce:")
    print(f"ID: {candidate['id']}")
    print(f"Název: {candidate.get('name')}")
    print(f"Tier: {candidate.get('tier')}")
    print(f"Bid: {candidate.get('bid')}")
    print(f"Bidder: {candidate.get('bidder')}")
    print(f"MinBid: {candidate.get('minBid')}")
    print(f"Limit: {candidate.get('limit')}")
    print(f"Uzávěrka: {format_time(candidate.get('closesAt'))}")

    result = send_bid(state, candidate)

    print("Odpověď serveru:")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
