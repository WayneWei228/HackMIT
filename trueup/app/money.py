"""Money handling. Every financial amount in TrueUp is a Decimal quantized to cents.

Floats are never allowed to touch an amount: SQLite + float produces
debit/credit imbalances of 1e-14 that break the double-entry validator and
off-by-a-cent variance comparisons.
"""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Any) -> Decimal:
    """Coerce anything to a cent-quantized Decimal. Rejects float silently-lossy input."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, float):
        # Route through str() so 0.1 becomes Decimal("0.1"), not the binary expansion.
        d = Decimal(str(value))
    elif isinstance(value, str):
        d = Decimal(value.replace(",", "").replace("$", "").strip() or "0")
    else:
        raise TypeError(f"cannot convert {type(value)!r} to money")
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def rate(value: Any) -> Decimal:
    """Unit rates keep more precision than cents (e.g. $0.02 per API unit)."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value.replace(",", "").replace("$", "").strip() or "0")
    return Decimal(value)


def pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Percentage with 2dp, or None when the denominator is zero."""
    denominator = money(denominator)
    if denominator == ZERO:
        return None
    return (money(numerator) / denominator * Decimal(100)).quantize(
        CENTS, rounding=ROUND_HALF_UP
    )


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that renders Decimal as a number-shaped string-free float.

    We emit Decimals as strings to survive round-tripping without precision loss;
    consumers re-hydrate with money().
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def jsonable(obj: Any) -> Any:
    """Recursively convert Decimals (and dates) to JSON-safe primitives."""
    import datetime as _dt

    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj
