# Phase 5 statistical mispricing review

## Research design

The question is whether a small logistic recalibration of pregame NBA market prices improves on the raw midpoint. Each `KXNBAGAME` event contributes its lexicographically first team ticker, so opposite contracts on the same game never enter the sample as separate observations. The collector requires two complementary binary settlements and the reviewed full-game rule pattern. Scalar settlements and rows with inconsistent metadata are excluded. The labels come from Kalshi's recorded settlement. [NBA contract terms](https://assets.kalshi.com/contract_terms/BASKETBALLGAMEWIN.pdf) · [Kalshi market listing](https://docs.kalshi.com/api-reference/market/get-markets)

The fixed window is October 20 through November 9, 2026, using the game date in the ticker. The prediction uses the hourly YES bid and ask closes ending at 12:00 UTC on that date and at 00:00 UTC twelve hours earlier. Both candles must have valid two-sided quotes. The date and hour are fixed across games. The loader also checks that the forecast precedes actual market close and the scheduled-start proxy derived from latest expiration minus 48 hours. A candle's end time measures its aggregation boundary and does not reveal the age of the individual quotes. [Kalshi batch candlesticks](https://docs.kalshi.com/api-reference/market/batch-get-market-candlesticks)

The baseline is the 12:00 UTC YES midpoint. The model uses an intercept, its log-odds, and the change in log-odds from the earlier midpoint. Log-odds inputs are clipped to probabilities in [0.005, 0.995]. The fit uses logistic loss and a fixed L2 penalty toward weights (0, 1, 0), which represent the clipped midpoint. The simulated training cutoff was 00:00 UTC November 3. Training used 92 games, while 15 earlier forecasts were excluded because their labels were unavailable at the freeze. The chronological holdout contains 47 games across six dates. The model uses market information only.

The saved raw request log under `captures/phase-5/` records request URLs, UTC times, and payloads. Its SHA-256 is `07b0d3c75cc1db3205019b40ba3f78c53a817d526e9ef45cd8ce8d1482797d1c`. The input is kept local. The download command uses Kalshi's recent-data tier and checks the cutoff, which was September 11, 2026 when captured. [Kalshi data tier guide](https://docs.kalshi.com/getting_started/historical_data)

## Holdout performance

| Forecast | Brier score |
| --- | ---: |
| Recalibrated midpoint and price change | 0.15583 |
| Raw midpoint | 0.16328 |

The difference was −0.00745. A paired bootstrap resampling whole game dates produced a 95% percentile interval of approximately [−0.01908, −0.00007] with six date blocks. The upper endpoint is close to zero, and the short holdout limits what can be inferred about future games.

| Probability bin | Model count | Model mean / observed | Baseline count | Baseline mean / observed |
| --- | ---: | ---: | ---: | ---: |
| 0–20% | 7 | 15.3% / 14.3% | 3 | 15.2% / 0.0% |
| 20–40% | 6 | 30.4% / 16.7% | 11 | 29.1% / 27.3% |
| 40–60% | 9 | 45.7% / 44.4% | 12 | 48.0% / 50.0% |
| 60–80% | 11 | 69.9% / 81.8% | 15 | 70.2% / 80.0% |
| 80–100% | 14 | 86.2% / 85.7% | 6 | 83.2% / 100.0% |

## Execution sensitivity

The order rule chooses at most one side per game when expected payoff exceeds the candle ask plus simulated taker fees by at least $0.02. NO asks are derived from YES bids. The simulation uses the captured series quadratic taker rate and cent-aligned debits. Historical fee overrides are unverified in the quote-only analysis. [Kalshi fee schedule](https://kalshi.com/fee-schedule) · [Fee rounding](https://docs.kalshi.com/getting_started/fee_rounding)

The quote-only scenario assumes one contract was available at each selected ask. It produced 27 hypothetical entries, $20.13 of debit and $2.87 of net settlement P&L, or 14.3% on debit. The raw midpoint generated no orders under the same rule. The available local book files matched zero holdout prediction times under the 10-second age limit. Executable return is therefore unavailable. When a matching book exists, the same depth walker simulates up to the candle ask limit and the report separates those fills and costs from the quote-only scenario.
