import pytest

from trueup.agents import learning
from trueup.db import (
    AccrualEstimate,
    APInvoice,
    CloseItem,
    Contract,
    LearningEntry,
    get_session,
)


def _estimate_and_invoice(session, model, est_cents, inv_cents, vendor="V-MINT", period="2026-07"):
    item = CloseItem(
        period=period, obligation_key="k", vendor_id=vendor, source="po", status="done"
    )
    session.add(item)
    session.flush()
    est = AccrualEstimate(
        period=period,
        close_item_id=item.id,
        model=model,
        amount_cents=est_cents,
        inputs_json={},
        reasoning="r",
    )
    inv = APInvoice(
        vendor_id=vendor,
        po_number="P",
        invoice_number="i",
        invoice_date="2026-08-03",
        service_period=period,
        amount_cents=inv_cents,
        arrived_period="2026-08",
    )
    session.add_all([est, inv])
    session.flush()
    return est, inv


def test_missed_price_change_is_diagnosed_from_the_contract(engine):
    with get_session(engine) as s:
        s.add(
            Contract(
                contract_id="CON-1-V2",
                vendor_id="V-MINT",
                monthly_rate_cents=140_000,
                effective_start="2026-07-01",
                effective_end="2026-12-31",
                status="Active",
                version=2,
            )
        )
        _, inv = _estimate_and_invoice(s, "run_rate", 120_000, 140_000)
        entry = learning.on_invoice_arrived(s, inv)
        assert entry.cause == "price_change" and entry.delta_cents == 20_000
        assert {e["source_table"] for e in entry.evidence_json} >= {"contracts", "ap_invoices"}


def test_exact_and_immaterial_estimates_create_no_lesson(engine):
    with get_session(engine) as s:
        _, inv = _estimate_and_invoice(s, "fixed_contract", 140_000, 140_050)
        assert learning.on_invoice_arrived(s, inv) is None


def test_invoice_with_no_estimate_is_an_undiscovered_obligation(engine):
    with get_session(engine) as s:
        inv = APInvoice(
            vendor_id="V-NEW",
            po_number=None,
            invoice_number="n",
            invoice_date="d",
            service_period="2026-07",
            amount_cents=50_000,
            arrived_period="2026-08",
        )
        s.add(inv)
        s.flush()
        assert learning.on_invoice_arrived(s, inv).cause == "undiscovered_obligation"


def test_replay_gate_blocks_a_lesson_that_worsens_an_old_estimate(engine):
    with get_session(engine) as s:
        _, inv = _estimate_and_invoice(s, "run_rate", 100, 90_000)
        entry = learning.on_invoice_arrived(s, inv)
        blocked = learning.promote(s, entry.id, {"a": 100, "b": 50}, {"a": 40, "b": 80})
        assert not blocked.promoted and blocked.flips == ["b: error 50 -> 80"]
        assert s.get(LearningEntry, entry.id).status == "rejected"


def test_passing_lesson_is_provisional_then_revocable_and_rendered(engine):
    with get_session(engine) as s:
        _, inv = _estimate_and_invoice(s, "run_rate", 100, 90_000)
        entry = learning.on_invoice_arrived(s, inv)
        assert learning.promote(s, entry.id, {"a": 100}, {"a": 40}).promoted
        assert entry.status == "provisional"
        assert "lesson" in learning.render_improvements_md(s)
        learning.revoke(s, entry.id, "contradicted by a later invoice")
        assert "No adopted lessons yet." in learning.render_improvements_md(s)
        with pytest.raises(ValueError):
            learning.promote(s, entry.id, {}, {})
