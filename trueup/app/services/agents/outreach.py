"""Outreach Agent — asks one person for one specific fact.

Routing is bottom-up: the person closest to the transaction is asked first, and
the Controller is the last resort, not the first. Asking the Controller to chase
a missing goods receipt is how finance automation becomes finance overhead.

The hard rule: silence is not evidence. An unanswered request leaves the fact
MISSING and escalates. It never becomes an assumed value.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import CompanyPurchaseOrder, CompanyVendor, TrueupObligation
from app.repositories.contracts import effective_version
from app.repositories.runs import log_run
from app.services.agents.common import add_evidence, advance, config, evidence_for, vendor_name
from app.services.llm import get_llm
from app.services.simulator.clock import close_cutoff

AGENT = "OutreachAgent"

REASONS = {
    "MISSING_RECEIPT": ("PO_OWNER", "Confirm goods/services received in the period"),
    "MISSING_USAGE": ("SERVICE_OWNER", "Provide measured usage for the service period"),
    "RATE_AMBIGUITY": ("PROCUREMENT_OWNER", "Confirm the rate currently in force under the contract"),
    "CONTRACT_PO_CONFLICT": ("PROCUREMENT_OWNER", "Resolve the contract vs PO pricing conflict"),
    "AP_MATCH_AMBIGUITY": ("AP_OWNER", "Confirm whether this period is already invoiced"),
    "UNKNOWN_MERCHANT": ("CARDHOLDER", "Identify the merchant and business purpose"),
    "MISSING_BUSINESS_PURPOSE": ("CARDHOLDER", "Provide business purpose and GL coding"),
    "DISPUTED_CHARGE": ("CARDHOLDER", "Confirm the status of the disputed charge"),
    "UNCLEAR_SERVICE_PERIOD": ("VENDOR_BILLING_CONTACT", "Confirm the service period billed"),
    "UNEXPLAINED_VARIANCE": ("CONTROLLER", "Explain the variance between accrual and invoice"),
}

# Bottom-up escalation order. Outreach starts at the row matching the reason and
# only walks upward if that person cannot answer.
LADDER = ["AP_OWNER", "SERVICE_OWNER", "PO_OWNER", "PROCUREMENT_OWNER",
          "CARDHOLDER", "VENDOR_BILLING_CONTACT", "CONTROLLER"]


def infer_reason(session: Session, ob: TrueupObligation) -> str:
    types = {e.evidence_type for e in evidence_for(session, ob.obligation_id)}
    if ob.invoice_status == "AMBIGUOUS":
        return "AP_MATCH_AMBIGUITY"
    if "CONTRACT_PO_CONFLICT" in types:
        return "CONTRACT_PO_CONFLICT"
    if any(t.endswith("_MISSING") for t in types):
        return "RATE_AMBIGUITY"
    if "NON_PO_DISPUTED" in types:
        return "DISPUTED_CHARGE"
    if ob.purchase_type == "USAGE_BASED" and "USAGE_QUANTITY" not in types:
        return "MISSING_USAGE"
    if ob.purchase_type == "RECEIPT_BASED" and "RECEIPT_QUANTITY" not in types:
        return "MISSING_RECEIPT"
    return "UNCLEAR_SERVICE_PERIOD"


def run(
    session: Session,
    obligation_id: str,
    as_of: dt.datetime | None = None,
    reason: str | None = None,
    fixture_replies: dict[str, str] | None = None,
) -> TrueupObligation:
    ob = session.get(TrueupObligation, obligation_id)
    as_of = as_of or close_cutoff(ob.period)
    reason = reason or infer_reason(session, ob)
    role, ask = REASONS.get(reason, ("CONTROLLER", "Review this obligation"))
    recipient = _resolve_recipient(session, ob, role)

    msg = get_llm().draft_outreach(reason, role, {
        "period": ob.period, "vendor_name": vendor_name(session, ob.vendor_id),
        "ask": ask, "obligation_id": ob.obligation_id,
    })

    created = [add_evidence(
        session, obligation_id=ob.obligation_id, evidence_type="OUTREACH_SENT",
        source_table="company_config", source_id=recipient["person_id"],
        fact=(f"Requested '{ask}' from {recipient['name']} ({role}) regarding {reason}. "
              f"Subject: {msg.get('subject','')}"),
        value={"reason": reason, "role": role, "recipient": recipient,
               "subject": msg.get("subject"), "body": msg.get("body")},
        agent=AGENT, at=as_of,
    ).evidence_id]

    reply = (fixture_replies or {}).get(reason)
    if reply:
        parsed = get_llm().parse_outreach_reply(reply, ask)
        if parsed.get("answered"):
            conf = float(parsed.get("confidence") or 0.6)
            created.append(add_evidence(
                session, obligation_id=ob.obligation_id, evidence_type="OUTREACH_REPLY",
                source_table="company_config", source_id=recipient["person_id"],
                fact=f"{recipient['name']} replied: {reply.strip()[:300]}",
                value={"reason": reason, "answered": True, "value": parsed.get("value"),
                       "raw_reply": reply},
                agent=AGENT, confidence=conf, at=as_of,
            ).evidence_id)

            # Promote the answer to the fact that was actually missing, attributed
            # to the person who supplied it. Without this the reply would be
            # decorative: the estimator would still have nothing to bind.
            promoted = {"MISSING_USAGE": "USAGE_QUANTITY",
                        "MISSING_RECEIPT": "RECEIPT_QUANTITY"}.get(reason)
            if promoted and parsed.get("value"):
                created.append(add_evidence(
                    session, obligation_id=ob.obligation_id, evidence_type=promoted,
                    source_table="company_config", source_id=recipient["person_id"],
                    fact=(f"{promoted.replace('_', ' ').lower()} of {parsed['value']} confirmed by "
                          f"{recipient['name']} ({role}) in response to a TrueUp request. "
                          f"Human-attested rather than system-metered; confidence is lower than a "
                          f"meter reading and the workpaper records the source."),
                    value={"quantity": str(parsed["value"]), "source": "OUTREACH",
                           "confirmed_by": recipient["person_id"], "reason": reason},
                    agent=AGENT, confidence=conf, at=as_of,
                ).evidence_id)
            advance(session, ob, stage="OUTREACH_ANSWERED", next_action="GATHER_EVIDENCE",
                    agent="EvidenceAgent", at=as_of)
            log_run(session, agent_name=AGENT, action="outreach", status="OK",
                    obligation_id=ob.obligation_id,
                    facts_used=[f"reason={reason}", f"role={role}"],
                    decision_summary=f"{recipient['name']} supplied the requested fact",
                    output_summary="re-running evidence gathering with the new fact",
                    output_record_ids=created, at=as_of)
            return ob

    # No reply. This is explicitly NOT evidence of anything.
    created.append(add_evidence(
        session, obligation_id=ob.obligation_id, evidence_type="OUTREACH_UNANSWERED",
        source_table="company_config", source_id=recipient["person_id"],
        fact=(f"No response from {recipient['name']} ({role}) regarding {reason}. "
              f"Absence of a reply is not evidence; the fact remains unknown and the item "
              f"is escalated rather than estimated."),
        value={"reason": reason, "role": role, "answered": False},
        agent=AGENT, confidence=0.0, at=as_of,
    ).evidence_id)
    advance(session, ob, stage="OUTREACH_UNANSWERED", next_action="CONTROLLER_REVIEW",
            agent="ControllerService", risk_level="HIGH", at=as_of)
    log_run(session, agent_name=AGENT, action="outreach", status="ESCALATED",
            obligation_id=ob.obligation_id,
            facts_used=[f"reason={reason}", f"role={role}", f"recipient={recipient['name']}"],
            decision_summary="Request unanswered; fact still missing",
            uncertainties=[f"{ask} is unknown"],
            output_summary="escalated to Controller without an assumed value",
            output_record_ids=created, at=as_of)
    return ob


def _resolve_recipient(session, ob, role) -> dict:
    people = config(session, "people")
    ownership = config(session, "ownership_map")

    if role == "VENDOR_BILLING_CONTACT":
        v = session.get(CompanyVendor, ob.vendor_id)
        return {"person_id": ob.vendor_id, "name": v.vendor_name if v else ob.vendor_id,
                "email": (v.billing_contact_email if v else None), "role": role}

    pid = None
    if role == "PO_OWNER" and ob.po_id:
        po = session.get(CompanyPurchaseOrder, ob.po_id)
        pid = po.po_owner_id if po else None
    elif role in ("SERVICE_OWNER", "PROCUREMENT_OWNER") and ob.contract_id:
        c = effective_version(session, ob.contract_id, ob.service_start_date, ob.service_end_date)
        if c:
            pid = c.service_owner_id if role == "SERVICE_OWNER" else c.procurement_owner_id
    pid = pid or ownership.get(role) or ownership.get("CONTROLLER")
    p = people.get(pid, {})
    return {"person_id": pid, "name": p.get("name", pid), "email": p.get("email"), "role": role}
