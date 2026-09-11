import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://zlodejipokladu.pages.dev"

ROOM_CODE = os.environ["ROOM_CODE"]
TOKEN = os.environ["TOKEN"]

# True = pouze vypíše plán.
# False = může odeslat skutečný příhoz.
DRY_RUN = False

MAX_BID_BY_TIER = {
    0: 60,
    1: 120,
    2: 200,
}

# Pokud je True, agent z bezpečnostních důvodů automaticky
# neodešle příhoz, pokud aukce zavírá za více než tuto dobu.
# Pro jednorázový test nastavujeme None.
TEST_ONLY_AUCTION_ID = "a19-5"


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


def current_open_auctions(state: dict) -> list[dict]:
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


def choose_bid(state: dict) -> dict | None:
    auctions = current_open_auctions(state)

    for auction in auctions:
        auction_id = auction.get("id")

        if (
            TEST_ONLY_AUCTION_ID is not None
            and auction_id != TEST_ONLY_AUCTION_ID
        ):
            continue

        tier = auction.get("tier")
        minimum_bid = auction.get("minBid")
        bidder = auction.get("bidder")

        max_bid = MAX_BID_BY_TIER.get(tier)

        if max_bid is None:
            print(f"Aukce {auction_id}: tier nemá nastavený limit.")
            continue

        if not isinstance(minimum_bid, int):
            print(f"Aukce {auction_id}: chybí platný minBid.")
            continue

        if bidder is None:
            raise RuntimeError(
                f"Aukce {auction_id} nemá bidder. "
                "Před ostrým příhozem ověř payload ve webu."
            )

        if minimum_bid > max_bid:
            print(
                f"Aukce {auction_id}: nepřihazovat, "
                f"{minimum_bid} > limit {max_bid}."
            )
            continue

        return {
            "id": auction_id,
            "amount": minimum_bid,
            "tier": tier,
            "current_bid": auction.get("bid"),
            "bidder": bidder,
            "max_bid": max_bid,
        }

    return None


def send_bid(auction_id: str, amount: int) -> dict:
    payload = {
        "code": ROOM_CODE,
        "token": TOKEN,
        "action": {
            "type": "auction-bid",
            "id": auction_id,
            "amount": amount,
        },
    }

    print()
    print("===== ODESÍLÁNÍ PŘÍHOZU =====")
    print(f"Aukce: {auction_id}")
    print(f"Částka: {amount}")
    print("Akce: auction-bid")

    return post_json("/api/act", payload)


def verify_bid(state: dict, auction_id: str, amount: int) -> None:
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
        print("Aukce po odeslání nebyla ve stavu nalezena.")
        return

    print(f"Stav aukce: {auction.get('status')}")
    print(f"Aktuální nabídka po akci: {auction.get('bid')}")
    print(f"Vedoucí po akci: {auction.get('bidder')}")
    print(f"Odeslaná částka: {amount}")


def main() -> None:
    print(f"Testing room: {ROOM_CODE}")
    print(f"DRY_RUN={DRY_RUN}")
    print(f"TEST_ONLY_AUCTION_ID={TEST_ONLY_AUCTION_ID}")

    state_before = get_state()
    selected_bid = choose_bid(state_before)

    if selected_bid is None:
        print()
        print("Nebyla nalezena aukce splňující podmínky.")
        return

    print()
    print("===== VYBRANÝ PŘÍHOZ =====")
    print(f"Aukce: {selected_bid['id']}")
    print(f"Tier: {selected_bid['tier']}")
    print(f"Aktuální nabídka: {selected_bid['current_bid']}")
    print(f"Minimální příhoz: {selected_bid['amount']}")
    print(f"Maximální limit: {selected_bid['max_bid']}")
    print(f"Současný vedoucí: {selected_bid['bidder']}")

    if DRY_RUN:
        print()
        print("DRY_RUN=True – příhoz nebyl odeslán.")
        return

    result = send_bid(
        auction_id=selected_bid["id"],
        amount=selected_bid["amount"],
    )

    print()
    print("Odpověď akce:")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])

    state_after = get_state()

    verify_bid(
        state=state_after,
        auction_id=selected_bid["id"],
        amount=selected_bid["amount"],
    )


if __name__ == "__main__":
    main()
