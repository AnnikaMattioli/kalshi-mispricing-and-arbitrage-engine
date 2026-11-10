"""Deterministically stress-test snapshot-priced plans using recorded sweeps."""
import argparse
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from kalshi_engine.arbitrage import ONE, walk_book
from kalshi_engine.scan import encode, event_tickers, load_frame, read_capture, scan_frame


@dataclass(frozen=True)
class Scenario:
    name: str
    delay_seconds: int
    leg_gap_seconds: int
    participation: Decimal


def simulate(frames, times, signal_time, plan, scenario, max_age):
    legs = plan["legs"]
    quantity = plan["quantity"]
    results = []
    for index, (leg, signal_fills) in enumerate(zip(legs, plan["fills"], strict=True)):
        arrival = signal_time + timedelta(seconds=scenario.delay_seconds + index * scenario.leg_gap_seconds)
        frame_index = bisect_right(times, arrival) - 1
        frame = frames[frame_index]
        book = frame.books.get(leg.ticker) if frame else None
        limit = signal_fills[-1].price
        age = (arrival - book.started_at).total_seconds() if book else None
        fills = ()
        if arrival > times[-1]:
            status = "beyond_capture"
        elif frame is None or leg.ticker not in frame.close_times or arrival >= frame.close_times[leg.ticker]:
            status = "market_unavailable"
        elif book is None:
            status = "missing_book"
        elif not book.started_at <= book.received_at <= arrival or age > max_age:
            status = "stale_quote"
        else:
            fills = walk_book(book, leg.side, quantity, frame.multiplier, allow_partial=True,
                              limit=limit, participation=scenario.participation)
            filled = sum(fill.quantity for fill in fills)
            status = "full" if filled == quantity else "partial" if filled else "unfilled"
        results.append({
            "leg": leg, "arrival_at": arrival.isoformat(), "limit": limit, "status": status,
            "quote_received_at": book.received_at.isoformat() if book else None,
            "quote_age_seconds": age, "fills": fills,
            "filled": sum((fill.quantity for fill in fills), Decimal("0")),
        })

    matched = min(row["filled"] for row in results)
    receipts = [datetime.fromisoformat(row["quote_received_at"]) for row in results if row["fills"]]
    debit = sum((fill.debit for row in results for fill in row["fills"]), Decimal("0"))
    # Filled residual positions add nonnegative gross payouts. Use only the matched
    # bundle for this lower bound, retaining all actual debits.
    conditional = plan["conservative_payout_floor"]
    matched_floor = conditional / quantity * matched
    for row in results:
        row["residual"] = row["filled"] - matched
    return {
        "full_bundle_filled": matched == quantity,
        "matched_quantity": matched,
        "has_residual_exposure": any(row["residual"] for row in results),
        "filled_quote_span_seconds": (
            (max(receipts) - min(receipts)).total_seconds() if receipts else None
        ),
        "gross_payout_lower_bound": matched_floor,
        "debit": debit,
        "net_lower_bound": matched_floor - debit,
        "legs": results,
    }


def replay(entries, scenarios, quantity, max_age):
    entries = sorted(entries, key=lambda item: item[0])
    times = [timestamp for timestamp, _ in entries]
    if len(set(times)) != len(times):
        raise ValueError("duplicate sweep timestamps")
    frames = [frame for _, frame in entries]
    counts = Counter()
    metrics = ("priced_plans", "eligible_positive_at_signal", "full_bundles",
               "with_residual_exposure", "beyond_capture", "positive_candidates_surviving")
    summaries = {scenario.name: Counter(dict.fromkeys(metrics, 0)) for scenario in scenarios}
    details = []
    for timestamp, frame in entries:
        if frame is None:
            continue
        for plan in scan_frame(frame, quantity, max_age):
            counts[plan["status"]] += 1
            if "fills" not in plan:
                continue
            # Stress all priced plans for diagnostics, while counting eligible
            # positive-edge candidates separately from these control plans.
            eligible = plan["conservative_edge"] > 0
            outcomes = {}
            for scenario in scenarios:
                result = simulate(frames, times, timestamp, plan, scenario, max_age)
                outcomes[scenario.name] = result
                summary = summaries[scenario.name]
                summary["priced_plans"] += 1
                summary["eligible_positive_at_signal"] += eligible
                summary["full_bundles"] += result["full_bundle_filled"]
                summary["with_residual_exposure"] += result["has_residual_exposure"]
                summary["beyond_capture"] += any(
                    leg["status"] == "beyond_capture" for leg in result["legs"]
                )
                summary["positive_candidates_surviving"] += (
                    eligible and result["full_bundle_filled"] and result["net_lower_bound"] > 0
                )
            details.append({"signal_at": timestamp.isoformat(), "conditional_full_fill": plan,
                            "execution": outcomes})
    return {"signal_counts": counts, "scenario_counts": summaries, "plans": details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="+")
    parser.add_argument("--event", required=True)
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--max-age", type=int, default=10)
    parser.add_argument("--delay", type=int, default=60, help="stressed arrival delay in seconds")
    parser.add_argument("--leg-gap", type=int, default=1, help="stressed gap between legs in seconds")
    parser.add_argument("--participation", type=Decimal, default=Decimal("0.5"))
    args = parser.parse_args()
    if (min(args.quantity, args.max_age) < 1 or min(args.delay, args.leg_gap) < 0
            or not args.participation.is_finite() or not 0 < args.participation <= ONE):
        parser.error("invalid quantity, age, delay, gap or participation")
    entries = []
    skipped = []
    for path in args.captures:
        try:
            records = read_capture(path)
            if records[-1]["kind"] != "sweep_end":
                raise ValueError("missing sweep summary")
            timestamp = datetime.fromisoformat(records[-1]["ended_at"])
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            skipped.append({"capture": str(path), "reason": str(exc)})
            continue
        try:
            frame = load_frame(records, args.event) if args.event in event_tickers(records) else None
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            skipped.append({"capture": str(path), "reason": str(exc)})
            frame = None
        entries.append((timestamp, frame))
    if not any(frame is not None for _, frame in entries):
        parser.exit(1, f"No usable sweeps for {args.event}. Skipped: {json.dumps(skipped)}\n")
    scenarios = (Scenario("instant", 0, 0, ONE),
                 Scenario("delayed", args.delay, 0, ONE),
                 Scenario("delayed_partial", args.delay, args.leg_gap, args.participation))
    try:
        result = replay(entries, scenarios, Decimal(args.quantity), args.max_age)
    except ValueError as exc:
        parser.exit(1, f"Replay failed: {exc}\n")
    print(json.dumps({"event": args.event, "scenarios": scenarios, "skipped": skipped, **result},
                     indent=2, default=encode))


if __name__ == "__main__":
    main()
