"""Project a period's usage when the data for it is incomplete: a typed catalog of methods.

Pure Decimal arithmetic over facts that were read from the tables. A reasoning model may choose a
method from the catalog, but it never supplies a quantity or an amount: every number here is
computed from the evidence, so a hallucinated parameter cannot change what is accrued.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

DEFAULT_WAIT_HOURS = 48
DEFAULT_MIN_COVERED_FRACTION = Decimal("0.25")
DEFAULT_HISTORY_PERIODS = 3
DEFAULT_CONSERVATIVE_FRACTION = Decimal("0.50")
MAX_CONFIDENCE = Decimal("0.85")
UNITS_PLACES = Decimal("0.0001")
CONFIDENCE_PLACES = Decimal("0.01")


class FallbackMethod(StrEnum):
    LINEAR_SCALE_TO_PERIOD = "LINEAR_SCALE_TO_PERIOD"
    TRAILING_AVERAGE = "TRAILING_AVERAGE"
    PRIOR_PERIOD_RUN_RATE = "PRIOR_PERIOD_RUN_RATE"
    TYPICAL_ORDER_AVERAGE = "TYPICAL_ORDER_AVERAGE"
    CONSERVATIVE_ESTIMATE = "CONSERVATIVE_ESTIMATE"


USAGE_METHODS = (
    FallbackMethod.LINEAR_SCALE_TO_PERIOD,
    FallbackMethod.TRAILING_AVERAGE,
    FallbackMethod.PRIOR_PERIOD_RUN_RATE,
)
RECEIPT_METHODS = (FallbackMethod.TYPICAL_ORDER_AVERAGE, FallbackMethod.CONSERVATIVE_ESTIMATE)
DEFAULT_METHOD = FallbackMethod.LINEAR_SCALE_TO_PERIOD

DEFINITIONS: dict[FallbackMethod, str] = {
    FallbackMethod.LINEAR_SCALE_TO_PERIOD: (
        "units so far x days in the period / days covered by the data. Uses this period's own "
        "usage, so it follows growth or decline inside the month."
    ),
    FallbackMethod.TRAILING_AVERAGE: (
        "units per day over the chosen prior complete periods x days in the period. Smooths out "
        "one unusual month, but ignores this period's own data."
    ),
    FallbackMethod.PRIOR_PERIOD_RUN_RATE: (
        "units per day in the latest prior complete period x days in the period. Assumes usage "
        "did not change since last period."
    ),
    FallbackMethod.TYPICAL_ORDER_AVERAGE: (
        "average units received on this vendor's earlier orders, as recorded in the receipts, "
        "x the PO unit price, never above the quantity ordered. Needs earlier receipts."
    ),
    FallbackMethod.CONSERVATIVE_ESTIMATE: (
        "an assumed share of the quantity ordered (the share is set in company policy), rounded "
        "down to whole units, x the PO unit price. An assumption, not a fact."
    ),
}


@dataclass(frozen=True)
class FallbackPolicy:
    """The company's rules for giving up on a reply and estimating from what is known."""

    wait_hours: int = DEFAULT_WAIT_HOURS
    min_covered_fraction: Decimal = DEFAULT_MIN_COVERED_FRACTION
    history_periods: int = DEFAULT_HISTORY_PERIODS
    conservative_fraction: Decimal = DEFAULT_CONSERVATIVE_FRACTION

    @classmethod
    def from_config(cls, value: Any) -> FallbackPolicy:
        if not isinstance(value, dict):
            return cls()
        hours = str(value.get("outreach_wait_hours", ""))
        history = str(value.get("history_periods", ""))
        try:
            fraction = Decimal(str(value["min_covered_fraction"]))
        except (KeyError, ArithmeticError, ValueError):
            fraction = DEFAULT_MIN_COVERED_FRACTION
        try:
            share = Decimal(str(value["conservative_received_fraction"]))
        except (KeyError, ArithmeticError, ValueError):
            share = DEFAULT_CONSERVATIVE_FRACTION
        if not Decimal(0) < share < Decimal(1):
            share = DEFAULT_CONSERVATIVE_FRACTION
        return cls(
            conservative_fraction=share,
            wait_hours=int(hours) if hours.isdigit() and int(hours) > 0 else DEFAULT_WAIT_HOURS,
            min_covered_fraction=fraction,
            history_periods=int(history)
            if history.isdigit() and int(history) > 0
            else DEFAULT_HISTORY_PERIODS,
        )


@dataclass(frozen=True)
class PeriodUsage:
    """One prior complete period's confirmed usage."""

    period: str
    days: int
    units: Decimal
    source_id: str


@dataclass(frozen=True)
class UsageFacts:
    """Everything a projection may use, all read from source records."""

    unit: str
    period_start: date
    period_end: date
    covered_start: date
    covered_end: date
    covered_units: Decimal
    source_id: str
    history: tuple[PeriodUsage, ...] = ()

    @property
    def period_days(self) -> int:
        return (self.period_end - self.period_start).days + 1

    @property
    def covered_days(self) -> int:
        return (self.covered_end - self.covered_start).days + 1

    @property
    def coverage_fraction(self) -> Decimal:
        return Decimal(self.covered_days) / Decimal(self.period_days)


@dataclass(frozen=True)
class Projection:
    method: FallbackMethod
    units: Decimal
    expression: str
    parameters: dict[str, Any]


class FallbackError(ValueError):
    """The method cannot be applied to these facts."""


def available_methods(facts: UsageFacts) -> list[FallbackMethod]:
    methods = [FallbackMethod.LINEAR_SCALE_TO_PERIOD]
    if facts.history:
        methods += [FallbackMethod.TRAILING_AVERAGE, FallbackMethod.PRIOR_PERIOD_RUN_RATE]
    return methods


def history_for(
    method: FallbackMethod, facts: UsageFacts, periods: list[str] | None = None
) -> tuple[PeriodUsage, ...]:
    """The prior periods a method uses: all of them, or the ones the caller named (checked)."""
    if method == FallbackMethod.LINEAR_SCALE_TO_PERIOD:
        return ()
    if not facts.history:
        raise FallbackError(f"{method.value} needs a prior complete period and there is none.")
    if method == FallbackMethod.PRIOR_PERIOD_RUN_RATE:
        latest = facts.history[-1]
        if periods is not None and periods != [latest.period]:
            raise FallbackError(f"{method.value} uses the latest period, {latest.period}.")
        return (latest,)
    if periods is None:
        return facts.history
    known = {h.period: h for h in facts.history}
    unknown = [p for p in periods if p not in known]
    if unknown or not periods or len(set(periods)) != len(periods):
        raise FallbackError(f"{method.value} was given periods {periods}, not in the evidence.")
    return tuple(known[p] for p in sorted(periods))


def project_units(
    method: FallbackMethod, facts: UsageFacts, periods: list[str] | None = None
) -> Projection:
    """The units expected for the whole period under one method."""
    if method == FallbackMethod.LINEAR_SCALE_TO_PERIOD:
        units = facts.covered_units * facts.period_days / facts.covered_days
        expression = f"{_q(facts.covered_units)} x {facts.period_days} / {facts.covered_days} days"
        parameters: dict[str, Any] = {
            "covered_units": _q(facts.covered_units),
            "covered_start": facts.covered_start.isoformat(),
            "covered_end": facts.covered_end.isoformat(),
            "covered_days": facts.covered_days,
            "period_days": facts.period_days,
        }
    else:
        used = history_for(method, facts, periods)
        total_units = sum((h.units for h in used), Decimal(0))
        total_days = sum(h.days for h in used)
        units = total_units / total_days * facts.period_days
        expression = f"{_q(total_units)} / {total_days} days x {facts.period_days}"
        parameters = {
            "history_periods": [h.period for h in used],
            "history_units": _q(total_units),
            "history_days": total_days,
            "period_days": facts.period_days,
        }
    return Projection(
        method=method,
        units=units.quantize(UNITS_PLACES, rounding=ROUND_HALF_UP),
        expression=expression,
        parameters=parameters,
    )


def confidence_for(
    method: FallbackMethod, facts: UsageFacts, cap: Decimal | None = None
) -> Decimal:
    """How far the projection can be trusted, never above `MAX_CONFIDENCE`."""
    base = {
        FallbackMethod.LINEAR_SCALE_TO_PERIOD: facts.coverage_fraction,
        FallbackMethod.TRAILING_AVERAGE: Decimal("0.55"),
        FallbackMethod.PRIOR_PERIOD_RUN_RATE: Decimal("0.50"),
    }[method]
    limit = MAX_CONFIDENCE if cap is None else min(MAX_CONFIDENCE, cap)
    return min(base, limit).quantize(CONFIDENCE_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PriorReceipt:
    """One earlier confirmed goods receipt for the vendor, on another order."""

    source_id: str
    order_id: str
    received_on: date
    units: Decimal


@dataclass(frozen=True)
class ReceiptFacts:
    """What a goods-received projection may use: the order and the vendor's earlier receipts."""

    unit: str
    ordered_units: Decimal
    unit_price: Decimal
    conservative_fraction: Decimal
    history: tuple[PriorReceipt, ...] = ()


def available_receipt_methods(facts: ReceiptFacts) -> list[FallbackMethod]:
    methods = [FallbackMethod.TYPICAL_ORDER_AVERAGE] if facts.history else []
    return [*methods, FallbackMethod.CONSERVATIVE_ESTIMATE]


def receipts_for(facts: ReceiptFacts, sources: list[str] | None = None) -> tuple[PriorReceipt, ...]:
    """The earlier receipts the typical-order method uses: all, or the ones named (checked)."""
    if not facts.history:
        raise FallbackError("TYPICAL_ORDER_AVERAGE needs an earlier receipt and there is none.")
    if sources is None:
        return facts.history
    known = {r.source_id: r for r in facts.history}
    unknown = [s for s in sources if s not in known]
    if unknown or not sources or len(set(sources)) != len(sources):
        raise FallbackError(f"Receipts {sources} are not in the vendor's recorded receipts.")
    return tuple(known[s] for s in sorted(sources))


def project_received_units(
    method: FallbackMethod, facts: ReceiptFacts, sources: list[str] | None = None
) -> Projection:
    """The units expected to have arrived on the order, in whole units, never above the order."""
    whole = Decimal(1)
    if method == FallbackMethod.TYPICAL_ORDER_AVERAGE:
        used = receipts_for(facts, sources)
        per_order: dict[str, Decimal] = {}
        for receipt in used:
            per_order[receipt.order_id] = (
                per_order.get(receipt.order_id, Decimal(0)) + receipt.units
            )
        average = sum(per_order.values(), Decimal(0)) / len(per_order)
        units = min(average.quantize(whole, rounding=ROUND_HALF_UP), facts.ordered_units)
        expression = (
            f"average of {', '.join(_q(u) for u in per_order.values())} received on "
            f"{len(per_order)} earlier order(s) = {_q(units)}"
        )
        parameters: dict[str, Any] = {
            "history_sources": [r.source_id for r in used],
            "history_orders": {k: _q(v) for k, v in per_order.items()},
            "average_units": _q(average),
            "ordered_units": _q(facts.ordered_units),
        }
    elif method == FallbackMethod.CONSERVATIVE_ESTIMATE:
        units = (facts.ordered_units * facts.conservative_fraction).quantize(
            whole, rounding=ROUND_DOWN
        )
        expression = (
            f"{_q(facts.conservative_fraction)} x {_q(facts.ordered_units)} ordered, "
            f"rounded down = {_q(units)}"
        )
        parameters = {
            "ordered_units": _q(facts.ordered_units),
            "assumed_fraction": _q(facts.conservative_fraction),
            "assumption": (
                f"Assumes {_q(facts.conservative_fraction * 100)}% of the quantity ordered "
                "arrived. This is a policy assumption, not a fact from any record."
            ),
        }
    else:
        raise FallbackError(f"{method.value} does not project received goods.")
    return Projection(method=method, units=units, expression=expression, parameters=parameters)


def receipt_confidence(method: FallbackMethod, cap: Decimal | None = None) -> Decimal:
    base = {
        FallbackMethod.TYPICAL_ORDER_AVERAGE: Decimal("0.50"),
        FallbackMethod.CONSERVATIVE_ESTIMATE: Decimal("0.30"),
    }[method]
    limit = MAX_CONFIDENCE if cap is None else min(MAX_CONFIDENCE, cap)
    return min(base, limit).quantize(CONFIDENCE_PLACES, rounding=ROUND_HALF_UP)


def _q(value: Decimal) -> str:
    return format(value.normalize(), "f")
