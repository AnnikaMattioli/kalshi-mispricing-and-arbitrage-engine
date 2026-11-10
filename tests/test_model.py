from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from kalshi_engine.arbitrage import Book
from kalshi_engine.model import matching_book, metrics, order_probe, study, two_sided
from kalshi_engine.model_data import SPLIT, at


class ModelTests(unittest.TestCase):
    def test_quote_validation(self):
        def candle(bid, ask):
            return {"yes_bid": {"close_dollars": bid}, "yes_ask": {"close_dollars": ask}}

        self.assertEqual(two_sided(candle(".2", ".3")), (Decimal(".2"), Decimal(".3")))
        for bid, ask in ((".6", ".5"), ("0", ".5"), (None, ".5"), ("NaN", ".5")):
            with self.subTest(bid=bid, ask=ask):
                self.assertIsNone(two_sided(candle(bid, ask)))

    def test_matching_book_rejects_stale_and_future_sweeps(self):
        at_time = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
        signal = at_time.timestamp()
        row = {"ticker": "A", "signal_ts": signal}
        fresh = Book(at_time - timedelta(seconds=5), at_time, (), ())
        stale = Book(at_time - timedelta(seconds=11), at_time, (), ())
        self.assertIsNone(matching_book({"A": [(signal + 1, fresh), (signal, stale)]}, row))
        self.assertIs(matching_book({"A": [(signal, fresh)]}, row), fresh)

    def test_depth_and_quote_returns_are_distinct(self):
        row = {"bid": Decimal(".30"), "ask": Decimal(".40"), "label": 1}
        absent = order_probe(row, .70, Decimal(1), None)
        self.assertEqual(absent["quote_debit"], Decimal(".42"))
        self.assertEqual(absent["quote_pnl"], Decimal(".58"))
        self.assertIsNone(absent["depth_pnl"])
        book = Book(None, None, (), ((Decimal(".65"), Decimal("2")),))
        present = order_probe(row, .70, Decimal(1), book)
        self.assertEqual(present["depth_debit"], Decimal(".37"))
        self.assertEqual(present["depth_pnl"], Decimal(".63"))
        self.assertIsNone(order_probe(row, .35, Decimal(1), book))

    def test_training_excludes_labels_unavailable_at_split(self):
        cutoff = int(at(SPLIT).timestamp())

        def row(index, signal, settled):
            return {
                "ticker": str(index), "signal_ts": signal, "settled_ts": settled,
                "day": "synthetic", "label": index % 2, "bid": Decimal(".48"),
                "ask": Decimal(".52"), "midpoint": .5, "early_midpoint": .5,
            }

        rows = [row(i, cutoff - 100, cutoff - 5) for i in range(40)]
        rows += [row(40, cutoff - 10, cutoff)]
        rows += [row(i, cutoff + 100, cutoff + 200) for i in range(41, 61)]
        result = study(rows, {}, Decimal(1))
        self.assertEqual(result["train_games"], 40)
        self.assertEqual(result["holdout_games"], 20)
        self.assertEqual(result["training_labels_unavailable_at_split"], 1)
        self.assertEqual(result["metrics"]["midpoint"]["brier"], .25)
        self.assertEqual(result["metrics"]["midpoint"]["calibration"][2]["n"], 20)
        self.assertEqual(metrics([{"p": 1.0, "label": 1}], "p")["calibration"][-1]["n"], 1)
