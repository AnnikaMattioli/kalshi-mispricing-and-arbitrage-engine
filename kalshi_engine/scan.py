"""Evaluate verified NYC weather contracts from one local collector sweep."""
import argparse
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re

from kalshi_engine.arbitrage import Book, Condition, candidates, evaluate
from kalshi_engine.collect import book_counts

SECONDARY_RULES_HASH = "c1f11eaf372267f2e69ca8ba131916928052ec5e92138e45c16e197f2d4bb507"
TERMS_URL = "https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf"


def verified_conditions(event, markets):
    match = re.fullmatch(r"KXHIGHNY-(\d{2})([A-Z]{3})(\d{2})", event)
    if match is None:
        raise ValueError(f"unverified NYC event ticker {event}")
    year, month, day = match.groups()
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    if month.title() not in months:
        raise ValueError(f"unverified NYC event month {event}")
    event_date = datetime(2000 + int(year), months.index(month.title()) + 1, int(day))
    date = f"{months[event_date.month - 1]} {event_date.day}, {event_date.year}"
    tails = [market.get("cap_strike") for market in markets.values()
             if market.get("event_ticker") == event and market.get("strike_type") == "less"]
    if len(tails) != 1 or type(tails[0]) is not int:
        raise ValueError(f"expected one integer lower tail for {event}")
    start = tails[0]
    prefix = f"If the maximum temperature recorded at New York City (CLINYC) for {date}, is "
    suffix = "° fahrenheit according to The Weather Company, then the market resolves to Yes."
    specifications = [(f"T{start}", "less", None, start, f"less than {start}")]
    specifications += [
        (f"B{low}.5", "between", low, low + 1, f"between {low}-{low + 1}")
        for low in range(start, start + 8, 2)
    ]
    top = start + 7
    specifications.append((f"T{top}", "greater", top, None, f"greater than {top}"))
    conditions = {}
    for suffix_ticker, operator, lower, upper, comparison in specifications:
        ticker = f"{event}-{suffix_ticker}"
        market = markets.get(ticker)
        if market is None or (
            market.get("event_ticker"), market.get("market_type"), market.get("strike_type"),
            market.get("floor_strike"), market.get("cap_strike"), market.get("rules_primary"),
            market.get("notional_value_dollars"),
        ) != (event, "binary", operator, lower, upper, prefix + comparison + suffix, "1.0000"):
            raise ValueError(f"missing or changed verified market {ticker}")
        secondary = market.get("rules_secondary", "").encode("utf-8")
        if sha256(secondary).hexdigest() != SECONDARY_RULES_HASH:
            raise ValueError(f"changed secondary rules for {ticker}")
        conditions[ticker] = Condition(ticker, operator, lower, upper)
    if {ticker for ticker, market in markets.items() if market["event_ticker"] == event} != set(conditions):
        raise ValueError(f"unexpected market in verified event {event}")
    return conditions


def parse_book(record):
    payload = record.get("payload")
    if record.get("status") != 200 or book_counts(payload) is None:
        return None
    ladders = []
    for side in ("yes_dollars", "no_dollars"):
        levels = tuple((Decimal(price), Decimal(size)) for price, size in payload["orderbook_fp"][side])
        if any(not p.is_finite() or not q.is_finite() or not 0 < p < 1 or q <= 0
               or p.as_tuple().exponent < -4 or q.as_tuple().exponent < -2 for p, q in levels):
            raise ValueError(f"invalid fixed-point level in {record['ticker']}")
        ladders.append(levels)
    if all(ladders) and sum(max(levels)[0] for levels in ladders) > 1:
        raise ValueError(f"crossed order book in {record['ticker']}")
    return Book(datetime.fromisoformat(record["started_at"]),
                datetime.fromisoformat(record["received_at"]), *ladders)


@dataclass(frozen=True)
class Frame:
    as_of: datetime
    conditions: dict
    books: dict
    close_times: dict
    multiplier: Decimal


def read_capture(path):
    with path.open(encoding="utf-8") as capture:
        return [json.loads(line) for line in capture]


def event_tickers(records):
    return sorted({r["ticker"] for r in records if r["kind"] == "event" and r.get("payload")})


def load_frame(records, event):
    if (len(records) < 2 or any(r.get("schema_version") != 1 for r in records)
            or records[0]["kind"] != "sweep_start" or records[-1]["kind"] != "sweep_end"):
        raise ValueError("expected one complete version 1 sweep")
    summary = records[-1]["counts"]
    if any(summary.get(key) for key in ("invalid_market_pages", "invalid_markets")):
        raise ValueError("capture has incomplete market discovery")

    series = {}
    markets = {}
    events = {}
    books = {}
    for record in records[1:-1]:
        kind = record["kind"]
        payload = record.get("payload")
        if kind == "series" and payload:
            series = payload["series"]
        elif kind == "markets":
            if not payload:
                raise ValueError("market discovery request failed")
            markets.update((m["ticker"], m) for m in payload["markets"])
        elif kind == "event" and payload:
            events[record["ticker"]] = payload["event"]
        elif kind == "book":
            books[record["ticker"]] = record
    if (series.get("ticker"), series.get("contract_terms_url"), series.get("fee_type")) != (
        "KXHIGHNY", TERMS_URL, "quadratic"
    ):
        raise ValueError("unverified series, terms or fee type")
    metadata = events.get(event, {})
    if metadata.get("series_ticker") != "KXHIGHNY" or metadata.get("settlement_sources") != [
        {"name": "The Weather Company", "url": "https://weather.com/kalshi"}
    ]:
        raise ValueError("missing verified event settlement source")
    if metadata.get("fee_type_override") or metadata.get("fee_multiplier_override") is not None:
        raise ValueError("event fee override requires review")
    conditions = verified_conditions(event, markets)
    multiplier = Decimal(str(series["fee_multiplier"]))
    if not multiplier.is_finite() or multiplier < 0:
        raise ValueError("invalid fee multiplier")
    as_of = datetime.fromisoformat(records[-1]["ended_at"])
    selected_books = {ticker: parse_book(books[ticker]) for ticker in conditions if ticker in books}
    close_times = {ticker: datetime.fromisoformat(markets[ticker]["close_time"])
                   for ticker in conditions}
    return Frame(as_of, conditions, selected_books, close_times, multiplier)


def scan_frame(frame, quantity, max_age):
    books = {ticker: book for ticker, book in frame.books.items()
             if frame.as_of < frame.close_times[ticker]}
    return [evaluate(kind, legs, frame.conditions, books, quantity, frame.as_of,
                     max_age, frame.multiplier) for kind, legs in candidates(frame.conditions)]


def scan(records, event, quantity, max_age):
    return scan_frame(load_frame(records, event), quantity, max_age)


def encode(value):
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(type(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--event", required=True)
    parser.add_argument("--quantity", type=int, default=1, help="whole contracts per leg")
    parser.add_argument("--max-age", type=int, default=10, help="seconds at sweep end")
    args = parser.parse_args()
    if args.quantity < 1 or args.max_age < 1:
        parser.error("quantity and maximum age must be positive")
    try:
        results = scan(read_capture(args.capture), args.event, Decimal(args.quantity), args.max_age)
    except (OSError, KeyError, TypeError, ValueError, InvalidOperation) as exc:
        parser.exit(1, f"Scan failed: {exc}\n")
    print(json.dumps(results, indent=2, default=encode))


if __name__ == "__main__":
    main()
