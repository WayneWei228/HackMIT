"""Build an EstimationContext from the database, respecting the as-of cutoff.

This is the only place the two halves meet: stateful reads on one side, the pure
estimator on the other. Keeping the boundary here is what lets replay rebuild a
historical context exactly and re-run the same function against it.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import CompanyPurchaseOrder, CompanyVendor, TrueupObligation
from app.money import money, rate
from app.repositories.asof import (
    accrued_by_obligation,
    disputed_non_po_spend,
    eligible_non_po_spend,
    visible_invoices,
    visible_service_evidence,
)
from app.repositories.contracts import effective_version
from app.services.agents.common import evidence_for
from app.services.estimators.context import (
    ContractSnapshot,
    EstimationContext,
    EvidenceFact,
    NonPoLineSnapshot,
    PoLineSnapshot,
    PoSnapshot,
)
from app.services.simulator.clock import close_cutoff, periods_before
from app.services.simulator.profile import ACCRUAL_LIABILITY


def build_context(session: Session, ob: TrueupObligation, as_of: dt.datetime | None = None):
    as_of = as_of or close_cutoff(ob.period)
    vendor = session.get(CompanyVendor, ob.vendor_id)

    contract = _contract_snapshot(session, ob)
    po = _po_snapshot(session, ob)
    usage_qty, usage_unit = _usage(session, ob, as_of)
    milestone = _milestone_amount(session, ob, as_of)
    non_po, disputed = _non_po(session, ob, as_of)
    expense_account, cost_center = _accounts(session, ob, po)

    ev_map: dict[str, EvidenceFact] = {}
    for e in evidence_for(session, ob.obligation_id):
        ev_map[e.evidence_type] = EvidenceFact(
            evidence_id=e.evidence_id, evidence_type=e.evidence_type,
            value=e.value_json or {}, confidence=money(e.confidence),
            source_table=e.source_table, source_id=e.source_id,
        )

    # No meter, but a person answered a TrueUp request with the figure. That is
    # evidence — weaker than a meter, attributed, and on the record — so the
    # estimator may bind it rather than falling back or refusing.
    if usage_qty is None:
        attested = ev_map.get("USAGE_QUANTITY")
        if attested and attested.value.get("source") == "OUTREACH":
            usage_qty = rate(attested.value.get("quantity") or 0) or None
            usage_unit = contract.rate_unit if contract else None

    return EstimationContext(
        obligation_id=ob.obligation_id,
        vendor_id=ob.vendor_id,
        vendor_name=vendor.vendor_name if vendor else ob.vendor_id,
        period=ob.period,
        purchase_type=ob.purchase_type,
        service_start=ob.service_start_date,
        service_end=ob.service_end_date,
        as_of=as_of,
        contract=contract,
        po=po,
        usage_quantity=usage_qty,
        usage_unit=usage_unit,
        milestone_accepted_amount=milestone,
        non_po_lines=tuple(non_po),
        non_po_disputed_count=disputed,
        historical_amounts=tuple(_history(session, ob, as_of)),
        invoice_found=ob.invoice_status == "FOUND",
        invoice_ambiguous=ob.invoice_status == "AMBIGUOUS",
        expense_account=expense_account,
        accrual_liability_account=ACCRUAL_LIABILITY,
        cost_center=cost_center,
        currency=vendor.default_currency if vendor else "USD",
        evidence=ev_map,
        classification_conflict="CLASSIFICATION_CONFLICT" in ev_map,
    )


def _contract_snapshot(session, ob):
    if not ob.contract_id:
        return None
    c = effective_version(session, ob.contract_id, ob.service_start_date, ob.service_end_date)
    if c is None:
        return None
    return ContractSnapshot(
        contract_row_id=c.contract_row_id, contract_id=c.contract_id,
        contract_version=c.contract_version, billing_model=c.billing_model,
        base_rate=rate(c.base_rate) if c.base_rate is not None else None,
        rate_unit=c.rate_unit, billing_frequency=c.billing_frequency,
        escalator_percent=rate(c.escalator_percent) if c.escalator_percent is not None else None,
        escalator_effective_date=c.escalator_effective_date,
        effective_start_date=c.effective_start_date, effective_end_date=c.effective_end_date,
        service_owner_id=c.service_owner_id, procurement_owner_id=c.procurement_owner_id,
    )


def _po_snapshot(session, ob):
    if not ob.po_id:
        return None
    po = session.get(CompanyPurchaseOrder, ob.po_id)
    if po is None:
        return None
    lines = tuple(
        PoLineSnapshot(
            po_line_id=l.get("po_line_id", ""), item_category=l.get("item_category", ""),
            gl_account_code=l.get("gl_account_code", po.gl_account),
            quantity_ordered=rate(l.get("quantity_ordered", 0)),
            unit_price=rate(l.get("unit_price", 0)),
            quantity_received=rate(l.get("quantity_received", 0)),
            quantity_billed=rate(l.get("quantity_billed", 0)),
            line_description=l.get("line_description", ""),
            receipt_required=bool(l.get("receipt_required", True)),
        )
        for l in (po.line_items_json or [])
    )
    return PoSnapshot(
        po_id=po.po_id, po_number=po.po_number, status=po.status, order_type=po.order_type,
        approved_total=money(po.approved_total), gl_account=po.gl_account,
        cost_center=po.cost_center, po_owner_id=po.po_owner_id, lines=lines,
    )


def _usage(session, ob, as_of):
    rows = [
        r for r in visible_service_evidence(session, as_of, vendor_id=ob.vendor_id,
                                            contract_id=ob.contract_id)
        if r.evidence_type == "USAGE_METER"
        and r.service_start_date >= ob.service_start_date
        and r.service_end_date <= ob.service_end_date
        and r.confirmation_status == "CONFIRMED"
    ]
    if not rows:
        return None, None
    total = sum(rate(r.quantity or 0) for r in rows)
    return total, rows[0].unit


def _milestone_amount(session, ob, as_of):
    if ob.purchase_type != "MILESTONE_BASED":
        return None
    rows = [
        r for r in visible_service_evidence(session, as_of, vendor_id=ob.vendor_id, po_id=ob.po_id)
        if r.evidence_type in ("DELIVERY_REPORT", "MILESTONE_ACCEPTANCE")
        and r.accepted_amount is not None
        and r.service_end_date <= ob.service_end_date
    ]
    if not rows:
        return None
    return money(sum(money(r.accepted_amount) for r in rows))


def _non_po(session, ob, as_of):
    if not ob.non_po_group_key:
        return [], 0
    rows = [
        r for r in eligible_non_po_spend(session, as_of, ob.period)
        if f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}" == ob.non_po_group_key
    ]
    # Transactions THIS obligation has already accrued remain part of its own
    # population. Without them, re-performing or replaying a posted non-PO accrual
    # would rebuild an empty population and compute zero: the estimate would stop
    # being reproducible the moment it was posted. Scoped to this obligation only —
    # rows accrued by a different one must stay invisible, or the duplicate guard
    # would be defeated.
    seen = {r.non_po_spend_id for r in rows}
    rows += [
        r for r in accrued_by_obligation(session, as_of, ob.period, ob.obligation_id)
        if f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}" == ob.non_po_group_key
        and r.non_po_spend_id not in seen
    ]
    rows.sort(key=lambda r: r.non_po_spend_id)
    disputed = [
        r for r in disputed_non_po_spend(session, as_of, ob.period)
        if f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}" == ob.non_po_group_key
    ]
    lines = [
        NonPoLineSnapshot(
            non_po_spend_id=r.non_po_spend_id, merchant_name=r.merchant_name,
            spend_source=r.spend_source, amount=money(r.amount),
            transaction_status=r.transaction_status, gl_account=r.gl_account,
            cost_center=r.cost_center, has_ap_link=bool(r.ap_invoice_id),
        )
        for r in rows
    ]
    return lines, len(disputed)


def _history(session, ob, as_of) -> list[Decimal]:
    """Prior invoices for this vendor that had already ARRIVED by the cutoff.

    Used only by the HISTORICAL_RUN_RATE fallback. Still routed through the as-of
    guard, because 'history' seen from the future is not history.
    """
    if not ob.contract_id:
        return []
    prior = set(periods_before(ob.period, 6))
    out = []
    for inv in visible_invoices(session, as_of, vendor_id=ob.vendor_id, contract_id=ob.contract_id):
        if inv.service_start_date and f"{inv.service_start_date:%Y-%m}" in prior:
            out.append(money(inv.amount))
    return out


def _accounts(session, ob, po):
    if po is not None:
        return po.gl_account, po.cost_center
    if ob.non_po_group_key:
        _, _, cc, gl = ob.non_po_group_key.split("|")
        return gl, cc
    from app.services.simulator.profile import VENDORS

    v = next((x for x in VENDORS if x["vendor_id"] == ob.vendor_id), None)
    return (v["gl"], v["cc"]) if v else ("6000-OTHER", "CC-000")
