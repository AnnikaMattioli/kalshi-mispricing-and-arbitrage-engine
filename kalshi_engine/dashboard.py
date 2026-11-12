"""Serve the dashboard and summarize saved sweeps on this Mac."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from kalshi_engine.scan import encode, event_tickers, load_frame, read_capture, scan_frame

DOCS = Path(__file__).resolve().parents[1] / "docs"
FILENAME = re.compile(r"\d{8}T\d{6}Z-([A-Z0-9_]+)-[a-f0-9]{8}\.jsonl")
ASSETS = {"/", "/index.html", "/dashboard.css", "/dashboard.js", "/local-sweeps.js", "/demo.json"}


def summarize(path, series, now, stale_after):
    result = {"file": path.name, "series": series}
    try:
        records = read_capture(path)
        if not records or records[0].get("series") != series or records[-1].get("kind") != "sweep_end":
            raise ValueError("Sweep has no valid completion record.")
        summary = records[-1]
        ended = datetime.fromisoformat(summary["ended_at"])
        age = (now - ended).total_seconds()
        if age < 0:
            raise ValueError("Sweep completion is ahead of the local clock.")
        events = []
        for ticker in event_tickers(records):
            try:
                frame = load_frame(records, ticker)
                plans = scan_frame(frame, Decimal(1), 10)
                ages = [age for plan in plans for age in plan.get("quote_age_seconds", [])]
                events.append({
                    "ticker": ticker, "decisions": Counter(plan["status"] for plan in plans),
                    "oldest_priced_quote_seconds": max(ages, default=None),
                })
            except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
                events.append({"ticker": ticker, "skipped": str(exc)})
        counts = summary["counts"]
        failed = summary.get("rate_limited") or any(counts.get(key) for key in (
            "request_failures", "invalid_market_pages", "invalid_markets", "books_unavailable",
        )) or counts.get("books_received", 0) != counts.get("markets_discovered", 0)
        result.update(captured_at=ended.isoformat(), age_seconds=age, stale=age > stale_after,
                      status="failed" if failed else "complete", counts=counts, events=events)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status="incomplete", detail=str(exc))
    return result


def latest_sweeps(directory, now, stale_after):
    latest = {}
    for path in sorted(directory.glob("*.jsonl"), reverse=True):
        match = FILENAME.fullmatch(path.name)
        if match and path.is_file() and not path.is_symlink():
            latest.setdefault(match[1], path)
    return [summarize(path, series, now, stale_after) for series, path in sorted(latest.items())]


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, capture_dir, stale_after, **kwargs):
        self.capture_dir = capture_dir
        self.stale_after = stale_after
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def send_head(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(403)
            return None
        if urlsplit(self.path).path not in ASSETS:
            self.send_error(404)
            return None
        return super().send_head()

    def do_GET(self):
        if urlsplit(self.path).path != "/api/sweeps":
            super().do_GET()
            return
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(403)
            return
        now = datetime.now(timezone.utc)
        sweeps = latest_sweeps(self.capture_dir, now, self.stale_after)
        body = json.dumps({"checked_at": now.isoformat(), "sweeps": sweeps}, default=encode).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=Path("captures"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--stale-after", type=int, default=120, help="capture age in seconds")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or args.stale_after < 1:
        parser.error("port must be in 0–65535 and stale-after must be positive")
    handler = partial(DashboardHandler, capture_dir=args.captures, stale_after=args.stale_after)
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/?local=1", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
