"""Pure read models over the 13-table store, one per screen.

Nothing here computes an accrual, a policy decision or a variance. Every amount, rule result,
diagnosis and decision is read from the row an agent already wrote, and only formatted here.
The hidden answer keys are never touched; documents come from the agent-visible manifest.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.controller_workspace import (
    REVIEW_STATES,
    build_packet,
    controller_id,
    review_queue,
)
from trueup.agents.document_support import support_gaps
from trueup.agents.selection_override import latest_override
from trueup.close_orchestrator import pending_agent
from trueup.ingest.manifest import CaseEntry, FileEntry, FileUniverse
from trueup.ingest.readers import UnsupportedFile, read_text
from trueup.learning.rules import CandidateRule
from trueup.service import models as v
from trueup.service import outreach_threads, runlog, stagechecks
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.types import coerce_money

HISTORY_PREFIX = "OBL-HIST-"
TWO_PLACES = Decimal("0.01")
_S, _A = e.WorkflowStage, e.NextAction

METHOD_LABELS = {
    e.EstimationMethod.FIXED_CONTRACT_RATE: "Contract rate",
    e.EstimationMethod.USAGE_TIMES_RATE: "Usage times rate",
    e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE: "Received quantity times price",
    e.EstimationMethod.MILESTONE_ACCEPTED_AMOUNT: "Accepted delivery",
    e.EstimationMethod.PREPAID_AMORTIZATION: "Prepaid amortization",
    e.EstimationMethod.HISTORICAL_RUN_RATE: "Historical run rate",
    e.EstimationMethod.NON_PO_BALANCE_SUM: "Non-PO balance",
}
TREATMENT_LABELS = {
    e.PurchaseType.FIXED_RECURRING: "Recurring fixed",
    e.PurchaseType.USAGE_BASED: "Recurring variable",
    e.PurchaseType.RECEIPT_BASED: "One-time fixed",
    e.PurchaseType.MILESTONE_BASED: "One-time variable",
    e.PurchaseType.PREPAID: "Prepaid",
    e.PurchaseType.NON_PO_CARD_SPEND: "Card spend",
    e.PurchaseType.NON_PO_DIRECT_SPEND: "Direct spend",
    e.PurchaseType.UNKNOWN: "Unclassified",
}
ITEM_LABELS = {
    e.PurchaseType.FIXED_RECURRING: "Subscription accrual",
    e.PurchaseType.USAGE_BASED: "Usage accrual",
    e.PurchaseType.RECEIPT_BASED: "Equipment purchase",
    e.PurchaseType.MILESTONE_BASED: "Campaign delivery",
    e.PurchaseType.PREPAID: "Prepaid amortization",
}
CHECK_LABELS = {
    "coverage_period": "Determine period coverage",
    "rate_applied": "Apply the governing rate",
    "credits_and_refunds": "Credits or refunds",
    "prepaid_amounts": "Prepaid amounts",
    "partial_period_offsets": "Partial-period offsets",
    "prior_close_comparison": "Compare to prior close",
}
# Rows that only the run log shows; the case timeline keeps to the working agents.
LOG_ONLY_AGENTS = {"verifier", "reviewer", "human_override", "orchestrator", "ingestion"}
CASE_CATEGORY = "Accruals"
PROFILE_BY_CATEGORY = {
    e.VendorCategory.SAAS: "Software subscription",
    e.VendorCategory.AI_CREDITS: "AI usage",
    e.VendorCategory.MARKETING: "Advertising campaign",
    e.VendorCategory.OTHER: "Equipment supplier",
    e.VendorCategory.CLOUD: "Cloud infrastructure",
    e.VendorCategory.DATA: "Data provider",
    e.VendorCategory.CONSULTING: "Consulting services",
    e.VendorCategory.HARDWARE: "Hardware supplier",
    e.VendorCategory.OFFICE: "Office supplies",
    e.VendorCategory.TRAVEL: "Travel",
}
CATEGORY_LABELS = {
    e.VendorCategory.SAAS: "SaaS",
    e.VendorCategory.AI_CREDITS: "AI credits",
}
AGENT_USES = {
    e.PurchaseType.FIXED_RECURRING: "contract price",
    e.PurchaseType.USAGE_BASED: "usage and contract rate",
    e.PurchaseType.RECEIPT_BASED: "goods receipt and PO price",
    e.PurchaseType.MILESTONE_BASED: "delivery report and budget",
    e.PurchaseType.PREPAID: "paid amount and term",
}


# ---- formatting ---------------------------------------------------------------------------------


def money(value: Any) -> str:
    return format(coerce_money(value).quantize(TWO_PLACES), "f")


def signed(value: Any) -> str:
    amount = coerce_money(value).quantize(TWO_PLACES)
    return f"+{amount:f}" if amount > 0 else f"{amount:f}"


def span_label(start: date, end: date) -> str:
    return f"{start:%b} {start.day} to {end:%b} {end.day}, {end.year}"


def period_label(period: str) -> str:
    year, month = period.split("-")
    return f"{date(int(year), int(month), 1):%B %Y}"


def utc_iso(moment: datetime) -> str:
    return moment.isoformat()


def initials(name: str) -> str:
    words = name.split()
    return (words[0][:2] if len(words) == 1 else "".join(w[0] for w in words[:2])).upper()


# ---- shared lookups -----------------------------------------------------------------------------


def _config(session: Session, key: str) -> Any:
    row = session.get(m.CompanyConfig, key)
    return row.config_value_json if row is not None else None


def _accounts(session: Session) -> dict[str, str]:
    rows = _config(session, "allowed_gl_accounts") or []
    return {r["account_code"]: r["name"] for r in rows}


def _account_label(accounts: dict[str, str], code: str | None) -> str | None:
    if not code:
        return None
    return f"{code} {accounts[code]}" if code in accounts else code


def _runs(session: Session, obligation_id: str) -> list[m.TrueUpAgentRun]:
    return list(
        session.scalars(
            select(m.TrueUpAgentRun)
            .where(m.TrueUpAgentRun.obligation_id == obligation_id)
            .order_by(m.TrueUpAgentRun.created_at, m.TrueUpAgentRun.run_id)
        )
    )


def _latest(runs: list[m.TrueUpAgentRun], agent: str, action: str | None = None):
    for run in reversed(runs):
        if run.agent_name == agent and (action is None or run.action == action):
            return run
    return None


def _workpaper(session: Session, ob: m.TrueUpObligation) -> m.TrueUpWorkpaper | None:
    if not ob.current_workpaper_id:
        return None
    return session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)


def _period_obligations(session: Session, period: str) -> list[m.TrueUpObligation]:
    return list(
        session.scalars(
            select(m.TrueUpObligation)
            .where(m.TrueUpObligation.period == period)
            .where(~m.TrueUpObligation.obligation_id.like(f"{HISTORY_PREFIX}%"))
            .order_by(m.TrueUpObligation.opened_at, m.TrueUpObligation.obligation_id)
        )
    )


def front_stage(session: Session, ob: m.TrueUpObligation) -> v.FrontStage:
    """The screen the case is on: the stage of the agent whose turn is next, else where it rests."""
    agent = pending_agent(session, ob)
    if agent is not None:
        return runlog.AGENT_STAGE.get(agent, "Verification")  # type: ignore[return-value]
    stage, action = ob.workflow_stage, ob.next_action
    if stage in (_S.DETECTED, _S.SEARCHING_AP):
        return "Ingestion"
    if stage == _S.GATHERING_EVIDENCE:
        return "Evidence"
    if stage == _S.CLASSIFYING:
        return "Obligation"
    if (stage, action) == (_S.ESTIMATING, _A.ESTIMATE):
        return "Estimation"
    if stage == _S.AWAITING_OUTREACH:
        sufficient = ob.evidence_status == e.EvidenceStatus.SUFFICIENT
        return "Estimation" if sufficient else "Evidence"
    return "Verification"


def case_status(ob: m.TrueUpObligation) -> v.CaseStatus:
    """A resting status appears only once the case has reached the state that produces it."""
    stage = ob.workflow_stage
    if stage in (_S.CLOSED, _S.CLOSED_NO_ACCRUAL):
        return "Complete"
    if stage == _S.AWAITING_ACTUAL_INVOICE:
        return "Close-ready" if ob.accrual_status == e.AccrualStatus.POSTED_SIMULATED else "Running"
    if stage == _S.AWAITING_CONTROLLER:
        return "Needs review"
    if stage == _S.BLOCKED:
        return "Blocked"
    if stage == _S.AWAITING_OUTREACH:
        return "Waiting"
    if is_pending(ob):
        return "Pending"
    return "Running"


def is_pending(ob: m.TrueUpObligation) -> bool:
    """Detection opened the obligation and no agent has worked it yet."""
    return (ob.workflow_stage, ob.next_action) in {
        (_S.DETECTED, _A.SEARCH_AP),
        (_S.SEARCHING_AP, _A.SEARCH_AP),
    }


def _vendor(session: Session, vendor_id: str) -> m.CompanyVendor:
    return session.get(m.CompanyVendor, vendor_id)


# ---- the close ----------------------------------------------------------------------------------


def close_view(
    session: Session, *, period: str, phase: v.Phase, now: datetime, universe: FileUniverse
) -> v.CloseView:
    people = _config(session, "people") or []
    names = {p["person_id"]: p["name"] for p in people}
    controller = controller_id(session)
    obligations = _period_obligations(session, period)
    rows = [case_row(session, ob, phase=phase, universe=universe) for ob in obligations]
    pending = session.scalars(
        select(m.TrueUpLearningRule).where(
            m.TrueUpLearningRule.status == e.LearningStatus.REPLAY_PASSED
        )
    ).all()
    return v.CloseView(
        period=period,
        period_label=period_label(period),
        phase=phase,
        clock=utc_iso(now),
        controller_id=controller,
        controller_name=names.get(controller, controller),
        people=[v.Person(person_id=p["person_id"], name=p["name"], role=p["role"]) for p in people],
        cases=rows,
        queue_count=len(review_queue(session, now=now)),
        pending_rules=len(pending),
        actions=v.CloseActions(
            can_run_close=phase != "JANUARY" and any(is_pending(ob) for ob in obligations),
            can_advance_to_january=phase == "CLOSED",
            can_advance_to_vendor_reply=phase == "JANUARY" and _has_open_request(session),
        ),
    )


def _has_open_request(session: Session) -> bool:
    """An email is out and its reply has not arrived."""
    return any(
        (card.value_json or {}).get("direction") == "REQUEST"
        for card in session.scalars(
            select(m.TrueUpEvidence).where(
                m.TrueUpEvidence.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE,
                m.TrueUpEvidence.status == e.EvidenceCardStatus.PENDING,
            )
        )
    )


def case_row(
    session: Session, ob: m.TrueUpObligation, *, phase: v.Phase, universe: FileUniverse
) -> v.CaseRow:
    wp = _workpaper(session, ob)
    vendor = _vendor(session, ob.vendor_id)
    trace = runlog.build_trace(session, ob, universe)
    classified = trace.latest("classification") is not None
    return v.CaseRow(
        obligation_id=ob.obligation_id,
        vendor_id=ob.vendor_id,
        vendor_name=vendor.vendor_name,
        initials=initials(vendor.vendor_name),
        item=ITEM_LABELS.get(ob.purchase_type, "Accrual") if classified else "Accrual",
        category=CASE_CATEGORY,
        purchase_type=TREATMENT_LABELS[ob.purchase_type] if classified else "Not classified yet",
        amount=money(wp.proposed_amount) if wp is not None else None,
        stage=front_stage(session, ob),
        status=case_status(ob),
        can_start=phase != "JANUARY" and is_pending(ob),
        current_agent=pending_agent(session, ob),
        stages_completed=runlog.stages_completed(trace.runs),
        log_count=len(trace.entries),
        handoff_count=len(trace.handoffs),
        workflow_stage=ob.workflow_stage.value,
        next_action=ob.next_action.value,
        updated_at=utc_iso(ob.updated_at),
    )


def controller_queue(session: Session, *, now: datetime):
    return review_queue(session, now=now)


# ---- one obligation -----------------------------------------------------------------------------


def obligation_detail(
    session: Session,
    obligation_id: str,
    *,
    universe: FileUniverse,
    seed_dir: Path,
    now: datetime,
    durations: dict[str, int] | None = None,
) -> v.ObligationDetail | None:
    ob = session.get(m.TrueUpObligation, obligation_id)
    if ob is None:
        return None
    wp = _workpaper(session, ob)
    trace = runlog.build_trace(session, ob, universe, durations)
    runs = trace.runs
    accounts = _accounts(session)
    case = _case_for(universe, ob)
    cards = trace.cards
    files = {f.file_id: f for f in universe.files}
    facts = _dedupe_facts(
        [_fact(c, files) for c in cards if c.source_table == "document"]
        if trace.latest("evidence", "extract_facts")
        else []
    )
    ingestion = _ingestion(session, universe, case, now, ob, trace)
    header = _header(session, ob, wp, case, accounts, trace)
    evidence = _evidence(runs, universe, ingestion, facts, seed_dir)
    obligation = _obligation_view(ob, wp, runs, evidence.facts, header)
    estimation = _estimation(session, ob, wp, runs, accounts, header)
    verification = _verification(session, ob, wp, runs, cards, accounts, header, now)
    views = {
        "Ingestion": ingestion,
        "Evidence": evidence,
        "Obligation": obligation,
        "Estimation": estimation,
        "Verification": verification,
    }
    main_agent = {
        "Ingestion": "ingestion",
        "Evidence": "evidence",
        "Obligation": "classification",
        "Estimation": "estimation",
        "Verification": "policy",
    }
    for stage, view in views.items():
        if trace.latest(main_agent[stage]) is not None:
            view.received = stagechecks.received_for(stage, trace)
            view.stage_checks = stagechecks.checks_for(stage, trace, session)
    return v.ObligationDetail(
        header=header,
        ingestion=ingestion,
        evidence=evidence,
        obligation=obligation,
        estimation=estimation,
        verification=verification,
        timeline=[]
        if is_pending(ob)
        else [_timeline(r) for r in runs if r.agent_name not in LOG_ONLY_AGENTS],
        escalation=escalation_of(session, ob),
        outreach_threads=outreach_threads.threads_for(session, ob, runs, now=now),
    )


def _dedupe_facts(facts: list[v.EvidenceFact]) -> list[v.EvidenceFact]:
    """One fact per label, value and source file."""
    seen: set[tuple[str, str, str | None]] = set()
    unique = []
    for fact in facts:
        marker = (fact.label, fact.value, fact.file_id)
        if marker not in seen:
            seen.add(marker)
            unique.append(fact)
    return unique


def escalation_of(session: Session, ob: m.TrueUpObligation) -> v.Escalation | None:
    """Set when the documents a person left selected cannot support the case, and it rests."""
    routed = {
        _S.AWAITING_OUTREACH: "OUTREACH",
        _S.AWAITING_CONTROLLER: "CONTROLLER",
        _S.BLOCKED: "BLOCKED",
    }.get(ob.workflow_stage)
    if routed is None:
        return None
    gaps = support_gaps(session, ob)
    if not gaps:
        return None
    lost = [g.label for g in gaps]
    who = {
        "OUTREACH": "Outreach asks the owner for it.",
        "CONTROLLER": "The Controller decides what happens next.",
        "BLOCKED": "The case is blocked for the Controller.",
    }[routed]
    return v.Escalation(
        reason="INSUFFICIENT_INFORMATION",
        missing=lost,
        message=(
            f"The documents still selected no longer support the {' and '.join(lost)}, so the "
            f"agent will not estimate from what it cannot support. {who}"
        ),
        routed_to=routed,  # type: ignore[arg-type]
    )


def _case_for(universe: FileUniverse, ob: m.TrueUpObligation) -> CaseEntry | None:
    case_id = f"CASE-{ob.obligation_id.removeprefix('OBL-')}"
    return next((c for c in universe.cases if c.case_id == case_id), None)


def _header(
    session: Session,
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper | None,
    case: CaseEntry | None,
    accounts: dict[str, str],
    trace: runlog.Trace,
) -> v.Header:
    vendor = _vendor(session, ob.vendor_id)
    prior = _prior_check(wp)
    classified = trace.latest("classification") is not None
    chips = [f"Vendor {vendor.vendor_id}"]
    if classified:
        chips.insert(0, TREATMENT_LABELS[ob.purchase_type])
    gl = _account_label(accounts, wp.expense_account if wp else None)
    if gl:
        chips.append(f"GL {gl.split(' - ')[0]}")
    title = case.title.removeprefix(vendor.vendor_name).strip() if case else ""
    return v.Header(
        obligation_id=ob.obligation_id,
        vendor_id=vendor.vendor_id,
        vendor_name=vendor.vendor_name,
        initials=initials(vendor.vendor_name),
        title=title or f"{period_label(ob.period)} accrual",
        period=ob.period,
        chips=chips,
        previous_accrual=money(prior["prior_amount"]) if prior else None,
        supported=money(wp.proposed_amount) if wp is not None else None,
        difference=signed(prior["delta"]) if prior else None,
        started=not is_pending(ob),
        status=case_status(ob),
        stage=front_stage(session, ob),
        current_agent=pending_agent(session, ob),
        stages_completed=runlog.stages_completed(trace.runs),
        log_count=len(trace.entries),
        handoff_count=len(trace.handoffs),
        workflow_stage=ob.workflow_stage.value,
        next_action=ob.next_action.value,
    )


def _prior_check(wp: m.TrueUpWorkpaper | None) -> dict[str, Any] | None:
    for check in ((wp.calculation_inputs_json or {}).get("checks") or []) if wp else []:
        if check.get("name") == "prior_close_comparison" and check["detail"].get("prior_amount"):
            return check["detail"]
    return None


# ---- ingestion and evidence ---------------------------------------------------------------------


def _ingestion(
    session: Session,
    universe: FileUniverse,
    case: CaseEntry | None,
    now: datetime,
    ob: m.TrueUpObligation,
    trace: runlog.Trace,
) -> v.IngestionView:
    run = trace.latest("ingestion", "select_files")
    if case is None:
        return v.IngestionView(
            available=False, judge=None, files_loaded=0, selected_count=0, summary=None, files=[]
        )
    visible = [f for f in universe.for_case(case.case_id) if _utc(f.available_at) <= _utc(now)]
    offered = [
        v.OfferedFile(
            file_id=f.file_id, name=f.name, kind=f.kind, format=f.format, size_label=f.size_label
        )
        for f in visible
    ]
    if run is None:
        return v.IngestionView(
            available=False,
            judge=None,
            files_loaded=0,
            selected_count=0,
            summary=None,
            files=[],
            offered=offered,
        )
    decisions = {d["file_id"]: d for d in run.facts_used_json or []}
    override = latest_override(session, ob.obligation_id)
    removed = override.excluded if override and override.run_id > run.run_id else frozenset()
    files = [
        v.SourceFile(
            file_id=f.file_id,
            name=f.name,
            kind=f.kind,
            format=f.format,
            size_label=f.size_label,
            selected=bool(decisions.get(f.file_id, {}).get("selected"))
            and f.file_id not in removed,
            user_removed=f.file_id in removed
            and bool(decisions.get(f.file_id, {}).get("selected")),
            reason=(
                "Removed by the user in the demo"
                if f.file_id in removed and decisions.get(f.file_id, {}).get("selected")
                else decisions.get(f.file_id, {}).get("reason")
            ),
            preview=f.preview,
        )
        for f in visible
    ]
    return v.IngestionView(
        available=True,
        judge=_judge_name(run),
        files_loaded=len(files),
        selected_count=sum(f.selected for f in files),
        summary=run.decision_summary,
        files=files,
        offered=offered,
    )


def _judge_name(run: m.TrueUpAgentRun | None) -> str | None:
    if run is None or " using the " not in run.decision_summary:
        return None
    return run.decision_summary.rsplit(" using the ", 1)[-1].rstrip(".")


def _pages(path: Path) -> list[str]:
    """A file's text, one entry per page for a PDF and a single entry for anything else."""
    try:
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            pages = [(page.extract_text() or "").strip() for page in PdfReader(str(path)).pages]
            return pages or [""]
        return [read_text(path)]
    except (UnsupportedFile, OSError, ValueError):
        return [""]


def _page_of(excerpt: str | None, pages: list[str]) -> int | None:
    """The first page whose text contains the excerpt, ignoring line breaks."""
    if not excerpt:
        return None
    needle = " ".join(excerpt.split())
    for number, text in enumerate(pages, start=1):
        if needle in " ".join(text.split()):
            return number
    return None


def _fact(card: m.TrueUpEvidence, files: dict[str, FileEntry]) -> v.EvidenceFact:
    label, _, value = card.fact.partition(": ")
    value = value.strip().rstrip(",;").removesuffix(".")
    if not value:
        label, value = card.fact, ""
    entry = files.get(card.source_id)
    key = (card.value_json or {}).get("key") if isinstance(card.value_json, dict) else None
    return v.EvidenceFact(
        evidence_id=card.evidence_id,
        page=None,
        label=label,
        value=value,
        key=key,
        file_id=card.source_id if entry else None,
        file_name=entry.name if entry else None,
        excerpt=card.source_excerpt,
        status=card.status.value,
    )


def _evidence(
    runs: list[m.TrueUpAgentRun],
    universe: FileUniverse,
    ingestion: v.IngestionView,
    facts: list[v.EvidenceFact],
    seed_dir: Path,
) -> v.EvidenceView:
    run = _latest(runs, "evidence", "extract_facts")
    by_id = {f.file_id: f for f in universe.files}
    documents = []
    pages_by_file: dict[str, list[str]] = {}
    for source in ingestion.files:
        if not source.selected:
            continue
        entry = by_id[source.file_id]
        pages = pages_by_file[entry.file_id] = _pages(seed_dir / entry.path)
        documents.append(
            v.EvidenceDocument(
                file_id=entry.file_id,
                name=entry.name,
                kind=entry.kind,
                format=entry.format,
                size_label=entry.size_label,
                pages=pages,
                fact_ids=[f.evidence_id for f in facts if f.file_id == entry.file_id],
            )
        )
    facts = [
        f.model_copy(update={"page": _page_of(f.excerpt, pages_by_file.get(f.file_id or "", []))})
        for f in facts
    ]
    return v.EvidenceView(
        available=run is not None,
        summary=run.decision_summary if run else None,
        documents=documents,
        facts=facts,
        uncertainties=list(run.uncertainties_json or []) if run else [],
    )


# ---- obligation and estimation ------------------------------------------------------------------


def _obligation_view(
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper | None,
    runs: list[m.TrueUpAgentRun],
    facts: list[v.EvidenceFact],
    header: v.Header,
) -> v.ObligationView:
    classify_run = _latest(runs, "classification", "classify_purchase")
    lookup_run = _latest(runs, "invoice_lookup")
    prior = _prior_check(wp)
    signals = [
        v.Signal(name=s["name"], value=str(s["value"]), points_to=s["points_to"])
        for s in (classify_run.facts_used_json if classify_run else [])
        if s["name"] != "cross_check"
    ]
    classified = classify_run is not None
    return v.ObligationView(
        available=classified,
        purchase_type=ob.purchase_type.value if classified else "",
        purchase_type_label=TREATMENT_LABELS[ob.purchase_type] if classified else "",
        rationale=classify_run.decision_summary if classify_run else None,
        signals=signals,
        service_start=ob.service_start_date.isoformat(),
        service_end=ob.service_end_date.isoformat(),
        service_period=span_label(ob.service_start_date, ob.service_end_date),
        invoice_status=ob.invoice_status.value,
        invoice_note=lookup_run.decision_summary if lookup_run else None,
        evidence_status=ob.evidence_status.value,
        accrual_required=(
            None
            if ob.invoice_status == e.InvoiceStatus.NOT_SEARCHED
            else ob.invoice_status != e.InvoiceStatus.INVOICE_FOUND
        ),
        estimated_amount=header.supported,
        basis=METHOD_LABELS[wp.estimation_method] if wp is not None else None,
        change_vs_prior=signed(prior["delta"]) if prior else None,
        facts=facts,
    )


def _calc_rows(wp: m.TrueUpWorkpaper) -> list[v.Row]:
    inputs = wp.calculation_inputs_json or {}
    method = wp.estimation_method
    rows: list[v.Row] = []
    if method == e.EstimationMethod.FIXED_CONTRACT_RATE:
        for seg in inputs.get("segments", []):
            rows.append(v.Row(label="Monthly rate", value=money(seg["monthly_rate"])))
            rows.append(v.Row(label="Days at this rate", value=str(seg["days"])))
        rows.append(v.Row(label="Days in period", value=str(inputs.get("period_days", ""))))
    elif method == e.EstimationMethod.USAGE_TIMES_RATE:
        rows.append(v.Row(label="Usage", value=f"{inputs['quantity']} {inputs.get('unit', '')}"))
        rows.append(v.Row(label="Unit rate applied", value=inputs["unit_rate"]))
        if inputs.get("base_rate"):
            rows.append(v.Row(label="Base contract rate", value=inputs["base_rate"]))
        rows.append(
            v.Row(
                label="Escalator step-up",
                value="Applied" if inputs.get("step_up_applied") else "No",
            )
        )
    elif method == e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE:
        rows.append(v.Row(label="Received quantity", value=inputs["received_quantity"]))
        rows.append(v.Row(label="Ordered quantity", value=inputs["ordered_quantity"]))
        rows.append(v.Row(label="Unit price", value=money(inputs["unit_price"])))
    elif method == e.EstimationMethod.MILESTONE_ACCEPTED_AMOUNT:
        rows.append(v.Row(label="Accepted delivery", value=money(inputs["accepted_amount"])))
        rows.append(v.Row(label="Budget cap", value=money(inputs["budget_cap"])))
    elif method == e.EstimationMethod.PREPAID_AMORTIZATION:
        rows.append(v.Row(label="Amount paid", value=money(inputs["paid_amount"])))
        rows.append(v.Row(label="Term in months", value=str(inputs["term_months"])))
    return rows


def _estimation(
    session: Session,
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper | None,
    runs: list[m.TrueUpAgentRun],
    accounts: dict[str, str],
    header: v.Header,
) -> v.EstimationView:
    run = _latest(runs, "estimation", "estimate_accrual")
    if wp is None:
        return v.EstimationView(
            available=False,
            outcome=_outcome(run),
            outcome_note=run.decision_summary if run else None,
            method=None,
            method_label=None,
            expression=None,
            amount=None,
            currency=None,
            calc_rows=[],
            checks=[],
            warnings=[],
            conflicts=[],
            inputs=[],
            rules_applied=[],
            recommendation=[],
            expense_account=None,
            liability_account=None,
            cost_center=None,
            entries=[],
        )
    inputs = wp.calculation_inputs_json or {}
    prior = _prior_check(wp)
    period = span_label(ob.service_start_date, ob.service_end_date)
    vendor = _vendor(session, ob.vendor_id)
    gl = _account_label(accounts, wp.expense_account) or wp.expense_account
    rules = [_rule_ref(session, r) for r in inputs.get("rules_applied") or []]
    return v.EstimationView(
        available=True,
        outcome=_outcome(run),
        outcome_note=run.decision_summary if run else None,
        method=wp.estimation_method.value,
        method_label=METHOD_LABELS[wp.estimation_method],
        expression=wp.calculation_expression,
        amount=money(wp.proposed_amount),
        currency=wp.currency,
        calc_rows=_calc_rows(wp),
        checks=[
            v.BuildCheck(
                name=c["name"],
                label=CHECK_LABELS.get(c["name"], c["name"]),
                result=c["result"],
                detail=c.get("detail") or {},
            )
            for c in inputs.get("checks") or []
        ],
        warnings=list(inputs.get("warnings") or []),
        conflicts=list(inputs.get("conflicts") or []),
        inputs=[
            v.InputCard(
                label="Obligation basis", value=METHOD_LABELS[wp.estimation_method], sub=None
            ),
            v.InputCard(label="Coverage period", value=period, sub=None),
            v.InputCard(
                label="Prior accrual",
                value=money(prior["prior_amount"]) if prior else "None",
                sub=f"Prior close {prior['prior_period']}" if prior else "First accrual",
            ),
            v.InputCard(label="GL account", value=gl, sub=None),
            v.InputCard(label="Vendor", value=vendor.vendor_name, sub=vendor.vendor_id),
        ],
        rules_applied=rules,
        recommendation=[
            v.Row(label="Service period", value=period),
            v.Row(label="Basis", value=METHOD_LABELS[wp.estimation_method]),
            v.Row(label="Compared to prior", value=signed(prior["delta"]) if prior else "No prior"),
            v.Row(label="GL account", value=gl),
            v.Row(label="Vendor", value=f"{vendor.vendor_name} ({vendor.vendor_id})"),
        ],
        expense_account=_account_label(accounts, wp.expense_account),
        liability_account=_account_label(accounts, wp.accrual_liability_account),
        cost_center=wp.cost_center,
        entries=_entries(wp, accounts),
    )


def _outcome(run: m.TrueUpAgentRun | None) -> str | None:
    if run is None:
        return None
    return "ESTIMATED" if run.status == e.AgentRunStatus.COMPLETED else "ESCALATED"


def _rule_ref(session: Session, applied: dict[str, Any]) -> v.RuleRef:
    row = session.get(m.TrueUpLearningRule, applied["learning_id"])
    rule = CandidateRule.model_validate(row.candidate_rule_json) if row else None
    return v.RuleRef(
        learning_id=applied["learning_id"],
        kind=applied["kind"],
        description=rule.description if rule else "",
        status=row.status.value if row else "UNKNOWN",
    )


def _entries(wp: m.TrueUpWorkpaper, accounts: dict[str, str]) -> list[v.JournalEntryView]:
    raw = wp.journal_entry_json
    if isinstance(raw, dict) and raw.get("entries"):
        entries = raw["entries"]
    elif isinstance(raw, list) and raw:
        entries = [
            {
                "entry_id": f"PROPOSED-{wp.workpaper_id}",
                "entry_type": "PROPOSED",
                "period": wp.period,
                "posting_date": "",
                "description": "Proposed accrual, not yet drafted",
                "lines": raw,
            }
        ]
    else:
        return []
    return [
        v.JournalEntryView(
            entry_id=entry["entry_id"],
            entry_type=entry["entry_type"],
            period=entry["period"],
            posting_date=str(entry.get("posting_date") or ""),
            description=entry["description"],
            lines=_lines(entry["lines"], accounts),
        )
        for entry in entries
    ]


def _lines(lines: list[dict[str, Any]], accounts: dict[str, str]) -> list[v.JournalLine]:
    result = []
    for line in lines:
        debit = coerce_money(line.get("debit") or "0")
        side, amount = (
            ("Dr", debit) if debit > 0 else ("Cr", coerce_money(line.get("credit") or "0"))
        )
        code = line["account_code"]
        result.append(
            v.JournalLine(
                side=side, account=code, account_name=accounts.get(code, ""), amount=money(amount)
            )
        )
    return result


# ---- verification -------------------------------------------------------------------------------


def _verification(
    session: Session,
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper | None,
    runs: list[m.TrueUpAgentRun],
    cards: list[m.TrueUpEvidence],
    accounts: dict[str, str],
    header: v.Header,
    now: datetime,
) -> v.VerificationView:
    policy_run = _latest(runs, "policy", "verify_policy")
    rules = [
        v.PolicyRule(
            rule_id=r["rule_id"],
            name=r["name"],
            status=r["status"],
            outcome=r.get("outcome"),
            detail=r["detail"],
        )
        for r in (policy_run.facts_used_json if policy_run else [])
    ]
    judged = policy_run is not None
    entries = _entries(wp, accounts) if wp is not None and judged else []
    accrual = next((x for x in entries if x.entry_type in ("ACCRUAL", "PROPOSED")), None)
    prior = _prior_check(wp)
    assertions: list[v.Row] = []
    if wp is not None and judged:
        assertions = [
            v.Row(label="Recommended accrual", value=money(wp.proposed_amount)),
            v.Row(label="Basis", value=wp.calculation_expression),
            v.Row(
                label="Service period", value=span_label(ob.service_start_date, ob.service_end_date)
            ),
            v.Row(
                label="Prior recurring amount",
                value=money(prior["prior_amount"]) if prior else "None",
            ),
        ]
        if accrual is not None:
            total = money(
                sum((coerce_money(x.amount) for x in accrual.lines if x.side == "Dr"), Decimal(0))
            )
            assertions.append(v.Row(label="Journal impact", value=f"{total} debit, {total} credit"))
    title, body = _final_note(header.status, ob, wp, rules)
    return v.VerificationView(
        available=judged,
        policy_decision=wp.policy_decision.value if wp is not None and judged else None,
        policy_summary=wp.policy_summary if wp is not None and judged else None,
        rules=rules,
        passed=sum(r.status == "PASS" for r in rules),
        total=len(rules),
        assertions=assertions,
        entries=entries,
        final_status=header.status,
        note_title=title,
        note_body=body,
        controller=_controller(session, ob, wp, cards, now),
        reconciliation=_reconciliation(wp),
        outreach=_outreach(cards),
    )


def _final_note(
    status: str, ob: m.TrueUpObligation, wp: m.TrueUpWorkpaper | None, rules: list[v.PolicyRule]
) -> tuple[str, str]:
    hits = [r for r in rules if r.status == "HIT"]
    hit_ids = ", ".join(r.rule_id for r in hits)
    if status == "Blocked":
        return (
            "Blocked by policy.",
            f"{hit_ids} blocked this accrual. The Controller cannot approve it.",
        )
    if status == "Needs review":
        why = f"{hit_ids} needs the Controller." if hits else "Waiting for the Controller."
        return "Controller review needed.", why
    if status == "Waiting":
        return (
            "Waiting on the service owner.",
            "An outreach request is open. The close resumes when the reply arrives.",
        )
    if status == "Close-ready":
        posted = "The accrual entry is posted to the simulated ledger. Waiting for the invoice."
        if hits:
            return (
                "Approved by the Controller.",
                f"{hit_ids} flagged this accrual and the Controller approved it. {posted}",
            )
        return "All policy rules cleared.", posted
    if status == "Complete":
        return "Closed.", "The invoice arrived and the accrual was graded against it."
    return "Checks in progress.", "Verification is not finished yet."


def _controller(
    session: Session,
    ob: m.TrueUpObligation,
    wp: m.TrueUpWorkpaper | None,
    cards: list[m.TrueUpEvidence],
    now: datetime,
) -> v.ControllerView:
    in_queue = (ob.workflow_stage, ob.next_action) in REVIEW_STATES
    record = None
    decisions = [c for c in cards if c.evidence_type == e.EvidenceCardType.CONTROLLER_DECISION]
    if decisions:
        value = decisions[-1].value_json or {}
        adjusted = value.get("adjusted_amount") or value.get("original_amount")
        record = v.ControllerRecord(
            decision=value.get("decision", ""),
            decided_by=value.get("decided_by"),
            notes=value.get("notes") or None,
            amount=money(adjusted) if adjusted else None,
        )
    if not in_queue:
        return v.ControllerView(
            in_queue=False,
            blocked=False,
            allowed_decisions=[],
            recommendation="",
            narrative="",
            reason="",
            record=record,
        )
    packet = build_packet(session, ob.obligation_id, now=now)
    item = next(i for i in review_queue(session, now=now) if i.obligation_id == ob.obligation_id)
    return v.ControllerView(
        in_queue=True,
        blocked=item.blocked,
        allowed_decisions=[d.value for d in packet.allowed_decisions],
        recommendation=packet.recommendation,
        narrative=packet.narrative,
        reason=item.reason,
        record=record,
    )


def _reconciliation(wp: m.TrueUpWorkpaper | None) -> v.ReconciliationView | None:
    record = (wp.calculation_inputs_json or {}).get("reconciliation") if wp else None
    if not record:
        return None
    return v.ReconciliationView(
        accrued=money(record["accrued"]),
        actual=money(record["actual"]),
        variance=signed(record["variance"]),
        root_cause=record.get("root_cause"),
        accepted=bool(record.get("invoice_accepted")),
        explanation=record["explanation"],
        invoice_ids=list(record.get("invoice_ids") or []),
        reconciled_at=record["reconciled_at"],
        resolved_dispute=record.get("resolved_dispute"),
    )


def _outreach(cards: list[m.TrueUpEvidence]) -> list[v.OutreachMessage]:
    messages = []
    for card in cards:
        if card.evidence_type != e.EvidenceCardType.OUTREACH_RESPONSE:
            continue
        value = card.value_json or {}
        request = value.get("direction") == "REQUEST"
        messages.append(
            v.OutreachMessage(
                direction="REQUEST" if request else "RESPONSE",
                topic=value.get("topic", ""),
                subject=value.get("subject"),
                body=value.get("body") if request else (card.source_excerpt or card.fact),
                to=value.get("recipient_email"),
                at=value.get("sent_at") or utc_iso(card.created_at),
                status=card.status.value,
            )
        )
    return messages


def _timeline(run: m.TrueUpAgentRun) -> v.TimelineEntry:
    return v.TimelineEntry(
        run_id=run.run_id,
        agent=run.agent_name,
        action=run.action,
        status=run.status.value,
        summary=run.decision_summary,
        output=run.output_summary,
        at=utc_iso(run.created_at),
    )


def _utc(moment: datetime) -> datetime:
    from datetime import UTC

    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# ---- learning -----------------------------------------------------------------------------------


def learning_view(session: Session) -> v.LearningView:
    vendors = {
        o.obligation_id: _vendor(session, o.vendor_id).vendor_name
        for o in session.scalars(select(m.TrueUpObligation))
    }
    rows = list(
        session.scalars(select(m.TrueUpLearningRule).order_by(m.TrueUpLearningRule.learning_id))
    )
    rules: list[v.RuleView] = []
    misses: list[v.MissLine] = []
    for row in rows:
        misses.append(
            v.MissLine(
                learning_id=row.learning_id,
                obligation_id=row.obligation_id,
                vendor_name=vendors.get(row.obligation_id, ""),
                period=_period_of(session, row.obligation_id),
                accrued=money(row.accrual_amount),
                actual=money(row.actual_amount),
                variance=signed(row.variance_amount),
                variance_percent=(
                    format(coerce_money(row.variance_percent).quantize(TWO_PLACES), "f")
                    if row.variance_percent is not None
                    else None
                ),
                root_cause=row.root_cause.value,
                summary=row.root_cause_summary,
            )
        )
        if row.candidate_rule_json is not None:
            rules.append(_rule_view(session, row, vendors))
    return v.LearningView(controller_id=controller_id(session), rules=rules, misses=misses)


def _period_of(session: Session, obligation_id: str) -> str:
    ob = session.get(m.TrueUpObligation, obligation_id)
    return ob.period if ob else ""


def _rule_view(session: Session, row: m.TrueUpLearningRule, vendors: dict[str, str]) -> v.RuleView:
    rule = CandidateRule.model_validate(row.candidate_rule_json)
    replay = row.replay_result_json or {}
    lifecycle = rule.lifecycle
    status = row.status
    return v.RuleView(
        learning_id=row.learning_id,
        status=status.value,
        kind=rule.kind.value,
        description=rule.description,
        root_cause=row.root_cause.value,
        predicate=rule.predicate.model_dump(mode="json"),
        support=len(rule.provenance),
        stage=lifecycle.stage if lifecycle else None,
        uses=lifecycle.uses if lifecycle else 0,
        contradictions=lifecycle.contradictions if lifecycle else 0,
        approved_by=row.approved_by,
        replay_passed=replay.get("passed"),
        total_error_before=replay.get("total_error_before"),
        total_error_after=replay.get("total_error_after"),
        criteria=dict(replay.get("criteria") or {}),
        replay=[
            v.ReplayLine(
                obligation_id=r["obligation_id"],
                vendor_name=vendors.get(r["obligation_id"], ""),
                period=r["period"],
                actual=r["actual"],
                before=r["before"],
                after=r["after"],
                supporting=r["supporting"],
            )
            for r in replay.get("rows") or []
        ],
        can_approve=status == e.LearningStatus.REPLAY_PASSED,
        can_reject=status in (e.LearningStatus.RULE_CANDIDATE, e.LearningStatus.REPLAY_PASSED),
        can_revoke=status == e.LearningStatus.ACTIVE,
    )


# ---- vendors ------------------------------------------------------------------------------------


def vendors_view(session: Session, *, period: str) -> v.VendorsView:
    rules = [
        (row, CandidateRule.model_validate(row.candidate_rule_json))
        for row in session.scalars(select(m.TrueUpLearningRule))
        if row.candidate_rule_json is not None
        and row.status in (e.LearningStatus.ACTIVE, e.LearningStatus.REPLAY_PASSED)
    ]
    result = []
    for vendor in session.scalars(select(m.CompanyVendor).order_by(m.CompanyVendor.vendor_id)):
        result.append(_vendor_view(session, vendor, period, rules))
    return v.VendorsView(vendors=result)


def _vendor_view(
    session: Session,
    vendor: m.CompanyVendor,
    period: str,
    rules: list[tuple[m.TrueUpLearningRule, CandidateRule]],
) -> v.VendorView:
    obligations = list(
        session.scalars(
            select(m.TrueUpObligation)
            .where(m.TrueUpObligation.vendor_id == vendor.vendor_id)
            .order_by(m.TrueUpObligation.period.desc(), m.TrueUpObligation.obligation_id)
        )
    )
    current = next((o for o in obligations if o.period == period), None)
    latest = current or (obligations[0] if obligations else None)
    contracts = list(
        session.scalars(
            select(m.CompanyContract)
            .where(m.CompanyContract.vendor_id == vendor.vendor_id)
            .order_by(m.CompanyContract.contract_version)
        )
    )
    history = []
    for ob in obligations[:4]:
        wp = _workpaper(session, ob)
        if wp is None:
            continue
        graded = (wp.calculation_inputs_json or {}).get("reconciliation")
        history.append(
            v.HistoryEntry(
                period=period_label(ob.period),
                amount=money(wp.proposed_amount),
                tag="Verified" if graded and graded.get("invoice_accepted") else "In review",
            )
        )
    ptype = latest.purchase_type if latest else e.PurchaseType.UNKNOWN
    wp_now = _workpaper(session, current) if current else None
    status = case_status(current) if current else None
    state: Any = (
        "Verified"
        if status == "Complete"
        else "Waiting for evidence"
        if status in ("Waiting", "Needs review", "Blocked")
        else "Autonomous"
    )
    memory = _memory(vendor, contracts, rules, ptype)
    relationship = [
        v.TimelineNote(when=c.effective_start_date.strftime("%b %Y"), what=_contract_note(c))
        for c in contracts
    ]
    relationship += [
        v.TimelineNote(
            when=period_label(ob.period),
            what=f"Accrual closed at {money(_workpaper(session, ob).proposed_amount)}",
        )
        for ob in reversed(obligations[:2])
        if _workpaper(session, ob) is not None
    ]
    relationship = relationship or [v.TimelineNote(when="Now", what="No history yet")]
    return v.VendorView(
        vendor_id=vendor.vendor_id,
        name=vendor.vendor_name,
        initials=initials(vendor.vendor_name),
        profile=PROFILE_BY_CATEGORY.get(
            vendor.vendor_category, vendor.vendor_category.value.title()
        ),
        treatment=TREATMENT_LABELS[ptype],
        workflow=ITEM_LABELS.get(ptype, "Accrual"),
        amount=money(wp_now.proposed_amount) if wp_now is not None else None,
        state=state,
        category=CATEGORY_LABELS.get(
            vendor.vendor_category, vendor.vendor_category.value.capitalize()
        ),
        acc_treatment=(
            METHOD_LABELS[wp_now.estimation_method] if wp_now is not None else "Not yet estimated"
        ),
        confidence="High"
        if history and all(h.tag == "Verified" for h in history[1:])
        else "Medium",
        history=history,
        sources=sorted({"Contract" for _ in contracts} | {"Invoices", "Purchase order"}),
        memory=memory,
        relationship=relationship,
        agents=[
            v.Row(label="Evidence agent", value="source documents"),
            v.Row(label="Obligation agent", value="purchase type"),
            v.Row(label="Estimation agent", value=AGENT_USES.get(ptype, "estimation basis")),
            v.Row(label="Verification agent", value="policy rules"),
        ],
        obligation_id=current.obligation_id if current else None,
    )


def _contract_note(contract: m.CompanyContract) -> str:
    if contract.contract_version > 1:
        return f"Contract amended to version {contract.contract_version}"
    return "Contract effective"


def _memory(
    vendor: m.CompanyVendor,
    contracts: list[m.CompanyContract],
    rules: list[tuple[m.TrueUpLearningRule, CandidateRule]],
    ptype: e.PurchaseType,
) -> str:
    notes: list[str] = []
    active = [c for c in contracts if c.status == e.ContractStatus.ACTIVE]
    latest = active[-1] if active else (contracts[-1] if contracts else None)
    if latest is not None and latest.contract_version > 1 and latest.base_rate is not None:
        notes.append(
            f"Contract price updated effective {latest.effective_start_date:%B} "
            f"{latest.effective_start_date.day}, {latest.effective_start_date.year}. "
            "Future accruals should reference the updated amount."
        )
    if latest is not None and latest.escalator_percent is not None:
        notes.append(
            f"The contract carries a {latest.escalator_percent}% escalator "
            f"effective {latest.escalator_effective_date}."
        )
    for row, rule in rules:
        if (
            ptype in rule.predicate.purchase_types
            and latest is not None
            and latest.escalator_percent is not None
        ):
            notes.append(
                f"Playbook rule {row.learning_id} ({row.status.value}): {rule.description}"
            )
    return " ".join(notes) or f"No changes on record for {vendor.vendor_name}."
