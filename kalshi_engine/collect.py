"""Collect public Kalshi REST snapshots for local replay."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def fetch(url):
    """Return the response envelope, including failures for provenance."""
    started = utc_now()
    status = None
    retry_after = None
    try:
        with urlopen(url, timeout=10) as response:
            status = response.status
            raw = response.read()
            received = utc_now()
        payload = json.loads(raw)
        return {
            "started_at": started, "received_at": received,
            "status": status, "payload": payload,
        }
    except HTTPError as exc:
        status = exc.code
        retry_after = exc.headers.get("Retry-After")
        error = str(exc)
        exc.close()
    except (URLError, OSError, HTTPException, ValueError) as exc:
        error = str(exc)
    return {
        "started_at": started, "failed_at": utc_now(), "status": status,
        "error": error, "retry_after": retry_after,
    }


def book_counts(payload):
    try:
        book = payload["orderbook_fp"]
        yes, no = book["yes_dollars"], book["no_dollars"]
        for levels in (yes, no):
            if not isinstance(levels, list) or any(
                not isinstance(level, list) or len(level) != 2
                or not all(isinstance(value, str) for value in level)
                for level in levels
            ):
                return None
        return len(yes), len(no)
    except (KeyError, TypeError):
        return None


def collect(directory, series, depth, request=fetch):
    """Write one JSONL file per sweep. A summary marks the end of a sweep."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}-{series}-{uuid4().hex[:8]}.jsonl"
    counts = Counter()
    retry_delay = 0
    markets = {}

    with path.open("x", encoding="utf-8") as capture:
        def write(kind, **data):
            capture.write(json.dumps({"schema_version": 1, "kind": kind, **data}) + "\n")
            capture.flush()

        def get(kind, endpoint, ticker=None, **query):
            nonlocal retry_delay
            url = f"{BASE_URL}/{endpoint}"
            if query:
                url += "?" + urlencode(query)
            response = request(url)
            write(kind, url=url, ticker=ticker, **response)
            if "error" in response:
                counts["request_failures"] += 1
            if response["status"] == 429:
                after = response.get("retry_after") or ""
                retry_delay = max(60, int(after)) if after.isdecimal() else 60
            return response.get("payload")

        write("sweep_start", started_at=utc_now(), series=series, depth=depth)
        get("series", f"series/{series}", series)
        cursor = ""
        seen_cursors = set()
        while not retry_delay:
            query = {"series_ticker": series, "status": "open", "limit": 100}
            if cursor:
                query["cursor"] = cursor
            page = get("markets", "markets", series, **query)
            if not isinstance(page, dict) or not isinstance(page.get("markets"), list):
                if page is not None:
                    counts["invalid_market_pages"] += 1
                break
            for market in page["markets"]:
                if not isinstance(market, dict) or any(
                    not isinstance(market.get(key), str)
                    or not re.fullmatch(r"[A-Z0-9_.-]+", market[key])
                    for key in ("ticker", "event_ticker")
                ):
                    counts["invalid_markets"] += 1
                    continue
                markets[market["ticker"]] = market["event_ticker"]
            cursor = page.get("cursor")
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in seen_cursors:
                counts["invalid_market_pages"] += 1
                break
            seen_cursors.add(cursor)

        counts["markets_discovered"] = len(markets)
        for event in sorted(set(markets.values())):
            if retry_delay:
                break
            get("event", f"events/{event}", event)

        for ticker in sorted(markets):
            if retry_delay:
                break
            counts["books_requested"] += 1
            payload = get("book", f"markets/{ticker}/orderbook", ticker, depth=depth)
            levels = book_counts(payload)
            if levels is None:
                counts["books_unavailable"] += 1
                continue
            yes, no = levels
            counts["books_received"] += 1
            counts["books_with_yes_bids"] += bool(yes)
            counts["books_with_no_bids"] += bool(no)
            counts["books_two_sided"] += bool(yes and no)
            counts["books_empty"] += not (yes or no)

        write("sweep_end", ended_at=utc_now(), counts=dict(counts), rate_limited=bool(retry_delay))

    return path, counts, retry_delay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", default="KXHIGHNY")
    parser.add_argument("--depth", type=int, choices=range(101), default=0,
                        metavar="0..100", help="levels per side (0 requests all levels)")
    parser.add_argument("--interval", type=int, default=60, help="seconds between sweep starts")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("captures"))
    args = parser.parse_args()
    if args.interval <= 0 or not re.fullmatch(r"[A-Z0-9_-]+", args.series):
        parser.error("interval must be positive and series must be an uppercase ticker")

    try:
        while True:
            started = monotonic()
            path, counts, retry_delay = collect(args.output, args.series, args.depth)
            print(f"{path} {json.dumps(dict(counts), sort_keys=True)}", flush=True)
            if args.once:
                incomplete = any(counts[key] for key in (
                    "request_failures", "invalid_market_pages", "invalid_markets",
                    "books_unavailable",
                ))
                return 1 if incomplete or not counts["books_received"] else 0
            sleep(max(retry_delay, args.interval - (monotonic() - started)))
    except KeyboardInterrupt:
        print("Collection stopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
