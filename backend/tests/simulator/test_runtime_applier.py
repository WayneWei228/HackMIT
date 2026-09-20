from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from trueup.simulator.clock import SimClock
from trueup.simulator.event_applier import EventApplyError, TriggerKind, apply_due_events
from trueup.simulator.event_schedule import EventSchedule, ScheduleError
from trueup.simulator.scenario_models import ScenarioEvent
from trueup.store.models import CompanyAPInvoice, CompanyContract, CompanyPurchaseOrder

CUTOFF = "2026-12-31T23:59:59Z"
OPENAI_DEC_RECEIVED = datetime(2027, 1, 5, 9, tzinfo=UTC)


def _invoices(sim):
    with sim.session() as session:
        return list(session.scalars(select(CompanyAPInvoice)))


def _snapshot(row):
    return {c.key: getattr(row, c.key) for c in row.__table__.columns}


def test_advancing_releases_only_invoices_already_received(sim):
    sim.advance_to(CUTOFF)
    cutoff = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    first = _invoices(sim)
    assert first
    assert all(inv.received_at <= cutoff for inv in first)

    sim.advance_to("2027-03-01T00:00:00Z")
    later = _invoices(sim)
    assert len(later) > len(first)
    assert any(inv.received_at > cutoff for inv in later)


def test_applying_the_same_window_twice_inserts_nothing_new(sim):
    first = sim.advance_to(CUTOFF)
    assert first.events
    with sim.session() as session:
        count = len(list(session.scalars(select(CompanyAPInvoice))))
    again = sim.apply_due_events()
    assert again.events == [] and again.triggers == []
    assert sim.advance_to(CUTOFF).events == []
    assert len(_invoices(sim)) == count


def test_applied_ids_match_what_was_released(sim):
    released = sim.advance_to(CUTOFF)
    with sim.session() as session:
        assert SimClock(session).applied_event_ids() == set(released.event_ids)


def test_mintlify_amendment_is_already_in_force_on_day_one(sim):
    with sim.session() as session:
        rows = session.scalars(
            select(CompanyContract).where(CompanyContract.contract_id == "CON-MINTLIFY")
        )
        versions = {r.contract_version: r for r in rows}
    assert versions[1].status == "SUPERSEDED"
    assert versions[1].effective_end_date == date(2026, 11, 30)
    assert versions[2].status == "ACTIVE"
    assert versions[2].effective_start_date == date(2026, 12, 1)
    assert versions[2].base_rate == Decimal("1400")


def test_receipt_event_updates_the_po_line_and_the_invoice_updates_billed_quantity(sim):
    def line():
        with sim.session() as session:
            return session.get(CompanyPurchaseOrder, "PO-ASUS-2026").line_items_json[0]

    assert (line()["quantity_received"], line()["quantity_billed"]) == ("0", "0")
    sim.advance_to("2026-12-18T14:04:59Z")
    assert line()["quantity_received"] == "0"
    sim.advance_to("2026-12-18T14:05:00Z")
    assert (line()["quantity_received"], line()["quantity_billed"]) == ("20", "0")
    sim.advance_to("2027-01-08T09:05:00Z")
    assert (line()["quantity_received"], line()["quantity_billed"]) == ("20", "20")
    sim.advance_to("2027-01-14T10:05:00Z")
    assert (line()["quantity_received"], line()["quantity_billed"]) == ("25", "20")


def test_openai_december_invoice_appears_only_when_received(sim):
    sim.advance_to("2027-01-05T08:59:59Z")
    with sim.session() as session:
        assert session.get(CompanyAPInvoice, "INV-OPENAI-2026-12") is None

    sim.advance_to(OPENAI_DEC_RECEIVED)
    with sim.session() as session:
        invoice = session.get(CompanyAPInvoice, "INV-OPENAI-2026-12")
        assert invoice.amount == Decimal("18600.00")
        assert invoice.received_at == OPENAI_DEC_RECEIVED
        assert invoice.status == "IN_QUEUE"


def test_update_event_changes_only_the_named_fields(sim_world, sim):
    event = next(
        e
        for e in sim_world.events
        if e.operation == "UPDATE" and e.table == "company_ap_invoices" and "status" in e.record
    )
    invoice_id = event.key["invoice_id"]
    just_before = event.available_at.timestamp() - 1
    sim.advance_to(datetime.fromtimestamp(just_before, UTC))
    with sim.session() as session:
        before = _snapshot(session.get(CompanyAPInvoice, invoice_id))

    sim.advance_to(event.available_at)
    with sim.session() as session:
        after = _snapshot(session.get(CompanyAPInvoice, invoice_id))
    changed = {k for k in before if before[k] != after[k]}
    assert changed <= set(event.record)
    assert "status" in changed
    assert after["updated_at"] == event.available_at


def test_update_without_updated_at_bumps_it_to_the_event_time(sim):
    sim.advance_to("2027-01-06T00:00:00Z")
    stamp = datetime(2027, 1, 6, tzinfo=UTC)
    event = ScenarioEvent(
        event_id="EVT-TEST-BUMP",
        available_at=stamp,
        operation="UPDATE",
        table="company_ap_invoices",
        record={"description": "corrected description"},
        key={"invoice_id": "INV-OPENAI-2026-12"},
    )
    with sim.session() as session:
        apply_due_events(session, EventSchedule([event]), stamp)
        row = session.get(CompanyAPInvoice, "INV-OPENAI-2026-12")
        assert row.description == "corrected description"
        assert row.updated_at == stamp
        assert row.amount == Decimal("18600.00")


def test_released_ap_invoice_produces_a_reconciliation_trigger(sim):
    released = sim.advance_to(OPENAI_DEC_RECEIVED)
    trigger = next(
        t
        for t in released.triggers
        if t.kind is TriggerKind.NEW_AP_INVOICE and t.record_id == "INV-OPENAI-2026-12"
    )
    assert trigger.target_agent == "ReconciliationAndTrueUpAgent"
    assert trigger.vendor_id == "VEN-OPENAI"
    assert trigger.at == OPENAI_DEC_RECEIVED
    assert trigger.event_id == "EVT-OPENAI-2027-01-INVOICE"


def test_the_full_timeline_yields_the_three_trigger_kinds_the_demo_uses(sim):
    released = sim.advance_to("2027-12-31T00:00:00Z")
    assert {t.kind for t in released.triggers} == {
        TriggerKind.NEW_AP_INVOICE,
        TriggerKind.AP_STATUS_CHANGE,
        TriggerKind.NEW_SERVICE_EVIDENCE,
    }


def test_events_are_applied_in_time_order(sim_world, sim):
    released = sim.advance_to("2027-12-31T00:00:00Z")
    stamps = [(e.available_at, e.event_id) for e in released.events]
    assert stamps == sorted(stamps)
    assert len(released.events) == len(sim_world.events)


def _custom(sim, event):
    with sim.session() as session:
        return apply_due_events(session, EventSchedule([event]), SimClock(session).now())


def test_insert_with_an_existing_primary_key_raises(sim_world, sim):
    sim.advance_to("2027-12-31T00:00:00Z")
    template = next(e for e in sim_world.events if e.table == "company_ap_invoices")
    duplicate = template.model_copy(update={"event_id": "EVT-TEST-DUPLICATE"})
    with pytest.raises(EventApplyError, match="exists"):
        _custom(sim, duplicate)


def test_update_of_a_missing_row_raises(sim):
    sim.advance_to("2027-12-31T00:00:00Z")
    event = ScenarioEvent(
        event_id="EVT-TEST-MISSING",
        available_at=datetime(2026, 1, 1, tzinfo=UTC),
        operation="UPDATE",
        table="company_ap_invoices",
        record={"status": "PAID"},
        key={"invoice_id": "INV-NOPE"},
    )
    with pytest.raises(EventApplyError, match="not found"):
        _custom(sim, event)


def test_applier_refuses_a_time_later_than_the_clock(sim_world, sim):
    with sim.session() as session, pytest.raises(EventApplyError, match="later than"):
        apply_due_events(session, EventSchedule(sim_world.events), datetime(2030, 1, 1, tzinfo=UTC))


def test_schedule_rejects_malformed_events(sim_world):
    stamp = datetime(2026, 2, 1, tzinfo=UTC)

    def update(**overrides):
        base = dict(
            event_id="EVT-X",
            available_at=stamp,
            operation="UPDATE",
            table="company_ap_invoices",
            record={"status": "PAID"},
            key={"invoice_id": "INV-1"},
        )
        return ScenarioEvent(**{**base, **overrides})

    with pytest.raises(ScheduleError, match="no column"):
        EventSchedule([update(record={"not_a_column": 1})])
    with pytest.raises(ScheduleError, match="primary key"):
        EventSchedule([update(record={"invoice_id": "INV-2"})])
    with pytest.raises(ScheduleError, match="key must be exactly"):
        EventSchedule([update(key={"vendor_id": "V"})])
    with pytest.raises(ScheduleError, match="duplicate event id"):
        EventSchedule([update(), update()])
    bad_insert = sim_world.events[0].model_copy(update={"record": {"vendor_id": "only"}})
    with pytest.raises(ScheduleError, match="does not fit"):
        EventSchedule([bad_insert])
