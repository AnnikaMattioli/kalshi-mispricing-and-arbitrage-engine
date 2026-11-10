from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from kalshi_engine import fed
from kalshi_engine.collect import collect
from kalshi_engine.scan import scan


def capture():
    def row(kind, **data):
        return {"kind": kind, "schema_version": 1, **data}

    markets = [{
        "event_ticker": fed.EVENT, "ticker": f"{fed.EVENT}-T{strike}",
        "market_type": "binary", "strike_type": "greater", "floor_strike": float(strike),
        "notional_value_dollars": "1.0000", "close_time": fed.CLOSE,
        "latest_expiration_time": "2026-12-16T19:05:00Z",
        "rules_primary": (
            "If the upper bound of the target federal funds rate published on the Federal "
            f"Reserve's official website is greater than {strike}% following the Federal "
            "Reserve's Dec 9, 2026 meeting, then the market resolves to Yes."
        ),
        "rules_secondary": fed.SECONDARY,
    } for strike in ("4.00", "4.25")]
    at = "2026-11-10T21:00:00+00:00"
    return [
        row("sweep_start"),
        row("series", payload={"series": {
            "ticker": "KXFED", "contract_terms_url": fed.TERMS_URL,
            "fee_type": "quadratic_with_maker_fees", "fee_multiplier": 1,
        }}),
        row("markets", payload={"markets": markets}),
        row("event", ticker=fed.EVENT, payload={"event": {
            "event_ticker": fed.EVENT, "series_ticker": "KXFED",
            "settlement_sources": [fed.SOURCE], "mutually_exclusive": False,
            "strike_date": "2026-12-09T19:00:00Z",
        }}),
        *(row("book", ticker=market["ticker"], status=200, started_at=at, received_at=at,
              payload={"orderbook_fp": {"yes_dollars": [[".20", "5"]],
                                        "no_dollars": [[".30", "5"]]}}) for market in markets),
        row("sweep_end", ended_at=at, counts={}),
    ]


class FedTests(unittest.TestCase):
    def test_directional_scan_distinguishes_fallbacks(self):
        records = capture()
        results = scan(records, fed.EVENT, Decimal(1), 10)
        self.assertEqual([r["strategy"] for r in results],
                         ["same_market", "same_market", "nested_threshold"])
        pair = results[-1]
        self.assertEqual([(l.ticker[-5:], l.side) for l in pair["legs"]],
                         [("T4.00", "yes"), ("T4.25", "no")])
        self.assertEqual(pair["ordinary_payout_floor"], 1)
        self.assertEqual(pair["no_data_payout"], 1)
        self.assertEqual(pair["conservative_payout_floor"], 0)
        self.assertEqual(pair["debit"], Decimal("1.54"))

    def test_strict_threshold(self):
        records = capture()
        markets = {m["ticker"]: m for m in records[2]["payload"]["markets"]}
        conditions = fed.verified_conditions(fed.EVENT, markets, records[3]["payload"]["event"])
        condition = conditions[f"{fed.EVENT}-T4.25"]
        self.assertFalse(condition.pays_yes(Decimal("4.25")))
        self.assertTrue(condition.pays_yes(Decimal("4.251")))

    def test_rejects_changed_terms_or_metadata(self):
        for key, value in (("floor_strike", 4.1), ("rules_secondary", "different expiry")):
            with self.subTest(key=key):
                records = capture()
                records[2]["payload"]["markets"][0][key] = value
                with self.assertRaises(ValueError):
                    scan(records, fed.EVENT, Decimal(1), 10)

    def test_event_filter_rejects_foreign_market(self):
        def request(url):
            parsed = urlsplit(url)
            if parsed.path.endswith("/markets"):
                self.assertEqual(parse_qs(parsed.query)["event_ticker"], [fed.EVENT])
                payload = {"markets": [{"ticker": "FOREIGN", "event_ticker": "OTHER"}]}
            else:
                payload = {}
            return {"status": 200, "payload": payload}

        with TemporaryDirectory() as directory:
            _, counts, _ = collect(Path(directory), "KXFED", 0, request, event=fed.EVENT)
        self.assertEqual(counts["markets_discovered"], 0)
        self.assertEqual(counts["invalid_markets"], 1)
