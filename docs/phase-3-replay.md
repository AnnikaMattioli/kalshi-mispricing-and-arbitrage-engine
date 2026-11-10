# Phase 3 live scanning and deterministic replay

## Live scanner

The scanner polls Kalshi's public REST API, writes each sweep locally, and scans it at sweep completion. It checks the NYC event date against each market's rule text, verifies all six strike predicates and metadata, and compares the secondary rules against the reviewed version. The capture must identify The Weather Company, the reviewed contract-terms URL and a supported quadratic fee without event overrides. New dates can pass the same checks. On November 10, 2026, three consecutive 10-second verification sweeps returned 12 books each across two NYC events. The normal polling interval is 60 seconds. [Order-book API](https://docs.kalshi.com/api-reference/market/get-market-orderbook) · [NYC contract terms](https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf)

## Replay assumptions

Replay sorts sweep timestamps and treats each sweep as available at completion. Each leg is attempted once using the latest complete sweep available by its simulated arrival. It respects the market close time, quote age limit and worst ask consumed for that leg at the signal. A missing event or failed event validation in a timed sweep blocks reuse of the prior sweep. Delayed attempts past the end of the dataset are reported separately.

Each scenario is an independent counterfactual for each priced plan. It does not share liquidity or capital with other plans. The depth participation setting scales every eligible price level and rounds down to the nearest hundredth of a contract. Available depth is a snapshot. Order changes between observations and the exact sequence of individual exchange fills are unobserved. Fees use the Phase 2 model. [Kalshi rounding mechanics](https://docs.kalshi.com/getting_started/fee_rounding)

Output keeps the full-fill payout floor and signal-time entry estimate separate from each scenario's simulated fills and debits. Each leg reports its local quote age and unpaired quantity. A receipt span measures the gap between the earliest and latest used book responses. The execution payout bound credits only the quantity filled on every leg and charges the debit for all fills. The remaining positions may pay more at settlement.

## Checkpoint results

Three real sweeps starting at 20:55:32, 20:55:42 and 20:55:52 UTC were replayed for `KXHIGHNY-26NOV11`, with 100 contracts per leg and a 15-second age limit. The scanner priced 12 control plans. Six other pairs lacked depth, and three basket observations failed the payout coverage check. No plan had a positive conservative edge at the signal.

| Scenario | Full bundles | Plans with residual exposure | Plans with a leg beyond capture | Positive candidates surviving |
| --- | ---: | ---: | ---: | ---: |
| Instant, 100% displayed depth | 12 | 0 | 0 | 0 |
| 12-second delay, 100% displayed depth | 4 | 0 | 8 | 0 |
| 12-second delay, 1-second gap, 50% displayed depth | 2 | 2 | 8 | 0 |

For example, the stressed `B59.5` plan at 20:55:37 UTC filled 53 YES and 100 NO. That leaves 53 matched pairs and 47 residual NO contracts. The conservative gross bound is $53 and the simulated debit is $94.50, giving a net lower bound of −$41.50 before any payout from the residual NO position.

The Python test suite covers chronological ordering, execution limits, end-of-capture censoring, missing sweeps, partial fills, residuals, and quote receipt spans. Replaying the same files in reverse argument order produces identical output for the complete checkpoint captures.
