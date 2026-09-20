"""Column types that keep money exact and reject bad enum values and naive-clock drift."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from sqlalchemy import DateTime, Text
from sqlalchemy.types import TypeDecorator


def coerce_money(value: object) -> Decimal:
    """Return an exact Decimal from a Decimal, int or numeric string. Floats are refused."""
    if isinstance(value, float):
        raise TypeError(f"money must be Decimal, int or str, never float: got {value!r}")
    if isinstance(value, bool) or not isinstance(value, Decimal | int | str):
        raise TypeError(f"money must be Decimal, int or str: got {type(value).__name__}")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"money must be finite: got {value!r}")
    return amount


class Money(TypeDecorator):
    """Decimal stored as TEXT so no digit is ever rounded. Compare in Python, not SQL."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else format(coerce_money(value), "f")

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)


class EnumText(TypeDecorator):
    """TEXT column that only accepts members of `enum_cls` and returns members on read."""

    impl = Text
    cache_ok = True

    def __init__(self, enum_cls: type[StrEnum]):
        super().__init__()
        self.enum_cls = enum_cls

    def process_bind_param(self, value, dialect):
        return None if value is None else self.enum_cls(value).value

    def process_result_value(self, value, dialect):
        return None if value is None else self.enum_cls(value)


class UTCDateTime(TypeDecorator):
    """Timestamps stored as naive UTC and returned timezone-aware, so cutoffs compare safely."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is None:  # a naive datetime is taken to already be UTC
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)
