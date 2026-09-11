import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]

PENDING_REQUEST_ID = os.environ["PENDING_REQUEST_ID"]
PENDING_AUCTION_ID = os.environ["PENDING_AUCTION_ID"]
PENDING_AMOUNT = int(os.environ["PENDING_AMOUNT"])


def post_json(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8")

    request = Request(
        url=url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zlodeji-agent-recovery/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")

            print(f"HTTP {response.status} {path}")

            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                print("Server nevrátil platný JSON.", file=sys.stderr)
                print(raw[:4000], file=sys.stderr)
                raise

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


def find_pending_auction(state: dict) -> dict | None:
    auctions = state.get("auctions", [])

    for auction in auctions:
        if (
            isinstance(auction, dict)
            and auction.get("id") == PENDING_AUCTION_ID
        ):
            return auction

    return None


def main() -> None:
    print("=== PENDING RECOVERY ===")
    print(f"Room: {ROOM_CODE}")
    print(f"Request ID: {PENDING_REQUEST_ID}")
    print(f"Aukce: {PENDING_AUCTION_ID}")
    print(f"Původní částka: {PENDING_AMOUNT}")

    state = get_state()

    round_number = state.get("round")
    auction = find_pending_auction(state)

    if auction is None:
        raise RuntimeError(
            f"Aukce {PENDING_AUCTION_ID} nebyla nalezena ve stavu."
        )

    print()
    print("=== AKTUÁLNÍ STAV AUKCE ===")
    print(f"Status: {auction.get('status')}")
    print(f"Bid: {auction.get('bid')}")
    print(f"Bidder: {auction.get('bidder')}")
    print(f"ClosesAt: {auction.get('closesAt')}")
    print(f"HardClose: {auction.get('hardClose')}")
    print(f"Aktuální kolo: {round_number}")

    action = {
        "type": "auction-bid",
        "id": PENDING_AUCTION_ID,
        "amount": PENDING_AMOUNT,
        "round": round_number,
    }

    payload = {
        "mode": "online",
        "code": ROOM_CODE,
        "token": TOKEN,
        "requestId": PENDING_REQUEST_ID,
        "action": action,
        "round": round_number,
    }

    print()
    print("=== ODESÍLÁNÍ RECOVERY REQUESTU ===")
    print("Endpoint: /api/entry")
    print("Action type: auction-bid")
    print(f"Action ID: {PENDING_AUCTION_ID}")
    print(f"Action amount: {PENDING_AMOUNT}")
    print(f"Round: {round_number}")

    result = post_json("/api/entry", payload)

    print()
    print("=== ODPOVĚĎ SERVERU ===")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])

    print()
    print("Recovery request byl odeslán.")
    print("Neodstraňuj zatím income-pending, dokud neověříme výsledek.")


if __name__ == "__main__":
    main()
