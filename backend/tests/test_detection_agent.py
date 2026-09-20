from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from trueup.agents.detection_agent import PeriodNotDetectableError, detect
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.session import create_all, get_session, make_engine

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
PERIOD = "2026-12"
DEMO_VENDORS = ["VEN-MINTLIFY", "VEN-OPENAI", "VEN-ASUS", "VEN-META", "VEN-NOTABILITY"]
PERIODS = {
    "2026-11": {"status": "CLOSED", "phase": "HISTORICAL"},
    "2026-12": {"status": "OPEN", "phase": "LIVE"},
    "2027-01": {"status": "OPEN", "phase": "LIVE"},
}


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def demo(world):
    sim = Simulator.from_world(world)
    sim.advance_to("2026-12-31T23:59:00Z")
    with sim.session() as session:
        yield session


@pytest.fixture
def session():
    engine = make_engine()
    create_all(engine)
    with get_session(engine) as s:
        s.add(
            m.CompanyConfig(
                config_key="accounting_periods", config_value_json=PERIODS, updated_at=NOW
            )
        )
        yield s


def vendor(session, vendor_id, *, active=True):
    session.add(
        m.CompanyVendor(
            vendor_id=vendor_id,
            vendor_name=vendor_id.title(),
            vendor_category=e.VendorCategory.OTHER,
            billing_cadence=e.BillingCadence.MONTHLY,
            default_currency="USD",
            is_active=active,
        )
    )
    session.flush()


def contract(
    session, contract_id, vendor_id, *, version=1, status=e.ContractStatus.ACTIVE, start, end=None
):
    session.add(
        m.CompanyContract(
            contract_row_id=f"{contract_id}-v{version}",
            contract_id=contract_id,
            contract_version=version,
            vendor_id=vendor_id,
            contract_name=contract_id,
            status=status,
            effective_start_date=start,
            effective_end_date=end,
            billing_model=e.BillingModel.FIXED_FEE,
            base_rate=Decimal("100.00"),
            rate_unit=e.RateUnit.MONTH,
            billing_frequency=e.BillingFrequency.MONTHLY_IN_ARREARS,
            contract_text="",
        )
    )
    session.flush()


def purchase_order(
    session,
    po_id,
    vendor_id,
    *,
    status=e.POStatus.OPEN,
    start=None,
    end=None,
    contract_id=None,
):
    session.add(
        m.CompanyPurchaseOrder(
            po_id=po_id,
            po_number=po_id,
            vendor_id=vendor_id,
            contract_id=contract_id,
            status=status,
            order_type=e.OrderType.STANDARD,
            entity_id="ENT-1",
            cost_center="CC-1",
            po_owner_id="OWN-1",
            approved_total=Decimal("1000.00"),
            currency="USD",
            service_start_date=start,
            service_end_date=end,
            gl_account="6000",
            description="test order",
            line_items_json=[],
        )
    )
    session.flush()


def non_po(
    session,
    spend_id,
    vendor_id,
    *,
    gl="6100",
    source=e.SpendSource.CORPORATE_CARD,
    status=e.TransactionStatus.SETTLED,
    accrued=False,
    ap_invoice_id=None,
):
    session.add(
        m.CompanyNonPOSpend(
            non_po_spend_id=spend_id,
            transaction_date=date(2026, 12, 10),
            month=PERIOD,
            vendor_id=vendor_id,
            merchant_name="Merchant",
            spend_source=source,
            cost_center="CC-1",
            gl_account=gl,
            amount=Decimal("50.00"),
            currency="USD",
            transaction_status=status,
            ap_invoice_id=ap_invoice_id,
            description="card spend",
            is_accrued=accrued,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.flush()


def ap_invoice(session, invoice_id, vendor_id):
    session.add(
        m.CompanyAPInvoice(
            invoice_id=invoice_id,
            vendor_id=vendor_id,
            invoice_number=invoice_id,
            invoice_date=date(2026, 12, 20),
            received_at=NOW,
            amount=Decimal("50.00"),
            currency="USD",
            status=e.APInvoiceStatus.POSTED,
            description="card spend invoice",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.flush()


def obligations(session):
    return session.scalars(
        select(m.TrueUpObligation).order_by(m.TrueUpObligation.obligation_id)
    ).all()


def test_opens_the_five_demo_obligations_from_the_real_seed(demo):
    result = detect(demo, PERIOD, now=NOW)
    assert result.opened == [f"OBL-{v.removeprefix('VEN-')}-{PERIOD}" for v in sorted(DEMO_VENDORS)]
    by_vendor = {o.vendor_id: o for o in obligations(demo)}
    assert set(by_vendor) == set(DEMO_VENDORS)
    assert (by_vendor["VEN-MINTLIFY"].contract_id, by_vendor["VEN-MINTLIFY"].po_id) == (
        "CON-MINTLIFY",
        "PO-MINTLIFY-2026",
    )
    assert by_vendor["VEN-ASUS"].contract_id is None
    assert by_vendor["VEN-ASUS"].po_id == "PO-ASUS-2026"
    assert by_vendor["VEN-NOTABILITY"].po_id is None
    assert by_vendor["VEN-NOTABILITY"].contract_id == "CON-NOTABILITY"


def test_every_obligation_ends_at_searching_ap_with_neutral_fields(demo):
    detect(demo, PERIOD, now=NOW)
    for o in obligations(demo):
        assert (o.workflow_stage, o.next_action) == (
            e.WorkflowStage.SEARCHING_AP,
            e.NextAction.SEARCH_AP,
        )
        assert o.assigned_agent == "detection"
        assert o.purchase_type == e.PurchaseType.UNKNOWN
        assert o.invoice_status == e.InvoiceStatus.NOT_SEARCHED
        assert o.evidence_status == e.EvidenceStatus.NOT_COLLECTED
        assert o.accrual_status == e.AccrualStatus.NOT_STARTED
        assert o.opened_at.replace(tzinfo=UTC) == NOW
        assert (o.service_start_date, o.service_end_date) == (date(2026, 12, 1), date(2026, 12, 31))


def test_rerun_opens_nothing_and_reports_the_existing_obligations(demo):
    first = detect(demo, PERIOD, now=NOW)
    second = detect(demo, PERIOD, now=NOW)
    assert second.opened == []
    assert len(obligations(demo)) == len(first.opened)
    already = [s for s in second.skipped if "already exists" in s.reason]
    assert sorted(s.obligation_id for s in already) == sorted(first.opened)


def test_contract_versions_collapse_to_one_obligation(session):
    vendor(session, "VEN-A")
    contract(session, "CON-A", "VEN-A", version=1, status=e.ContractStatus.SUPERSEDED,
             start=date(2026, 1, 1), end=date(2026, 12, 15))  # fmt: skip
    contract(session, "CON-A", "VEN-A", version=2, start=date(2026, 12, 16), end=date(2027, 12, 15))
    result = detect(session, PERIOD, now=NOW)
    assert result.opened == ["OBL-A-2026-12"]
    row = obligations(session)[0]
    assert (row.service_start_date, row.service_end_date) == (date(2026, 12, 1), date(2026, 12, 31))


def test_contract_and_po_sharing_an_id_make_one_obligation(session):
    vendor(session, "VEN-A")
    contract(session, "CON-A", "VEN-A", start=date(2026, 1, 1), end=date(2027, 12, 31))
    purchase_order(session, "PO-A", "VEN-A", contract_id="CON-A")
    assert detect(session, PERIOD, now=NOW).opened == ["OBL-A-2026-12"]
    row = obligations(session)[0]
    assert (row.contract_id, row.po_id) == ("CON-A", "PO-A")


def test_a_second_po_on_the_same_contract_does_not_carry_the_contract_again(session):
    vendor(session, "VEN-A")
    contract(session, "CON-A", "VEN-A", start=date(2026, 1, 1), end=date(2027, 12, 31))
    purchase_order(session, "PO-A1", "VEN-A", contract_id="CON-A")
    purchase_order(session, "PO-A2", "VEN-A", contract_id="CON-A")
    assert detect(session, PERIOD, now=NOW).opened == ["OBL-A-2026-12", "OBL-A-2026-12-02"]
    rows = {o.po_id: o.contract_id for o in obligations(session)}
    assert rows == {"PO-A1": "CON-A", "PO-A2": None}


@pytest.mark.parametrize("status", [e.ContractStatus.EXPIRED, e.ContractStatus.TERMINATED])
def test_expired_and_terminated_contracts_are_skipped(session, status):
    vendor(session, "VEN-A")
    contract(
        session, "CON-A", "VEN-A", status=status, start=date(2026, 1, 1), end=date(2027, 12, 31)
    )
    result = detect(session, PERIOD, now=NOW)
    assert result.opened == []
    assert status in result.skipped[0].reason


@pytest.mark.parametrize(
    "status", [e.POStatus.CANCELLED, e.POStatus.CLOSED, e.POStatus.FULLY_BILLED]
)
def test_purchase_orders_that_cannot_accrue_are_skipped(session, status):
    vendor(session, "VEN-A")
    purchase_order(session, "PO-A", "VEN-A", status=status)
    result = detect(session, PERIOD, now=NOW)
    assert result.opened == []
    assert [(s.kind, s.ref) for s in result.skipped] == [("purchase_order", "PO-A")]
    assert status in result.skipped[0].reason


def test_windows_that_miss_the_period_are_skipped(session):
    vendor(session, "VEN-A")
    contract(session, "CON-EARLY", "VEN-A", start=date(2026, 1, 1), end=date(2026, 11, 30))
    contract(session, "CON-LATE", "VEN-A", start=date(2027, 1, 1), end=date(2027, 12, 31))
    purchase_order(session, "PO-OLD", "VEN-A", start=date(2026, 1, 1), end=date(2026, 11, 30))
    result = detect(session, PERIOD, now=NOW)
    assert result.opened == []
    assert {s.ref for s in result.skipped} == {"CON-EARLY", "CON-LATE", "PO-OLD"}


def test_non_po_spend_groups_into_one_obligation_per_group(session):
    vendor(session, "VEN-A")
    for n in range(3):
        non_po(session, f"NP-{n}", "VEN-A")
    non_po(session, "NP-OTHER-GL", "VEN-A", gl="6200")
    non_po(session, "NP-DIRECT", "VEN-A", source=e.SpendSource.DIRECT_NON_PO_INVOICE)
    result = detect(session, PERIOD, now=NOW)
    assert len(result.opened) == 3
    keys = sorted(o.non_po_group_key for o in obligations(session))
    assert keys == [
        "CORPORATE_CARD:VEN-A:6100",
        "CORPORATE_CARD:VEN-A:6200",
        "DIRECT_NON_PO_INVOICE:VEN-A:6100",
    ]
    assert all(o.contract_id is None and o.po_id is None for o in obligations(session))


def test_non_po_rows_that_are_settled_elsewhere_are_skipped(session):
    vendor(session, "VEN-A")
    ap_invoice(session, "INV-1", "VEN-A")
    non_po(session, "NP-ACCRUED", "VEN-A", accrued=True)
    non_po(session, "NP-INVOICED", "VEN-A", ap_invoice_id="INV-1")
    non_po(session, "NP-VOIDED", "VEN-A", status=e.TransactionStatus.VOIDED)
    non_po(session, "NP-POSTED", "VEN-A", status=e.TransactionStatus.POSTED_TO_AP)
    result = detect(session, PERIOD, now=NOW)
    assert result.opened == []
    assert {s.ref for s in result.skipped} == {
        "NP-ACCRUED",
        "NP-INVOICED",
        "NP-VOIDED",
        "NP-POSTED",
    }


def test_non_po_row_without_a_vendor_is_skipped(session):
    vendor(session, "VEN-A")
    non_po(session, "NP-1", None)
    result = detect(session, PERIOD, now=NOW)
    assert result.opened == []
    assert "not mapped" in result.skipped[0].reason


@pytest.mark.parametrize("period", ["2026-11", "2030-05"])
def test_closed_or_unknown_periods_are_refused(session, period):
    with pytest.raises(PeriodNotDetectableError):
        detect(session, period, now=NOW)
    assert obligations(session) == []


def test_a_period_that_has_not_started_is_refused(session):
    with pytest.raises(PeriodNotDetectableError, match="has not started"):
        detect(session, "2027-01", now=NOW)


def test_unseen_vendors_are_detected_by_structure_alone(session):
    for vendor_id in ("VEN-ZETA", "VEN-QUARK"):
        vendor(session, vendor_id)
    contract(session, "CON-ZETA", "VEN-ZETA", start=date(2026, 12, 1), end=date(2027, 11, 30))
    purchase_order(
        session, "PO-QUARK", "VEN-QUARK", start=date(2026, 12, 1), end=date(2026, 12, 31)
    )
    assert detect(session, PERIOD, now=NOW).opened == ["OBL-QUARK-2026-12", "OBL-ZETA-2026-12"]


def test_inactive_vendor_is_skipped(session):
    vendor(session, "VEN-A", active=False)
    purchase_order(session, "PO-A", "VEN-A")
    result = detect(session, PERIOD, now=NOW)
    assert result.opened == []
    assert "inactive" in result.skipped[0].reason


def test_ids_stay_unique_when_a_vendor_gains_candidates_later(session):
    vendor(session, "VEN-A")
    purchase_order(session, "PO-A1", "VEN-A")
    purchase_order(session, "PO-A2", "VEN-A")
    assert detect(session, PERIOD, now=NOW).opened == ["OBL-A-2026-12", "OBL-A-2026-12-02"]
    purchase_order(session, "PO-A3", "VEN-A")
    assert detect(session, PERIOD, now=NOW).opened == ["OBL-A-2026-12-03"]
    ids = [o.obligation_id for o in obligations(session)]
    assert len(ids) == len(set(ids)) == 3


def test_run_log_is_written(demo):
    result = detect(demo, PERIOD, now=NOW)
    run = demo.scalars(select(m.TrueUpAgentRun)).one()
    assert (run.agent_name, run.action) == ("detection", "detect_obligations")
    assert run.status == "COMPLETED"
    assert run.output_record_ids_json == result.opened
    mintlify_v2 = demo.scalars(
        select(m.CompanyContract.contract_row_id).where(
            m.CompanyContract.contract_id == "CON-MINTLIFY",
            m.CompanyContract.contract_version == 2,
        )
    ).one()
    assert {mintlify_v2, "PO-ASUS-2026"} <= set(run.input_record_ids_json)
    decisions = {f["decision"] for f in run.facts_used_json}
    assert "opened" in decisions
    assert "Opened 5 obligations" in run.decision_summary


def test_run_log_records_skips(session):
    vendor(session, "VEN-A")
    purchase_order(session, "PO-A", "VEN-A", status=e.POStatus.CANCELLED)
    detect(session, PERIOD, now=NOW)
    run = session.scalars(select(m.TrueUpAgentRun)).one()
    assert run.output_record_ids_json == []
    assert [f["decision"] for f in run.facts_used_json] == ["skipped"]
