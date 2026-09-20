"""Journal Entry Service — simulated posting.

Simulated, and labelled as such everywhere: status is POSTED_SIMULATED, and the
company policy flag `simulated_posting_only` stays true. TrueUp prepares and
records entries; it does not claim to write to a production ERP.

No LLM touches this file. Amounts and balancing are arithmetic.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CompanyGlEntry,
    CompanyNonPoSpend,
    TrueupObligation,
    TrueupWorkpaper,
)
from app.money import ZERO, jsonable, money
from app.repositories.ids import stable_id
from app.repositories.runs import log_run
from app.services.agents.common import advance, config
from app.services.simulator.clock import close_cutoff, posting_date

AGENT = "JournalEntryService"


class PostingRefused(RuntimeError):
    pass


def post(session: Session, workpaper_id: str, as_of: dt.datetime | None = None) -> CompanyGlEntry:
    wp = session.get(TrueupWorkpaper, workpaper_id)
    ob = session.get(TrueupObligation, wp.obligation_id)
    as_of = as_of or close_cutoff(ob.period)

    _validate(session, wp, ob)

    je = wp.journal_entry_json or {}
    entry_id = stable_id("GL", wp.workpaper_id, "ACCRUAL")

    existing = session.get(CompanyGlEntry, entry_id)
    if existing is not None and existing.status == "POSTED_SIMULATED":
        raise PostingRefused(f"accrual already posted as {entry_id}")

    entry = CompanyGlEntry(
        gl_entry_id=entry_id, period=ob.period, posting_date=posting_date(ob.period),
        vendor_id=ob.vendor_id, obligation_id=ob.obligation_id, entry_type="ACCRUAL",
        status="POSTED_SIMULATED", description=je.get("description", ""),
        lines_json=jsonable(je.get("lines", [])), source_workpaper_id=wp.workpaper_id,
        reversal_of_gl_entry_id=None, created_at=as_of,
    )
    session.merge(entry)

    wp.status = "POSTED"
    wp.updated_at = as_of
    advance(session, ob, stage="POSTED", next_action="AWAIT_ACTUAL_INVOICE",
            agent="ReconciliationAndTrueUpAgent", accrual_status="POSTED", at=as_of)

    marked = _mark_non_po_accrued(session, ob, entry_id, as_of)
    session.flush()

    log_run(session, agent_name=AGENT, action="post_accrual", status="OK",
            obligation_id=ob.obligation_id, workpaper_id=wp.workpaper_id,
            facts_used=[f"workpaper status {wp.status}", f"policy {wp.policy_decision}",
                        f"controller {wp.controller_decision or 'n/a'}"],
            decision_summary=f"Simulated accrual entry {entry_id} for {money(wp.proposed_amount)} "
                             f"{wp.currency}",
            output_summary=f"debit {wp.expense_account} / credit {wp.accrual_liability_account}"
                           + (f"; {marked} non-PO transaction(s) flagged accrued" if marked else ""),
            input_record_ids=[wp.workpaper_id], output_record_ids=[entry_id], at=as_of)
    return entry


def _validate(session, wp: TrueupWorkpaper, ob: TrueupObligation) -> None:
    if wp.status not in ("APPROVED", "PENDING_CONTROLLER", "POSTED"):
        raise PostingRefused(f"workpaper status {wp.status} is not postable")
    if wp.policy_decision == "BLOCK":
        raise PostingRefused("policy blocked this workpaper")
    if wp.policy_decision in ("REQUIRE_CONTROLLER", "REQUIRE_OUTREACH") and \
            wp.controller_decision not in ("APPROVED", "APPROVED_WITH_ADJUSTMENT"):
        raise PostingRefused(
            f"policy decision {wp.policy_decision} requires a Controller approval first"
        )
    periods = config(session, "accounting_periods")
    if periods.get(ob.period, {}).get("status") != "OPEN":
        raise PostingRefused(f"period {ob.period} is closed")

    lines = (wp.journal_entry_json or {}).get("lines") or []
    debits = sum(money(l.get("debit", 0)) for l in lines)
    credits = sum(money(l.get("credit", 0)) for l in lines)
    if not lines or debits != credits:
        raise PostingRefused(f"entry does not balance: debits {debits} != credits {credits}")
    if debits == ZERO:
        raise PostingRefused("refusing to post a zero-value entry")

    allowed = set(config(session, "allowed_gl_accounts").get("accounts", []))
    for l in lines:
        if l["account"] not in allowed:
            raise PostingRefused(f"account {l['account']} is not permitted")


def _mark_non_po_accrued(session, ob, entry_id, as_of) -> int:
    """Flag the individual card transactions, so next month's detection cannot
    pick them up a second time."""
    if not ob.non_po_group_key:
        return 0
    rows = session.scalars(
        select(CompanyNonPoSpend).where(CompanyNonPoSpend.month == ob.period)
    )
    n = 0
    for r in rows:
        key = f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}"
        if key != ob.non_po_group_key or r.ap_invoice_id or r.is_accrued:
            continue
        if r.transaction_status in ("VOIDED", "DISPUTED"):
            continue
        r.is_accrued = True
        r.gl_entry_id = entry_id
        r.updated_at = as_of
        n += 1
    return n


def post_true_up(
    session: Session,
    *,
    obligation_id: str,
    workpaper_id: str,
    period: str,
    vendor_id: str,
    amount,
    expense_account: str,
    liability_account: str,
    cost_center: str,
    description: str,
    at: dt.datetime,
) -> CompanyGlEntry:
    """The adjusting entry once the real invoice lands.

    A positive variance (actual > accrual) debits expense further; a negative one
    reverses part of the accrual. Either way it balances.
    """
    amount = money(amount)
    if amount >= ZERO:
        lines = [
            {"account": expense_account, "cost_center": cost_center,
             "debit": str(amount), "credit": str(ZERO), "memo": description},
            {"account": liability_account, "cost_center": cost_center,
             "debit": str(ZERO), "credit": str(amount), "memo": "True-up of under-accrual"},
        ]
    else:
        lines = [
            {"account": liability_account, "cost_center": cost_center,
             "debit": str(-amount), "credit": str(ZERO), "memo": "Reverse over-accrual"},
            {"account": expense_account, "cost_center": cost_center,
             "debit": str(ZERO), "credit": str(-amount), "memo": description},
        ]
    entry_id = stable_id("GL", workpaper_id, "TRUEUP")
    entry = CompanyGlEntry(
        gl_entry_id=entry_id, period=period, posting_date=at.date(), vendor_id=vendor_id,
        obligation_id=obligation_id, entry_type="TRUE_UP", status="POSTED_SIMULATED",
        description=description, lines_json=jsonable(lines),
        source_workpaper_id=workpaper_id, reversal_of_gl_entry_id=None, created_at=at,
    )
    session.merge(entry)
    session.flush()
    return entry
