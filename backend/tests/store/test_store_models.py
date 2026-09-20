from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from trueup.store import enums as e
from trueup.store import models as m

PRIMARY_KEYS = {
    m.CompanyVendor: "VEN-DATAFORGE",
    m.CompanyContract: "CON-DATAFORGE-V1",
    m.CompanyPurchaseOrder: "PO-DATAFORGE-2026",
    m.CompanyServiceEvidence: "USE-DATAFORGE-2026-12",
    m.CompanyNonPOSpend: "NPO-0001",
    m.CompanyAPInvoice: "INV-DATAFORGE-2026-12",
    m.CompanyGLEntry: "GL-ACCRUAL-DATAFORGE-2026-12",
    m.CompanyConfig: "approval_thresholds",
    m.TrueUpObligation: "OBL-DATAFORGE-2026-12",
    m.TrueUpEvidence: "EVD-0001",
    m.TrueUpWorkpaper: "WP-DATAFORGE-2026-12",
    m.TrueUpAgentRun: "RUN-000001",
    m.TrueUpLearningRule: "LRN-0001",
}


def test_every_table_has_a_row_in_the_fixture():
    assert set(PRIMARY_KEYS) == {mapper.class_ for mapper in m.Base.registry.mappers}


@pytest.mark.parametrize("model", list(PRIMARY_KEYS), ids=lambda model: model.__tablename__)
def test_every_table_round_trips_one_row(one_of_each, model):
    one_of_each.expire_all()
    assert one_of_each.get(model, PRIMARY_KEYS[model]) is not None


def test_decimals_dates_and_json_survive_a_round_trip(one_of_each):
    one_of_each.expire_all()
    contract = one_of_each.get(m.CompanyContract, "CON-DATAFORGE-V1")
    assert contract.base_rate == Decimal("0.005")
    assert contract.escalator_effective_date == date(2026, 12, 1)
    assert contract.rate_unit is e.RateUnit.API_CALL

    invoice = one_of_each.get(m.CompanyAPInvoice, "INV-DATAFORGE-2026-12")
    assert invoice.amount == Decimal("55125.00")
    assert invoice.received_at == datetime(2027, 1, 4, 9, 0, tzinfo=UTC)
    assert invoice.duplicate_flag is False
    assert invoice.line_items_json is None

    workpaper = one_of_each.get(m.TrueUpWorkpaper, "WP-DATAFORGE-2026-12")
    assert workpaper.calculation_inputs_json == {"usage": "10500000", "rate": "0.005"}
    assert workpaper.controller_decision is None

    spend = one_of_each.get(m.CompanyNonPOSpend, "NPO-0001")
    assert spend.amount == Decimal("-100.00")
    assert spend.is_accrued is False


def test_child_row_needs_an_existing_vendor_by_commit(store_session):
    store_session.add(
        m.CompanyContract(
            contract_row_id="X-V1",
            contract_id="X",
            contract_version=1,
            vendor_id="VEN-MISSING",
            contract_name="Orphan",
            status=e.ContractStatus.ACTIVE,
            effective_start_date=date(2026, 1, 1),
            billing_model=e.BillingModel.FIXED_FEE,
            billing_frequency=e.BillingFrequency.MONTHLY_IN_ARREARS,
            contract_text="",
        )
    )
    with pytest.raises(IntegrityError):
        store_session.commit()
    store_session.rollback()


def test_rows_can_be_added_in_any_order_within_one_transaction(store_session):
    store_session.add(
        m.CompanyContract(
            contract_row_id="Y-V1",
            contract_id="Y",
            contract_version=1,
            vendor_id="VEN-LATE",
            contract_name="Child first",
            status=e.ContractStatus.ACTIVE,
            effective_start_date=date(2026, 1, 1),
            billing_model=e.BillingModel.FIXED_FEE,
            billing_frequency=e.BillingFrequency.MONTHLY_IN_ARREARS,
            contract_text="",
        )
    )
    store_session.flush()
    store_session.add(
        m.CompanyVendor(
            vendor_id="VEN-LATE",
            vendor_name="Late Vendor",
            vendor_category=e.VendorCategory.OTHER,
            billing_cadence=e.BillingCadence.AD_HOC,
            default_currency="USD",
        )
    )
    store_session.commit()
    assert store_session.get(m.CompanyContract, "Y-V1").vendor_id == "VEN-LATE"


def test_contract_versions_are_unique_per_contract(one_of_each):
    one_of_each.add(
        m.CompanyContract(
            contract_row_id="CON-DATAFORGE-V1-DUP",
            contract_id="CON-DATAFORGE",
            contract_version=1,
            vendor_id="VEN-DATAFORGE",
            contract_name="Duplicate version",
            status=e.ContractStatus.SUPERSEDED,
            effective_start_date=date(2026, 1, 1),
            billing_model=e.BillingModel.USAGE_BASED,
            billing_frequency=e.BillingFrequency.VARIABLE,
            contract_text="",
        )
    )
    with pytest.raises(IntegrityError):
        one_of_each.flush()
    one_of_each.rollback()
