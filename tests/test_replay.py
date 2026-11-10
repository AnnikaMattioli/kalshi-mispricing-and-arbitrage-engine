from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import unittest

from kalshi_engine.arbitrage import Book, Condition
from kalshi_engine.replay import Scenario, replay
from kalshi_engine.scan import Frame

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
END = NOW + timedelta(hours=1)


def frame(second, yes_bid=".40", no_bid=".50", yes_depth="4", no_depth="4"):
    at = NOW + timedelta(seconds=second)
    book = Book(at - timedelta(seconds=1), at, ((D(yes_bid), D(yes_depth)),),
                ((D(no_bid), D(no_depth)),))
    return Frame(at, {"test": Condition("test", "less", upper=D(60))},
                 {"test": book}, {"test": END}, D(1))


class ReplayTests(unittest.TestCase):
    def test_delay_partial_and_residual_are_separate_from_conditional_payout(self):
        signal, later, horizon = frame(0), frame(10, yes_depth="1"), frame(20)
        entries = [(x.as_of, x) for x in (signal, later, horizon)]
        instant = Scenario("instant", 0, 0, D(1))
        stressed = Scenario("stressed", 10, 1, D(".5"))
        report = replay(entries, [instant, stressed], D(1), 5)
        self.assertEqual(report, replay(entries[::-1], [instant, stressed], D(1), 5))
        first = report["plans"][0]
        self.assertEqual(first["conditional_full_fill"]["conservative_payout_floor"], D(1))
        self.assertTrue(first["execution"]["instant"]["full_bundle_filled"])
        partial = first["execution"]["stressed"]
        self.assertFalse(partial["full_bundle_filled"])
        self.assertTrue(partial["has_residual_exposure"])
        self.assertEqual(partial["filled_quote_span_seconds"], 0)
        self.assertEqual(partial["matched_quantity"], D(".5"))
        self.assertEqual(partial["gross_payout_lower_bound"], D(".5"))
        self.assertEqual([leg["status"] for leg in partial["legs"]], ["full", "partial"])
        self.assertEqual([leg["residual"] for leg in partial["legs"]], [D(".5"), D(0)])
        self.assertEqual([leg["quote_age_seconds"] for leg in partial["legs"]], [1, 2])
        self.assertEqual(report["scenario_counts"]["stressed"]["positive_candidates_surviving"], 0)

    def test_limit_no_lookahead_and_end_of_capture(self):
        signal, later = frame(0), frame(10, no_bid=".45")
        entries = [(x.as_of, x) for x in (signal, later)]
        scenarios = [Scenario("early", 5, 0, D(1)), Scenario("later", 10, 0, D(1))]
        report = replay(entries, scenarios, D(1), 10)
        first, last = report["plans"]
        self.assertTrue(first["execution"]["early"]["full_bundle_filled"])
        self.assertEqual(first["execution"]["later"]["legs"][0]["status"], "unfilled")
        self.assertEqual(first["execution"]["later"]["legs"][1]["status"], "full")
        self.assertEqual(last["execution"]["later"]["legs"][0]["status"], "beyond_capture")

    def test_missing_sweep_blocks_reuse_of_previous_book(self):
        signal, horizon = frame(0), frame(15)
        entries = [(signal.as_of, signal), (NOW + timedelta(seconds=2), None),
                   (horizon.as_of, horizon)]
        report = replay(entries, [Scenario("delayed", 5, 0, D(1))], D(1), 10)
        self.assertEqual(report["plans"][0]["execution"]["delayed"]["legs"][0]["status"],
                         "market_unavailable")

    def test_receipt_span_with_sequential_snapshots(self):
        signal, later = frame(0), frame(10)
        entries = [(signal.as_of, signal), (later.as_of, later)]
        report = replay(entries, [Scenario("sequential", 0, 10, D(1))], D(1), 10)
        execution = report["plans"][0]["execution"]["sequential"]
        self.assertTrue(execution["full_bundle_filled"])
        self.assertEqual(execution["filled_quote_span_seconds"], 10)
