"""Classification Agent — picks the accounting path.

The deterministic classifier is authoritative: it reads structured contract and
PO fields, which is what an auditor would do. The LLM reads the free-text
description and offers a second opinion.

When the two disagree, TrueUp does not average them or prefer the model. It
records a CLASSIFICATION_CONFLICT evidence card, and escalates if the item is
material or already high-risk. Disagreement between a rule and a model is
information, not noise.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import CompanyContract, CompanyPurchaseOrder, TrueupObligation
from app.money import money
from app.repositories.contracts import effective_version
from app.repositories.runs import log_run
from app.services.agents.common import add_evidence, advance, config, vendor_name
from app.services.llm import get_llm
from app.services.simulator.clock import close_cutoff

AGENT = "ClassificationAgent"

TYPES = ("FIXED_RECURRING", "USAGE_BASED", "RECEIPT_BASED", "MILESTONE_BASED",
         "NON_PO_CARD_SPEND", "NON_PO_DIRECT_SPEND", "UNKNOWN")


def classify_deterministic(contract: CompanyContract | None,
                           po: CompanyPurchaseOrder | None,
                           non_po_group_key: str | None) -> tuple[str, str]:
    """Structured fields only. No text, no model."""
    if non_po_group_key:
        source = non_po_group_key.split("|")[1]
        if source in ("PCARD", "CORPORATE_CARD"):
            return "NON_PO_CARD_SPEND", f"non-PO spend_source={source}"
        return "NON_PO_DIRECT_SPEND", f"non-PO spend_source={source}"
    if po is not None:
        if po.order_type == "MILESTONE":
            return "MILESTONE_BASED", "purchase_orders.order_type=MILESTONE"
        if any(l.get("receipt_required") for l in (po.line_items_json or [])):
            return "RECEIPT_BASED", "PO line carries receipt_required=true"
        return "RECEIPT_BASED", "purchase order without milestone terms"
    if contract is not None:
        if contract.billing_model == "FIXED_RECURRING":
            return "FIXED_RECURRING", "contracts.billing_model=FIXED_RECURRING"
        if contract.billing_model == "USAGE_BASED":
            return "USAGE_BASED", "contracts.billing_model=USAGE_BASED"
    return "UNKNOWN", "no structured field determines the accounting path"


def run(session: Session, obligation_id: str, as_of: dt.datetime | None = None) -> TrueupObligation:
    ob = session.get(TrueupObligation, obligation_id)
    as_of = as_of or close_cutoff(ob.period)

    contract = (effective_version(session, ob.contract_id, ob.service_start_date, ob.service_end_date)
                if ob.contract_id else None)
    po = session.get(CompanyPurchaseOrder, ob.po_id) if ob.po_id else None

    det_type, det_basis = classify_deterministic(contract, po, ob.non_po_group_key)

    description = " ".join(filter(None, [
        po.description if po else None,
        contract.contract_name if contract else None,
        f"{contract.billing_model} at {contract.base_rate} per {contract.rate_unit}" if contract else None,
        ob.non_po_group_key,
    ]))
    llm = get_llm().classify_purchase_type(
        description,
        {"billing_model": contract.billing_model if contract else None,
         "order_type": po.order_type if po else None,
         "vendor": vendor_name(session, ob.vendor_id)},
    )
    llm_type = llm.get("purchase_type", "UNKNOWN")
    llm_conf = float(llm.get("confidence") or 0)

    created = [add_evidence(
        session, obligation_id=ob.obligation_id, evidence_type="CLASSIFICATION",
        source_table="company_contracts" if contract else "company_purchase_orders",
        source_id=(contract.contract_row_id if contract else (po.po_id if po else ob.non_po_group_key or "")),
        fact=(f"Deterministic classification: {det_type} ({det_basis}). "
              f"LLM cross-check: {llm_type} at confidence {llm_conf} ({llm.get('reason','')})."),
        value={"deterministic": det_type, "deterministic_basis": det_basis,
               "llm": llm_type, "llm_confidence": llm_conf, "authoritative": det_type},
        agent=AGENT, at=as_of,
    ).evidence_id]

    conflict = llm_type != det_type and llm_type != "UNKNOWN" and llm_conf >= 0.6
    status, next_action, agent = "OK", "ESTIMATE", "EstimationAgent"

    if conflict:
        created.append(add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type="CLASSIFICATION_CONFLICT",
            source_table="trueup_evidence", source_id=created[0],
            fact=(f"Classification disagreement: structured fields say {det_type} "
                  f"({det_basis}); document text reads as {llm_type} (confidence {llm_conf}). "
                  f"The deterministic result stands; the disagreement is recorded for review."),
            value={"deterministic": det_type, "llm": llm_type, "llm_confidence": llm_conf},
            agent=AGENT, confidence=0.5, at=as_of,
        ).evidence_id)

        if _is_material_or_risky(session, ob):
            status, next_action, agent = "ESCALATED", "REVIEW_CLASSIFICATION", "ControllerService"
            advance(session, ob, risk_level="HIGH", at=as_of)

    advance(session, ob, stage="CLASSIFIED", next_action=next_action, agent=agent,
            purchase_type=det_type, at=as_of)

    log_run(session, agent_name=AGENT, action="classify", status=status,
            obligation_id=ob.obligation_id,
            facts_used=[f"deterministic={det_type} via {det_basis}",
                        f"llm={llm_type}@{llm_conf}"],
            decision_summary=f"Authoritative classification {det_type}"
                             + (" (LLM disagrees)" if conflict else ""),
            uncertainties=([f"LLM reads this as {llm_type}, not {det_type}"] if conflict else []),
            output_summary=f"next={next_action} -> {agent}",
            output_record_ids=created, at=as_of)
    return ob


def _is_material_or_risky(session, ob) -> bool:
    if ob.risk_level == "HIGH":
        return True
    thresholds = config(session, "approval_thresholds")
    limit = money(thresholds.get("controller_review", "25000.00"))
    if ob.po_id:
        po = session.get(CompanyPurchaseOrder, ob.po_id)
        if po and money(po.approved_total) >= limit:
            return True
    return False
