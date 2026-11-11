"""Generate the public dashboard demo entirely from fictional inputs."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from random import Random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kalshi_engine.arbitrage import Book, Condition
from kalshi_engine.model import study
from kalshi_engine.model_data import SPLIT, at
from kalshi_engine.replay import Scenario, replay
from kalshi_engine.scan import Frame, encode

D = Decimal


def demo_replay():
    start = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    names = ("DEMO-NORTH", "DEMO-SOUTH")
    conditions = {name: Condition(name, "winner") for name in names}
    outcomes = ({names[0]: 1, names[1]: 0}, {names[0]: 0, names[1]: 1})
    entries = []
    samples = [
        (((".42", 25), (".45", 20)), ((".43", 25), (".46", 20))),
        (((".42", 30), (".45", 20)), ((".43", 6), (".46", 20))),
        (((".47", 25), (".49", 20)), ((".51", 35), (".54", 20))),
        (((".48", 25), (".49", 20)), ((".50", 30), (".53", 20))),
    ]
    for index, levels in enumerate(samples):
        timestamp = start + timedelta(seconds=index * 5)
        books = {}
        for offset, (name, asks) in enumerate(zip(names, levels, strict=True)):
            books[name] = Book(
                timestamp - timedelta(seconds=1), timestamp - timedelta(milliseconds=300 * offset),
                ((D(".32"), D(50)),), tuple((1 - D(price), D(size)) for price, size in asks),
            )
        frame = Frame(timestamp, conditions, books,
                      dict.fromkeys(names, start + timedelta(hours=1)), D(1),
                      ordinary_outcomes=outcomes)
        entries.append((timestamp, frame))
    scenarios = (Scenario("instant", 0, 0, D(1)), Scenario("delayed", 5, 0, D(1)),
                 Scenario("delayed_partial", 5, 1, D(".50")))
    return {"scenarios": scenarios, **replay(entries, scenarios, D(10), 10)}


def demo_model():
    rng = Random(2026)
    split = at(SPLIT)
    rows = []
    for index in range(400):
        day = split + timedelta(days=index // 10 - 25)
        signal = day + timedelta(hours=12)
        midpoint = rng.randint(14, 86) / 100
        true_probability = min(.99, max(.01, .50 + 1.4 * (midpoint - .50)))
        rows.append({
            "day": day.date().isoformat(), "ticker": f"DEMO-{index:03d}",
            "signal_ts": int(signal.timestamp()), "settled_ts": int(signal.timestamp()) + 3600,
            "midpoint": midpoint, "early_midpoint": min(.97, max(.03, midpoint + rng.uniform(-.1, .1))),
            "bid": D(str(midpoint)) - D(".01"), "ask": D(str(midpoint)) + D(".01"),
            "label": int(rng.random() < true_probability),
        })
    report = study(rows, {}, D(1))
    del report["predictions"]
    return report


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "docs" / "demo.json"
    target.write_text(json.dumps({"replay": demo_replay(), "model": demo_model()},
                                 indent=2, default=encode) + "\n", encoding="utf-8")
