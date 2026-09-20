from sqlalchemy import select

from trueup.agents import learning
from trueup.datagen import generator
from trueup.db import (
    AccrualEstimate,
    APInvoice,
    AuditLog,
    CloseItem,
    JELineRow,
    LearningEntry,
    OutreachRequest,
    ProposedJERow,
    get_session,
)
from trueup.orchestrator import run_close


def test_november_close_end_to_end(world):
    result = run_close(world, "2026-11")
    assert result.counts == {"done": 4, "needs_review": 1}
    with get_session(world) as s:
        estimates = {e.model: e.amount_cents for e in s.scalars(select(AccrualEstimate))}
        assert estimates["received_qty"] in {3_200_000, 2_470_000}
        review = s.scalars(select(CloseItem).where(CloseItem.status == "needs_review")).one()
        assert review.vendor_id == "V-MINT"
        reasons = [r.reason for r in s.scalars(select(OutreachRequest))]
        assert reasons == ["po_contract_mismatch"]
        # every JE has evidence and balances exactly
        for je in s.scalars(select(ProposedJERow)):
            assert je.evidence_json
            lines = list(s.scalars(select(JELineRow).where(JELineRow.je_id == je.id)))
            assert sum(x.debit_cents for x in lines) == sum(x.credit_cents for x in lines)
        assert s.scalars(select(AuditLog).where(AuditLog.action == "close.completed")).one()


def test_dynamic_vendor_with_no_history_waits_then_forces(engine):
    generator.generate(engine, seed=42)
    result = run_close(engine, "2026-01")
    assert result.counts.get("waiting") == 1
    forced = run_close(engine, "2026-01", force=True)
    assert forced.counts.get("needs_review", 0) >= 1


def test_invoice_arrival_grades_the_estimate(world):
    run_close(world, "2026-11")
    ids = generator.release_invoices(world, "2026-12")  # service month 2026-11 invoices land
    with get_session(world) as s:
        entries = [learning.on_invoice_arrived(s, s.get(APInvoice, i)) for i in ids]
        graded = [e for e in entries if e is not None]
        # Mintlify matched its contract-based estimate exactly, so only OpenAI missed
        assert [e.cause for e in graded] == ["usage_higher_than_run_rate"]
        assert graded[0].delta_cents > 0
        assert s.scalars(select(LearningEntry)).one().status == "proposed"
