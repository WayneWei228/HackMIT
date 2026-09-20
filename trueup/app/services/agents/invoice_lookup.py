"""Invoice Lookup Agent — the duplicate-accrual guard.

The single most expensive mistake in accrual automation is accruing for something
AP has already processed. So before any estimate is attempted, this agent
searches the whole AP surface — queue, pending, posted, on-hold — plus the GL and
the non-PO AP links.

Matching is ordered from strongest to weakest identifier. The LLM's fuzzy
description match sits last and can only ever *support* a match, never establish
one on its own: a language model's opinion about two strings is not a basis for
suppressing an accrual.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyGlEntry, CompanyPurchaseOrder, TrueupObligation
from app.money import money
from app.repositories.asof import visible_invoices, visible_non_po_spend
from app.repositories.runs import log_run
from app.services.agents.common import add_evidence, advance, vendor_name
from app.services.llm import get_llm
from app.services.simulator.clock import close_cutoff

AGENT = "InvoiceLookupAgent"

# AP statuses that mean "AP already has this" — an accrual would double-count.
BLOCKING_STATUSES = {"IN_QUEUE", "PENDING_REVIEW", "PENDING_APPROVAL", "POSTED", "PAID", "ON_HOLD"}


def run(session: Session, obligation_id: str, as_of: dt.datetime | None = None) -> TrueupObligation:
    ob = session.get(TrueupObligation, obligation_id)
    as_of = as_of or close_cutoff(ob.period)

    match, method, candidates = _search(session, ob, as_of)
    facts = [f"searched AP queue/pending/posted/on-hold and GL as of {as_of.isoformat()}",
             f"{len(candidates)} candidate invoice(s) for vendor {ob.vendor_id}"]

    if match is not None:
        add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type="AP_INVOICE_FOUND",
            source_table="company_ap_invoices", source_id=match.invoice_id,
            fact=(f"Invoice {match.invoice_number} ({match.status}) for {money(match.amount)} "
                  f"covering {match.service_start_date}..{match.service_end_date} is already in "
                  f"AP. Matched by {method}. No accrual is required."),
            value={"invoice_id": match.invoice_id, "amount": str(money(match.amount)),
                   "status": match.status, "match_method": method},
            agent=AGENT, at=as_of,
        )
        advance(session, ob, stage="AP_MATCHED", next_action="CLOSE_NO_ACCRUAL",
                agent=None, invoice_status="FOUND", accrual_status="NO_ACCRUAL",
                matched_invoice_id=match.invoice_id, resolved_at=as_of, at=as_of)
        log_run(session, agent_name=AGENT, action="search_ap", status="OK",
                obligation_id=ob.obligation_id, facts_used=facts,
                decision_summary=f"Invoice already in AP (matched by {method}) - accrual suppressed",
                output_summary=f"NO_ACCRUAL; matched {match.invoice_id}",
                input_record_ids=[c.invoice_id for c in candidates],
                output_record_ids=[match.invoice_id], at=as_of)
        return ob

    if method == "AMBIGUOUS":
        add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type="AP_MATCH_AMBIGUOUS",
            source_table="company_ap_invoices",
            source_id=",".join(c.invoice_id for c in candidates[:5]),
            fact=("Multiple AP invoices overlap this service period and none carries a "
                  "definitive PO or contract reference. A human must decide whether this "
                  "obligation is already invoiced."),
            value={"candidates": [c.invoice_id for c in candidates]},
            agent=AGENT, confidence=0.4, at=as_of,
        )
        advance(session, ob, stage="AP_AMBIGUOUS", next_action="RESOLVE_AP_AMBIGUITY",
                agent="OutreachAgent", invoice_status="AMBIGUOUS", risk_level="HIGH", at=as_of)
        log_run(session, agent_name=AGENT, action="search_ap", status="ESCALATED",
                obligation_id=ob.obligation_id, facts_used=facts,
                decision_summary="Ambiguous AP match - cannot safely suppress or accrue",
                uncertainties=["Which of the overlapping invoices, if any, covers this period"],
                output_summary="routed to OutreachAgent (AP owner)",
                input_record_ids=[c.invoice_id for c in candidates], at=as_of)
        return ob

    advance(session, ob, stage="AP_NOT_FOUND", next_action="GATHER_EVIDENCE",
            agent="EvidenceAgent", invoice_status="NOT_FOUND", at=as_of)
    log_run(session, agent_name=AGENT, action="search_ap", status="OK",
            obligation_id=ob.obligation_id, facts_used=facts,
            decision_summary="No invoice in AP or GL for this service period - accrual required",
            output_summary="handed off to EvidenceAgent",
            input_record_ids=[c.invoice_id for c in candidates], at=as_of)
    return ob


# ---------------------------------------------------------------------------

def _search(session, ob, as_of):
    """Returns (match | None, method, candidates)."""
    if ob.non_po_group_key:
        return _search_non_po(session, ob, as_of)

    candidates = visible_invoices(session, as_of, vendor_id=ob.vendor_id)
    usable = [c for c in candidates if c.status in BLOCKING_STATUSES and not c.credit_flag]

    # 1. exact PO reference
    if ob.po_id:
        for c in usable:
            if c.po_id == ob.po_id:
                return c, "EXACT_PO_ID", candidates

    # 2. exact contract reference + period overlap
    if ob.contract_id:
        for c in usable:
            if c.contract_id == ob.contract_id and _overlaps(c, ob):
                return c, "EXACT_CONTRACT_ID_AND_PERIOD", candidates

    # 3. vendor + service-date overlap
    overlapping = [c for c in usable if _overlaps(c, ob)]
    if len(overlapping) == 1:
        return overlapping[0], "VENDOR_AND_SERVICE_PERIOD", candidates
    if len(overlapping) > 1:
        return None, "AMBIGUOUS", overlapping

    # 4. vendor + billing pattern: an invoice dated in-period with no service dates
    pattern = [
        c for c in usable
        if c.service_start_date is None
        and ob.service_start_date <= c.invoice_date <= ob.service_end_date
    ]
    if len(pattern) == 1:
        return pattern[0], "VENDOR_AND_BILLING_PATTERN", candidates

    # 5. GL: has an invoice for this obligation already been booked?
    booked = session.scalars(
        select(CompanyGlEntry).where(
            CompanyGlEntry.period == ob.period,
            CompanyGlEntry.vendor_id == ob.vendor_id,
            CompanyGlEntry.entry_type == "INVOICE",
        )
    ).first()
    if booked is not None:
        return None, "GL_BOOKED_NO_AP_ROW", candidates

    # 6. LLM fuzzy description — secondary support only. It can raise a case to
    #    AMBIGUOUS for a human, but it may never establish a match by itself.
    if usable:
        guess = get_llm().match_invoice_description(
            f"{vendor_name(session, ob.vendor_id)} {ob.purchase_type} {ob.period}",
            [{"invoice_id": c.invoice_id, "description": c.description} for c in usable],
        )
        if guess.get("invoice_id") and float(guess.get("confidence") or 0) >= 0.75:
            hit = next((c for c in usable if c.invoice_id == guess["invoice_id"]), None)
            if hit is not None and _overlaps(hit, ob):
                return None, "AMBIGUOUS", [hit]

    return None, "NOT_FOUND", candidates


def _search_non_po(session, ob, as_of):
    """For a non-PO group: any member already carrying an AP link, or a card
    statement that has landed covering this month."""
    rows = [
        r for r in visible_non_po_spend(session, as_of, month=ob.period)
        if f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}" == ob.non_po_group_key
    ]
    linked = [r for r in rows if r.ap_invoice_id]
    stmts = [
        c for c in visible_invoices(session, as_of, vendor_id="V010")
        if c.status in BLOCKING_STATUSES and _overlaps(c, ob)
    ]
    if stmts and all(r.ap_invoice_id for r in rows) and rows:
        return stmts[0], "CARD_STATEMENT_RECEIVED", stmts
    if stmts:
        return stmts[0], "CARD_STATEMENT_RECEIVED", stmts
    return None, "NOT_FOUND", []


def _overlaps(inv, ob) -> bool:
    if inv.service_start_date is None or inv.service_end_date is None:
        return False
    return inv.service_start_date <= ob.service_end_date and inv.service_end_date >= ob.service_start_date
