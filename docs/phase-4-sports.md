# Phase 4 sports checkpoint

## Settlement map

The reviewed event is `KXNBAGAME-26NOV10MIAUTA`, the full-game Miami Heat versus Utah Jazz winner market scheduled for November 10, 2026. Its two $1 markets are one per team. The settlement source hierarchy starts with the governing league, then ESPN and the remaining sources specified in the full terms. The full-game result includes overtime. NBA rules call for additional periods after a regulation tie, and Kalshi separately specifies half-dollar payouts for each side if the official result is tied and no Tie strike is listed. Post-expiration revisions do not change settlement. [Kalshi event rules](https://kalshi.com/markets/kxnbagame/nba-game/kxnbagame-26nov10miauta) · [Full basketball contract terms](https://assets.kalshi.com/contract_terms/BASKETBALLGAMEWIN.pdf) · [NBA timing and overtime rules](https://official.nba.com/rule-no-5-scoring-and-timing)

| Official result or contingency | Miami YES | Utah YES | YES basket |
| --- | ---: | ---: | ---: |
| Miami wins | $1 | $0 | $1 |
| Utah wins | $0 | $1 | $1 |
| Official tie with no Tie strike | $0.50 | $0.50 | $1 |
| Last-fair-price resolution | Exchange-determined | Exchange-determined | $0 conservative lower bound |

- A postponed game that starts within 48 hours can settle on the eventual official result. Cancellation or failure to start within that window can lead to fair-price settlement.
- For a game stopped after tip-off and not scheduled to resume within the window, the full-game terms use the official record if 48 minutes of NBA play have elapsed or the league declares an official outcome. Otherwise fair-price settlement applies.
- A pregame forfeit or failure to participate can lead to fair-price settlement. After tip-off, a league-declared winner by forfeit controls the full-game winner contract.
- Kalshi may wait up to 48 hours from the end of the game for missing results and use fair prices if the result remains unavailable. The reviewed terms do not establish a fixed combined fair-price payout across the two markets. [Full basketball contract terms](https://assets.kalshi.com/contract_terms/BASKETBALLGAMEWIN.pdf)

## Capture and executable example

The local file `captures/20261110T211202Z-KXNBAGAME-ce4954a4.jsonl` contains both markets' public books. Both had YES and NO bids, with book receipts 0.327 seconds apart.

| Team | YES bid levels | NO bid levels | Best YES ask | Contracts at that ask |
| --- | ---: | ---: | ---: | ---: |
| Miami | 75 | 21 | $0.79 | 455,014.49 |
| Utah | 21 | 76 | $0.22 | 369,822.80 |

The one-contract-per-team YES basket cost $1.01 before fees and $1.05 after simulated taker fees and rounding. Its official-result floor is $1, giving a simulated edge of −$0.05 even under that settlement assumption. The conservative floor for fair-price resolution is $0. The two same-market YES + NO checks also had sufficient depth and cost $1.05 each. The capture reports a quadratic fee with maker fees and multiplier 1. The existing taker simulation uses aggregate depth as one simulated fill per consumed level. [Kalshi fees](https://kalshi.com/fee-schedule) · [Fee rounding](https://docs.kalshi.com/getting_started/fee_rounding)

The profile checks event identity, both team IDs, the captured rule fingerprints, and settlement and fee metadata. It passes discrete payouts through the same engine as weather and economics. Other games require review before they can enter this profile. The local scan, replay, and live scanner all ran successfully. All 22 Python tests passed, including a regression test for a polling-loop bug that could silently narrow the weather event filter after the first sweep.
