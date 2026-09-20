"""Apply due scheduled events to the company tables and report what an agent should react to."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from sqlalchemy.orm import Session

from trueup.simulator.clock import SimClock
from trueup.simulator.event_schedule import EventSchedule
from trueup.simulator.scenario_models import PRIMARY_KEYS, ScenarioEvent
from trueup.simulator.seed_loader import ORM_MODELS, field_values, record_to_row


class EventApplyError(RuntimeError):
    """An event cannot be applied: duplicate primary key, missing row, or future clock."""


class TriggerKind(StrEnum):
    NEW_AP_INVOICE = "NEW_AP_INVOICE"
    AP_STATUS_CHANGE = "AP_STATUS_CHANGE"
    NEW_SERVICE_EVIDENCE = "NEW_SERVICE_EVIDENCE"
    NON_PO_STATUS_CHANGE = "NON_PO_STATUS_CHANGE"
    CONTRACT_VERSION = "CONTRACT_VERSION"


@dataclass(frozen=True)
class Trigger:
    kind: TriggerKind
    target_agent: str
    event_id: str
    table: str
    record_id: str
    vendor_id: str | None
    at: datetime


@dataclass
class Released:
    events: list[ScenarioEvent] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)

    @property
    def event_ids(self) -> list[str]:
        return [e.event_id for e in self.events]

    @property
    def by_table(self) -> Counter[str]:
        return Counter(e.table for e in self.events)


def apply_due_events(
    session: Session, schedule: EventSchedule, now: datetime, vendor_id: str | None = None
) -> Released:
    """Apply every unapplied event released by `now`, then remember their ids in the clock row.

    With `vendor_id` only that vendor's events are applied, and `now` is that vendor's own moment,
    so it may be earlier than the shared clock.
    """
    clock = SimClock(session)
    if vendor_id is None and now > clock.now():
        raise EventApplyError("cannot apply events later than the simulation clock")
    released = Released()
    for event in schedule.due(now, clock.applied_event_ids()):
        if vendor_id is not None and event_vendor(session, event) != vendor_id:
            continue
        row = _apply(session, event)
        released.events.append(event)
        trigger = _trigger(event, row)
        if trigger is not None:
            released.triggers.append(trigger)
    clock.mark_applied(released.event_ids)
    return released


def event_vendor(session: Session, event: ScenarioEvent) -> str | None:
    """The vendor an event is about: named in an inserted record or on the row it updates."""
    if event.operation == "INSERT":
        return event.record.get("vendor_id")
    row = session.get(ORM_MODELS[event.table], event.key[PRIMARY_KEYS[event.table]])
    return getattr(row, "vendor_id", None)


def _apply(session: Session, event: ScenarioEvent):
    model = ORM_MODELS[event.table]
    pk = PRIMARY_KEYS[event.table]
    if event.operation == "INSERT":
        row = record_to_row(event.table, event.record)
        if session.get(model, getattr(row, pk)) is not None:
            raise EventApplyError(f"{event.event_id}: {event.table} {getattr(row, pk)} exists")
        session.add(row)
        session.flush()
        return row
    row = session.get(model, event.key[pk])
    if row is None:
        raise EventApplyError(f"{event.event_id}: {event.table} {event.key[pk]} not found")
    values = field_values(event.table, event.record)
    if hasattr(row, "updated_at") and "updated_at" not in values:
        values["updated_at"] = event.available_at
    for name, value in values.items():
        setattr(row, name, value)
    session.flush()
    return row


_INSERT_TRIGGERS = {
    "company_ap_invoices": (TriggerKind.NEW_AP_INVOICE, "ReconciliationAndTrueUpAgent"),
    "company_service_evidence": (TriggerKind.NEW_SERVICE_EVIDENCE, "DetectionAgent"),
    "company_contracts": (TriggerKind.CONTRACT_VERSION, "EvidenceAgent"),
}
_UPDATE_TRIGGERS = {
    "company_ap_invoices": ("status", TriggerKind.AP_STATUS_CHANGE, "ReconciliationAndTrueUpAgent"),
    "company_non_po_spend": (
        "transaction_status",
        TriggerKind.NON_PO_STATUS_CHANGE,
        "ReconciliationAndTrueUpAgent",
    ),
}


def _trigger(event: ScenarioEvent, row) -> Trigger | None:
    if event.operation == "INSERT":
        rule = _INSERT_TRIGGERS.get(event.table)
        if rule is None:
            return None
        kind, agent = rule
    else:
        update_rule = _UPDATE_TRIGGERS.get(event.table)
        if update_rule is None or update_rule[0] not in event.record:
            return None
        _, kind, agent = update_rule
    return Trigger(
        kind=kind,
        target_agent=agent,
        event_id=event.event_id,
        table=event.table,
        record_id=getattr(row, PRIMARY_KEYS[event.table]),
        vendor_id=getattr(row, "vendor_id", None),
        at=event.available_at,
    )
