"""The run log and the handoffs of one obligation, read straight from the rows the agents wrote.

Nothing here is a template for a case: every entry is one `trueup_agent_runs` row, and every handoff
is one verifier row plus the record its producing agent wrote. Titles are labels for an agent's
action; the sentences, numbers, quotes and ids come from the rows. A case that has not run has no
rows, so its log and its handoffs are empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.ingestion import FileDecision, IngestionResult
from trueup.agents.selection_override import AGENT_NAME as OVERRIDE_AGENT
from trueup.ingest.manifest import FileUniverse
from trueup.service import models as v
from trueup.store import enums as e
from trueup.store import models as m
from trueup.verification.models import POLICY_VERSION, ActionProposal, ActionType

STAGES = ("Ingestion", "Evidence", "Obligation", "Estimation", "Verification")
STAGE_AGENTS: dict[str, frozenset[str]] = {
    "Ingestion": frozenset({"invoice_lookup", "ingestion"}),
    "Evidence": frozenset({"evidence"}),
    "Obligation": frozenset({"classification"}),
    "Estimation": frozenset({"estimation"}),
    "Verification": frozenset({"policy"}),
}
AGENT_STAGE = {agent: stage for stage, agents in STAGE_AGENTS.items() for agent in agents}

_KIND = {
    "verifier": "VERIFICATION",
    "reviewer": "REVIEW",
    "controller_workspace": "CONTROLLER",
    OVERRIDE_AGENT: "HUMAN_OVERRIDE",
    "orchestrator": "SYSTEM",
}
_METHOD = {"verifier": "CODE", OVERRIDE_AGENT: "HUMAN", "controller_workspace": "HUMAN"}

# A short label for what each agent's action is. The sentences shown next to it are the row's own.
_TITLES = {
    ("invoice_lookup", "search_ap"): "Invoice lookup searched accounts payable",
    ("ingestion", "select_files"): "Ingestion selected files",
    ("evidence", "extract_facts"): "Evidence extracted facts",
    ("classification", "classify_purchase"): "Classification chose the purchase type",
    ("estimation", "estimate_accrual"): "Estimation computed the accrual",
    ("policy", "verify_policy"): "Policy checked the accrual",
    ("reviewer", "review"): "Reviewer checked the workpaper",
    ("journal_entry_service", "draft_entry"): "Journal entry service drafted the entry",
    ("journal_entry_service", "post_simulated"): "Journal entry service posted the entry",
    ("journal_entry_service", "post_reversal"): "Journal entry service posted the reversal",
    ("outreach", "send_outreach"): "Outreach asked the owner",
    ("outreach", "process_reply"): "Outreach processed a reply",
    ("controller_workspace", "record_decision"): "Controller decided",
    ("reconciliation", "match_invoice"): "Reconciliation matched the invoice",
    ("reconciliation", "reconcile"): "Reconciliation graded the accrual",
    ("learning", "evaluate"): "Learning evaluated the miss",
    ("learning", "record_outcome"): "Learning recorded the outcome",
    (OVERRIDE_AGENT, "deselect_files"): "A person changed the file selection",
}

# The agent that hands work on from each state, and the agent that takes it up.
_FROM_AGENT = {
    "DETECTED/SEARCH_AP": "detection",
    "SEARCHING_AP/SEARCH_AP": "invoice_lookup",
    "GATHERING_EVIDENCE/GATHER_EVIDENCE": "evidence",
    "CLASSIFYING/CLASSIFY": "classification",
    "ESTIMATING/ESTIMATE": "estimation",
    "ESTIMATING/VERIFY_POLICY": "policy",
    "AWAITING_OUTREACH/SEND_OUTREACH": "outreach",
    "AWAITING_CONTROLLER/CONTROLLER_REVIEW": "controller_workspace",
    "BLOCKED/CONTROLLER_REVIEW": "controller_workspace",
    "READY_TO_DRAFT/DRAFT_ENTRY": "journal_entry_service",
    "AWAITING_ACTUAL_INVOICE/WAIT_FOR_INVOICE": "reconciliation",
    "RECONCILING/MATCH_AND_TRUE_UP": "reconciliation",
    "RECONCILING/EVALUATE_LEARNING": "learning",
}
_TO_AGENT = {
    "SEARCHING_AP/SEARCH_AP": "invoice_lookup",
    "GATHERING_EVIDENCE/GATHER_EVIDENCE": "ingestion",
    "CLASSIFYING/CLASSIFY": "classification",
    "ESTIMATING/ESTIMATE": "estimation",
    "ESTIMATING/VERIFY_POLICY": "policy",
    "AWAITING_OUTREACH/SEND_OUTREACH": "outreach",
    "AWAITING_CONTROLLER/CONTROLLER_REVIEW": "controller_workspace",
    "BLOCKED/CONTROLLER_REVIEW": "controller_workspace",
    "READY_TO_DRAFT/DRAFT_ENTRY": "journal_entry_service",
    "AWAITING_ACTUAL_INVOICE/WAIT_FOR_INVOICE": "reconciliation",
    "RECONCILING/MATCH_AND_TRUE_UP": "reconciliation",
    "RECONCILING/EVALUATE_LEARNING": "learning",
    "CLOSED/NONE": "orchestrator",
    "CLOSED_NO_ACCRUAL/NONE": "orchestrator",
}


def run_number(run_id: str) -> int:
    return int(run_id.rsplit("-", 1)[-1])


def iso(moment: datetime) -> str:
    moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class Trace:
    """Everything one obligation's log, handoffs and stage checks are read from."""

    ob: m.TrueUpObligation
    runs: list[m.TrueUpAgentRun]
    cards: list[m.TrueUpEvidence]
    wp: m.TrueUpWorkpaper | None
    universe: FileUniverse
    durations: dict[str, int] = field(default_factory=dict)
    entries: list[v.LogEntry] = field(default_factory=list)
    handoffs: list[v.Handoff] = field(default_factory=list)
    seq_of_run: dict[str, int] = field(default_factory=dict)

    def card(self, evidence_id: str) -> m.TrueUpEvidence | None:
        return next((c for c in self.cards if c.evidence_id == evidence_id), None)

    def rows(self, agent: str, action: str | None = None) -> list[m.TrueUpAgentRun]:
        return [
            r for r in self.runs if r.agent_name == agent and (action is None or r.action == action)
        ]

    def latest(self, agent: str, action: str | None = None) -> m.TrueUpAgentRun | None:
        rows = self.rows(agent, action)
        return rows[-1] if rows else None


def case_runs(session: Session, obligation_id: str) -> list[m.TrueUpAgentRun]:
    return sorted(
        session.scalars(
            select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.obligation_id == obligation_id)
        ),
        key=lambda r: run_number(r.run_id),
    )


def build_trace(
    session: Session,
    ob: m.TrueUpObligation,
    universe: FileUniverse,
    durations: dict[str, int] | None = None,
) -> Trace:
    """Read the case's rows and build its log entries and handoffs, in run order."""
    cards = list(
        session.scalars(
            select(m.TrueUpEvidence)
            .where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
            .order_by(m.TrueUpEvidence.evidence_id)
        )
    )
    wp = None
    if ob.current_workpaper_id:
        wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
    trace = Trace(
        ob=ob,
        runs=case_runs(session, ob.obligation_id),
        cards=cards,
        wp=wp,
        universe=universe,
        durations=durations or {},
    )
    _build_handoffs(trace)
    _build_entries(trace)
    if _not_started(ob):
        # Detection's own gate row exists, but the case has not run yet: nothing to show.
        trace.entries.clear()
        trace.handoffs.clear()
    return trace


def _not_started(ob: m.TrueUpObligation) -> bool:
    return (ob.workflow_stage, ob.next_action) in {
        (e.WorkflowStage.DETECTED, e.NextAction.SEARCH_AP),
        (e.WorkflowStage.SEARCHING_AP, e.NextAction.SEARCH_AP),
    }


# ---- verification -----------------------------------------------------------------------------


def verification_of(row: m.TrueUpAgentRun) -> v.LogVerification | None:
    if row.agent_name != "verifier":
        return None
    facts = row.facts_used_json or []
    result = next((f["result"] for f in facts if f.get("kind") == "verification_result"), None)
    if result is None:
        return None
    applied = [c for c in result["checks"] if not c.get("skipped")]
    return v.LogVerification(
        verdict=result["verdict"],
        passed=sum(1 for c in applied if c["passed"]),
        total=len(applied),
        policy_version=result.get("policy_version", POLICY_VERSION),
        checks=[
            v.LogCheck(
                check_id=c["check_id"],
                passed=c["passed"],
                sentence=c["detail"],
                expected=c.get("expected"),
                actual=c.get("actual"),
            )
            for c in applied
        ],
    )


def _routing(row: m.TrueUpAgentRun) -> dict[str, str] | None:
    return next((f for f in row.facts_used_json or [] if f.get("kind") == "routing"), None)


def _proposal(row: m.TrueUpAgentRun) -> dict[str, Any] | None:
    fact = next((f for f in row.facts_used_json or [] if f.get("kind") == "action_proposal"), None)
    return fact.get("proposal") if fact else None


# ---- handoffs ---------------------------------------------------------------------------------


def _build_handoffs(trace: Trace) -> None:
    pending: list[tuple[float, v.Handoff]] = []
    index = {r.run_id: i for i, r in enumerate(trace.runs)}
    for row in trace.runs:
        if row.agent_name != "verifier":
            continue
        route = _routing(row)
        proposal = _proposal(row)
        if route is None or route["from"] == route["routed"] or route["routed"] == "none":
            continue
        producer_agent = _FROM_AGENT.get(route["from"], "orchestrator")
        producer = _nearest(trace, producer_agent, index[row.run_id], index)
        kind, record, ids = _record_of(trace, route["from"], producer)
        pending.append(
            (
                run_number(row.run_id),
                v.Handoff(
                    seq=0,
                    at=iso(row.created_at),
                    from_agent=producer_agent,
                    to_agent=_TO_AGENT.get(route["routed"], "orchestrator"),
                    stage_from=route["from"],
                    stage_to=route["routed"],
                    payload_kind=kind,
                    payload={"proposal": proposal, "record": record},
                    run_id=run_number(producer.run_id) if producer else None,
                    run_ref=producer.run_id if producer else None,
                    record_ids=ids,
                    verification=verification_of(row),
                ),
            )
        )
    for row in trace.rows("ingestion", "select_files"):
        pending.append((run_number(row.run_id) + 0.5, _selection_handoff(trace, row)))
    pending.sort(key=lambda item: item[0])
    for number, (_, handoff) in enumerate(pending, start=1):
        handoff.seq = number
        trace.handoffs.append(handoff)


def _nearest(
    trace: Trace, agent: str, position: int, index: dict[str, int]
) -> m.TrueUpAgentRun | None:
    rows = [r for r in trace.runs if r.agent_name == agent]
    if not rows:
        return None
    return min(rows, key=lambda r: (abs(index[r.run_id] - position), -index[r.run_id]))


def _selection_handoff(trace: Trace, row: m.TrueUpAgentRun) -> v.Handoff:
    """Ingestion to Evidence is not a workflow edge, so it has no gate; the record is still real."""
    files = {f.file_id: f for f in trace.universe.files}
    decisions = [FileDecision(**d) for d in row.facts_used_json or []]
    override = next(
        (
            r
            for r in trace.rows(OVERRIDE_AGENT, "deselect_files")
            if run_number(r.run_id) > run_number(row.run_id)
        ),
        None,
    )
    removed = set(override.output_record_ids_json or []) if override else set()
    proposal = ActionProposal(
        action_type=ActionType.SELECT_FILES,
        actor="ingestion",
        obligation_id=trace.ob.obligation_id,
        period=trace.ob.period,
        policy_version=POLICY_VERSION,
        stage_from="GATHERING_EVIDENCE/GATHER_EVIDENCE",
        stage_to="GATHERING_EVIDENCE/GATHER_EVIDENCE",
    ).model_dump(mode="json")
    record = {
        "judge": row.decision_summary.rsplit(" using the ", 1)[-1].rstrip("."),
        "files": [
            {
                "file_id": d.file_id,
                "name": files[d.file_id].name if d.file_id in files else d.file_id,
                "kind": files[d.file_id].kind if d.file_id in files else None,
                "selected": d.selected and d.file_id not in removed,
                "removed_by_user": d.file_id in removed,
                "reason": d.reason,
            }
            for d in decisions
        ],
    }
    return v.Handoff(
        seq=0,
        at=iso(row.created_at),
        from_agent="ingestion",
        to_agent="evidence",
        stage_from="GATHERING_EVIDENCE/GATHER_EVIDENCE",
        stage_to="GATHERING_EVIDENCE/GATHER_EVIDENCE",
        payload_kind="IngestionResult",
        payload={"proposal": proposal, "record": record},
        run_id=run_number(row.run_id),
        run_ref=row.run_id,
        record_ids=[d.file_id for d in decisions if d.selected and d.file_id not in removed],
        verification=None,
    )


def _card_record(card: m.TrueUpEvidence) -> dict[str, Any]:
    value = card.value_json if isinstance(card.value_json, dict) else {}
    return {
        "evidence_id": card.evidence_id,
        "type": card.evidence_type.value,
        "fact": card.fact,
        "key": value.get("key"),
        "number": value.get("number"),
        "source_id": card.source_id,
        "file": value.get("file"),
        "quote": card.source_excerpt,
        "confidence": format(card.confidence, "f"),
        "status": card.status.value,
    }


def _record_of(
    trace: Trace, frm: str, producer: m.TrueUpAgentRun | None
) -> tuple[str, dict[str, Any], list[str]]:
    ob, wp = trace.ob, trace.wp
    generic = {
        "summary": producer.decision_summary if producer else None,
        "facts_used": producer.facts_used_json if producer else [],
        "output_ids": list(producer.output_record_ids_json or []) if producer else [],
    }
    if frm == "DETECTED/SEARCH_AP":
        record = {
            "obligation_id": ob.obligation_id,
            "vendor_id": ob.vendor_id,
            "period": ob.period,
            "contract_id": ob.contract_id,
            "po_id": ob.po_id,
            "non_po_group_key": ob.non_po_group_key,
            "service_start_date": ob.service_start_date.isoformat(),
            "service_end_date": ob.service_end_date.isoformat(),
        }
        return "Obligation", record, [ob.obligation_id]
    if frm == "SEARCHING_AP/SEARCH_AP":
        record = {
            "invoice_status": ob.invoice_status.value,
            "matched_invoice_id": ob.matched_invoice_id,
            **generic,
        }
        return "InvoiceLookupResult", record, list(generic["output_ids"])
    if frm == "GATHERING_EVIDENCE/GATHER_EVIDENCE":
        live = [c for c in trace.cards if c.source_table == "document"]
        record = {"summary": generic["summary"], "cards": [_card_record(c) for c in live]}
        return "EvidenceCards", record, [c.evidence_id for c in live]
    if frm == "CLASSIFYING/CLASSIFY":
        record = {"purchase_type": ob.purchase_type.value, "signals": generic["facts_used"]}
        record["summary"] = generic["summary"]
        return "Classification", record, list(generic["output_ids"])
    if frm == "ESTIMATING/ESTIMATE":
        if wp is None:
            return "EstimationOutcome", generic, list(generic["output_ids"])
        record = {
            "workpaper_id": wp.workpaper_id,
            "method": wp.estimation_method.value,
            "amount": format(wp.proposed_amount, "f"),
            "currency": wp.currency,
            "expression": wp.calculation_expression,
            "inputs": wp.calculation_inputs_json,
            "proposed_entry": wp.journal_entry_json,
        }
        return "Workpaper", record, [wp.workpaper_id]
    if frm == "ESTIMATING/VERIFY_POLICY":
        record = {
            "decision": wp.policy_decision.value if wp else None,
            "summary": wp.policy_summary if wp else generic["summary"],
            "rules": generic["facts_used"],
        }
        return "PolicyResult", record, [wp.workpaper_id] if wp else []
    if frm == "READY_TO_DRAFT/DRAFT_ENTRY":
        record = {"entries": wp.journal_entry_json if wp else None, **generic}
        return "DraftedEntries", record, [wp.workpaper_id] if wp else []
    if frm in ("AWAITING_CONTROLLER/CONTROLLER_REVIEW", "BLOCKED/CONTROLLER_REVIEW"):
        decisions = [
            _card_record(c)
            for c in trace.cards
            if c.evidence_type == e.EvidenceCardType.CONTROLLER_DECISION
        ]
        return (
            "ControllerDecision",
            {**generic, "decisions": decisions},
            list(generic["output_ids"]),
        )
    if frm == "AWAITING_OUTREACH/SEND_OUTREACH":
        messages = [
            _card_record(c)
            for c in trace.cards
            if c.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE
        ]
        return (
            "OutreachExchange",
            {**generic, "messages": messages},
            [m_["evidence_id"] for m_ in messages],
        )
    return "AgentRecord", generic, list(generic["output_ids"])


# ---- log entries ------------------------------------------------------------------------------


def _build_entries(trace: Trace) -> None:
    stage_of: dict[str, tuple[str, str]] = {}
    for handoff in trace.handoffs:
        if handoff.run_ref:
            stage_of.setdefault(handoff.run_ref, (handoff.stage_from, handoff.stage_to))
    for seq, row in enumerate(trace.runs, start=1):
        trace.seq_of_run[row.run_id] = seq
        trace.entries.append(_entry(trace, row, seq, stage_of))


def _entry(
    trace: Trace, row: m.TrueUpAgentRun, seq: int, stage_of: dict[str, tuple[str, str]]
) -> v.LogEntry:
    kind = _KIND.get(row.agent_name, "AGENT")
    verification = verification_of(row)
    frm, to = stage_of.get(row.run_id, (None, None))
    route = _routing(row)
    if route is not None:
        frm, to = route["from"], route["routed"]
    return v.LogEntry(
        seq=seq,
        run_id=run_number(row.run_id),
        run_ref=row.run_id,
        at=iso(row.created_at),
        agent=row.agent_name,
        action=row.action,
        kind=kind,
        method=_method(row),
        stage_from=frm,
        stage_to=to,
        title=_title(row, route),
        summary=row.decision_summary,
        detail=v.LogDetail(
            facts_used=list(row.facts_used_json or []),
            uncertainties=[str(u) for u in row.uncertainties_json or []],
            input_ids=[str(i) for i in row.input_record_ids_json or []],
            output_ids=[str(i) for i in row.output_record_ids_json or []],
            sources=_sources(trace, row),
            rules=_rules(row, verification),
            duration_ms=trace.durations.get(row.run_id),
        ),
        verification=verification,
    )


def _title(row: m.TrueUpAgentRun, route: dict[str, str] | None) -> str:
    if row.agent_name == "verifier" and route is not None:
        moved = "held" if route["from"] == route["routed"] else "moved"
        return f"Verification gate {moved} {route['from']} to {route['routed']}"
    if (row.agent_name, row.action) == ("outreach", "send_outreach") and _to_vendor(row):
        return "Outreach asked the vendor"
    return _TITLES.get((row.agent_name, row.action), f"{row.agent_name}: {row.action}")


def _to_vendor(row: m.TrueUpAgentRun) -> bool:
    """A dispute or a variance question goes to the vendor's billing contact, not to an owner."""
    topics = {f.get("topic") for f in row.facts_used_json or [] if isinstance(f, dict)}
    return bool(topics & {"INVOICE_DISPUTE", "VARIANCE_EXPLANATION"})


def _method(row: m.TrueUpAgentRun) -> v.Method | None:
    if row.agent_name in _METHOD:
        return _METHOD[row.agent_name]  # type: ignore[return-value]
    if row.agent_name == "orchestrator":
        return None
    text = f"{row.decision_summary} {row.output_summary}"
    return "LLM" if "llm_judge" in text or "llm_extractor" in text else "CODE"


def _sources(trace: Trace, row: m.TrueUpAgentRun) -> list[v.LogSource]:
    files = {f.file_id: f for f in trace.universe.files}
    found: dict[str, v.LogSource] = {}
    ids = [*(row.input_record_ids_json or []), *(row.output_record_ids_json or [])]
    for fact in row.facts_used_json or []:
        if isinstance(fact, dict):
            if "evidence_id" in fact:
                ids.append(fact["evidence_id"])
            ids += (fact.get("proposal") or {}).get("evidence_ids", [])
            for withdrawn in fact.get("withdrawn_facts", []):
                key = f"{fact.get('removed_file')}:{withdrawn['label']}:{withdrawn['value']}"
                found[key] = v.LogSource(
                    file_name=fact.get("file"),
                    file_id=fact.get("removed_file"),
                    evidence_id=None,
                    quote=withdrawn["quote"],
                )
    if row.agent_name == "ingestion":
        for decision in row.facts_used_json or []:
            entry = files.get(decision.get("file_id", ""))
            if decision.get("selected") and entry is not None:
                found[entry.file_id] = v.LogSource(
                    file_name=entry.name, file_id=entry.file_id, evidence_id=None, quote=None
                )
        return list(found.values())
    for evidence_id in dict.fromkeys(ids):
        card = trace.card(str(evidence_id))
        if card is None or card.source_table != "document":
            continue
        entry = files.get(card.source_id)
        found[card.evidence_id] = v.LogSource(
            file_name=entry.name if entry else (card.value_json or {}).get("file"),
            file_id=card.source_id,
            evidence_id=card.evidence_id,
            quote=card.source_excerpt,
        )
    return list(found.values())


def _rules(row: m.TrueUpAgentRun, verification: v.LogVerification | None) -> list[v.LogRule]:
    if verification is not None:
        return [
            v.LogRule(rule_id=c.check_id, fired=not c.passed, sentence=c.sentence)
            for c in verification.checks
        ]
    if row.agent_name == "policy":
        return [
            v.LogRule(
                rule_id=r["rule_id"], fired=r["status"] == "HIT", sentence=r.get("detail", "")
            )
            for r in row.facts_used_json or []
            if isinstance(r, dict) and "rule_id" in r
        ]
    return []


def selection_from(row: m.TrueUpAgentRun, case_id: str) -> IngestionResult:
    """Rebuild an Ingestion result from its run row."""
    decisions = [FileDecision(**d) for d in row.facts_used_json or []]
    return IngestionResult(
        case_id=case_id,
        files_loaded=len(decisions),
        decisions=decisions,
        judge=row.decision_summary.rsplit(" using the ", 1)[-1].rstrip("."),
    )


def stages_completed(
    runs: list[m.TrueUpAgentRun], ob: m.TrueUpObligation | None = None
) -> list[str]:
    """The stages every one of whose agents has run.

    Evidence reads one file at a time, so it is complete only once the obligation has left the
    gathering state: having read some of the files is not having read them all.
    """
    ran = {r.agent_name for r in runs}
    gathering = ob is not None and ob.workflow_stage == e.WorkflowStage.GATHERING_EVIDENCE
    return [
        stage
        for stage in STAGES
        if STAGE_AGENTS[stage] <= ran and not (stage == "Evidence" and gathering)
    ]
