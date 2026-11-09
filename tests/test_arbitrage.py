from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import unittest

from kalshi_engine.arbitrage import Book, Condition, Leg, candidates, evaluate, payout_floors, walk_book
from kalshi_engine.scan import parse_book


NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
CONDITIONS = {
    "low": Condition("low", "less", upper=D("57")),
    "range": Condition("range", "between", D("57"), D("58")),
    "next": Condition("next", "between", D("59"), D("60")),
    "high": Condition("high", "greater", lower=D("60")),
}
PAIR = (Leg("low", "yes"), Leg("low", "no"))


class ArbitrageTests(unittest.TestCase):
    def test_same_market_floor_and_fees(self):
        book = Book(NOW, NOW, ((D(".19"), D("2")),), ((D(".80"), D("2")),))
        result = evaluate("same_market", PAIR, CONDITIONS, {"low": book}, D("1"), NOW, 10, D("1"))
        self.assertEqual(result["conservative_payout_floor"], D("1"))
        self.assertEqual(result["debit"], D("1.05"))
        self.assertEqual(result["conservative_edge"], D("-.05"))
        self.assertEqual(result["status"], "no_edge")

    def test_fractional_gap_blocks_basket(self):
        kind, legs = next(c for c in candidates(CONDITIONS) if c[0] == "outcome_basket")
        result = evaluate(kind, legs, CONDITIONS, {}, D("1"), NOW, 10, D("1"))
        self.assertEqual(result["ordinary_payout_floor"], 0)
        self.assertEqual(result["status"], "incomplete_outcome_basket")

    def test_inclusive_boundaries_can_cover_all_real_values(self):
        conditions = {
            "low": CONDITIONS["low"],
            "range": CONDITIONS["range"],
            "high": Condition("high", "greater", lower=D("58")),
        }
        legs = tuple(Leg(ticker, "yes") for ticker in conditions)
        self.assertEqual(payout_floors(legs, conditions), (1, 0))
        self.assertEqual(payout_floors(legs[:-1], conditions), (0, 0))

    def test_nested_thresholds_in_both_directions(self):
        for operator, a, b, expected in (
            ("less", Condition("a", "less", upper=D("57")),
             Condition("b", "less", upper=D("59")), (Leg("b", "yes"), Leg("a", "no"))),
            ("greater", Condition("a", "greater", lower=D("57")),
             Condition("b", "greater", lower=D("59")), (Leg("a", "yes"), Leg("b", "no"))),
        ):
            with self.subTest(operator=operator):
                conditions = {"a": a, "b": b}
                legs = next(legs for kind, legs in candidates(conditions) if kind == "nested_threshold")
                self.assertEqual(legs, expected)
                self.assertEqual(payout_floors(legs, conditions), (1, 0))

    def test_depth_walk_sorts_asks_and_carries_rounding(self):
        book = Book(NOW, NOW, (), ((D(".67"), D("1")), (D(".68"), D("1")), (D(".69"), D("1"))))
        fills = walk_book(book, "yes", D("3"), D("1"))
        self.assertEqual([fill.price for fill in fills], [D(".31"), D(".32"), D(".33")])
        self.assertEqual([fill.rebate for fill in fills], [D("0"), D("0"), D(".01")])
        self.assertEqual(sum(fill.debit for fill in fills), D("1.01"))
        self.assertIsNone(walk_book(book, "yes", D("4"), D("1")))

    def test_fractional_fill_aligns_cost_plus_fee(self):
        book = Book(NOW, NOW, (), ((D(".78"), D(".25")),))
        fill, = walk_book(book, "yes", D(".25"), D("1"))
        self.assertEqual(fill.trade_fee, D(".003003"))
        self.assertEqual(fill.rounding_fee, D(".001997"))
        self.assertEqual(fill.debit, D(".06"))

    def test_stale_missing_and_thin_books(self):
        bid = ((D(".5"), D(".5")),)
        stale = Book(NOW - timedelta(seconds=11), NOW, bid, bid)
        fresh = Book(NOW - timedelta(seconds=10), NOW, bid, bid)
        for books, expected in (
            ({}, "missing_book"),
            ({"low": stale}, "stale_quote"),
            ({"low": fresh}, "insufficient_depth"),
        ):
            with self.subTest(expected=expected):
                result = evaluate("same_market", PAIR, CONDITIONS, books, D("1"), NOW, 10, D("1"))
                self.assertEqual(result["status"], expected)

    def test_crossed_book_is_rejected(self):
        record = {"ticker": "low", "status": 200, "payload": {"orderbook_fp": {
            "yes_dollars": [[".60", "1"]], "no_dollars": [[".41", "1"]],
        }}}
        with self.assertRaisesRegex(ValueError, "crossed"):
            parse_book(record)
