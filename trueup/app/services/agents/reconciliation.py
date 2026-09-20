"""Reconciliation and True-Up Agent — where the estimate gets graded.

This is the agent that makes TrueUp a learning system rather than a calculator.
When the real invoice arrives, it is compared against what was accrued, and the
difference is attributed to a cause using the evidence that was on the workpaper
at the time — not with hindsight, and not by asking a model to guess.

Root-cause attribution is deterministic. The LLM is invited afterwards to write
the explanation in English and to flag a contradiction, but the taxonomy label
that drives learning comes from arithmetic on recorded facts.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CompanyApInvoice,
    CompanyNonPoSpend,
    TrueupLearningRule,
    TrueupObligation,
    TrueupWorkpaper,
)
from app.money import ZERO, money, pct, rate
from app.repositories.ids import stable_id
from app.repositories.runs import log_run
from app.services import journal
from app.services.agents.common import add_evidence, advance, config, evidence_for
from app.services.llm import get_llm
from app.services.simulator.clock import period_dates

AGENT = "ReconciliationAndTrueUpAgent"

ROOT_CAUSES = (
    "MISSED_ESCALATOR", "USAGE_VARIANCE", "SCOPE_CHANGE", "TIMING_DIFFERENCE",
    "MULTI_PERIOD_INVOICE", "DUPLICATE_NON_PO_ACCRUAL", "SOURCE_DATA_ERROR", "UNKNOWN",
)


def run(session: Session, invoice_id: str, at: dt.datetime | None = None) -> list[TrueupLearningRule]:
    inv = session.get(CompanyApInvoice, invoice_id)
    at = at or inv.received_at
    matches = _match_to_accruals(session, inv)
    if not matches:
        log_run(session, agent_name=AGENT, action="reconcile", status="OK",
                decision_summary=f"Invoice {invoice_id} matches no posted accrual",
                output_summary="nothing to true up", input_record_ids=[invoice_id], at=at)
        return []

    out = []
    for ob, wp, allocated in matches:
        out.append(_true_up_one(session, inv, ob, wp, allocated, at))
    return out


# ---------------------------------------------------------------------------

def _match_to_accruals(session, inv) -> list[tuple]:
    """Find the posted accrual(s) this invoice settles, allocating the amount
    deterministically across periods when the invoice spans more than one."""
    stmt = select(TrueupObligation).where(
        TrueupObligation.vendor_id == inv.vendor_id,
        TrueupObligation.accrual_status == "POSTED",
    )
    cands = [o for o in session.scalars(stmt)]

    if inv.po_id:
        cands = [o for o in cands if o.po_id == inv.po_id] or \
                [o for o in cands if o.vendor_id == inv.vendor_id]
    elif inv.contract_id:
        cands = [o for o in cands if o.contract_id == inv.contract_id]

    s_start = inv.service_start_date or inv.invoice_date
    s_end = inv.service_end_date or inv.invoice_date
    overlapping = [
        o for o in cands
        if o.service_start_date <= s_end and o.service_end_date >= s_start
    ]
    if not overlapping:
        return []

    # A statement that itemises by accrual group is allocated by that key. Only
    # fall back to date-proportional allocation for a genuinely multi-period
    # invoice, where days are the meaningful basis.
    by_group = _allocate_by_group(session, inv, overlapping)
    if by_group is not None:
        return by_group

    total_days = sum(_overlap_days(o, s_start, s_end) for o in overlapping) or 1
    out = []
    running = ZERO
    for i, o in enumerate(sorted(overlapping, key=lambda x: x.period)):
        wp = session.get(TrueupWorkpaper, o.current_workpaper_id)
        if wp is None or wp.status not in ("POSTED",):
            continue
        if len(overlapping) == 1:
            share = money(inv.amount)
        elif i == len(overlapping) - 1:
            share = money(money(inv.amount) - running)   # last period absorbs rounding
        else:
            share = money(money(inv.amount) * Decimal(_overlap_days(o, s_start, s_end)) / Decimal(total_days))
            running += share
        out.append((o, wp, share))
    return out


def _allocate_by_group(session, inv, overlapping):
    """Split an itemised invoice across same-period accrual groups by its own
    line items, rather than pretending date overlap tells them apart."""
    lines = inv.line_items_json or []
    keyed = {l["group_key"]: money(l["amount"]) for l in lines if l.get("group_key")}
    if not keyed:
        return None
    out = []
    for o in overlapping:
        if not o.non_po_group_key or o.non_po_group_key not in keyed:
            continue
        wp = session.get(TrueupWorkpaper, o.current_workpaper_id)
        if wp is None or wp.status != "POSTED":
            continue
        out.append((o, wp, keyed[o.non_po_group_key]))
    return out or None


def _overlap_days(ob, s_start, s_end) -> int:
    start = max(ob.service_start_date, s_start)
    end = min(ob.service_end_date, s_end)
    return max((end - start).days + 1, 0)


def _true_up_one(session, inv, ob: TrueupObligation, wp: TrueupWorkpaper, actual, at):
    accrued = money(wp.proposed_amount)
    actual = money(actual)
    variance = money(actual - accrued)
    variance_pct = pct(variance, accrued)
    multi_period = bool(
        inv.service_start_date and inv.service_end_date
        and (inv.service_end_date - inv.service_start_date).days > 45
    )

    add_evidence(
        session, obligation_id=ob.obligation_id, evidence_type="ACTUAL_INVOICE",
        source_table="company_ap_invoices", source_id=inv.invoice_id,
        fact=(f"Invoice {inv.invoice_number} received {inv.received_at:%Y-%m-%d} for "
              f"{money(inv.amount)} covering {inv.service_start_date}..{inv.service_end_date}. "
              f"Allocated {actual} to {ob.period}. Accrued {accrued}. Variance {variance}."),
        value={"invoice_id": inv.invoice_id, "invoice_amount": str(money(inv.amount)),
               "allocated_to_period": str(actual), "accrued": str(accrued),
               "variance": str(variance), "variance_percent": str(variance_pct)
               if variance_pct is not None else None,
               "description": inv.description},
        agent=AGENT, at=at,
    )

    root_cause, summary, detail = _diagnose(session, ob, wp, inv, accrued, actual, variance, multi_period)

    # LLM writes the English; it does not pick the label.
    narrative = get_llm().diagnose_variance({
        "deterministic_root_cause": root_cause,
        "deterministic_summary": summary,
        "accrued": str(accrued), "actual": str(actual), "variance": str(variance),
        "workpaper_expression": wp.calculation_expression,
        "invoice_description": inv.description,
    })

    thresholds = config(session, "approval_thresholds")
    material = (abs(variance) >= money(thresholds.get("material_variance", "0"))) or (
        variance_pct is not None and abs(variance_pct) >= Decimal(thresholds.get("material_variance_pct", "10"))
    )

    if variance != ZERO:
        journal.post_true_up(
            session, obligation_id=ob.obligation_id, workpaper_id=wp.workpaper_id,
            period=ob.period, vendor_id=ob.vendor_id, amount=variance,
            expense_account=wp.expense_account, liability_account=wp.accrual_liability_account,
            cost_center=wp.cost_center,
            description=f"True-up {ob.period} {ob.vendor_id} vs {inv.invoice_number} ({root_cause})",
            at=at,
        )

    learning_id = stable_id("LRN", ob.obligation_id, inv.invoice_id)
    lr = session.get(TrueupLearningRule, learning_id)
    if lr is None:
        lr = TrueupLearningRule(learning_id=learning_id, obligation_id=ob.obligation_id,
                                created_at=at)
        session.add(lr)
    lr.workpaper_id = wp.workpaper_id
    lr.invoice_id = inv.invoice_id
    lr.actual_amount = actual
    lr.accrual_amount = accrued
    lr.variance_amount = variance
    lr.variance_percent = variance_pct
    lr.root_cause = root_cause
    lr.root_cause_summary = summary + (
        f" | Narrative: {narrative.get('explanation','')}" if narrative.get("explanation") else ""
    )
    lr.status = "OBSERVED"
    lr.updated_at = at

    wp.status = "TRUED_UP"
    wp.updated_at = at
    advance(session, ob, stage="TRUED_UP", next_action="HALT", agent="LearningAgent",
            accrual_status="TRUED_UP", matched_invoice_id=inv.invoice_id, resolved_at=at, at=at)
    session.flush()

    log_run(session, agent_name=AGENT, action="true_up",
            status="ESCALATED" if material else "OK",
            obligation_id=ob.obligation_id, workpaper_id=wp.workpaper_id,
            facts_used=[f"accrued={accrued}", f"actual={actual}", f"variance={variance}",
                        f"variance_pct={variance_pct}"] + detail,
            decision_summary=f"{root_cause}: {summary}",
            uncertainties=([f"Variance of {variance} is material and requires adjustment review"]
                           if material else []),
            output_summary=f"learning record {learning_id} created; handed to LearningAgent",
            input_record_ids=[inv.invoice_id, wp.workpaper_id],
            output_record_ids=[learning_id], at=at)
    return lr


# ---------------------------------------------------------------------------
# Deterministic root-cause attribution
# ---------------------------------------------------------------------------

def _diagnose(session, ob, wp, inv, accrued, actual, variance, multi_period):
    """Attribute the variance using the facts that were on the workpaper.

    Ordered most-specific first. Anything that does not fit a known pattern is
    UNKNOWN — and UNKNOWN is a real answer here, not a failure. A system that
    can always name a cause is a system that invents them.
    """
    inputs = wp.calculation_inputs_json or {}
    ev = {e.evidence_type: (e.value_json or {}) for e in evidence_for(session, ob.obligation_id)}
    detail = []

    if variance == ZERO:
        return "TIMING_DIFFERENCE", (
            "Accrual matched the invoice exactly; only the timing of the document differed."
        ), detail

    # --- missed escalator ---------------------------------------------------
    esc = ev.get("CONTRACT_ESCALATOR") or {}
    used_base_rate = "base_rate" in str(inputs.get("rate_source", ""))
    if esc.get("in_force") and used_base_rate and variance > ZERO:
        esc_pct = rate(esc.get("escalator_percent") or 0)
        implied = money(accrued * esc_pct / Decimal(100))
        detail.append(f"escalator {esc_pct}% in force since {esc.get('escalator_effective_date')}")
        detail.append(f"variance explained by escalator would be {implied}")
        if implied != ZERO and abs(variance - implied) <= max(money("1.00"), abs(implied) * Decimal("0.02")):
            return "MISSED_ESCALATOR", (
                f"The accrual used the contract base rate of "
                f"{inputs.get('unit_rate') or inputs.get('monthly_rate')}, but a {esc_pct}% "
                f"escalator took effect on {esc.get('escalator_effective_date')}, before this "
                f"service period began. The variance of {variance} equals the escalator applied "
                f"to the accrued amount ({implied}). The rate was on the contract record and "
                f"was not applied."
            ), detail

    # --- the estimate was a fallback, not a measurement ---------------------
    # A run-rate accrual that missed is not a mystery: it was explicitly flagged
    # as a fallback because the meter had not landed. Attribute it honestly
    # rather than letting it fall through to UNKNOWN.
    if wp.estimation_method == "HISTORICAL_RUN_RATE":
        detail.append("accrual used the HISTORICAL_RUN_RATE fallback")
        return "USAGE_VARIANCE", (
            f"No usage meter had landed by cutoff, so the accrual fell back to a historical run "
            f"rate of {accrued} rather than measured usage. Actual usage for the period billed "
            f"at {actual}, a difference of {variance}. The usage existed upstream; it simply had "
            f"not been fetched before the close."
        ), detail

    # --- non-PO timing ------------------------------------------------------
    if ob.non_po_group_key:
        late = _late_non_po(session, ob)
        if late:
            detail.append(f"{len(late)} transaction(s) posted after the close cutoff")
            return "TIMING_DIFFERENCE", (
                f"{len(late)} card transaction(s) totalling {money(sum(money(r.amount) for r in late))} "
                f"posted after the {ob.period} cutoff and so could not be seen at close. They appear "
                f"on the statement, producing the variance of {variance}."
            ), detail
        if variance < ZERO:
            return "DUPLICATE_NON_PO_ACCRUAL", (
                f"The accrual exceeded the statement by {abs(variance)}; transactions were likely "
                f"counted that AP had already processed separately."
            ), detail

    # --- scope change on a PO ----------------------------------------------
    if ob.po_id and variance != ZERO:
        recv = rate((ev.get("RECEIPT_QUANTITY") or {}).get("quantity") or 0)
        if recv:
            detail.append(f"receipt quantity on record was {recv}")
            return "SCOPE_CHANGE", (
                f"The invoice bills {actual} against a receipt of {recv} units. The delivered "
                f"scope differs from what was received and accepted by the cutoff."
            ), detail

    # --- multi-period -------------------------------------------------------
    if multi_period:
        return "MULTI_PERIOD_INVOICE", (
            f"Invoice {inv.invoice_number} covers "
            f"{inv.service_start_date}..{inv.service_end_date}, which spans more than one close "
            f"period. Its amount was allocated across periods by service days."
        ), detail

    # --- usage variance -----------------------------------------------------
    if ob.purchase_type == "USAGE_BASED":
        qty = rate((ev.get("USAGE_QUANTITY") or {}).get("quantity") or 0)
        unit_rate = rate(inputs.get("unit_rate") or 0)

        # If the invoice itemises usage and that line reconciles to the meter,
        # then usage is NOT the driver — something else on the invoice is, and
        # nothing on the record says what. Do not relabel it as usage drift.
        unexplained = _unexplained_lines(inv, qty, unit_rate)
        if unexplained:
            detail.append(f"invoice usage line reconciles to the meter ({qty}); "
                          f"{len(unexplained)} line(s) do not correspond to any record")
            return "UNKNOWN", (
                f"The metered usage line reconciles exactly to the {qty} "
                f"{inputs.get('unit') or 'units'} recorded at cutoff. The variance of {variance} "
                f"comes from "
                + "; ".join(f"'{u['description']}' ({u['amount']})" for u in unexplained)
                + ", which corresponds to no contract term, purchase order, receipt or usage "
                  "record TrueUp holds. TrueUp will not invent an explanation for it."
            ), detail

        if qty and unit_rate:
            implied_qty = money(actual) / unit_rate if unit_rate else ZERO
            drift = abs(implied_qty - qty) / qty if qty else Decimal(0)
            detail.append(f"metered {qty}, invoice implies {implied_qty.quantize(Decimal('1'))}")
            if drift > Decimal("0.01"):
                return "USAGE_VARIANCE", (
                    f"The meter read {qty} {inputs.get('unit') or 'units'} at cutoff, but the "
                    f"invoice implies roughly {implied_qty.quantize(Decimal('1'))} at the same "
                    f"rate. Late-arriving usage accounts for the variance of {variance}."
                ), detail

    # --- nothing fits -------------------------------------------------------
    detail.append("no known pattern explains this variance")
    return "UNKNOWN", (
        f"The invoice is {variance} away from the accrual and no recorded fact explains it. "
        f"Invoice description: '{inv.description}'. The contract rate, metered usage, receipts "
        f"and transaction population on the workpaper are all consistent with the amount accrued. "
        f"This needs a human; TrueUp will not invent a cause."
    ), detail


def _unexplained_lines(inv, metered_qty, unit_rate) -> list[dict]:
    """Invoice lines that no recorded fact accounts for.

    Only meaningful when the usage line itself reconciles to the meter — that is
    what rules out 'more usage arrived' as the explanation.
    """
    lines = inv.line_items_json or []
    if len(lines) < 2 or not metered_qty or not unit_rate:
        return []
    usage_ok = any(
        l.get("quantity") and abs(rate(l["quantity"]) - metered_qty) <= metered_qty * Decimal("0.001")
        for l in lines
    )
    if not usage_ok:
        return []
    return [
        {"description": l.get("description", "(unlabelled)"), "amount": l.get("amount")}
        for l in lines if not l.get("quantity")
    ]


def _late_non_po(session, ob):
    from app.services.simulator.clock import close_cutoff

    cutoff = close_cutoff(ob.period)
    rows = session.scalars(
        select(CompanyNonPoSpend).where(CompanyNonPoSpend.month == ob.period)
    )
    return [
        r for r in rows
        if f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}" == ob.non_po_group_key
        and r.created_at > cutoff
        and r.transaction_status not in ("VOIDED", "DISPUTED")
    ]
