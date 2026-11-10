"""Train and evaluate the fixed NBA pregame probability study."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path
from random import Random
from urllib.parse import urlsplit

from kalshi_engine import nba
from kalshi_engine.arbitrage import Book, ONE, walk_book
from kalshi_engine.model_data import HOUR, SERIES, SPLIT, at, cohort
from kalshi_engine.scan import encode, parse_book, read_capture

EDGE = Decimal("0.02")


def two_sided(candle):
    try:
        bid, ask = (Decimal(candle[side]["close_dollars"]) for side in ("yes_bid", "yes_ask"))
        if 0 < bid <= ask < 1:
            return bid, ask
    except (InvalidOperation, TypeError, KeyError):
        pass
    return None


def prepare(requests):
    markets = []
    candles = defaultdict(list)
    series = {}
    for record in requests:
        if record.get("status") != 200:
            raise ValueError("request file contains a failed request")
        path = urlsplit(record["url"]).path
        if path.endswith("/markets"):
            markets.extend(record["payload"]["markets"])
        elif path.endswith("/markets/candlesticks"):
            for market in record["payload"]["markets"]:
                candles[market["market_ticker"]].extend(market["candlesticks"])
        elif path.endswith(f"/series/{SERIES}"):
            series = record["payload"]["series"]
    if (series.get("ticker"), series.get("fee_type"), series.get("contract_terms_url")) != (
        SERIES, "quadratic_with_maker_fees", nba.TERMS_URL
    ):
        raise ValueError("unverified NBA series or fee type")
    multiplier = Decimal(str(series["fee_multiplier"]))
    if not multiplier.is_finite() or multiplier < 0:
        raise ValueError("invalid taker fee multiplier")

    rows, rejected = cohort(markets)
    counts = Counter(rejected)
    counts["verified_binary_games"] = len(rows)
    usable = []
    for row in rows:
        signal = row["signal_ts"]
        by_time = {c["end_period_ts"]: c for c in candles[row["ticker"]]}
        quotes = [two_sided(by_time.get(ts, {})) for ts in (signal - 12 * HOUR, signal)]
        if any(quote is None for quote in quotes):
            counts["missing_or_invalid_candles"] += 1
            continue
        early, current = quotes
        usable.append(dict(row, bid=current[0], ask=current[1],
                           midpoint=float(sum(current) / 2), early_midpoint=float(sum(early) / 2)))
    counts["usable_games"] = len(usable)
    return usable, counts, multiplier


def logit(probability):
    probability = min(0.995, max(0.005, probability))
    return log(probability / (1 - probability))


def features(row):
    current = logit(row["midpoint"])
    return 1.0, current, current - logit(row["early_midpoint"])


def probability(weights, values):
    score = sum(weight * value for weight, value in zip(weights, values, strict=True))
    return 1 / (1 + exp(-max(-40, min(40, score))))


def train(rows):
    """Regularized logistic recalibration with a fixed baseline-centered penalty."""
    anchor = (0.0, 1.0, 0.0)
    weights = list(anchor)
    vectors = [(features(row), row) for row in rows]
    for _ in range(1000):
        gradient = [0.05 * (weight - center) for weight, center in zip(weights, anchor)]
        for values, row in vectors:
            error = (probability(weights, values) - row["label"]) / len(rows)
            for index, value in enumerate(values):
                gradient[index] += error * value
        weights = [weight - 0.1 * step for weight, step in zip(weights, gradient)]
    return weights


def metrics(rows, key):
    bins = []
    for index in range(5):
        selected = [row for row in rows if min(4, int(row[key] * 5)) == index]
        n = len(selected)
        bins.append({"lower": index / 5, "upper": (index + 1) / 5, "n": n,
                     "mean_probability": sum(row[key] for row in selected) / n if n else None,
                     "observed_frequency": sum(row["label"] for row in selected) / n if n else None})
    return {"brier": sum((row[key] - row["label"]) ** 2 for row in rows) / len(rows),
            "calibration": bins}


def brier_delta_interval(rows):
    """Resample whole UTC game dates to retain same-day dependence."""
    by_day = defaultdict(list)
    for row in rows:
        actual = row["label"]
        by_day[row["day"]].append((row["model"] - actual) ** 2 - (row["midpoint"] - actual) ** 2)
    blocks = [(sum(values), len(values)) for values in by_day.values()]
    rng = Random(2026)
    means = []
    for _ in range(2000):
        sample = rng.choices(blocks, k=len(blocks))
        means.append(sum(value for value, _ in sample) / sum(n for _, n in sample))
    means.sort()
    return {"lower": means[50], "upper": means[1949], "day_blocks": len(blocks)}


def depth_index(paths, multiplier):
    books = defaultdict(list)
    for path in paths:
        records = read_capture(path)
        if not records or records[0].get("kind") != "sweep_start" or records[-1].get("kind") != "sweep_end":
            continue
        if any(r.get("schema_version") != 1 for r in records):
            continue
        series = next((r.get("payload", {}).get("series", {}) for r in records
                       if r.get("kind") == "series"), {})
        if (series.get("ticker"), series.get("fee_type"), Decimal(str(series.get("fee_multiplier", -1)))) != (
            SERIES, "quadratic_with_maker_fees", multiplier
        ):
            continue
        as_of = datetime.fromisoformat(records[-1]["ended_at"]).timestamp()
        valid_events = {
            event["event_ticker"] for r in records if r.get("kind") == "event"
            for event in [r.get("payload", {}).get("event", {})]
            if event.get("series_ticker") == SERIES and not event.get("fee_type_override")
            and event.get("fee_multiplier_override") is None
        }
        for r in records:
            if r.get("kind") == "book" and r["ticker"].rsplit("-", 1)[0] in valid_events:
                book = parse_book(r)
                if book and book.started_at <= book.received_at and book.received_at.timestamp() <= as_of:
                    books[r["ticker"]].append((as_of, book))
    return books


def matching_book(books, row):
    signal = row["signal_ts"]
    eligible = [item for item in books.get(row["ticker"], ())
                if item[0] <= signal and signal - item[1].started_at.timestamp() <= 10]
    return max(eligible, key=lambda item: item[0])[1] if eligible else None


def order_probe(row, probability, multiplier, book):
    """One-contract threshold rule. Candle liquidity is hypothetical."""
    choices = []
    for side, price, chance, won in (
        ("yes", row["ask"], probability, row["label"]),
        ("no", ONE - row["bid"], 1 - probability, 1 - row["label"]),
    ):
        synthetic_bid = ((ONE - price, ONE),)
        quote = Book(None, None, synthetic_bid if side == "no" else (),
                     synthetic_bid if side == "yes" else ())
        debit = walk_book(quote, side, ONE, multiplier)[0].debit
        choices.append((Decimal(str(chance)) - debit, side, price, won, debit))
    edge, side, price, won, debit = max(choices)
    if edge < EDGE:
        return None
    fills = walk_book(book, side, ONE, multiplier, limit=price) if book else None
    actual_debit = sum(fill.debit for fill in fills) if fills else None
    return {"side": side, "limit": price, "quote_debit": debit, "quote_pnl": won - debit,
            "depth_debit": actual_debit, "depth_pnl": won - actual_debit if fills else None}


def returns(rows, key):
    selected = [row[key] for row in rows if row[key] is not None]
    output = {}
    for basis in ("quote", "depth"):
        filled = [order for order in selected if order[f"{basis}_debit"] is not None]
        debit = sum(order[f"{basis}_debit"] for order in filled)
        pnl = sum(order[f"{basis}_pnl"] for order in filled)
        output[basis] = {"trades": len(filled), "debit": debit, "pnl": pnl if filled else None,
                         "return_on_debit": pnl / debit if filled else None}
    return output


def study(rows, books, multiplier):
    cutoff = at(SPLIT).timestamp()
    rows = sorted(rows, key=lambda row: (row["signal_ts"], row["ticker"]))
    train_rows = [row for row in rows if row["signal_ts"] < cutoff and row["settled_ts"] < cutoff]
    holdout = [dict(row) for row in rows if row["signal_ts"] >= cutoff]
    if len(train_rows) < 40 or len(holdout) < 20 or len({row["label"] for row in train_rows}) < 2:
        raise ValueError("insufficient chronological train or holdout observations")
    weights = train(train_rows)
    coverage = 0
    for row in holdout:
        book = matching_book(books, row)
        coverage += book is not None
        row["model"] = probability(weights, features(row))
        for name in ("model", "midpoint"):
            row[f"{name}_order"] = order_probe(row, row[name], multiplier, book)
    return {
        "train_games": len(train_rows), "holdout_games": len(holdout),
        "training_labels_unavailable_at_split": sum(row["signal_ts"] < cutoff for row in rows) - len(train_rows),
        "weights": weights, "depth_matched_games": coverage,
        "metrics": {name: metrics(holdout, name) for name in ("model", "midpoint")},
        "brier_delta_day_bootstrap": brier_delta_interval(holdout),
        "returns": {name: returns(holdout, f"{name}_order") for name in ("model", "midpoint")},
        "predictions": holdout,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests", type=Path)
    parser.add_argument("--depth", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    try:
        raw = args.requests.read_bytes()
        rows, counts, multiplier = prepare([json.loads(line) for line in raw.splitlines()])
        result = study(rows, depth_index(args.depth, multiplier), multiplier)
    except (OSError, KeyError, ValueError, TypeError, InvalidOperation) as exc:
        parser.exit(1, f"Study failed: {exc}\n")
    print(json.dumps({"data_sha256": sha256(raw).hexdigest(), "coverage": counts, **result},
                     indent=2, default=encode))


if __name__ == "__main__":
    main()
