from trueup.db import POLine, get_session
from trueup.estimators import models


def test_mintlify_uses_effective_contract_rate_and_flags_stale_po(world):
    with get_session(world) as s:
        line = s.get(POLine, "PO-2026-1001-001")
        est = models.fixed_contract(s, line, "V-MINT", "2026-11")
        before = models.fixed_contract(s, line, "V-MINT", "2026-06")
    assert est.amount_cents == 140_000 and "po_contract_mismatch" in est.flags
    assert before.amount_cents == 120_000 and not before.flags


def test_asus_accrues_only_received_laptops(world):
    with get_session(world) as s:
        est = models.received_qty(s.get(POLine, "PO-2026-1003-001"))
    assert est.amount_cents == 20 * 160_000 == 3_200_000


def test_meta_accrues_delivered_not_budget(world):
    with get_session(world) as s:
        est = models.received_qty(s.get(POLine, "PO-2026-1004-001"))
    assert est.amount_cents == 24_700 * 100


def test_run_rate_uses_last_three_invoices_then_needs_outreach_without_history(world, engine):
    with get_session(world) as s:
        line = s.get(POLine, "PO-2026-1002-001")
        est = models.run_rate(s, line, "V-OAI", "PO-2026-1002", "2026-11")
        assert est.amount_cents and est.inputs["window"] == 3
        none = models.run_rate(s, line, "V-OAI", "PO-2026-1002", "2026-01")
        assert none.amount_cents is None and none.missing
        forced = models.run_rate(s, line, "V-OAI", "PO-2026-1002", "2026-01", force=True)
        assert forced.amount_cents == line.unit_price_cents and "forced" in forced.flags
