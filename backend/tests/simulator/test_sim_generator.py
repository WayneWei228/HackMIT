import json
from decimal import Decimal

import pytest

from trueup.simulator import generator, validators
from trueup.simulator.fixtures import close_cutoff, utc
from trueup.simulator.scenario_models import PRIMARY_KEYS, TABLE_MODELS

D = Decimal
CAST = {"Mintlify", "OpenAI", "ASUS", "Meta", "Notability"}


def truth(world, period, vendor_id, scenario=None):
    rows = [
        t
        for t in world.truth
        if t.period == period
        and t.vendor_id == vendor_id
        and (scenario is None or t.scenario == scenario)
    ]
    assert len(rows) == 1, rows
    return rows[0]


def final(world):
    return validators.snapshot(world)


def at_close(world, period):
    return validators.snapshot(world, close_cutoff(period))


def static_by_id(rows, attribute):
    return {getattr(row, attribute): row for row in rows}


def test_same_seed_is_byte_identical():
    first = generator.render_files(generator.generate(42))
    second = generator.render_files(generator.generate(42))
    assert first == second


def test_different_seed_changes_variation_but_not_pinned_numbers(sim_world):
    other = generator.generate(7)
    assert generator.render_files(other) != generator.render_files(sim_world)
    varying = truth(sim_world, "2026-10", "VEN-OPENAI").expected_actual_amount
    assert truth(other, "2026-10", "VEN-OPENAI").expected_actual_amount != varying
    for world in (sim_world, other):
        assert truth(world, "2026-12", "VEN-OPENAI").expected_actual_amount == D("18600.00")
        assert truth(world, "2026-12", "VEN-MINTLIFY").expected_actual_amount == D("1400.00")
        assert truth(world, "2026-12", "VEN-ASUS").expected_actual_amount == D("32000.00")
        meta = truth(world, "2026-12", "VEN-META")
        assert (meta.expected_baseline_accrual, meta.expected_actual_amount) == (
            D("24700.00"),
            D("30000.00"),
        )


def test_emitted_json_has_no_floats():
    def refuse(text):
        raise AssertionError(f"float in fixture JSON: {text}")

    for text in generator.render_files(generator.generate(42)).values():
        json.loads(text, parse_float=refuse)


def test_cast_is_exactly_the_five_vendors_and_events_stay_small(sim_world):
    names = {v.vendor_name for v in sim_world.static.company_vendors}
    assert names == CAST
    assert len(sim_world.events) <= 30
    assert not sim_world.static.company_non_po_spend
    assert not [e for e in sim_world.events if e.table == "company_non_po_spend"]


def test_day_one_is_rich_and_holds_no_future_records(sim_world):
    static = sim_world.static
    total = sum(len(getattr(static, table)) for table in TABLE_MODELS)
    assert 40 <= total <= 60
    start = generator.SIM_START
    assert static.company_ap_invoices and static.company_service_evidence
    assert all(inv.received_at <= start for inv in static.company_ap_invoices)
    assert all(row.created_at <= start for row in static.company_service_evidence)
    visible = validators.snapshot(sim_world, start)
    assert set(visible["company_ap_invoices"]) == {i.invoice_id for i in static.company_ap_invoices}
    assert "INV-OPENAI-2026-12" not in visible["company_ap_invoices"]


def test_events_are_ordered_unique_and_start_after_the_clock(sim_world):
    keys = [(e.available_at, e.event_id) for e in sim_world.events]
    assert keys == sorted(keys)
    assert len({e.event_id for e in sim_world.events}) == len(keys)
    assert keys[0][0] >= generator.SIM_START
    for table, pk in PRIMARY_KEYS.items():
        assert pk in validators.TABLE_MODELS[table].model_fields


def test_mintlify_amendment_is_in_force_on_day_one_and_po_is_stale(sim_world):
    contracts = static_by_id(sim_world.static.company_contracts, "contract_row_id")
    v1, v2 = contracts["CON-MINTLIFY-V1"], contracts["CON-MINTLIFY-V2"]
    assert (v1.base_rate, v1.status, v1.effective_end_date.isoformat()) == (
        D("1200.00"),
        "SUPERSEDED",
        "2026-11-30",
    )
    assert (v2.base_rate, v2.status, v2.effective_start_date.isoformat()) == (
        D("1400.00"),
        "ACTIVE",
        "2026-12-01",
    )
    assert "from $1,200 to $1,400 per month" in v2.contract_text
    po = static_by_id(sim_world.static.company_purchase_orders, "po_id")["PO-MINTLIFY-2026"]
    assert po.line_items_json[0].unit_price == D("1200.00")
    invoices = static_by_id(sim_world.static.company_ap_invoices, "invoice_id")
    for period in ("2026-09", "2026-10", "2026-11"):
        assert invoices[f"INV-MINTLIFY-{period}"].amount == D("1200.00")
    assert {"GL-MINTLIFY-2026-11-ACCRUAL", "GL-MINTLIFY-2026-11-ACCRUAL-REV"} <= {
        e.gl_entry_id for e in sim_world.static.company_gl_entries
    }
    dec = truth(sim_world, "2026-12", "VEN-MINTLIFY")
    assert (dec.expected_actual_amount, dec.expected_baseline_accrual) == (
        D("1400.00"),
        D("1400.00"),
    )
    assert (dec.expected_root_cause, dec.expected_close_status) == (None, "DONE")


def test_openai_history_already_contains_a_missed_escalator(sim_world):
    contract = static_by_id(sim_world.static.company_contracts, "contract_id")["CON-OPENAI"]
    stale = contract.base_rate
    step_up = stale * (100 + contract.escalator_percent) / 100
    assert (stale, step_up) == (D("0.016"), D("0.02"))
    assert contract.escalator_effective_date.isoformat() == "2026-09-01"
    accruals = static_by_id(sim_world.static.company_gl_entries, "gl_entry_id")
    for period in ("2026-10", "2026-11"):
        row = truth(sim_world, period, "VEN-OPENAI")
        assert row.expected_root_cause == "MISSED_ESCALATOR"
        assert row.expected_actual_amount == row.expected_baseline_accrual * D("1.25")
        booked = accruals[f"GL-OPENAI-{period}-ACCRUAL"].lines_json[0].debit
        assert booked == row.expected_baseline_accrual
        assert row.invoice_arrival_time > close_cutoff(period)
        assert row.invoice_arrival_time <= generator.SIM_START
    assert not [t for t in sim_world.truth if t.vendor_id == "VEN-OPENAI" and t.period == "2026-09"]
    evidence = {e.service_evidence_id for e in sim_world.static.company_service_evidence}
    assert evidence == {f"USE-OPENAI-{p}" for p in ("2026-09", "2026-10", "2026-11")}


def test_openai_december_is_incomplete_until_the_owner_replies(sim_world):
    close = at_close(sim_world, "2026-12")["company_service_evidence"]
    partial = close["USE-OPENAI-2026-12-PARTIAL"]
    assert (partial["quantity"], partial["confirmation_status"]) == ("576000", "PENDING")
    assert partial["service_end_date"] == "2026-12-19"
    assert "USE-OPENAI-2026-12-CONFIRMED" not in close
    reply = next(
        o for o in sim_world.outreach if o.outreach_key == "OPENAI-2026-12-USAGE_CONFIRMATION"
    )
    assert reply.recipient_role == "SERVICE_OWNER"
    assert reply.parsed_truth == {
        "resolved": True,
        "service_received": True,
        "quantity": "930000",
        "unit": "API_CALL",
    }
    assert reply.service_evidence_on_response.quantity == D("930000")
    assert reply.available_at > close_cutoff("2026-12")
    dec = truth(sim_world, "2026-12", "VEN-OPENAI")
    assert D(930_000) * D("0.02") == dec.expected_actual_amount == D("18600.00")
    assert dec.expected_baseline_accrual == D(576_000) * D("0.02") == D("11520.00")
    assert (dec.expected_root_cause, dec.expected_close_status) == ("USAGE_VARIANCE", "WAITING")


def test_asus_partial_receipt_then_remainder(sim_world):
    po = static_by_id(sim_world.static.company_purchase_orders, "po_id")["PO-ASUS-2026"]
    line = po.line_items_json[0]
    assert (po.approved_total, line.quantity_ordered, line.unit_price) == (
        D("40000.00"),
        D(25),
        D("1600.00"),
    )
    assert (line.quantity_received, line.receipt_required, line.useful_life_months) == (0, True, 36)
    close = at_close(sim_world, "2026-12")
    receipt = close["company_service_evidence"]["USE-ASUS-2026-12-18"]
    assert (receipt["quantity"], receipt["accepted_amount"]) == ("20", "32000.00")
    posted = close["company_purchase_orders"]["PO-ASUS-2026"]["line_items_json"][0]
    assert (posted["quantity_received"], posted["quantity_billed"]) == ("20", "0")
    assert "INV-ASUS-2026-12" not in close["company_ap_invoices"]
    end = final(sim_world)["company_purchase_orders"]["PO-ASUS-2026"]["line_items_json"][0]
    assert (end["quantity_received"], end["quantity_billed"]) == ("25", "20")
    row = truth(sim_world, "2026-12", "VEN-ASUS")
    assert row.expected_actual_amount == D("32000.00") > D("25000")
    assert row.expected_close_status == "NEEDS_REVIEW"


def test_meta_delivered_amount_is_below_the_budget_and_the_invoice_is_wrong(sim_world):
    po = static_by_id(sim_world.static.company_purchase_orders, "po_id")["PO-META-2026"]
    assert po.approved_total == D("30000.00")
    evidence = at_close(sim_world, "2026-12")["company_service_evidence"]["USE-META-2026-12"]
    assert (evidence["evidence_type"], evidence["accepted_amount"]) == (
        "MILESTONE_ACCEPTANCE",
        "24700.00",
    )
    invoice = final(sim_world)["company_ap_invoices"]["INV-META-2026-12"]
    assert invoice["amount"] == "30000.00"
    row = truth(sim_world, "2026-12", "VEN-META")
    assert (row.expected_baseline_accrual, row.expected_root_cause, row.expected_close_status) == (
        D("24700.00"),
        "SOURCE_DATA_ERROR",
        "DONE",
    )


def test_notability_prepaid_and_wrong_treatment_are_on_day_one(sim_world):
    static = sim_world.static
    invoice = static_by_id(static.company_ap_invoices, "invoice_id")["INV-NOTABILITY-2026-12"]
    contract = static_by_id(static.company_contracts, "contract_id")["CON-NOTABILITY"]
    assert (invoice.amount, invoice.status) == (D("21600.00"), "PAID")
    assert (contract.effective_start_date.isoformat(), contract.effective_end_date.isoformat()) == (
        "2026-12-01",
        "2027-11-30",
    )
    monthly = invoice.amount / 12
    assert monthly == D("1800") == contract.base_rate
    assert invoice.amount - monthly == D("19800")
    entries = static_by_id(static.company_gl_entries, "gl_entry_id")
    wrong = entries["GL-NOTABILITY-2026-12-MANUAL"]
    assert wrong.entry_type == "MANUAL_ADJUSTMENT" and wrong.period == "2026-12"
    assert (wrong.lines_json[0].account_code, wrong.lines_json[0].debit) == (
        "610100",
        D("21600.00"),
    )
    assert entries["GL-NOTABILITY-2026-12"].lines_json[0].account_code == "150100"
    assert truth(sim_world, "2026-12", "VEN-NOTABILITY").expected_close_status == "NEEDS_REVIEW"


def test_the_close_statuses_are_all_demonstrated(sim_world):
    by_vendor = {
        t.vendor_id: t.expected_close_status for t in sim_world.truth if t.expected_close_status
    }
    assert by_vendor == {
        "VEN-MINTLIFY": "DONE",
        "VEN-OPENAI": "WAITING",
        "VEN-ASUS": "NEEDS_REVIEW",
        "VEN-META": "DONE",
        "VEN-NOTABILITY": "NEEDS_REVIEW",
    }


def test_outreach_fixtures_include_an_insufficient_reply(sim_world):
    keys = {o.outreach_key: o for o in sim_world.outreach}
    assert set(keys) == {
        "OPENAI-2026-12-USAGE_CONFIRMATION",
        "ASUS-2026-12-IN_SERVICE_DATE",
        "ASUS-2026-12-SERVICE_CONFIRMATION",
        "META-2026-12-INVOICE_DISPUTE",
    }
    weak = keys["ASUS-2026-12-IN_SERVICE_DATE"]
    assert weak.parsed_truth["resolved"] is False
    assert weak.service_evidence_on_response is None
    owner = keys["ASUS-2026-12-SERVICE_CONFIRMATION"]
    assert owner.parsed_truth == {
        "resolved": True,
        "service_received": True,
        "quantity": "20",
        "unit": "EACH",
    }
    record = owner.service_evidence_on_response
    assert record is not None and record.po_id == "PO-ASUS-2026-B"
    assert record.evidence_type == "MANUAL_CONFIRMATION"
    assert record.confirmation_status == "OWNER_CONFIRMED"
    assert record.quantity == 20 and record.created_at == owner.available_at


def test_period_layout(sim_world):
    meta = sim_world.static.meta
    assert meta["historical_periods"] == ["2026-09", "2026-10", "2026-11"]
    assert meta["live_periods"] == ["2026-12", "2027-01"]
    clock = next(c for c in sim_world.static.company_config if c.config_key == "simulation_clock")
    assert clock.config_value_json["current_time"] == "2026-12-01T08:00:00Z"
    periods = next(
        c for c in sim_world.static.company_config if c.config_key == "accounting_periods"
    ).config_value_json
    assert {p: periods[p]["status"] for p in periods} == {
        "2026-09": "CLOSED",
        "2026-10": "CLOSED",
        "2026-11": "CLOSED",
        "2026-12": "OPEN",
        "2027-01": "OPEN",
    }


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_generated_world_passes_every_validator(seed):
    validators.validate_all(generator.generate(seed))


def test_january_close_sees_invoices_revealed_after_december(sim_world):
    assert "INV-MINTLIFY-2026-12" not in at_close(sim_world, "2026-12")["company_ap_invoices"]
    assert (
        "INV-MINTLIFY-2026-12"
        in validators.snapshot(sim_world, utc(2027, 1, 5))["company_ap_invoices"]
    )
