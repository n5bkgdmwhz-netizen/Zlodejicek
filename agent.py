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

TARGET_AUCTION_ID = os.environ.get("TARGET_AUCTION_ID", "")
DRY_RUN = True


def post_json(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8")

    request = Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zlodeji-agent-readonly/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            print(f"HTTP {response.status} {path}")
            return json.loads(raw)

    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        print(f"HTTP {error.code} {path}", file=sys.stderr)
        print(response_body[:4000], file=sys.stderr)
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


def choose_auction(state: dict) -> dict | None:
    round_number = state.get("round")
    auctions = state.get("auctions", [])

    candidates = [
        auction
        for auction in auctions
        if isinstance(auction, dict)
        and auction.get("round") == round_number
        and auction.get("status") == "open"
    ]

    if TARGET_AUCTION_ID:
        candidates = [
            auction
            for auction in candidates
            if auction.get("id") == TARGET_AUCTION_ID
        ]

    candidates.sort(
        key=lambda auction: auction.get("closesAt", float("inf"))
    )

    for auction in candidates:
        tier = auction.get("tier")
        minimum_bid = auction.get("minBid")
        max_bid = MAX_BID_BY_TIER.get(tier)

        if (
            isinstance(minimum_bid, int)
            and isinstance(max_bid, int)
            and minimum_bid <= max_bid
        ):
            return auction

    return None


def main() -> None:
    print(f"Room: {ROOM_CODE}")
    print(f"DRY_RUN: {DRY_RUN}")

    state = get_state()
    auction = choose_auction(state)

    if auction is None:
        print("Nebyla nalezena vhodná otevřená aukce.")
        return

    round_number = state["round"]
    request_id = str(uuid.uuid4())

    action = {
        "type": "auction-bid",
        "id": auction["id"],
        "amount": auction["minBid"],
        "round": round_number,
    }

    candidate_payload = {
        "mode": "online",
        "code": ROOM_CODE,
        "token": "<SECRET>",
        "requestId": request_id,
        "action": action,
        "round": round_number,
    }

    print()
    print("===== VYBRANÁ AUKCE =====")
    print(f"ID: {auction.get('id')}")
    print(f"Název: {auction.get('name')}")
    print(f"Tier: {auction.get('tier')}")
    print(f"Status: {auction.get('status')}")
    print(f"Aktuální nabídka: {auction.get('bid')}")
    print(f"Minimální příhoz: {auction.get('minBid')}")
    print(f"Vedoucí: {auction.get('bidder')}")
    print(f"Uzávěrka: {format_time(auction.get('closesAt'))}")
    print(f"Volné zlato: {state.get('me', {}).get('availableGold')}")
    print(f"Rezervované zlato: {state.get('me', {}).get('auctionHeld')}")

    print()
    print("===== KANDIDÁTNÍ PAYLOAD =====")
    print(json.dumps(candidate_payload, ensure_ascii=False, indent=2))

    print()
    print("Žádný zápisový request nebyl odeslán.")


if __name__ == "__main__":
    main()
