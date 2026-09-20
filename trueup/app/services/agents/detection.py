"""Detection Agent — opens the cases.

Input: a close period. Output: one obligation per thing that might need accruing.

Detection is deliberately generous: it is cheaper to open a case and close it as
NO_ACCRUAL once Invoice Lookup finds the invoice than to never notice the
obligation at all. An accrual you never considered is invisible; one you
considered and dismissed is on the record.

Idempotent — re-running a period reuses the same content-addressed obligation ids
rather than creating duplicates.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CompanyContract,
    CompanyPurchaseOrder,
    TrueupObligation,
)
from app.money import money, rate
from app.repositories.asof import eligible_non_po_spend
from app.repositories.ids import stable_id
from app.repositories.runs import log_run
from app.services.agents.common import add_evidence, vendor_name
from app.services.simulator.clock import close_cutoff, period_dates

AGENT = "DetectionAgent"


def run(session: Session, period: str, as_of: dt.datetime | None = None) -> list[TrueupObligation]:
    as_of = as_of or close_cutoff(period)
    start, end = period_dates(period)
    opened: list[TrueupObligation] = []

    opened += _detect_contract_obligations(session, period, start, end, as_of)
    opened += _detect_po_obligations(session, period, start, end, as_of)
    opened += _detect_non_po_obligations(session, period, start, end, as_of)

    session.flush()
    log_run(
        session, agent_name=AGENT, action="detect_period", status="OK",
        decision_summary=f"Scanned contracts, purchase orders and non-PO spend for {period} "
                         f"as of {as_of.isoformat()}",
        output_summary=f"{len(opened)} obligation(s) open for {period}",
        output_record_ids=[o.obligation_id for o in opened],
        at=as_of,
    )
    return opened


# ---------------------------------------------------------------------------

def _upsert(session, *, obligation_id, vendor_id, period, start, end, purchase_type,
            contract_id=None, po_id=None, non_po_group_key=None, as_of=None):
    ob = session.get(TrueupObligation, obligation_id)
    if ob:
        return ob, False
    ob = TrueupObligation(
        obligation_id=obligation_id, vendor_id=vendor_id, period=period,
        contract_id=contract_id, po_id=po_id, non_po_group_key=non_po_group_key,
        service_start_date=start, service_end_date=end, purchase_type=purchase_type,
        invoice_status="NOT_SEARCHED", evidence_status="PENDING",
        workflow_stage="DETECTED", next_action="SEARCH_AP",
        assigned_agent="InvoiceLookupAgent", accrual_status="NONE", risk_level="LOW",
        current_workpaper_id=None, matched_invoice_id=None,
        opened_at=as_of, updated_at=as_of, resolved_at=None,
    )
    session.add(ob)
    session.flush()
    return ob, True


def _detect_contract_obligations(session, period, start, end, as_of):
    """Any contract version whose effective window overlaps the period creates an
    expectation of service — and therefore a possible accrual."""
    out = []
    seen: set[str] = set()
    rows = session.scalars(select(CompanyContract))
    for c in rows:
        if c.effective_start_date > end:
            continue
        if c.effective_end_date is not None and c.effective_end_date < start:
            continue
        if c.contract_id in seen:
            continue
        # A per-order supply agreement carries pricing but creates no recurring
        # monthly obligation of its own — it is reached through its purchase
        # orders. Opening a case for it every month would be noise.
        if c.billing_model not in ("FIXED_RECURRING", "USAGE_BASED"):
            continue
        seen.add(c.contract_id)

        ptype = "FIXED_RECURRING" if c.billing_model == "FIXED_RECURRING" else "USAGE_BASED"
        ob_id = stable_id("OB", c.vendor_id, period, c.contract_id)
        ob, created = _upsert(
            session, obligation_id=ob_id, vendor_id=c.vendor_id, period=period,
            start=start, end=end, purchase_type=ptype, contract_id=c.contract_id, as_of=as_of,
        )
        if created:
            add_evidence(
                session, obligation_id=ob_id, evidence_type="OBLIGATION_TRIGGER",
                source_table="company_contracts", source_id=c.contract_row_id,
                fact=(f"Contract {c.contract_id} v{c.contract_version} ({c.contract_name}) is "
                      f"effective {c.effective_start_date}..{c.effective_end_date} and overlaps "
                      f"service period {period}; a monthly obligation is expected."),
                value={"contract_id": c.contract_id, "version": c.contract_version,
                       "billing_model": c.billing_model},
                agent=AGENT, at=as_of,
            )
            out.append(ob)
    return out


def _detect_po_obligations(session, period, start, end, as_of):
    """Open/approved POs with quantity received but not billed, and milestone
    orders whose delivery window overlaps the period."""
    out = []
    for po in session.scalars(select(CompanyPurchaseOrder)):
        if po.status not in ("APPROVED", "OPEN", "PARTIALLY_RECEIVED"):
            continue
        if po.service_start_date and po.service_start_date > end:
            continue
        if po.service_end_date and po.service_end_date < start:
            continue

        lines = po.line_items_json or []
        unbilled = sum(
            max(rate(l.get("quantity_received", 0)) - rate(l.get("quantity_billed", 0)), 0)
            for l in lines
        )
        is_milestone = po.order_type == "MILESTONE"
        if unbilled <= 0 and not is_milestone:
            continue

        ptype = "MILESTONE_BASED" if is_milestone else "RECEIPT_BASED"
        ob_id = stable_id("OB", po.vendor_id, period, po.po_id)
        ob, created = _upsert(
            session, obligation_id=ob_id, vendor_id=po.vendor_id, period=period,
            start=start, end=end, purchase_type=ptype, po_id=po.po_id,
            contract_id=po.contract_id, as_of=as_of,
        )
        if created:
            add_evidence(
                session, obligation_id=ob_id, evidence_type="OBLIGATION_TRIGGER",
                source_table="company_purchase_orders", source_id=po.po_id,
                fact=(f"PO {po.po_number} is {po.status} with delivery window "
                      f"{po.service_start_date}..{po.service_end_date}. "
                      + (f"Unbilled received quantity = {unbilled}." if unbilled
                         else "Milestone/delivery-billed order pending acceptance.")),
                value={"po_id": po.po_id, "unbilled_quantity": str(unbilled),
                       "order_type": po.order_type,
                       "approved_total": str(money(po.approved_total))},
                agent=AGENT, at=as_of,
            )
            out.append(ob)
    return out


def _detect_non_po_obligations(session, period, start, end, as_of):
    """Group eligible non-PO spend by (period, spend source, cost centre, GL
    account) — the natural accrual unit, because that is the granularity the
    journal entry posts at."""
    out = []
    rows = eligible_non_po_spend(session, as_of, period)
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r.spend_source, r.cost_center, r.gl_account), []).append(r)

    for (source, cc, gl), members in sorted(groups.items()):
        group_key = f"{period}|{source}|{cc}|{gl}"
        ptype = "NON_PO_CARD_SPEND" if source in ("PCARD", "CORPORATE_CARD") else "NON_PO_DIRECT_SPEND"
        ob_id = stable_id("OB", "NONPO", period, group_key)
        total = money(sum(money(m.amount) for m in members))
        ob, created = _upsert(
            session, obligation_id=ob_id, vendor_id="V010", period=period,
            start=start, end=end, purchase_type=ptype, non_po_group_key=group_key, as_of=as_of,
        )
        if created:
            add_evidence(
                session, obligation_id=ob_id, evidence_type="OBLIGATION_TRIGGER",
                source_table="company_non_po_spend", source_id=group_key,
                fact=(f"{len(members)} eligible {source} transaction(s) in {period} for "
                      f"{cc}/{gl} totalling {total}, none linked to an AP invoice and none "
                      f"yet accrued."),
                value={"group_key": group_key, "transaction_count": len(members),
                       "gross_amount": str(total),
                       "transaction_ids": [m.non_po_spend_id for m in members]},
                agent=AGENT, at=as_of,
            )
            out.append(ob)
    return out
