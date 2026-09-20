"""The simulation clock, stored in the agent-visible `simulation_clock` config row.

The same JSON value records which scheduled events were already applied and the seed, so
"apply each event exactly once" survives a process restart.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from trueup.store.models import CompanyConfig

CLOCK_KEY = "simulation_clock"


class ClockError(RuntimeError):
    """The clock is missing, or an operation would move time backwards."""


def parse_ts(value: str | datetime) -> datetime:
    """An ISO-8601 string or datetime as UTC-aware. Naive values are taken to be UTC."""
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def iso(stamp: datetime) -> str:
    return stamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class SimClock:
    def __init__(self, session: Session):
        self.session = session

    def _row(self) -> CompanyConfig | None:
        return self.session.get(CompanyConfig, CLOCK_KEY)

    def _value(self) -> dict:
        row = self._row()
        if row is None:
            raise ClockError("no simulation_clock row; run reset first")
        return dict(row.config_value_json)

    def _write(self, value: dict, at: datetime) -> None:
        row = self._row()
        if row is None:
            self.session.add(
                CompanyConfig(config_key=CLOCK_KEY, config_value_json=value, updated_at=at)
            )
        else:
            row.config_value_json = value
            row.updated_at = at
        self.session.flush()

    def now(self) -> datetime:
        return parse_ts(self._value()["current_time"])

    def seed(self) -> int | None:
        return self._value().get("seed")

    def applied_event_ids(self) -> set[str]:
        return set(self._value().get("applied_event_ids", []))

    def set(self, at: str | datetime, *, from_reset: bool = False, seed: int | None = None) -> None:
        """Place the clock anywhere. Only a reset may do this, and it forgets applied events."""
        if not from_reset:
            raise ClockError("the clock can only be set by a reset; use advance_to")
        stamp = parse_ts(at)
        self._write(
            {"current_time": iso(stamp), "applied_event_ids": [], "seed": seed},
            stamp,
        )

    def advance_to(self, at: str | datetime) -> datetime:
        target = parse_ts(at)
        current = self.now()
        if target < current:
            raise ClockError(f"cannot move the clock back from {iso(current)} to {iso(target)}")
        value = self._value()
        value["current_time"] = iso(target)
        self._write(value, target)
        return target

    def advance_days(self, days: int) -> datetime:
        if days < 0:
            raise ClockError("cannot move the clock back")
        return self.advance_to(self.now() + timedelta(days=days))

    def mark_applied(self, event_ids: Iterable[str]) -> None:
        value = self._value()
        value["applied_event_ids"] = sorted(
            set(value.get("applied_event_ids", [])) | set(event_ids)
        )
        self._write(value, self.now())
