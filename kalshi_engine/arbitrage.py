"""Settlement floors and depth-based taker simulation for dollar contracts."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from itertools import combinations

ONE = Decimal("1")
CENT = Decimal("0.01")
MICRO = Decimal("0.000001")


@dataclass(frozen=True)
class Condition:
    ticker: str
    operator: str
    lower: Decimal | None = None
    upper: Decimal | None = None

    def pays_yes(self, value):
        if self.operator == "less":
            return value < self.upper
        if self.operator == "greater":
            return value > self.lower
        if self.operator == "between":
            return self.lower <= value <= self.upper
        raise ValueError(f"unsupported comparison: {self.operator}")


@dataclass(frozen=True)
class Leg:
    ticker: str
    side: str


@dataclass(frozen=True)
class Book:
    started_at: datetime
    received_at: datetime
    yes_bids: tuple
    no_bids: tuple


@dataclass(frozen=True)
class Fill:
    price: Decimal
    quantity: Decimal
    trade_fee: Decimal
    rounding_fee: Decimal
    rebate: Decimal

    @property
    def debit(self):
        return self.price * self.quantity + self.trade_fee + self.rounding_fee - self.rebate


def outcome_samples(conditions):
    """Cover each endpoint, each intervening interval, and both tails."""
    edges = sorted({edge for c in conditions for edge in (c.lower, c.upper) if edge is not None})
    return [edges[0] - ONE, *edges, *((a + b) / 2 for a, b in zip(edges, edges[1:])),
            edges[-1] + ONE]


def payout_floors(legs, conditions):
    """Per bundle, assuming $1 complements within a market in every state."""
    relevant = {leg.ticker: conditions[leg.ticker] for leg in legs}
    ordinary = min(sum(
        relevant[leg.ticker].pays_yes(value) == (leg.side == "yes") for leg in legs
    ) for value in outcome_samples(relevant.values()))
    # Allow each fallback YES value to range independently over [0, 1].
    fallback = sum(min(legs.count(Leg(ticker, "yes")), legs.count(Leg(ticker, "no")))
                   for ticker in relevant)
    return ordinary, min(ordinary, fallback)


def candidates(conditions):
    for ticker in conditions:
        yield "same_market", (Leg(ticker, "yes"), Leg(ticker, "no"))
    if len(conditions) >= 2:
        yield "outcome_basket", tuple(Leg(ticker, "yes") for ticker in conditions)
    for a, b in combinations(conditions.values(), 2):
        if a.operator == b.operator == "less" and a.upper != b.upper:
            narrow, wide = sorted((a, b), key=lambda c: c.upper)
        elif a.operator == b.operator == "greater" and a.lower != b.lower:
            wide, narrow = sorted((a, b), key=lambda c: c.lower)
        else:
            continue
        yield "nested_threshold", (Leg(wide.ticker, "yes"), Leg(narrow.ticker, "no"))


def walk_book(book, side, quantity, multiplier, *, allow_partial=False, limit=ONE, participation=ONE):
    """Simulate one fill per consumed level and one order per leg."""
    bids = book.no_bids if side == "yes" else book.yes_bids
    remaining = quantity
    accumulator = Decimal("0")
    fills = []
    for bid, available in sorted(bids, reverse=True):
        price = ONE - bid
        if price > limit:
            break
        take = min(remaining, (available * participation).quantize(CENT, rounding=ROUND_FLOOR))
        if not take:
            continue
        trade_fee = (Decimal("0.07") * multiplier * take * price * (ONE - price)).quantize(
            MICRO, rounding=ROUND_CEILING
        )
        gross = price * take + trade_fee
        rounding = gross.quantize(CENT, rounding=ROUND_CEILING) - gross
        accumulator += rounding
        rebate = min(accumulator, trade_fee + rounding).quantize(CENT, rounding=ROUND_FLOOR)
        accumulator -= rebate
        fills.append(Fill(price, take, trade_fee, rounding, rebate))
        remaining -= take
        if not remaining:
            return tuple(fills)
    return tuple(fills) if allow_partial else None


def evaluate(kind, legs, conditions, books, quantity, as_of, max_age, multiplier):
    ordinary, conservative = payout_floors(legs, conditions)
    result = {
        "strategy": kind, "legs": legs, "quantity": quantity,
        "ordinary_payout_floor": ordinary * quantity,
        "conservative_payout_floor": conservative * quantity,
    }
    if kind == "outcome_basket" and not ordinary:
        return dict(result, status="incomplete_outcome_basket")

    simulated = []
    receipt_times = []
    quote_ages = []
    for leg in legs:
        book = books.get(leg.ticker)
        if book is None:
            return dict(result, status="missing_book", blocked_leg=leg)
        if not book.started_at <= book.received_at <= as_of or (
            as_of - book.started_at > timedelta(seconds=max_age)
        ):
            return dict(result, status="stale_quote", blocked_leg=leg)
        receipt_times.append(book.received_at)
        quote_ages.append((as_of - book.started_at).total_seconds())
        fills = walk_book(book, leg.side, quantity, multiplier)
        if fills is None:
            return dict(result, status="insufficient_depth", blocked_leg=leg)
        simulated.append(fills)

    debit = sum(fill.debit for order in simulated for fill in order)
    edge = result["conservative_payout_floor"] - debit
    return dict(result, status="positive_simulated_edge" if edge > 0 else "no_edge",
                fills=simulated, debit=debit, conservative_edge=edge,
                quote_age_seconds=quote_ages,
                quote_span_seconds=(max(receipt_times) - min(receipt_times)).total_seconds(),
                ordinary_edge=result["ordinary_payout_floor"] - debit)
