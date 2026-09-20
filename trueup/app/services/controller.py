"""Controller Workspace — where human judgement enters the record.

Every decision writes an evidence card and an agent-run entry, because
'the Controller approved it' is itself an auditable fact that must survive the
conversation in which it was said.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import TrueupLearningRule, TrueupObligation, TrueupWorkpaper
from app.money import money
from app.repositories.runs import log_run
from app.schemas.rules import parse_candidate
from app.services.agents.common import add_evidence, advance, config
from app.services.simulator.clock import close_cutoff

AGENT = "ControllerService"

DECISIONS = ("APPROVE", "APPROVE_WITH_ADJUSTMENT", "REJECT", "REQUEST_EVIDENCE")


def decide(
    session: Session,
    obligation_id: str,
    decision: str,
    *,
    adjusted_amount=None,
    notes: str = "",
    approver: str = "P-CONTROLLER",
    at: dt.datetime | None = None,
) -> TrueupWorkpaper | None:
    ob = session.get(TrueupObligation, obligation_id)
    if ob is None:
        raise ValueError(f"no obligation {obligation_id!r}")
    at = at or close_cutoff(ob.period)
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    people = config(session, "people")
    who = people.get(approver, {}).get("name", approver)

    if decision not in DECISIONS:
        raise ValueError(f"unknown controller decision {decision!r}")

    if wp is None:
        advance(session, ob, stage="CONTROLLER_REVIEWED", next_action="CLOSE_BLOCKED",
                agent=None, accrual_status="BLOCKED", at=at)
        log_run(session, agent_name=AGENT, action="decide", status="OK",
                obligation_id=obligation_id, decision_summary=f"{who}: {decision} (no workpaper)",
                output_summary=notes, at=at)
        return None

    original = money(wp.proposed_amount)

    if decision == "APPROVE":
        wp.controller_decision = "APPROVED"
        wp.status = "APPROVED"
        next_action, agent, accrual = "POST_ENTRY", "JournalEntryService", "APPROVED"
        summary = f"{who} approved {original} as proposed"

    elif decision == "APPROVE_WITH_ADJUSTMENT":
        new_amount = money(adjusted_amount)
        wp.controller_decision = "APPROVED_WITH_ADJUSTMENT"
        wp.proposed_amount = new_amount
        wp.calculation_expression = (
            f"{wp.calculation_expression} | Controller adjustment to {new_amount}"
        )
        inputs = dict(wp.calculation_inputs_json or {})
        inputs["controller_adjustment"] = {
            "from": str(original), "to": str(new_amount), "by": who, "notes": notes}
        wp.calculation_inputs_json = inputs
        wp.journal_entry_json = _rebalance(wp.journal_entry_json, new_amount)
        wp.status = "APPROVED"
        next_action, agent, accrual = "POST_ENTRY", "JournalEntryService", "APPROVED"
        summary = f"{who} adjusted the accrual from {original} to {new_amount}"

    elif decision == "REJECT":
        wp.controller_decision = "REJECTED"
        wp.status = "REJECTED"
        next_action, agent, accrual = "CLOSE_NO_ACCRUAL", None, "NO_ACCRUAL"
        summary = f"{who} rejected the proposed accrual of {original}"
        ob.resolved_at = at

    else:  # REQUEST_EVIDENCE
        wp.controller_decision = "EVIDENCE_REQUESTED"
        wp.status = "DRAFT"
        next_action, agent, accrual = "REQUEST_MISSING_FACT", "OutreachAgent", "PROPOSED"
        summary = f"{who} requested further evidence before approving"

    wp.controller_notes = notes
    wp.updated_at = at
    session.flush()

    ev = add_evidence(
        session, obligation_id=obligation_id, evidence_type="CONTROLLER_DECISION",
        source_table="trueup_workpapers", source_id=wp.workpaper_id,
        fact=f"{summary}. Notes: {notes or '(none)'}",
        value={"decision": decision, "approver": approver, "approver_name": who,
               "original_amount": str(original), "final_amount": str(money(wp.proposed_amount)),
               "notes": notes},
        agent=AGENT, at=at,
    )
    advance(session, ob, stage="CONTROLLER_REVIEWED", next_action=next_action, agent=agent,
            accrual_status=accrual, at=at)
    log_run(session, agent_name=AGENT, action="decide", status="OK",
            obligation_id=obligation_id, workpaper_id=wp.workpaper_id,
            facts_used=[f"policy_decision={wp.policy_decision}", f"proposed={original}"],
            decision_summary=summary, output_summary=f"workpaper -> {wp.status}; next={next_action}",
            output_record_ids=[ev.evidence_id, wp.workpaper_id], at=at)
    return wp


def decide_rule(
    session: Session,
    learning_id: str,
    decision: str,
    *,
    approver: str = "P-CONTROLLER",
    notes: str = "",
    at: dt.datetime | None = None,
) -> TrueupLearningRule:
    """Approve, reject or revoke a learned rule. Only this call can set ACTIVE."""
    lr = session.get(TrueupLearningRule, learning_id)
    if lr is None:
        raise ValueError(f"no learning record {learning_id!r}")
    at = at or dt.datetime.now()
    people = config(session, "people")
    who = people.get(approver, {}).get("name", approver)

    if decision == "APPROVE_RULE":
        if lr.status != "REPLAY_PASSED":
            raise ValueError(
                f"cannot activate {learning_id}: status is {lr.status}, not REPLAY_PASSED. "
                "A rule must pass historical replay before a Controller can activate it."
            )
        parse_candidate(lr.candidate_rule_json)
        lr.status, lr.approved_by = "ACTIVE", approver
        summary = f"{who} activated rule {lr.candidate_rule_json.get('rule_key')}"
    elif decision == "REJECT_RULE":
        lr.status, lr.approved_by = "REJECTED", approver
        summary = f"{who} rejected the candidate rule"
    elif decision == "REVOKE_RULE":
        lr.status, lr.approved_by = "REVOKED", approver
        summary = f"{who} revoked a previously active rule"
    else:
        raise ValueError(f"unknown rule decision {decision!r}")

    lr.updated_at = at
    session.flush()

    add_evidence(
        session, obligation_id=lr.obligation_id, evidence_type="CONTROLLER_RULE_DECISION",
        source_table="trueup_learning_rules", source_id=learning_id,
        fact=f"{summary}. Notes: {notes or '(none)'}",
        value={"decision": decision, "approver": approver, "status": lr.status, "notes": notes},
        agent=AGENT, at=at,
    )
    log_run(session, agent_name=AGENT, action="decide_rule", status="OK",
            obligation_id=lr.obligation_id,
            facts_used=[f"replay={((lr.replay_result_json or {}).get('verdict'))}"],
            decision_summary=summary, output_summary=f"learning rule {learning_id} -> {lr.status}",
            output_record_ids=[learning_id], at=at)
    return lr


def _rebalance(je: dict | None, amount) -> dict:
    je = dict(je or {})
    lines = []
    for l in je.get("lines", []):
        l = dict(l)
        if money(l.get("debit", 0)) != 0:
            l["debit"] = str(money(amount))
        if money(l.get("credit", 0)) != 0:
            l["credit"] = str(money(amount))
        lines.append(l)
    je["lines"] = lines
    return je
