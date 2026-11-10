"""Reviewed settlement profile for the December 2026 FOMC decision."""
from decimal import Decimal
import re

from kalshi_engine.arbitrage import Condition

EVENT = "KXFED-26DEC"
TERMS_URL = "https://assets.kalshi.com/contract_terms/FED.pdf"
SOURCE = {
    "name": "Federal Reserve Board of Governors",
    "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
}
CLOSE = "2026-12-09T18:55:00Z"
SECONDARY = (
    "This market will expire the first 2:05 PM ET following the release of a Federal Reserve "
    "statement for their Dec 9, 2026 meeting or one week following the last day of that meeting."
)


def verified_conditions(event, markets, metadata):
    if event != EVENT or metadata.get("strike_date") != "2026-12-09T19:00:00Z":
        raise ValueError(f"unreviewed Fed meeting {event}")
    if metadata.get("mutually_exclusive") is not False:
        raise ValueError(f"expected a directional Fed event for {event}")
    conditions = {}
    for ticker, market in sorted(markets.items()):
        if market["event_ticker"] != event:
            continue
        match = re.fullmatch(r"KXFED-26DEC-T([0-9]+\.[0-9]{2})", ticker)
        if not match:
            raise ValueError(f"unsupported Fed market {ticker}")
        strike_text = match[1]
        strike = Decimal(strike_text)
        rule = (
            "If the upper bound of the target federal funds rate published on the Federal "
            f"Reserve's official website is greater than {strike_text}% following the Federal "
            "Reserve's Dec 9, 2026 meeting, then the market resolves to Yes."
        )
        if (
            market.get("market_type"), market.get("strike_type"), market.get("cap_strike"),
            market.get("notional_value_dollars"), market.get("rules_primary"),
            market.get("rules_secondary"), market.get("close_time"),
            market.get("latest_expiration_time"),
        ) != ("binary", "greater", None, "1.0000", rule, SECONDARY, CLOSE, "2026-12-16T19:05:00Z"):
            raise ValueError(f"changed Fed contract rules or timing for {ticker}")
        if Decimal(str(market.get("floor_strike"))) != strike:
            raise ValueError(f"Fed strike differs from the rule text for {ticker}")
        conditions[ticker] = Condition(ticker, "greater", lower=strike)
    if len(conditions) < 2:
        raise ValueError(f"insufficient verified Fed strikes for {event}")
    return conditions
