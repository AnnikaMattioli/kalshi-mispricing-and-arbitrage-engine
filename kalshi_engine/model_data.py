"""Fetch the fixed Phase 5 NBA cohort from Kalshi's public API."""
import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from kalshi_engine import nba
from kalshi_engine.collect import BASE_URL, fetch

SERIES = "KXNBAGAME"
START = date(2026, 10, 20)
SPLIT = date(2026, 11, 3)
END = date(2026, 11, 10)
HOUR = 3600


def at(day, hour=0):
    return datetime.combine(day, time(hour), timezone.utc)


def event_day(ticker):
    match = re.fullmatch(r"KXNBAGAME-(\d{2}[A-Z]{3}\d{2})[A-Z]{6}", ticker)
    return datetime.strptime(match[1], "%y%b%d").date() if match else None


def cohort(markets):
    """One lexicographically first team contract per verified binary game."""
    games = defaultdict(list)
    for market in markets:
        day = event_day(market["event_ticker"])
        if day and START <= day < END:
            games[market["event_ticker"]].append(market)
    rows = []
    rejected = defaultdict(int)
    for event, markets in sorted(games.items()):
        markets.sort(key=lambda market: market["ticker"])
        day = event_day(event)
        signal = at(day, 12)
        teams = (event[-6:-3], event[-3:])
        if (len(markets) != 2 or {m["ticker"] for m in markets} !=
                {f"{event}-{team}" for team in teams}
                or {(m.get("result"), m.get("settlement_value_dollars")) for m in markets}
                != {("yes", "1.0000"), ("no", "0.0000")}):
            rejected["noncomplementary_or_nonbinary"] += 1
            continue
        if any(
            m.get("market_type") != "binary" or m.get("strike_type") != "structured"
            or m.get("notional_value_dollars") != "1.0000"
            or not re.fullmatch(
                r"If .+ wins the .+ Pro Basketball game originally scheduled for "
                + re.escape(f"{day:%b} {day.day}, {day.year}")
                + r", then the market resolves to Yes\.",
                m.get("rules_primary", ""),
            )
            or sha256(m.get("rules_secondary", "").encode()).hexdigest() != nba.SECONDARY
            for m in markets
        ):
            rejected["unverified_rules"] += 1
            continue
        # The NBA market's latest expiration is 48 hours after scheduled tip.
        # Require the morning forecast to precede this proxy and actual close.
        if any(
            signal >= min(datetime.fromisoformat(m["close_time"]),
                          datetime.fromisoformat(m["latest_expiration_time"]) - timedelta(hours=48))
            for m in markets
        ):
            rejected["timing"] += 1
            continue
        rows.append({
            "event": event, "ticker": markets[0]["ticker"], "day": day.isoformat(),
            "signal_ts": int(signal.timestamp()), "label": int(markets[0]["result"] == "yes"),
            "settled_ts": max(datetime.fromisoformat(m["settlement_ts"]).timestamp() for m in markets),
        })
    return rows, dict(rejected)


def download(directory):
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / "requests.jsonl"
    with raw_path.open("x", encoding="utf-8") as raw:
        def get(endpoint, **query):
            url = f"{BASE_URL}/{endpoint}"
            if query:
                url += "?" + urlencode(query)
            response = fetch(url)
            raw.write(json.dumps({"url": url, **response}) + "\n")
            raw.flush()
            if response.get("status") != 200 or "payload" not in response:
                raise ValueError(f"request failed for {endpoint}: {response.get('error')}")
            return response["payload"]

        cutoff = get("historical/cutoff")
        if datetime.fromisoformat(cutoff["market_settled_ts"]) > at(START):
            raise ValueError("fixed cohort has moved into the archive; use the saved request file")
        get(f"series/{SERIES}")
        cursor = ""
        seen = set()
        markets = []
        while True:
            page = get("markets", series_ticker=SERIES, status="settled", limit=100,
                       min_settled_ts=int(at(START).timestamp()),
                       max_settled_ts=int(at(END + timedelta(days=1)).timestamp()), cursor=cursor)
            markets.extend(page["markets"])
            cursor = page["cursor"]
            if not cursor:
                break
            if cursor in seen:
                raise ValueError("market cursor repeated")
            seen.add(cursor)
        rows, _ = cohort(markets)
        by_time = defaultdict(list)
        for row in rows:
            by_time[row["signal_ts"]].append(row["ticker"])
        for signal, tickers in sorted(by_time.items()):
            get("markets/candlesticks", market_tickers=",".join(tickers),
                start_ts=signal - 14 * HOUR, end_ts=signal, period_interval=60)
    return raw_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("captures/phase-5"))
    args = parser.parse_args()
    try:
        print(download(args.output))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Download failed: {exc}\n")


if __name__ == "__main__":
    main()
