"""Collect and scan public Kalshi books locally. Emits one JSON object per sweep."""
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from time import monotonic, sleep

from kalshi_engine import fed
from kalshi_engine.collect import collect
from kalshi_engine.scan import encode, event_tickers, load_frame, read_capture, scan_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("captures"))
    parser.add_argument("--series", choices=("KXHIGHNY", "KXFED"), default="KXHIGHNY")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--max-age", type=int, default=10)
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if min(args.interval, args.max_age, args.quantity) < 1:
        parser.error("interval, maximum age and quantity must be positive")
    event = fed.EVENT if args.series == "KXFED" else None
    try:
        while True:
            started = monotonic()
            path, counts, retry_delay = collect(args.output, args.series, 0, event=event)
            records = read_capture(path)
            events = {}
            for event in event_tickers(records):
                try:
                    frame = load_frame(records, event)
                    events[event] = scan_frame(frame, Decimal(args.quantity), args.max_age)
                except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
                    events[event] = {"skipped": str(exc)}
            print(json.dumps({"capture": str(path), "counts": counts, "events": events},
                             default=encode), flush=True)
            if args.once:
                return 0 if any(isinstance(result, list) for result in events.values()) else 1
            sleep(max(retry_delay, args.interval - (monotonic() - started)))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
