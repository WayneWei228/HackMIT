from datetime import datetime
from decimal import Decimal

import pytest

from trueup.simulator import validators
from trueup.simulator.fixtures import utc
from trueup.simulator.scenario_models import APInvoiceRecord, ScenarioEvent


def event(world, event_id):
    return next(e for e in world.events if e.event_id == event_id)


def problems(fn, world):
    return "\n".join(fn(world))


def test_validate_all_raises_with_every_violation(corrupt):
    corrupt.static.company_contracts[0].vendor_id = "VEN-MISSING"
    corrupt.static.company_gl_entries[0].lines_json[0].debit += 1
    with pytest.raises(validators.WorldValidationError) as caught:
        validators.validate_all(corrupt)
    assert "VEN-MISSING" in str(caught.value) and "unbalanced" in str(caught.value)


def test_referential_catches_missing_vendor_person_and_config(corrupt):
    corrupt.static.company_contracts[0].vendor_id = "VEN-MISSING"
    corrupt.static.company_purchase_orders[0].po_owner_id = "NOBODY-9"
    corrupt.static.company_config = [
        c for c in corrupt.static.company_config if c.config_key != "policy_rules"
    ]
    found = problems(validators.validate_referential_integrity, corrupt)
    assert "unknown reference VEN-MISSING" in found
    assert "unknown reference NOBODY-9" in found
    assert "missing required key policy_rules" in found


def test_referential_catches_a_dangling_po_link_on_a_history_invoice(corrupt):
    corrupt.static.company_ap_invoices[0].po_id = "PO-NOPE"
    assert "PO-NOPE" in problems(validators.validate_referential_integrity, corrupt)


def test_accounting_catches_unbalanced_gl(corrupt):
    corrupt.static.company_gl_entries[0].lines_json[1].credit += 5
    assert "unbalanced" in problems(validators.validate_accounting_logic, corrupt)


def test_accounting_catches_an_invoice_that_disagrees_with_truth(corrupt):
    event(corrupt, "EVT-MINTLIFY-2027-01-INVOICE").record["amount"] = "1500.00"
    found = problems(validators.validate_accounting_logic, corrupt)
    assert "INV-MINTLIFY-2026-12" in found and "!= truth" in found


def test_accounting_catches_a_wrong_recomputed_usage_amount(corrupt):
    event(corrupt, "EVT-OPENAI-2027-01-INVOICE").record["amount"] = "18000.00"
    truth = next(t for t in corrupt.truth if t.invoice_id == "INV-OPENAI-2026-12")
    truth.expected_actual_amount = Decimal("18000.00")
    assert "recomputed" in problems(validators.validate_accounting_logic, corrupt)


def test_accounting_catches_a_wrong_escalated_rate_in_history(corrupt):
    truth = next(t for t in corrupt.truth if t.scenario == "escalator_history")
    truth.expected_baseline_accrual += 100
    assert "escalated amount" in problems(validators.validate_accounting_logic, corrupt)


def test_accounting_catches_a_mismatch_case_that_agrees_with_its_evidence(corrupt):
    event(corrupt, "EVT-META-2027-01-INVOICE").record["amount"] = "24700.00"
    truth = next(t for t in corrupt.truth if t.scenario == "wrong_invoice_amount")
    truth.expected_actual_amount = Decimal("24700.00")
    assert "mismatch case agrees" in problems(validators.validate_accounting_logic, corrupt)


def test_accounting_catches_a_po_invoiced_beyond_its_approved_total(corrupt):
    corrupt.static.company_purchase_orders[0].approved_total = Decimal("100.00")
    assert "exceeds approved" in problems(validators.validate_accounting_logic, corrupt)


def test_timeline_catches_a_future_invoice_in_static_data(corrupt):
    invoice = APInvoiceRecord.model_validate(event(corrupt, "EVT-MINTLIFY-2027-01-INVOICE").record)
    corrupt.static.company_ap_invoices.append(invoice)
    found = problems(validators.validate_timeline, corrupt)
    assert "future-dated rows in company_ap_invoices" in found
    assert "duplicates" in found


def test_timeline_catches_future_evidence_in_static_data(corrupt):
    corrupt.static.company_service_evidence[0].created_at = utc(2026, 12, 2, 10)
    found = problems(validators.validate_timeline, corrupt)
    assert "future-dated rows in company_service_evidence" in found


def test_timeline_catches_an_invoice_dated_before_service_ended(corrupt):
    event(corrupt, "EVT-MINTLIFY-2027-01-INVOICE").record["invoice_date"] = "2026-12-15"
    assert "dated before its service ended" in problems(validators.validate_timeline, corrupt)


def test_timeline_catches_an_invoice_that_arrives_before_close(corrupt):
    invoice = event(corrupt, "EVT-MINTLIFY-2027-01-INVOICE")
    early = "2026-12-20T09:00:00Z"
    invoice.record["received_at"] = invoice.record["created_at"] = early
    invoice.record["invoice_date"] = "2026-12-31"
    invoice.available_at = datetime.fromisoformat(early)
    found = problems(validators.validate_timeline, corrupt)
    assert "arrives before close" in found
    assert "is visible at close" in found


def test_timeline_catches_double_application_and_orphan_updates(corrupt):
    corrupt.events.append(corrupt.events[0].model_copy(deep=True))
    orphan = event(corrupt, "EVT-MINTLIFY-2027-01-PENDING").model_copy(deep=True)
    orphan.event_id = "EVT-ORPHAN"
    orphan.key = {"invoice_id": "INV-DOES-NOT-EXIST"}
    corrupt.events.append(orphan)
    found = problems(validators.validate_timeline, corrupt)
    assert "duplicate event id" in found
    assert "does not exist yet" in found


def test_timeline_catches_a_contract_version_that_appears_late(corrupt):
    record = corrupt.static.company_contracts[1].model_dump(mode="json")
    record.update(contract_row_id="CON-MINTLIFY-V3", contract_version=3)
    corrupt.events.append(
        ScenarioEvent(
            event_id="EVT-LATE-CONTRACT",
            available_at=utc(2026, 12, 2, 10),
            operation="INSERT",
            table="company_contracts",
            record=record,
        )
    )
    assert "appears after it is usable" in problems(validators.validate_timeline, corrupt)


def test_timeline_catches_missing_service_evidence_at_close(corrupt):
    corrupt.events = [e for e in corrupt.events if e.event_id != "EVT-OPENAI-2026-12-USAGE-PARTIAL"]
    assert "no service evidence available by close" in problems(
        validators.validate_timeline, corrupt
    )


def test_coverage_catches_missing_scenarios(corrupt):
    corrupt.truth = [
        t
        for t in corrupt.truth
        if t.scenario not in ("wrong_invoice_amount", "prepaid_wrong_treatment")
    ]
    corrupt.outreach = [o for o in corrupt.outreach if o.parsed_truth.get("resolved") is not False]
    found = problems(validators.validate_scenario_coverage, corrupt)
    assert "wrong-amount invoice" in found
    assert "prepaid wrong treatment" in found
    assert "insufficient reply" in found


def test_coverage_catches_a_history_with_no_escalator_miss(corrupt):
    corrupt.truth = [t for t in corrupt.truth if t.expected_root_cause != "MISSED_ESCALATOR"]
    assert "historical missed escalator" in problems(validators.validate_scenario_coverage, corrupt)


def test_coverage_catches_a_demo_that_misses_a_close_status(corrupt):
    for t in corrupt.truth:
        if t.expected_close_status == "NEEDS_REVIEW":
            t.expected_close_status = None
    assert "the close statuses" in problems(validators.validate_scenario_coverage, corrupt)


def test_clean_world_has_no_violations(sim_world):
    for fn in (
        validators.validate_referential_integrity,
        validators.validate_accounting_logic,
        validators.validate_timeline,
        validators.validate_scenario_coverage,
    ):
        assert fn(sim_world) == []
