from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.support import bare_obligation
from trueup.agents.invoice_lookup_agent import Verdict, lookup
from trueup.close_orchestrator import NO_EVIDENCE, SEARCH, walk_to
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
PERIOD = "2026-12"
DEC_1, DEC_31 = date(2026, 12, 1), date(2026, 12, 31)
GATHER = (e.WorkflowStage.GATHERING_EVIDENCE, e.NextAction.GATHER_EVIDENCE)
CONTROLLER = (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)
DEMO_VENDORS = ("VEN-MINTLIFY", "VEN-OPENAI", "VEN-ASUS", "VEN-META")


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def sim(world):
    return Simulator.from_world(world)


@pytest.fixture
def session(sim):
    with sim.session() as s:
        yield s


def open_for(session, vendor_id, period=PERIOD):
    if vendor_id in DEMO_VENDORS + ("VEN-NOTABILITY",):
        return walk_to(session, vendor_id, period, now=NOW, to=SEARCH, settings=NO_EVIDENCE)
    return bare_obligation(session, vendor_id, period, now=NOW, to=SEARCH)


def lookup_run(session):
    return session.scalars(
        select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "invoice_lookup")
    ).one()


def routed(result):
    return (result.routed_stage, result.next_action)


def add_vendor(session, vendor_id="VEN-ZORBLAX"):
    session.add(
        m.CompanyVendor(
            vendor_id=vendor_id,
            vendor_name="Zorblax Labs",
            vendor_category=e.VendorCategory.SAAS,
            billing_cadence=e.BillingCadence.MONTHLY,
            default_currency="USD",
        )
    )
    session.flush()
    return vendor_id


def add_invoice(session, vendor_id, start, end, **overrides):
    n = len(session.scalars(select(m.CompanyAPInvoice)).all())
    columns = dict(
        invoice_id=f"INV-TEST-{n:03d}",
        vendor_id=vendor_id,
        invoice_number=f"T-{n:03d}",
        invoice_date=end or DEC_31,
        received_at=datetime(2026, 12, 20, tzinfo=UTC),
        service_start_date=start,
        service_end_date=end,
        amount=Decimal("100.00"),
        currency="USD",
        po_id=None,
        contract_id=None,
        status=e.APInvoiceStatus.IN_QUEUE,
        duplicate_flag=False,
        credit_flag=False,
        description="test invoice",
        line_items_json=None,
        created_at=NOW,
        updated_at=NOW,
    )
    row = m.CompanyAPInvoice(**{**columns, **overrides})
    session.add(row)
    session.flush()
    return row


def unseen(session):
    vendor_id = add_vendor(session)
    return vendor_id, open_for(session, vendor_id)


@pytest.mark.parametrize("vendor_id", DEMO_VENDORS)
def test_demo_obligations_have_no_invoice_at_close(session, vendor_id):
    ob = open_for(session, vendor_id)
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING
    assert result.matched_invoice_id is None
    assert routed(result) == GATHER
    assert (ob.workflow_stage, ob.next_action) == GATHER
    assert ob.invoice_status == e.InvoiceStatus.MISSING and ob.matched_invoice_id is None
    assert ob.assigned_agent == "invoice_lookup"


def test_the_previous_months_invoice_never_matches(session):
    result = lookup(session, open_for(session, "VEN-MINTLIFY").obligation_id, now=NOW)
    assert result.ignored_other_periods >= 3
    assert result.candidates == []


def test_prepaid_annual_invoice_routes_to_evidence_without_a_match(session):
    ob = open_for(session, "VEN-NOTABILITY")
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING
    assert result.matched_invoice_id is None and ob.matched_invoice_id is None
    assert routed(result) == GATHER
    assert [(c.invoice_id, c.verdict) for c in result.candidates] == [
        ("INV-NOTABILITY-2026-12", Verdict.MULTI_PERIOD)
    ]
    assert "in advance" in result.reason
    assert ob.accrual_status == e.AccrualStatus.NOT_STARTED and ob.resolved_at is None
    run = lookup_run(session)
    assert run.uncertainties_json and "INV-NOTABILITY-2026-12" in run.uncertainties_json[0]


def test_january_invoices_are_found_for_recurring_and_usage_vendors(sim):
    sim.advance_to("2027-01-31T00:00:00Z")
    with sim.session() as session:
        for vendor_id, invoice_id, amount in (
            ("VEN-MINTLIFY", "INV-MINTLIFY-2026-12", "1400.00"),
            ("VEN-OPENAI", "INV-OPENAI-2026-12", "18600.00"),
            ("VEN-META", "INV-META-2026-12", "30000.00"),
        ):
            ob = open_for(session, vendor_id)
            result = lookup(session, ob.obligation_id, now=JANUARY)
            assert result.invoice_status == e.InvoiceStatus.INVOICE_FOUND, vendor_id
            assert result.matched_invoice_id == invoice_id
            assert [c.amount for c in result.candidates] == [amount]
            assert routed(result) == (e.WorkflowStage.CLOSED_NO_ACCRUAL, e.NextAction.NONE)
            assert ob.matched_invoice_id == invoice_id
            assert ob.accrual_status == e.AccrualStatus.NOT_NEEDED
            assert ob.resolved_at is not None


def test_a_part_period_january_invoice_goes_to_the_controller(sim):
    sim.advance_to("2027-01-31T00:00:00Z")
    with sim.session() as session:
        ob = open_for(session, "VEN-ASUS")
        result = lookup(session, ob.obligation_id, now=JANUARY)
    assert result.invoice_status == e.InvoiceStatus.AMBIGUOUS
    assert result.matched_invoice_id is None
    assert result.candidates[0].verdict == Verdict.PARTIAL
    assert routed(result) == CONTROLLER


def test_january_invoices_are_invisible_at_close_even_after_they_exist(sim):
    sim.advance_to("2027-01-31T00:00:00Z")
    with sim.session() as session:
        ob = open_for(session, "VEN-MINTLIFY")
        result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING
    assert [c.verdict for c in result.candidates] == [Verdict.NOT_YET_RECEIVED]


def test_exact_match_for_an_unseen_vendor(session):
    vendor_id, ob = unseen(session)
    invoice = add_invoice(session, vendor_id, DEC_1, DEC_31)
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.INVOICE_FOUND
    assert result.matched_invoice_id == invoice.invoice_id
    assert routed(result) == (e.WorkflowStage.CLOSED_NO_ACCRUAL, e.NextAction.NONE)


def test_another_periods_invoice_is_ignored(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, date(2026, 11, 1), date(2026, 11, 30))
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING
    assert result.ignored_other_periods == 1


@pytest.mark.parametrize("status", [e.APInvoiceStatus.VOIDED, e.APInvoiceStatus.REJECTED])
def test_voided_or_rejected_invoices_are_ignored(session, status):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, DEC_31, status=status)
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING
    assert [c.verdict for c in result.candidates] == [Verdict.VOIDED_OR_REJECTED]


def test_credit_memos_are_not_bills(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, DEC_31, credit_flag=True)
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING
    assert [c.verdict for c in result.candidates] == [Verdict.CREDIT_MEMO]


def test_a_future_received_invoice_is_ignored(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, DEC_31, received_at=datetime(2027, 1, 3, tzinfo=UTC))
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING
    assert result.matched_invoice_id is None
    assert [c.verdict for c in result.candidates] == [Verdict.NOT_YET_RECEIVED]


def test_two_invoices_for_the_same_period_are_ambiguous(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, DEC_31)
    add_invoice(session, vendor_id, DEC_1, DEC_31)
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.AMBIGUOUS
    assert result.matched_invoice_id is None and routed(result) == CONTROLLER


def test_a_duplicate_flagged_invoice_is_ambiguous(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, DEC_31, duplicate_flag=True)
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.AMBIGUOUS


def test_a_part_period_invoice_is_ambiguous(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, date(2026, 12, 15))
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.AMBIGUOUS
    assert [c.verdict for c in result.candidates] == [Verdict.PARTIAL]


def test_an_exact_period_invoice_on_a_different_po_is_ambiguous(session):
    ob = open_for(session, "VEN-MINTLIFY")
    add_invoice(session, "VEN-MINTLIFY", DEC_1, DEC_31, po_id="PO-OPENAI-2026")
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.AMBIGUOUS
    assert [c.verdict for c in result.candidates] == [Verdict.MISMATCHED_REFERENCE]


def test_an_overlapping_invoice_on_another_po_is_not_ours(session):
    ob = open_for(session, "VEN-MINTLIFY")
    add_invoice(session, "VEN-MINTLIFY", DEC_1, date(2026, 12, 15), po_id="PO-OPENAI-2026")
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.MISSING


def test_an_undated_invoice_dated_in_the_period_is_ambiguous(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, None, None, invoice_date=date(2026, 12, 10))
    result = lookup(session, ob.obligation_id, now=NOW)
    assert result.invoice_status == e.InvoiceStatus.AMBIGUOUS


def test_an_exact_invoice_plus_a_multi_period_one_is_ambiguous(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, DEC_31)
    add_invoice(session, vendor_id, DEC_1, date(2027, 11, 30))
    assert lookup(session, ob.obligation_id, now=NOW).invoice_status == e.InvoiceStatus.AMBIGUOUS


def test_wrong_stage_raises_and_a_second_run_raises(session):
    ob = walk_to(session, "VEN-META", PERIOD, now=NOW, settings=NO_EVIDENCE)
    with pytest.raises(IllegalTransitionError):
        lookup(session, ob.obligation_id, now=NOW)
    fresh = open_for(session, "VEN-MINTLIFY")
    lookup(session, fresh.obligation_id, now=NOW)
    with pytest.raises(IllegalTransitionError):
        lookup(session, fresh.obligation_id, now=NOW)


def test_run_log_records_candidates_and_outcome(session):
    vendor_id, ob = unseen(session)
    invoice = add_invoice(session, vendor_id, DEC_1, DEC_31)
    lookup(session, ob.obligation_id, now=NOW)
    run = lookup_run(session)
    assert (run.agent_name, run.action) == ("invoice_lookup", "search_ap")
    assert run.status == e.AgentRunStatus.COMPLETED
    assert run.obligation_id == ob.obligation_id
    assert run.input_record_ids_json == [invoice.invoice_id]
    assert run.output_record_ids_json == [invoice.invoice_id]
    assert run.facts_used_json[0]["verdict"] == "EXACT"
    assert run.facts_used_json[0]["amount"] == "100.00"
    assert not any(isinstance(v, float) for f in run.facts_used_json for v in f.values())


def test_an_ambiguous_run_is_escalated_with_an_uncertainty(session):
    vendor_id, ob = unseen(session)
    add_invoice(session, vendor_id, DEC_1, date(2026, 12, 15))
    lookup(session, ob.obligation_id, now=NOW)
    run = lookup_run(session)
    assert run.status == e.AgentRunStatus.ESCALATED and run.uncertainties_json
