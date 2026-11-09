# Phase 1 weather review

## Live capture

The local review file is `captures/20261108T233120Z-KXHIGHNY-7e23507a.jsonl`. The collector queried Kalshi's production REST API without credentials on 8 November 2026. The first and last book responses arrived at 23:31:22.367 and 23:31:25.825 UTC, a span of 3.46 seconds.

| Event | Books received | YES bid depth present | NO bid depth present | Both sides | Empty |
| --- | ---: | ---: | ---: | ---: | ---: |
| `KXHIGHNY-26NOV08` | 6 | 1 | 5 | 0 | 0 |
| `KXHIGHNY-26NOV09` | 6 | 5 | 6 | 5 | 0 |
| Total | 12 | 6 | 11 | 5 | 0 |

To inspect an individual record locally:

```sh
grep '"kind": "book"' captures/20261108T233120Z-KXHIGHNY-7e23507a.jsonl | grep 'KXHIGHNY-26NOV09-B57.5' | python3 -m json.tool
```

That response arrived at 23:31:24.278 UTC. It contains 35 YES bid levels and 31 NO bid levels. The best YES bid was $0.6400 for 4.00 contracts and the best NO bid was $0.3500 for 161.00 contracts. The implied best asks were $0.6500 for 161.00 YES and $0.3600 for 4.00 NO. This is a depth check at one observation time. [Kalshi order-book reference](https://docs.kalshi.com/api-reference/market/get-market-orderbook)

## Hand-checked outcome map

The captured market rules specify the daily maximum at New York City (`CLINYC`) in degrees Fahrenheit from The Weather Company. Each event is marked mutually exclusive in its metadata. The series response links the GLOBALTEMPERATURE terms, which specify inclusive endpoints for “between” and settlement at the source's reported precision. They list The Weather Company first in the source hierarchy, followed by NWS and the relevant national weather service. The event metadata names The Weather Company for these two events. [Full contract terms](https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf) · [Named source portal](https://weather.com/kalshi)

Each row gives the YES condition for the ticker formed by joining the event prefix, a hyphen, and the suffix. For ordinary temperature settlement, YES pays $1 if its condition holds and $0 otherwise, with NO paying the complement.

| Nov 8 suffix | YES condition | Nov 9 suffix | YES condition |
| --- | --- | --- | --- |
| `T61` | x < 61 | `T57` | x < 57 |
| `B61.5` | 61 ≤ x ≤ 62 | `B57.5` | 57 ≤ x ≤ 58 |
| `B63.5` | 63 ≤ x ≤ 64 | `B59.5` | 59 ≤ x ≤ 60 |
| `B65.5` | 65 ≤ x ≤ 66 | `B61.5` | 61 ≤ x ≤ 62 |
| `B67.5` | 67 ≤ x ≤ 68 | `B63.5` | 63 ≤ x ≤ 64 |
| `T68` | x > 68 | `T64` | x > 64 |

The two lower-tail boundaries belong to the first bracket, and the two upper-tail boundaries belong to the last bracket. Every endpoint of an interior bracket belongs to that bracket alone. Every whole degree maps to exactly one YES, with both tails included. If fractional reports are admissible, the following open intervals give **zero** YES payouts across the full basket:

| Event | Gaps |
| --- | --- |
| Nov 8 | (62, 63), (64, 65), (66, 67) |
| Nov 9 | (58, 59), (60, 61), (62, 63) |

For example, on Nov 9, 58 pays the `B57.5` YES and 59 pays the `B59.5` YES. A reported 58.5 would satisfy neither bracket nor either tail. The verified terms leave source precision to the official report. This review did not establish an authoritative whole-degree guarantee for `CLINYC`, so the full basket's ordinary-settlement payout floor is $0 over the conservative domain. [Full contract terms](https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf)

## Settlement exceptions

- The first official non-preliminary report generally controls. Preliminary values may change through conversion or rounding. Kalshi may delay expiration if it finds a material error and consider a correction before expiration. The terms exclude post-expiration revisions. A portal label of “Final” does not remove the material-error procedure. [Full contract terms](https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf) · [Kalshi NYC market rules](https://kalshi.com/markets/kxhighny)
- If reliable data is still unavailable by expiration, strikes resolve at the last fair price determined by Kalshi. This may produce fractional payouts. The reviewed terms supply no fixed sum for those prices across the basket. Kalshi may also initiate an outcome review under Rule 7.1. The normal-temperature map does not determine those payouts. [Full contract terms](https://assets.kalshi.com/contract_terms/GLOBALTEMPERATURE.pdf) · [Kalshi market settlement FAQ](https://help.kalshi.com/en/articles/13823821-market-faqs)
