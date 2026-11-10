# Phase 4 economics checkpoint

## Contract and settlement

The first economics profile is `KXFED`, scoped to the December 9, 2026 meeting (`KXFED-26DEC`). The settlement input is the upper bound of the target federal funds rate range published by the Federal Reserve for that meeting. The effective overnight funds rate and the lower end of the range are different quantities. The event contains 11 strict greater-than strikes from 2.75% through 5.25% at 0.25 percentage point increments. A rate exactly at a strike resolves NO on that strike. YES payouts can overlap across strikes. [December Kalshi event](https://kalshi.com/markets/kxfed/fed-funds-rate) · [Full FED contract terms](https://assets.kalshi.com/contract_terms/FED.pdf) · [FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)

Trading is scheduled to close at 1:55 p.m. Eastern on December 9. Expiration is the first 2:05 p.m. Eastern following the meeting statement or the one-week deadline, whichever comes first. The terms exclude revisions after expiration and specify NO if data is unavailable at expiration. Kalshi may also initiate a market outcome review. The scanner reports the ordinary payout floor, the payout under the explicit all-NO provision, and a conservative bound allowing independent discretionary settlement values across strikes. [Full FED contract terms](https://assets.kalshi.com/contract_terms/FED.pdf)

## Worked nested pair

Buy YES above 4.00% and NO above 4.25%, one contract per leg.

| Settlement input | YES above 4.00% | NO above 4.25% | Total |
| --- | ---: | ---: | ---: |
| Upper bound ≤ 4.00% | $0 | $1 | $1 |
| 4.00% < upper bound ≤ 4.25% | $1 | $1 | $2 |
| Upper bound > 4.25% | $1 | $0 | $1 |
| No data at expiration | $0 | $1 | $1 |

The ordinary and no-data floors are both $1. The independent discretionary bound is $0 for this cross-market pair. The capture identifies a quadratic fee with maker fees and multiplier 1. The scanner uses the existing quadratic taker simulation. In the review book, the two asks were $0.96 and $0.90. Each leg added one cent after fee rounding, making the estimated total $1.88. The ordinary floor less that debit was −$0.88. [Fee schedule](https://kalshi.com/fee-schedule) · [Fee rounding](https://docs.kalshi.com/getting_started/fee_rounding)

## Live data and engine reuse

The event-filtered capture `captures/20261110T210247Z-KXFED-c73bbfb8.jsonl` returned all 11 December books across 3.25 seconds. Seven had YES bids, six had NO bids, two had both sides, and none was empty. This is one time sample. An unfiltered request discovered multiple meetings, so the collector now supports `--event` to bound sweep duration.

| Candidate type | Checked | Priced | Insufficient depth | Positive edge |
| --- | ---: | ---: | ---: | ---: |
| YES + NO | 11 | 2 | 9 | 0 |
| Nested thresholds | 55 | 1 | 54 | 0 |

The Fed profile validates the captured rule text, expiry, source, and strike metadata before passing the predicates to the same depth walker, payout engine, and replay used for NYC. A directional Fed event produces same-market and nested candidates. This checkpoint verifies one meeting. New Fed meetings need their own rule review. The saved capture and live scanner both ran successfully, and the existing NYC replay was checked for regressions. The 19 Python tests cover exact threshold equality, all-NO payout reporting, and rejection of changed settlement rules and foreign event rows.
