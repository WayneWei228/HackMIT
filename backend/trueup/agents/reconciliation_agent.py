"""Reconciliation agent: grade a posted accrual against the invoice that arrives after close.

Fully deterministic: amounts, matching and diagnosis are code, never a model. It never looks at a
vendor id or name. No separate true-up entry is posted: the accrual reverses on the first day of
the next period and the invoice is booked there, so the variance lands in that period by
construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.store.types import coerce_money
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "reconciliation"
TOLERANCE = Decimal("0.01")
RATE_TOLERANCE = Decimal("0.00001")
# An invoice with no line items has no stated rate, so the rate is implied as total / quantity,
# rounded half up to six places (finer than any contract rate in the data).
IMPLIED_RATE_PLACES = Decimal("0.000001")
_WAIT = (e.WorkflowStage.AWAITING_ACTUAL_INVOICE, e.NextAction.WAIT_FOR_INVOICE)
_RECONCILE = (e.WorkflowStage.RECONCILING, e.NextAction.MATCH_AND_TRUE_UP)
_LEARN = (e.WorkflowStage.RECONCILING, e.NextAction.EVALUATE_LEARNING)
_CLOSED = (e.WorkflowStage.CLOSED, e.NextAction.NONE)
_CONTROLLER = (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)
_EXCLUDED = (e.APInvoiceStatus.VOIDED, e.APInvoiceStatus.REJECTED)
_SYSTEMATIC = (
    e.RootCause.USAGE_VARIANCE,
    e.RootCause.MISSED_ESCALATOR,
    e.RootCause.TIMING_DIFFERENCE,
)


class ReconciliationError(ValueError):
    """Raised when an obligation cannot be reconciled."""


class ReconciliationResult(BaseModel):
    obligation_id: str
    accrued: Decimal
    actual: Decimal
    variance: Decimal
    tolerance: Decimal
    root_cause: e.RootCause | None
    invoice_ids: list[str]
    invoice_accepted: bool
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    explanation: str
    path: list[str]


@dataclass
class Diagnosis:
    root_cause: e.RootCause | None
    accepted: bool
    explanation: str
    path: list[str] = field(default_factory=list)


def collect_arrivals(session: Session, *, now: datetime) -> list[str]:
    """Match late invoices to obligations waiting for one; return the ids ready to reconcile."""
    now = _utc(now)
    waiting = session.scalars(
        select(m.TrueUpObligation)
        .where(
            m.TrueUpObligation.workflow_stage == _WAIT[0],
            m.TrueUpObligation.next_action == _WAIT[1],
        )
        .order_by(m.TrueUpObligation.obligation_id)
    ).all()
    ready: list[str] = []
    for ob in waiting:
        matches, considered = _matching_invoices(session, ob, now)
        if not matches:
            continue
        workpaper = _workpaper(session, ob)
        inputs = dict(workpaper.calculation_inputs_json or {})
        inputs["matched_invoice_ids"] = [inv.invoice_id for inv in matches]
        workpaper.calculation_inputs_json = inputs
        ob.matched_invoice_id = matches[0].invoice_id
        ob.invoice_status = e.InvoiceStatus.MATCHED_AFTER_CLOSE
        advance(ob, *_RECONCILE, AGENT_NAME, at=now)
        AgentRunLog(session).append(
            agent_name=AGENT_NAME,
            action="match_invoice",
            status=e.AgentRunStatus.COMPLETED,
            decision_summary=(
                f"Matched {len(matches)} invoice(s) to {ob.obligation_id} after close."
            ),
            output_summary="Routed to RECONCILING/MATCH_AND_TRUE_UP.",
            at=now,
            obligation_id=ob.obligation_id,
            workpaper_id=workpaper.workpaper_id,
            facts_used=considered,
            uncertainties=[c["reason"] for c in considered if c["decision"] == "IGNORED_DUPLICATE"]
            or None,
            input_record_ids=[c["invoice_id"] for c in considered],
            output_record_ids=[inv.invoice_id for inv in matches],
        )
        ready.append(ob.obligation_id)
    return ready


def reconcile(session: Session, obligation_id: str, *, now: datetime) -> ReconciliationResult:
    """Compare the accrual with the matched invoices, diagnose a variance and route."""
    now = _utc(now)
    ob = session.get(m.TrueUpObligation, obligation_id)
    if ob is None:
        raise ReconciliationError(f"unknown obligation {obligation_id}")
    if (ob.workflow_stage, ob.next_action) != _RECONCILE:
        raise IllegalTransitionError(
            f"{obligation_id} is at {ob.workflow_stage}/{ob.next_action}, "
            f"not {_RECONCILE[0]}/{_RECONCILE[1]}"
        )
    workpaper = _workpaper(session, ob)
    inputs = dict(workpaper.calculation_inputs_json or {})
    ids = inputs.get("matched_invoice_ids") or (
        [ob.matched_invoice_id] if ob.matched_invoice_id else []
    )
    invoices = [
        inv
        for inv in (session.get(m.CompanyAPInvoice, i) for i in ids)
        if inv is not None
        and inv.status not in _EXCLUDED
        and not inv.credit_flag
        and not inv.duplicate_flag
    ]
    if not invoices:
        raise ReconciliationError(f"{obligation_id} has no usable matched invoice")

    accrued = coerce_money(workpaper.proposed_amount)
    actual = sum((coerce_money(inv.amount) for inv in invoices), Decimal("0"))
    variance = actual - accrued
    de_minimis = _de_minimis(session)
    currency_clash = any(inv.currency != workpaper.currency for inv in invoices)

    diagnosis = _diagnose(
        workpaper.estimation_method,
        inputs,
        invoices,
        accrued,
        actual,
        _rate_candidates(session, ob),
    )
    if currency_clash:
        diagnosis = Diagnosis(
            e.RootCause.UNKNOWN,
            False,
            f"Invoice currency differs from the accrual currency {workpaper.currency}.",
            [*diagnosis.path, "currency mismatch"],
        )
    target = _route(diagnosis, variance, de_minimis, currency_clash)

    advance(ob, *target, AGENT_NAME, at=now)
    if target != _CONTROLLER:
        ob.accrual_status = e.AccrualStatus.TRUE_UP_COMPLETE

    record = {
        "accrued": _money(accrued),
        "actual": _money(actual),
        "variance": _money(variance),
        "tolerance": _money(TOLERANCE),
        "root_cause": diagnosis.root_cause.value if diagnosis.root_cause else None,
        "invoice_ids": [inv.invoice_id for inv in invoices],
        "invoice_accepted": diagnosis.accepted,
        "explanation": diagnosis.explanation,
        "path": diagnosis.path,
        "reconciled_at": now.isoformat(),
    }
    inputs["reconciliation"] = record
    workpaper.calculation_inputs_json = inputs
    cards = _invoice_cards(session, ob, invoices, diagnosis, now)

    routed = e.WorkflowStage(target[0]), e.NextAction(target[1])
    escalated = target == _CONTROLLER
    label = diagnosis.root_cause.value if diagnosis.root_cause else "MATCH"
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="reconcile",
        status=e.AgentRunStatus.ESCALATED if escalated else e.AgentRunStatus.COMPLETED,
        decision_summary=(
            f"{label}: accrued {_money(accrued)}, invoiced {_money(actual)}, "
            f"variance {_money(variance)}. {diagnosis.explanation}"
        ),
        output_summary=f"Routed to {routed[0].value}/{routed[1].value}.",
        at=now,
        obligation_id=ob.obligation_id,
        workpaper_id=workpaper.workpaper_id,
        facts_used=[
            record,
            *[{"invoice": inv.invoice_id, "amount": _money(inv.amount)} for inv in invoices],
        ],
        uncertainties=(
            [diagnosis.explanation]
            if escalated or diagnosis.root_cause == e.RootCause.UNKNOWN
            else None
        ),
        input_record_ids=[inv.invoice_id for inv in invoices] + [workpaper.workpaper_id],
        output_record_ids=cards or [ob.obligation_id],
    )
    return ReconciliationResult(
        obligation_id=ob.obligation_id,
        accrued=accrued,
        actual=actual,
        variance=variance,
        tolerance=TOLERANCE,
        root_cause=diagnosis.root_cause,
        invoice_ids=[inv.invoice_id for inv in invoices],
        invoice_accepted=diagnosis.accepted,
        routed_stage=routed[0],
        next_action=routed[1],
        explanation=diagnosis.explanation,
        path=diagnosis.path,
    )


def _route(
    diagnosis: Diagnosis, variance: Decimal, de_minimis: Decimal, currency_clash: bool
) -> tuple[e.WorkflowStage, e.NextAction]:
    cause = diagnosis.root_cause
    if cause is None:
        return _CLOSED
    if cause == e.RootCause.SOURCE_DATA_ERROR or currency_clash:
        return _CONTROLLER
    if cause in _SYSTEMATIC:
        return _LEARN
    return _LEARN if abs(variance) <= de_minimis else _CONTROLLER


def _diagnose(
    method: e.EstimationMethod,
    inputs: dict[str, Any],
    invoices: list[m.CompanyAPInvoice],
    accrued: Decimal,
    actual: Decimal,
    rate_candidates: list[Decimal],
) -> Diagnosis:
    variance = actual - accrued
    if abs(variance) <= TOLERANCE:
        return Diagnosis(None, True, "The invoice matches the accrual within tolerance.", ["match"])

    qty = _invoice_quantity(invoices)
    price = _invoice_unit_price(invoices)
    methods = e.EstimationMethod
    cause = e.RootCause

    if method == methods.MILESTONE_ACCEPTED_AMOUNT:
        accepted = _dec(inputs.get("accepted_amount"))
        cap = _dec(inputs.get("budget_cap"))
        if accepted is not None and actual > accepted:
            note = (
                " It equals the PO budget cap, not the delivered amount." if actual == cap else ""
            )
            return Diagnosis(
                cause.SOURCE_DATA_ERROR,
                False,
                f"The invoice bills {_money(actual)} but only {_money(accepted)} was delivered "
                f"and accepted.{note} The invoice is not accepted as the truth.",
                ["milestone purchase", "invoice above accepted amount"],
            )
        if accepted is not None and actual < accepted:
            return Diagnosis(
                cause.TIMING_DIFFERENCE,
                True,
                f"The invoice is {_money(accepted - actual)} below the accepted amount; the "
                "balance is billed in a later invoice.",
                ["milestone purchase", "invoice below accepted amount"],
            )

    if method == methods.RECEIVED_QUANTITY_TIMES_PRICE:
        received = _dec(inputs.get("received_quantity"))
        po_price = _dec(inputs.get("unit_price"))
        if qty is not None and received is not None:
            if qty > received:
                return Diagnosis(
                    cause.SOURCE_DATA_ERROR,
                    False,
                    f"The invoice bills {qty} units but only {received} were received. "
                    "The invoice is not accepted as the truth.",
                    ["receipt purchase", "invoice quantity above received quantity"],
                )
            if qty < received and (price is None or po_price is None or price == po_price):
                return Diagnosis(
                    cause.TIMING_DIFFERENCE,
                    True,
                    f"The invoice covers {qty} of {received} received units; the rest is billed "
                    "later.",
                    ["receipt purchase", "invoice quantity below received quantity"],
                )

    if method == methods.USAGE_TIMES_RATE:
        quantity = _dec(inputs.get("quantity"))
        rate = _dec(inputs.get("unit_rate"))
        if quantity is not None and rate is not None:
            implied = False
            if price is None and quantity > 0:
                price = (actual / quantity).quantize(IMPLIED_RATE_PLACES, ROUND_HALF_UP)
                implied = True
            if price is not None and _differs(price, rate):
                contract_rate = next((c for c in rate_candidates if not _differs(price, c)), None)
                if (
                    contract_rate is not None
                    and abs(actual - quantity * contract_rate) <= TOLERANCE
                ):
                    source = "implied invoice rate" if implied else "invoice rate"
                    return Diagnosis(
                        cause.MISSED_ESCALATOR,
                        True,
                        f"The {source} {price} is a contract rate the estimate did not use "
                        f"({rate}).",
                        [
                            "usage purchase",
                            "implied rate differs" if implied else "invoice rate differs",
                            "rate is a contract rate",
                        ],
                    )
            elif qty is not None and qty != quantity and abs(actual - qty * rate) <= TOLERANCE:
                return Diagnosis(
                    cause.USAGE_VARIANCE,
                    True,
                    f"The invoice measures {qty} units against the estimate's {quantity} at the "
                    "same rate.",
                    ["usage purchase", "invoice quantity differs", "rate unchanged"],
                )

    if (
        method == methods.FIXED_CONTRACT_RATE
        and _differs(actual, accrued)
        and _in(actual, rate_candidates)
    ):
        return Diagnosis(
            cause.MISSED_ESCALATOR,
            True,
            f"The invoice equals a contract rate ({_money(actual)}) the estimate did not use "
            f"({_money(accrued)}).",
            ["fixed purchase", "invoice equals another contract rate"],
        )

    return Diagnosis(
        cause.UNKNOWN,
        True,
        f"The variance of {_money(variance)} is not explained by quantity, rate or delivery.",
        ["no rule explains the variance"],
    )


def matching_invoices(
    session: Session, ob: m.TrueUpObligation, *, now: datetime
) -> list[m.CompanyAPInvoice]:
    """Invoices that match an obligation's vendor, window and references as of `now`.

    `ob` may be a transient (unsaved) obligation: only its vendor, service window, PO and
    contract are read. Nothing is written.
    """
    return _matching_invoices(session, ob, _utc(now))[0]


def _matching_invoices(
    session: Session, ob: m.TrueUpObligation, now: datetime
) -> tuple[list[m.CompanyAPInvoice], list[dict[str, str]]]:
    start, end = ob.service_start_date, ob.service_end_date
    invoices = session.scalars(
        select(m.CompanyAPInvoice)
        .where(m.CompanyAPInvoice.vendor_id == ob.vendor_id)
        .order_by(m.CompanyAPInvoice.invoice_date, m.CompanyAPInvoice.invoice_id)
    ).all()
    matches: list[m.CompanyAPInvoice] = []
    considered: list[dict[str, str]] = []

    def note(inv: m.CompanyAPInvoice, decision: str, reason: str) -> None:
        considered.append(
            {
                "invoice_id": inv.invoice_id,
                "decision": decision,
                "reason": reason,
                "amount": _money(inv.amount),
            }
        )

    for inv in invoices:
        first, last = inv.service_start_date, inv.service_end_date
        if first is None or last is None:
            if not start <= inv.invoice_date <= end:
                continue
        elif last < start or first > end:
            continue
        elif not (first >= start and last <= end):
            note(inv, "IGNORED_WINDOW", "The service window runs beyond this obligation.")
            continue
        if inv.received_at > now:
            note(inv, "IGNORED_FUTURE", "Received after the search date.")
        elif inv.status in _EXCLUDED:
            note(inv, "IGNORED_STATUS", f"Invoice status is {inv.status}.")
        elif inv.credit_flag:
            note(inv, "IGNORED_CREDIT", "A credit memo is not a bill for the period.")
        elif inv.duplicate_flag:
            note(inv, "IGNORED_DUPLICATE", "Flagged as a duplicate, so it is not summed.")
        elif _other_reference(inv, ob):
            note(inv, "IGNORED_REFERENCE", "Refers to a different PO or contract.")
        else:
            note(inv, "MATCHED", "Same vendor, inside the service window, consistent reference.")
            matches.append(inv)
    return matches, considered


def _other_reference(inv: m.CompanyAPInvoice, ob: m.TrueUpObligation) -> bool:
    return bool(inv.po_id and ob.po_id and inv.po_id != ob.po_id) or bool(
        inv.contract_id and ob.contract_id and inv.contract_id != ob.contract_id
    )


def _rate_candidates(session: Session, ob: m.TrueUpObligation) -> list[Decimal]:
    if not ob.contract_id:
        return []
    rows = session.scalars(
        select(m.CompanyContract).where(m.CompanyContract.contract_id == ob.contract_id)
    ).all()
    rates: list[Decimal] = []
    for row in rows:
        if row.base_rate is not None:
            rates.append(coerce_money(row.base_rate))
            if row.escalator_percent is not None:
                rates.append(
                    coerce_money(row.base_rate) * (1 + coerce_money(row.escalator_percent) / 100)
                )
    return rates


def _de_minimis(session: Session) -> Decimal:
    row = session.get(m.CompanyConfig, "approval_thresholds")
    value = (row.config_value_json or {}).get("de_minimis_threshold_usd") if row else None
    return _dec(value) or Decimal("0")


def _invoice_cards(
    session: Session,
    ob: m.TrueUpObligation,
    invoices: list[m.CompanyAPInvoice],
    diagnosis: Diagnosis,
    now: datetime,
) -> list[str]:
    prefix = f"EVD-{ob.obligation_id}-INV-"
    existing = session.scalars(
        select(m.TrueUpEvidence.evidence_id).where(m.TrueUpEvidence.evidence_id.like(f"{prefix}%"))
    ).all()
    number = len(existing)
    ids: list[str] = []
    for inv in invoices:
        number += 1
        window = f"{inv.service_start_date} to {inv.service_end_date}"
        card = m.TrueUpEvidence(
            evidence_id=f"{prefix}{number:02d}",
            obligation_id=ob.obligation_id,
            evidence_type=e.EvidenceCardType.INVOICE,
            source_table="company_ap_invoices",
            source_id=inv.invoice_id,
            fact=f"Invoice {inv.invoice_number}: {_money(inv.amount)} {inv.currency} for {window}",
            value_json={
                "key": "INVOICE_AMOUNT",
                "number": _money(inv.amount),
                "unit": inv.currency,
                "invoice_id": inv.invoice_id,
                "accepted": diagnosis.accepted,
                "root_cause": diagnosis.root_cause.value if diagnosis.root_cause else None,
            },
            source_excerpt=inv.description,
            confidence=Decimal("1.00"),
            status=(
                e.EvidenceCardStatus.VERIFIED
                if diagnosis.accepted
                else e.EvidenceCardStatus.CONFLICTING
            ),
            created_by_agent=AGENT_NAME,
            created_at=now,
        )
        session.add(card)
        ids.append(card.evidence_id)
    session.flush()
    return ids


def _workpaper(session: Session, ob: m.TrueUpObligation) -> m.TrueUpWorkpaper:
    workpaper = (
        session.get(m.TrueUpWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    )
    if workpaper is None:
        raise ReconciliationError(f"{ob.obligation_id} has no workpaper")
    return workpaper


def _invoice_quantity(invoices: list[m.CompanyAPInvoice]) -> Decimal | None:
    total = Decimal("0")
    for inv in invoices:
        quantities = [_dec(line.get("quantity")) for line in _lines(inv)]
        if not quantities or any(q is None for q in quantities):
            return None
        total += sum(quantities, Decimal("0"))  # type: ignore[arg-type]
    return total


def _invoice_unit_price(invoices: list[m.CompanyAPInvoice]) -> Decimal | None:
    prices = {_dec(line.get("unit_price")) for inv in invoices for line in _lines(inv)}
    return prices.pop() if len(prices) == 1 and None not in prices else None


def _lines(inv: m.CompanyAPInvoice) -> list[dict[str, Any]]:
    items = inv.line_items_json
    return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return coerce_money(value)
    except (TypeError, ValueError):
        return None


def _differs(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) > RATE_TOLERANCE


def _in(value: Decimal, candidates: list[Decimal]) -> bool:
    return any(abs(value - c) <= RATE_TOLERANCE for c in candidates)


def _money(value: object) -> str:
    return f"{coerce_money(value):.2f}"


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
