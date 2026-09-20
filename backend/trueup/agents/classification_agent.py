"""Classification agent: decide an obligation's purchase type and hand it to the next stage.

Deterministic rules over structured fields are the authority: contract billing model and
frequency, PO order type and line categories, receipt requirements and service evidence types.
The rules never look at a vendor id or name. An optional language model cross-check reads only
descriptive text with dollar amounts masked. If it disagrees, the rules cannot decide, or the
evidence contradicts the rules, the obligation goes to the Controller instead of moving on.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.gateway import llm
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "classification"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "classify.md"
CONTRACT_EXCERPT_CHARS = 1200
_AMOUNT = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_P = e.PurchaseType


class Signal(BaseModel):
    name: str
    value: str
    points_to: str


class ClassificationOpinion(BaseModel):
    purchase_type: e.PurchaseType
    reason: str


CrossCheckStatus = Literal[
    "not_requested", "skipped_no_model", "failed", "agreed", "disagreed", "inconclusive"
]


class ClassificationResult(BaseModel):
    obligation_id: str
    purchase_type: e.PurchaseType
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    signals: list[Signal]
    rationale: str
    cross_check: CrossCheckStatus
    opinion: ClassificationOpinion | None = None
    uncertainties: list[str]


@dataclass(frozen=True)
class StructuralFacts:
    contract_billing_model: str | None = None
    contract_billing_frequency: str | None = None
    po_present: bool = False
    po_order_type: str | None = None
    line_categories: tuple[str, ...] = ()
    receipt_required: bool = False
    po_window_months: int = 0
    non_po_sources: tuple[str, ...] = ()
    evidence_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class FreeText:
    contract_excerpt: str = ""
    po_description: str = ""
    line_descriptions: tuple[str, ...] = field(default_factory=tuple)

    def render(self) -> str:
        parts = []
        if self.contract_excerpt:
            parts.append(f"Contract: {self.contract_excerpt}")
        if self.po_description:
            parts.append(f"Purchase order: {self.po_description}")
        parts += [f"Line: {text}" for text in self.line_descriptions]
        return "\n".join(parts) or "(no descriptive text available)"


CrossCheck = Callable[[FreeText], ClassificationOpinion]


def classify_structure(facts: StructuralFacts) -> tuple[e.PurchaseType, list[Signal]]:
    """Pure rules over structured fields. Returns the type and the signals that fired."""
    signals: list[Signal] = []

    def fire(name: str, value: object, points_to: e.PurchaseType) -> e.PurchaseType:
        signals.append(Signal(name=name, value=str(value), points_to=points_to.value))
        return points_to

    model, frequency = facts.contract_billing_model, facts.contract_billing_frequency
    if model in ("USAGE_BASED", "SEAT_BASED"):
        return fire("contract.billing_model", model, _P.USAGE_BASED), signals
    if model == "MILESTONE_BASED":
        return fire("contract.billing_model", model, _P.MILESTONE_BASED), signals
    if model == "FIXED_FEE":
        if frequency == "ANNUAL":
            return fire("contract.billing_frequency", "ANNUAL on FIXED_FEE", _P.PREPAID), signals
        return fire("contract.billing_model", model, _P.FIXED_RECURRING), signals

    categories = set(facts.line_categories)
    if facts.po_present and categories:
        if categories == {"MATERIAL"} and facts.receipt_required:
            fire("po.item_category", "MATERIAL", _P.RECEIPT_BASED)
            return fire("po.receipt_required", True, _P.RECEIPT_BASED), signals
        if categories <= {"BLANKET_LIMIT", "ENHANCED_LIMIT"}:
            if facts.receipt_required and facts.po_order_type == "PROJECT":
                fire("po.order_type", facts.po_order_type, _P.MILESTONE_BASED)
                fire("po.item_category", sorted(categories)[0], _P.MILESTONE_BASED)
                return fire("po.receipt_required", True, _P.MILESTONE_BASED), signals
            if not facts.receipt_required and facts.po_order_type == "BLANKET":
                fire("po.order_type", facts.po_order_type, _P.USAGE_BASED)
                return fire("po.item_category", sorted(categories)[0], _P.USAGE_BASED), signals
        if categories == {"SERVICE"} and facts.po_window_months >= 2:
            fire("po.item_category", "SERVICE", _P.FIXED_RECURRING)
            return fire("po.window_months", facts.po_window_months, _P.FIXED_RECURRING), signals

    if not facts.po_present and facts.contract_billing_model is None and facts.non_po_sources:
        sources = set(facts.non_po_sources)
        if sources <= {"PROCUREMENT_CARD", "CORPORATE_CARD"}:
            return fire("non_po.spend_source", sorted(sources)[0], _P.NON_PO_CARD_SPEND), signals
        if sources == {"DIRECT_NON_PO_INVOICE"}:
            return fire(
                "non_po.spend_source", "DIRECT_NON_PO_INVOICE", _P.NON_PO_DIRECT_SPEND
            ), signals

    return _P.UNKNOWN, signals


def evidence_conflicts(purchase_type: e.PurchaseType, evidence_types: tuple[str, ...]) -> list[str]:
    """Measured evidence that only fits another purchase type than the one the rules chose."""
    found = []
    if "SYSTEM_USAGE" in evidence_types and purchase_type != _P.USAGE_BASED:
        found.append(f"System usage evidence exists but the rules chose {purchase_type.value}.")
    if "GOODS_RECEIPT" in evidence_types and purchase_type != _P.RECEIPT_BASED:
        found.append(f"A goods receipt exists but the rules chose {purchase_type.value}.")
    return found


def llm_cross_check(text: FreeText) -> ClassificationOpinion:
    prompt = PROMPT_PATH.read_text().replace("{{TEXT}}", text.render())
    return cast(ClassificationOpinion, llm.complete_json(prompt, ClassificationOpinion))


def classify(
    session: Session,
    obligation_id: str,
    *,
    now: datetime,
    cross_check: CrossCheck | bool | None = None,
) -> ClassificationResult:
    obligation = session.get(m.TrueUpObligation, obligation_id)
    if obligation is None:
        raise LookupError(f"unknown obligation {obligation_id}")
    state = (obligation.workflow_stage, obligation.next_action)
    if state != (e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY):
        raise IllegalTransitionError(
            f"{obligation_id} is at {state[0]}/{state[1]}, not CLASSIFYING/CLASSIFY"
        )

    contract, po, service_rows, non_po_rows, cards = _load(session, obligation)
    facts = _facts(contract, po, service_rows, non_po_rows)
    rule_type, signals = classify_structure(facts)

    uncertainties: list[str] = []
    if rule_type == _P.UNKNOWN:
        uncertainties.append("The structural rules could not decide the purchase type.")
    conflicts = (
        evidence_conflicts(rule_type, facts.evidence_types) if rule_type != _P.UNKNOWN else []
    )
    uncertainties += conflicts

    status, opinion, note = _run_cross_check(cross_check, contract, po, rule_type)
    if note:
        uncertainties.append(note)
    if opinion is not None and status == "disagreed":
        uncertainties.append(
            f"The language model cross-check says {opinion.purchase_type.value}, "
            f"the rules say {rule_type.value}."
        )

    escalate = rule_type == _P.UNKNOWN or bool(conflicts) or status == "disagreed"
    obligation.purchase_type = rule_type
    if escalate:
        advance(
            obligation,
            e.WorkflowStage.AWAITING_CONTROLLER,
            e.NextAction.CONTROLLER_REVIEW,
            AGENT_NAME,
            at=now,
        )
    else:
        advance(obligation, e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE, AGENT_NAME, at=now)

    fired = ", ".join(f"{s.name}={s.value}" for s in signals) or "none"
    rationale = f"Rules chose {rule_type.value} from: {fired}."
    result = ClassificationResult(
        obligation_id=obligation_id,
        purchase_type=rule_type,
        routed_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        signals=signals,
        rationale=rationale,
        cross_check=status,
        opinion=opinion,
        uncertainties=uncertainties,
    )
    _log(session, obligation, result, contract, po, service_rows, cards, now, escalate)
    return result


def _load(session: Session, obligation: m.TrueUpObligation):
    po = session.get(m.CompanyPurchaseOrder, obligation.po_id) if obligation.po_id else None
    contract_id = obligation.contract_id or (po.contract_id if po else None)
    query = select(m.CompanyContract).where(m.CompanyContract.vendor_id == obligation.vendor_id)
    if contract_id:
        query = query.where(m.CompanyContract.contract_id == contract_id)
    versions = list(session.scalars(query.order_by(m.CompanyContract.contract_version.desc())))
    covering = [
        c
        for c in versions
        if c.effective_start_date <= obligation.service_end_date
        and (c.effective_end_date is None or c.effective_end_date >= obligation.service_start_date)
    ]
    active = [c for c in covering if c.status == e.ContractStatus.ACTIVE]
    contract = (active or covering or versions or [None])[0]
    service_rows = list(
        session.scalars(
            select(m.CompanyServiceEvidence).where(
                m.CompanyServiceEvidence.vendor_id == obligation.vendor_id
            )
        )
    )
    non_po_rows = list(
        session.scalars(
            select(m.CompanyNonPOSpend).where(
                m.CompanyNonPOSpend.vendor_id == obligation.vendor_id,
                m.CompanyNonPOSpend.month == obligation.period,
            )
        )
    )
    cards = list(
        session.scalars(
            select(m.TrueUpEvidence).where(
                m.TrueUpEvidence.obligation_id == obligation.obligation_id
            )
        )
    )
    return contract, po, service_rows, non_po_rows, cards


def structural_facts_for(session: Session, obligation: m.TrueUpObligation) -> StructuralFacts:
    """The structured facts the rules read for an obligation, without writing anything.

    `obligation` may be transient (unsaved): only its vendor, window, PO, contract and period
    are read.
    """
    contract, po, service_rows, non_po_rows, _cards = _load(session, obligation)
    return _facts(contract, po, service_rows, non_po_rows)


def _facts(contract, po, service_rows, non_po_rows) -> StructuralFacts:
    lines = list(po.line_items_json or []) if po else []
    window = 0
    if po and po.service_start_date and po.service_end_date:
        start, end = po.service_start_date, po.service_end_date
        window = (end.year - start.year) * 12 + (end.month - start.month) + 1
    return StructuralFacts(
        contract_billing_model=contract.billing_model.value if contract else None,
        contract_billing_frequency=contract.billing_frequency.value if contract else None,
        po_present=po is not None,
        po_order_type=po.order_type.value if po else None,
        line_categories=tuple(sorted({str(line["item_category"]) for line in lines})),
        receipt_required=any(bool(line.get("receipt_required")) for line in lines),
        po_window_months=window,
        non_po_sources=tuple(sorted({row.spend_source.value for row in non_po_rows})),
        evidence_types=tuple(sorted({row.evidence_type.value for row in service_rows})),
    )


def _free_text(contract, po) -> FreeText:
    excerpt = (
        _AMOUNT.sub("[amount]", contract.contract_text[:CONTRACT_EXCERPT_CHARS]) if contract else ""
    )
    lines = tuple(
        _AMOUNT.sub("[amount]", str(line.get("line_description", "")))
        for line in (po.line_items_json or [] if po else [])
    )
    return FreeText(
        contract_excerpt=excerpt,
        po_description=_AMOUNT.sub("[amount]", po.description) if po else "",
        line_descriptions=lines,
    )


def _run_cross_check(cross_check, contract, po, rule_type):
    if not cross_check:
        return "not_requested", None, None
    runner = cross_check
    if cross_check is True:
        if not llm.available():
            return (
                "skipped_no_model",
                None,
                "The language model cross-check was skipped: no model is configured.",
            )
        runner = llm_cross_check
    try:
        opinion = runner(_free_text(contract, po))
    except llm.LLMError as exc:
        return "failed", None, f"The language model cross-check failed: {exc}"
    if opinion.purchase_type == _P.UNKNOWN:
        return "inconclusive", opinion, "The language model could not tell from the text."
    if rule_type == _P.UNKNOWN:
        return (
            "inconclusive",
            opinion,
            f"The language model suggests {opinion.purchase_type.value} "
            "but the rules could not decide.",
        )
    if opinion.purchase_type == rule_type:
        return "agreed", opinion, None
    return "disagreed", opinion, None


def _log(session, obligation, result, contract, po, service_rows, cards, now, escalate) -> None:
    facts_used = [s.model_dump() for s in result.signals]
    facts_used.append({"name": "cross_check", "value": result.cross_check, "points_to": ""})
    input_ids = [
        x for x in (contract.contract_row_id if contract else None, po.po_id if po else None) if x
    ]
    input_ids += [row.service_evidence_id for row in service_rows] + [c.evidence_id for c in cards]
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="classify_purchase",
        status=e.AgentRunStatus.ESCALATED if escalate else e.AgentRunStatus.COMPLETED,
        decision_summary=(
            f"Classified {obligation.vendor_id} {obligation.period} as "
            f"{result.purchase_type.value} and routed to {result.routed_stage.value}. "
            f"{result.rationale}"
        ),
        output_summary=f"purchase_type={result.purchase_type.value}",
        at=now,
        obligation_id=obligation.obligation_id,
        facts_used=facts_used,
        uncertainties=result.uncertainties or None,
        input_record_ids=input_ids,
        output_record_ids=[obligation.obligation_id],
    )
