import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from kalshi_engine.collect import collect


def success(payload):
    return {"status": 200, "started_at": "start", "received_at": "end", "payload": payload}


class CollectorTests(unittest.TestCase):
    def test_paginated_capture_preserves_depth_and_separates_missing_from_empty(self):
        def request(url):
            parsed = urlsplit(url)
            if parsed.path.endswith("/markets"):
                cursor = parse_qs(parsed.query).get("cursor")
                tickers = ("C",) if cursor else ("A", "B")
                return success({
                    "markets": [{"ticker": ticker, "event_ticker": "EVENT"} for ticker in tickers],
                    "cursor": "" if cursor else "next page",
                })
            if "/markets/" in parsed.path:
                self.assertEqual(parse_qs(parsed.query)["depth"], ["0"])
                ticker = parsed.path.split("/")[-2]
                if ticker == "C":
                    return {"status": 404, "error": "missing"}
                bids = [["0.1234", "1.25"]] if ticker == "A" else []
                return success({"orderbook_fp": {"yes_dollars": bids, "no_dollars": []}})
            return success({})

        with TemporaryDirectory() as directory:
            path, counts, delay = collect(Path(directory), "TEST", 0, request)
            records = [json.loads(line) for line in path.read_text().splitlines()]

        self.assertEqual([record["kind"] for record in records], [
            "sweep_start", "series", "markets", "markets", "event",
            "book", "book", "book", "sweep_end",
        ])
        self.assertEqual(counts["markets_discovered"], 3)
        self.assertEqual(counts["books_received"], 2)
        self.assertEqual(counts["books_empty"], 1)
        self.assertEqual(counts["books_unavailable"], 1)
        self.assertEqual(counts["request_failures"], 1)
        self.assertEqual(delay, 0)
        self.assertEqual(records[5]["payload"]["orderbook_fp"]["yes_dollars"], [["0.1234", "1.25"]])
        self.assertTrue(all(record["schema_version"] == 1 for record in records))

    def test_rate_limit_stops_the_sweep(self):
        urls = []

        def request(url):
            urls.append(url)
            return {"status": 429, "error": "rate limited", "retry_after": "120"}

        with TemporaryDirectory() as directory:
            path, counts, delay = collect(Path(directory), "TEST", 0, request)
            summary = json.loads(path.read_text().splitlines()[-1])

        self.assertEqual(len(urls), 1)
        self.assertEqual(counts["request_failures"], 1)
        self.assertEqual(delay, 120)
        self.assertTrue(summary["rate_limited"])

    def test_repeated_cursor_marks_discovery_incomplete(self):
        def request(url):
            return success({"markets": [], "cursor": "same"})

        with TemporaryDirectory() as directory:
            _, counts, _ = collect(Path(directory), "TEST", 0, request)

        self.assertEqual(counts["invalid_market_pages"], 1)
