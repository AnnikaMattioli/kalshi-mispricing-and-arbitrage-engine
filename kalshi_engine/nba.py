"""Reviewed full-game winner profile for Miami–Utah on November 10, 2026."""
from decimal import Decimal
from hashlib import sha256

from kalshi_engine.arbitrage import Condition

EVENT = "KXNBAGAME-26NOV10MIAUTA"
TERMS_URL = "https://assets.kalshi.com/contract_terms/BASKETBALLGAMEWIN.pdf"
SOURCES = [
    {"name": "ESPN", "url": "https://www.espn.com"},
    {"name": "the Governing League", "url": "https://www.nba.com"},
]
TEAM_IDS = {
    "MIA": "a17e4a68-2999-4f60-b67e-3e80aa9e198b",
    "UTA": "6f60dfb1-fda1-423f-b76f-67e9d24b9644",
}
PRIMARY = {
    "MIA": "c48323993440bfa3e60eef0dd86725bf0b33cdcfe953f3ab2e85a2ad38ea27a7",
    "UTA": "7a3592ee609720629e7781bcb9e1339a9fddf85f9b985086ef017cea82ea5934",
}
SECONDARY = "6151ee9b4de11ad7e2672df30490361521e905bcfdb21156cd6adeb755b27bfd"


def verified_outcomes(event, markets, metadata):
    if event != EVENT or metadata.get("mutually_exclusive") is not True or metadata.get(
        "product_metadata", {}
    ).get("competition_scope") != "Game":
        raise ValueError(f"unreviewed full-game NBA event {event}")
    expected = {f"{event}-{team}" for team in TEAM_IDS}
    if {ticker for ticker, market in markets.items() if market["event_ticker"] == event} != expected:
        raise ValueError("NBA winner basket requires exactly the two reviewed team strikes")
    conditions = {}
    for team, team_id in TEAM_IDS.items():
        ticker = f"{event}-{team}"
        market = markets[ticker]
        primary, secondary = (
            sha256(market.get(key, "").encode()).hexdigest()
            for key in ("rules_primary", "rules_secondary")
        )
        if (market.get("market_type"), market.get("strike_type"),
                market.get("notional_value_dollars"), market.get("custom_strike"),
                primary, secondary) != (
            "binary", "structured", "1.0000", {"basketball_team": team_id},
            PRIMARY[team], SECONDARY,
        ):
            raise ValueError(f"changed NBA team or settlement rules for {ticker}")
        conditions[ticker] = Condition(ticker, "winner")
    miami, utah = conditions
    half = Decimal("0.50")
    # Map each verified outcome to YES settlement values. NO is the complement.
    return conditions, (
        {miami: 1, utah: 0},
        {miami: 0, utah: 1},
        {miami: half, utah: half},
    )
