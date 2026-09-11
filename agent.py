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

# Jednorázový zápisový test.
DRY_RUN = False

TARGET_AUCTION_ID = os.environ["TARGET_AUCTION_ID"]
TEST_BID_AMOUNT = int(os.environ["TEST_BID_AMOUNT"])


def post_json(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8")

    request = Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zlodeji-agent-write-test/1.0",
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


def find_target_auction(state: dict) -> dict:
    auctions = state.get("auctions", [])
    round_number = state.get("round")

    auction = next(
        (
            item
            for item in auctions
            if isinstance(item, dict)
            and item.get("id") == TARGET_AUCTION_ID
        ),
        None,
    )

    if auction is None:
        raise RuntimeError(
            f"Aukce {TARGET_AUCTION_ID} nebyla nalezena."
        )

    if auction.get("round") != round_number:
        raise RuntimeError(
            f"Aukce není z aktuálního kola. "
            f"Aukce: {auction.get('round')}, aktuální: {round_number}."
        )

    if auction.get("status") != "open":
        raise RuntimeError(
            f"Aukce není otevřená. Stav: {auction.get('status')}."
        )

    return auction


def send_test_bid(state: dict, auction: dict) -> dict:
    payload = {
        "code": ROOM_CODE,
        "token": TOKEN,
        "requestId": str(uuid.uuid4()),
        "action": {
            "type": "auction-bid",
            "id": auction["id"],
            "amount": TEST_BID_AMOUNT,
            "round": state["round"],
        },
    }

    print()
    print("===== TESTOVACÍ ZÁPIS =====")
    print(f"Endpoint: /api/action")
    print(f"Aukce: {auction['id']}")
    print(f"Původní nabídka: {auction.get('bid')}")
    print(f"Nová nabídka: {TEST_BID_AMOUNT}")
    print(f"Round: {state['round']}")
    print(f"Request ID: {payload['requestId']}")

    return post_json("/api/action", payload)


def verify_result(auction_id: str) -> None:
    state = get_state()

    auction = next(
        (
            item
            for item in state.get("auctions", [])
            if isinstance(item, dict)
            and item.get("id") == auction_id
        ),
        None,
    )

    print()
    print("===== OVĚŘENÍ =====")

    if auction is None:
        print("Aukce nebyla nalezena.")
        return

    print(f"Status: {auction.get('status')}")
    print(f"Bid: {auction.get('bid')}")
    print(f"Bidder: {auction.get('bidder')}")
    print(f"Počet příhozů: {auction.get('bids')}")


def main() -> None:
    print(f"Room: {ROOM_CODE}")
    print(f"Target auction: {TARGET_AUCTION_ID}")
    print(f"Test bid amount: {TEST_BID_AMOUNT}")

    state = get_state()
    auction = find_target_auction(state)

    print()
    print("===== KONTROLA PŘED TESTEM =====")
    print(f"Status: {auction.get('status')}")
    print(f"Současný bidder: {auction.get('bidder')}")
    print(f"Současný bid: {auction.get('bid')}")
    print(f"Minimální bid podle stavu: {auction.get('minBid')}")
    print(f"Uzávěrka: {format_time(auction.get('closesAt'))}")

    if TEST_BID_AMOUNT < auction["minBid"]:
        raise RuntimeError(
            f"TEST_BID_AMOUNT musí být alespoň {auction['minBid']}."
        )

    result = send_test_bid(state, auction)

    print()
    print("===== ODPOVĚĎ SERVERU =====")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])

    verify_result(auction["id"])


if __name__ == "__main__":
    main()
