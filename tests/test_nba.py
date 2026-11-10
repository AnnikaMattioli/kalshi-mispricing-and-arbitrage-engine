from contextlib import redirect_stdout
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import unittest
from unittest.mock import patch

from kalshi_engine import live, nba
from kalshi_engine.arbitrage import Leg, payout_floors


class NbaTests(unittest.TestCase):
    def markets(self):
        return {
            f"{nba.EVENT}-{team}": {
                "event_ticker": nba.EVENT, "market_type": "binary",
                "strike_type": "structured", "notional_value_dollars": "1.0000",
                "custom_strike": {"basketball_team": team_id},
                "rules_primary": team, "rules_secondary": "test rules",
            } for team, team_id in nba.TEAM_IDS.items()
        }

    def verify(self, markets):
        metadata = {"mutually_exclusive": True, "product_metadata": {"competition_scope": "Game"}}
        primary = {team: sha256(team.encode()).hexdigest() for team in nba.TEAM_IDS}
        with patch.object(nba, "PRIMARY", primary), patch.object(
            nba, "SECONDARY", sha256(b"test rules").hexdigest()
        ):
            return nba.verified_outcomes(nba.EVENT, markets, metadata)

    def test_verified_basket_preserves_tie_and_discretionary_cases(self):
        conditions, outcomes = self.verify(self.markets())
        basket = tuple(Leg(ticker, "yes") for ticker in conditions)
        self.assertEqual(payout_floors(basket, conditions, outcomes), (1, 0))
        self.assertEqual([outcomes[2][leg.ticker] for leg in basket], [Decimal(".50")] * 2)
        pair = (basket[0], Leg(basket[0].ticker, "no"))
        self.assertEqual(payout_floors(pair, conditions, outcomes), (1, 1))

    def test_missing_team_or_changed_settlement_rules_fail_closed(self):
        markets = self.markets()
        del markets[f"{nba.EVENT}-UTA"]
        with self.assertRaisesRegex(ValueError, "two reviewed team strikes"):
            self.verify(markets)
        markets = self.markets()
        markets[f"{nba.EVENT}-MIA"]["rules_secondary"] = "changed rules"
        with self.assertRaisesRegex(ValueError, "changed NBA team or settlement rules"):
            self.verify(markets)

    def test_live_weather_filter_stays_unset_after_first_sweep(self):
        with patch("sys.argv", ["live"]), patch.object(
            live, "collect", side_effect=[("capture", {}, 0), ("capture", {}, 0), KeyboardInterrupt]
        ) as collect, patch.object(live, "read_capture", return_value=[]), patch.object(
            live, "event_tickers", return_value=["weather-event"]
        ), patch.object(live, "load_frame", return_value=None), patch.object(
            live, "scan_frame", return_value=[]
        ), patch.object(live, "sleep"), redirect_stdout(StringIO()):
            self.assertEqual(live.main(), 130)
        self.assertEqual([call.kwargs["event"] for call in collect.call_args_list], [None] * 3)
