# Phase 2 weather arbitrage review

## Settlement and candidate rules

The scanner compares the captured primary and secondary rules with the reviewed NYC events from November 8 and 9, 2026. A changed or missing strike blocks analysis. New event dates need a separate rule review before scanning. [Phase 1 settlement map](phase-1-weather.md)

- A YES and a NO on the same $1 contract form a $1 bundle. The calculation uses complementary payouts within a contract, including when the YES settlement value is scalar. The execution calculation sums both entry debits without crediting collateral offsets. [Kalshi on paired positions](https://news.kalshi.com/p/prices-and-trades) · [Settlement reporting](https://docs.kalshi.com/fix/market-settlement)
- For a YES basket, the engine checks the truth values at each strike boundary, in each interval between boundaries, and in the tails. The reviewed NYC baskets fail this coverage check if fractional source values are admissible. For example, 58.5°F leaves the Nov 9 YES basket with a $0 payout.
- A nested threshold buys YES on the broader predicate and NO on the narrower one. For example, YES on x < 59 and NO on x < 57 pay $1 below 57, $2 from 57 inclusive to 59 exclusive, and $1 from 59 onward. The test suite exercises both threshold directions using synthetic contracts. Each reviewed real event has only one strict lower tail and one strict upper tail, so neither has a same-direction nested pair.
- The conservative floor allows each market's fallback YES settlement value to vary independently from $0 to $1, with NO taking the complement. The nested example has a $1 ordinary floor and a $0 conservative floor. The fallback is a bound on gross payout under the reviewed terms. [GLOBALTEMPERATURE rules](https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf)

## Depth, fees, and timestamps

The simulation walks implied asks from the best available price outward. A missing, stale, or thin book blocks the candidate. The maximum-age check compares each request start with the capture's sweep end. Exchange quote age and order-level fills are unavailable from these public REST snapshots.

The capture identifies a quadratic taker fee with multiplier 1. The simulator applies `0.07 × multiplier × size × price × (1 − price)` per simulated fill, rounds the trade fee up to $0.000001, aligns the debit up to the cent, and applies eligible cent rebates from that leg's rounding accumulator. It uses a non-direct balance and models each consumed price level as one fill in a separate order for each leg. Aggregate depth cannot reveal how the exchange would split fills, so the resulting cost is an estimate. Results are conditional on full fills at the recorded depth. [Kalshi fee schedule](https://kalshi.com/fee-schedule) · [Kalshi rounding mechanics](https://docs.kalshi.com/getting_started/fee_rounding)

## Worked example from the local review capture

Scan `captures/20261109T000433Z-KXHIGHNY-c05cb392.jsonl` with `--event KXHIGHNY-26NOV09`. For the `T57` pair at one contract per side:

| Leg | Implied ask | Model fee | Trade fee | Debit rounded to cents |
| --- | ---: | ---: | ---: | ---: |
| YES | $0.21 | $0.011613 | $0.011613 | $0.23 |
| NO | $0.80 | $0.011200 | $0.011200 | $0.82 |

The pair costs $1.05 and has a $1.00 payout floor, for a simulated edge of −$0.05. Five same-market pairs had enough depth and a nonpositive edge, one lacked depth, and the six-strike YES basket failed the coverage check. The earlier Phase 1 capture yielded the same counts.

Run `python3 -m unittest discover -s tests -v`. The tests cover payout boundaries, missing outcomes, fallback floors, nested thresholds, missing and stale books, insufficient depth, price ordering, fractional fees, cumulative rebates, and crossed books. The CLI was exercised against both local real captures.
