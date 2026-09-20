"""The ordered, validated list of scheduled future events. Held by the Simulator only."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from trueup.simulator.scenario_models import PRIMARY_KEYS, TABLE_MODELS, ScenarioEvent


class ScheduleError(ValueError):
    """A scheduled event is malformed for its target table."""


class EventSchedule:
    def __init__(self, events: Iterable[ScenarioEvent]):
        ordered = sorted(events, key=lambda e: (_utc(e.available_at), e.event_id))
        seen: set[str] = set()
        for event in ordered:
            if event.event_id in seen:
                raise ScheduleError(f"duplicate event id {event.event_id}")
            seen.add(event.event_id)
            _validate(event)
        self._events = ordered

    @classmethod
    def load(cls, path: str | Path) -> EventSchedule:
        return cls(ScenarioEvent.model_validate(raw) for raw in json.loads(Path(path).read_text()))

    def __len__(self) -> int:
        return len(self._events)

    def due(self, now: datetime, applied: set[str]) -> list[ScenarioEvent]:
        """Unapplied events released by `now`, in the order they should be applied."""
        return [
            e for e in self._events if e.event_id not in applied and _utc(e.available_at) <= now
        ]


def _utc(stamp: datetime) -> datetime:
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def _validate(event: ScenarioEvent) -> None:
    model_cls = TABLE_MODELS[event.table]
    pk = PRIMARY_KEYS[event.table]
    try:
        if event.operation == "INSERT":
            model_cls.model_validate(event.record)
            return
    except ValueError as exc:
        raise ScheduleError(f"{event.event_id}: record does not fit {event.table}: {exc}") from exc
    if set(event.key or {}) != {pk}:
        raise ScheduleError(f"{event.event_id}: UPDATE key must be exactly {{{pk!r}}}")
    unknown = set(event.record) - set(model_cls.model_fields)
    if unknown:
        raise ScheduleError(f"{event.event_id}: {event.table} has no column(s) {sorted(unknown)}")
    if pk in event.record:
        raise ScheduleError(f"{event.event_id}: UPDATE must not change the primary key")
