from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.store.session import create_all, get_session, make_engine

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)


@pytest.fixture
def store_engine():
    engine = make_engine()
    create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def store_session(store_engine):
    with get_session(store_engine) as session:
        yield session


def make_obligation(**overrides) -> m.TrueUpObligation:
    fields = dict(
        obligation_id="OBL-DATAFORGE-2026-12",
        vendor_id="VEN-DATAFORGE",
        period="2026-12",
        contract_id="CON-DATAFORGE",
        po_id="PO-DATAFORGE-2026",
        service_start_date=date(2026, 12, 1),
        service_end_date=date(2026, 12, 31),
        purchase_type=e.PurchaseType.USAGE_BASED,
        invoice_status=e.InvoiceStatus.NOT_SEARCHED,
        evidence_status=e.EvidenceStatus.NOT_COLLECTED,
        workflow_stage=e.WorkflowStage.DETECTED,
        next_action=e.NextAction.SEARCH_AP,
        accrual_status=e.AccrualStatus.NOT_STARTED,
        risk_level="LOW",
        opened_at=NOW,
        updated_at=NOW,
    )
    return m.TrueUpObligation(**{**fields, **overrides})


def make_gl_entry(**overrides) -> m.CompanyGLEntry:
    fields = dict(
        gl_entry_id="GL-ACCRUAL-DATAFORGE-2026-12",
        period="2026-12",
        posting_date=date(2026, 12, 31),
        vendor_id="VEN-DATAFORGE",
        obligation_id="OBL-DATAFORGE-2026-12",
        entry_type=e.GLEntryType.ACCRUAL,
        status=e.GLEntryStatus.POSTED,
        description="December 2026 DataForge accrual",
        lines_json=[
            {"account": "610200", "debit": "52500.00", "credit": "0"},
            {"account": "210100", "debit": "0", "credit": "52500.00"},
        ],
        source_workpaper_id="WP-DATAFORGE-2026-12",
        created_at=NOW,
    )
    return m.CompanyGLEntry(**{**fields, **overrides})


@pytest.fixture
def obligation_factory():
    return make_obligation


@pytest.fixture
def gl_entry_factory():
    return make_gl_entry


@pytest.fixture
def one_of_each(store_session):
    """One realistic row in every table, inserted in dependency order."""
    session = store_session

    def add(*rows):
        session.add_all(rows)
        session.flush()

    add(
        m.CompanyVendor(
            vendor_id="VEN-DATAFORGE",
            vendor_name="DataForge",
            vendor_category=e.VendorCategory.DATA,
            billing_cadence=e.BillingCadence.USAGE_BASED,
            default_currency="USD",
            billing_contact_email="billing@dataforge.example",
        )
    )
    add(
        m.CompanyContract(
            contract_row_id="CON-DATAFORGE-V1",
            contract_id="CON-DATAFORGE",
            contract_version=1,
            vendor_id="VEN-DATAFORGE",
            contract_name="DataForge API platform",
            status=e.ContractStatus.ACTIVE,
            effective_start_date=date(2026, 1, 1),
            billing_model=e.BillingModel.USAGE_BASED,
            base_rate=Decimal("0.005"),
            rate_unit=e.RateUnit.API_CALL,
            billing_frequency=e.BillingFrequency.MONTHLY_IN_ARREARS,
            escalator_percent=Decimal("5"),
            escalator_effective_date=date(2026, 12, 1),
            contract_text="Usage fees increase by five percent (5%).",
        ),
        m.CompanyPurchaseOrder(
            po_id="PO-DATAFORGE-2026",
            po_number="PO-2026-0101",
            vendor_id="VEN-DATAFORGE",
            contract_id="CON-DATAFORGE",
            status=e.POStatus.OPEN,
            order_type=e.OrderType.BLANKET,
            entity_id="ENT-001",
            cost_center="CC-DATA",
            po_owner_id="PROC-001",
            approved_total=Decimal("600000.00"),
            currency="USD",
            gl_account="610200",
            description="DataForge API consumption",
            line_items_json=[{"po_line_id": "PO-2026-0101-001", "item_category": "BLANKET_LIMIT"}],
        ),
    )
    add(
        m.CompanyServiceEvidence(
            service_evidence_id="USE-DATAFORGE-2026-12",
            vendor_id="VEN-DATAFORGE",
            po_id="PO-DATAFORGE-2026",
            service_start_date=date(2026, 12, 1),
            service_end_date=date(2026, 12, 31),
            evidence_type=e.ServiceEvidenceType.SYSTEM_USAGE,
            quantity=Decimal("10500000"),
            unit="API_CALL",
            source_system=e.SourceSystem.ENGINEERING_PLATFORM,
            confirmation_status=e.ConfirmationStatus.SYSTEM_VERIFIED,
            created_at=NOW,
        ),
        m.CompanyAPInvoice(
            invoice_id="INV-DATAFORGE-2026-12",
            vendor_id="VEN-DATAFORGE",
            invoice_number="DF-2027-001",
            invoice_date=date(2027, 1, 3),
            received_at=datetime(2027, 1, 4, 9, 0, tzinfo=UTC),
            amount=Decimal("55125.00"),
            currency="USD",
            po_id="PO-DATAFORGE-2026",
            status=e.APInvoiceStatus.IN_QUEUE,
            description="December 2026 API consumption",
            created_at=NOW,
            updated_at=NOW,
        ),
        make_obligation(),
    )
    add(
        m.TrueUpWorkpaper(
            workpaper_id="WP-DATAFORGE-2026-12",
            obligation_id="OBL-DATAFORGE-2026-12",
            period="2026-12",
            estimation_method=e.EstimationMethod.USAGE_TIMES_RATE,
            proposed_amount=Decimal("52500.00"),
            currency="USD",
            calculation_expression="10500000 * 0.005",
            calculation_inputs_json={"usage": "10500000", "rate": "0.005"},
            expense_account="610200",
            accrual_liability_account="210100",
            cost_center="CC-DATA",
            status=e.WorkpaperStatus.DRAFT,
            policy_decision=e.PolicyDecision.NOT_RUN,
            policy_summary="",
            journal_entry_json={},
            created_by_agent="EstimationAgent",
            created_at=NOW,
            updated_at=NOW,
        ),
        make_gl_entry(),
    )
    add(
        m.TrueUpEvidence(
            evidence_id="EVD-0001",
            obligation_id="OBL-DATAFORGE-2026-12",
            evidence_type=e.EvidenceCardType.SERVICE_USAGE,
            source_table="company_service_evidence",
            source_id="USE-DATAFORGE-2026-12",
            fact="VERIFIED_USAGE",
            value_json={"quantity": "10500000", "unit": "API_CALL"},
            confidence=Decimal("0.99"),
            status=e.EvidenceCardStatus.VERIFIED,
            created_by_agent="EvidenceAgent",
            created_at=NOW,
        ),
        m.TrueUpLearningRule(
            learning_id="LRN-0001",
            obligation_id="OBL-DATAFORGE-2026-12",
            workpaper_id="WP-DATAFORGE-2026-12",
            invoice_id="INV-DATAFORGE-2026-12",
            actual_amount=Decimal("55125.00"),
            accrual_amount=Decimal("52500.00"),
            variance_amount=Decimal("2625.00"),
            variance_percent=Decimal("5.00"),
            root_cause=e.RootCause.MISSED_ESCALATOR,
            root_cause_summary="Escalator effective 2026-12-01 was not applied.",
            status=e.LearningStatus.DIAGNOSED,
            created_at=NOW,
            updated_at=NOW,
        ),
        m.CompanyNonPOSpend(
            non_po_spend_id="NPO-0001",
            transaction_date=date(2026, 12, 12),
            month="2026-12",
            merchant_name="OfficeMart",
            spend_source=e.SpendSource.CORPORATE_CARD,
            cost_center="CC-OPS",
            gl_account="610400",
            amount=Decimal("-100.00"),
            currency="USD",
            transaction_status=e.TransactionStatus.SETTLED,
            description="Returned chair mat",
            created_at=NOW,
            updated_at=NOW,
        ),
        m.CompanyConfig(
            config_key="approval_thresholds",
            config_value_json={"controller_review_above_usd": 25000},
            updated_at=NOW,
        ),
    )
    AgentRunLog(session).append(
        agent_name="EstimationAgent",
        action="ESTIMATE",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary="Used verified usage times the contract rate.",
        output_summary="Drafted workpaper WP-DATAFORGE-2026-12",
        at=NOW,
        obligation_id="OBL-DATAFORGE-2026-12",
        workpaper_id="WP-DATAFORGE-2026-12",
        facts_used=["EVD-0001"],
        input_record_ids=["EVD-0001"],
        output_record_ids=["WP-DATAFORGE-2026-12"],
    )
    session.commit()
    return session
