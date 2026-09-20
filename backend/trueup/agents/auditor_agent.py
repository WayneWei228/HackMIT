"""Auditor agent: the independent second line that re-performs the close and documents controls.

Read-only over the 13 tables. It never changes an obligation, workpaper, entry, card or rule. It
re-derives what the other agents recorded, from the records and the source files, and reports
every difference as a typed finding. Its only write is one row in the append-only agent-run log.

Controls (deterministic code; a language model may only word the summary, never state a number):
AUD-01 evidence traceability, AUD-02 recomputation, AUD-03 journal entries, AUD-04 policy and
approvals, AUD-05 workflow integrity, AUD-06 cutoff and duplicates, AUD-07 reconciliation,
AUD-08 learning rules, AUD-09 completeness, AUD-10 verified handoffs.
Entry point: `audit(session, now=..., period=...)`.

Two helpers are borrowed from the agents whose work is re-performed (the policy rules and the
variance diagnosis), so that a recorded outcome is compared with what the same logic gives on the
recorded inputs.
"""

from __future__ import annotations

import calendar
import json
import re
import unicodedata
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents import policy_agent, reconciliation_agent
from trueup.agents.controller_workspace import ControllerWorkspaceError, controller_id
from trueup.agents.detection_agent import CONTRACT_STATUSES_IN_FORCE, PO_STATUSES_TO_ACCRUE
from trueup.agents.estimation_agent import compute
from trueup.agents.ingestion import SEED_DIR, load_universe
from trueup.agents.learning_agent import HISTORY_PREFIX
from trueup.gateway import llm
from trueup.ingest.manifest import FileEntry, FileUniverse
from trueup.ingest.readers import UnsupportedFile, read_text
from trueup.learning.rules import BiasGuardError, CandidateRule, reject_vendor_references
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, UnbalancedEntryError, assert_balanced
from trueup.store.workflow import INITIAL, allowed_transitions

AGENT_NAME = "auditor"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "audit_summary.md"
TOLERANCE = Decimal("0.01")
CENT = Decimal("0.01")
OUT_OF_SCOPE_PREFIXES = (HISTORY_PREFIX, "OBL-FIXTURE-")
MIN_CONFIRMATIONS = 3

CHECKS: dict[str, str] = {
    "AUD-01": "Evidence traceability",
    "AUD-02": "Recomputation",
    "AUD-03": "Journal entries",
    "AUD-04": "Policy and approvals",
    "AUD-05": "Workflow integrity",
    "AUD-06": "Cutoff and duplicates",
    "AUD-07": "Reconciliation",
    "AUD-08": "Learning rules",
    "AUD-09": "Completeness",
    "AUD-10": "Verified handoffs",
}

_ACCRUAL = e.GLEntryType.ACCRUAL
_REVERSAL = e.GLEntryType.ACCRUAL_REVERSAL
_APPROVING = (e.ControllerDecision.APPROVE, e.ControllerDecision.APPROVE_WITH_ADJUSTMENT)
_LEDGER_LIVE = (e.GLEntryStatus.POSTED, e.GLEntryStatus.REVERSED)
_POSTED_WORKPAPER = (e.WorkpaperStatus.POSTED_SIMULATED, e.WorkpaperStatus.TRUE_UP_COMPLETE)
_EXCLUDED_INVOICE = (e.APInvoiceStatus.VOIDED, e.APInvoiceStatus.REJECTED)
_S, _A = e.WorkflowStage, e.NextAction

# The workflow state each logged action starts from. Actions that do not move an obligation
# (posting, replays, the auditor's own rows) are left out.
_STARTS_AT: dict[tuple[str, str], tuple[e.WorkflowStage, e.NextAction]] = {
    ("invoice_lookup", "search_ap"): (_S.SEARCHING_AP, _A.SEARCH_AP),
    ("evidence", "extract_facts"): (_S.GATHERING_EVIDENCE, _A.GATHER_EVIDENCE),
    ("classification", "classify_purchase"): (_S.CLASSIFYING, _A.CLASSIFY),
    ("estimation", "estimate_accrual"): (_S.ESTIMATING, _A.ESTIMATE),
    ("policy", "verify_policy"): (_S.ESTIMATING, _A.VERIFY_POLICY),
    ("journal_entry_service", "draft_entry"): (_S.READY_TO_DRAFT, _A.DRAFT_ENTRY),
    ("reconciliation", "match_invoice"): (_S.AWAITING_ACTUAL_INVOICE, _A.WAIT_FOR_INVOICE),
    ("reconciliation", "reconcile"): (_S.RECONCILING, _A.MATCH_AND_TRUE_UP),
    ("learning", "evaluate"): (_S.RECONCILING, _A.EVALUATE_LEARNING),
    ("outreach", "send_outreach"): (_S.AWAITING_OUTREACH, _A.SEND_OUTREACH),
    ("outreach", "process_reply"): (_S.AWAITING_OUTREACH, _A.SEND_OUTREACH),
}


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class ControlStatus(StrEnum):
    PASS = "PASS"
    NOTE = "NOTE"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Finding(BaseModel):
    finding_id: str
    check_id: str
    severity: Severity
    obligation_id: str | None
    record_ids: list[str]
    expected: str | None
    actual: str | None
    message: str


class Control(BaseModel):
    check_id: str
    name: str
    status: ControlStatus
    detail: str


class ObligationAudit(BaseModel):
    obligation_id: str
    vendor_id: str
    period: str
    state: str
    controls: list[Control]
    findings: list[Finding]


class AuditReport(BaseModel):
    audited_at: datetime
    period: str | None
    obligations: list[ObligationAudit]
    global_controls: list[Control]
    findings: list[Finding]
    counts: dict[str, int]
    summary: str
    summary_source: Literal["template", "llm"]
    summary_note: str | None
    run_id: str | None

    @property
    def passed(self) -> bool:
        return self.counts.get(Severity.CRITICAL.value, 0) == 0

    def for_obligation(self, obligation_id: str) -> ObligationAudit:
        return next(o for o in self.obligations if o.obligation_id == obligation_id)

    def ids(self, check_id: str, severity: Severity | None = None) -> list[str | None]:
        """Obligation ids (None for a global one) of the findings under a control."""
        return [
            f.obligation_id
            for f in self.findings
            if f.check_id == check_id and (severity is None or f.severity == severity)
        ]


Narrator = Callable[[dict[str, Any]], str]


def audit(
    session: Session,
    *,
    now: datetime,
    period: str | None = None,
    obligation_ids: list[str] | None = None,
    seed_dir: Path | str = SEED_DIR,
    narrator: Narrator | None = None,
    persist: bool = True,
) -> AuditReport:
    """Re-perform every control over the live obligations of a period, or the ones named."""
    now = _utc(now)
    world = _World.load(session, now, Path(seed_dir))
    scoped = _scope(session, period, obligation_ids)
    audits = [_audit_obligation(world, ob) for ob in scoped]

    periods = [period] if period else sorted({ob.period for ob in scoped})
    global_recorder = _Recorder(None)
    _guarded(global_recorder, "AUD-08", lambda: _rules_control(world, global_recorder))
    for value in periods:
        _guarded(
            global_recorder, "AUD-09", lambda v=value: _period_control(world, v, global_recorder)
        )
    global_controls = global_recorder.controls()
    findings = sorted(
        [*global_recorder.findings, *(f for a in audits for f in a.findings)],
        key=lambda f: (_RANK[f.severity], f.obligation_id or "", f.check_id, f.finding_id),
    )
    counts = {s.value: sum(1 for f in findings if f.severity == s) for s in Severity}
    summary, source, note = _narrate(_facts(period, audits, counts, findings), narrator)
    report = AuditReport(
        audited_at=now,
        period=period,
        obligations=audits,
        global_controls=global_controls,
        findings=findings,
        counts=counts,
        summary=summary,
        summary_source=source,
        summary_note=note,
        run_id=None,
    )
    if persist:
        report.run_id = _log(session, report, now)
    return report


# ---- scope and world ----------------------------------------------------------------------------


_RANK = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}


def _scope(
    session: Session, period: str | None, obligation_ids: list[str] | None
) -> list[m.TrueUpObligation]:
    query = select(m.TrueUpObligation).order_by(m.TrueUpObligation.obligation_id)
    if obligation_ids is not None:
        query = query.where(m.TrueUpObligation.obligation_id.in_(obligation_ids))
    elif period is not None:
        query = query.where(m.TrueUpObligation.period == period)
    rows = session.scalars(query).all()
    if obligation_ids is not None:
        return list(rows)
    return [ob for ob in rows if not ob.obligation_id.startswith(OUT_OF_SCOPE_PREFIXES)]


@dataclass
class _World:
    session: Session
    now: datetime
    seed_dir: Path
    universe: FileUniverse | None
    controller: str | None
    threshold: Decimal | None
    chart: dict[str, str]
    rule_rows: list[m.TrueUpLearningRule]
    approved_at: dict[str, datetime]
    texts: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session, now: datetime, seed_dir: Path) -> _World:
        try:
            universe: FileUniverse | None = load_universe(seed_dir)
        except (OSError, ValueError):
            universe = None
        try:
            controller: str | None = controller_id(session)
        except ControllerWorkspaceError:
            controller = None
        thresholds = _config(session, "approval_thresholds") or {}
        limit = thresholds.get("controller_review_above_usd")
        rows = session.scalars(
            select(m.TrueUpLearningRule).order_by(
                m.TrueUpLearningRule.created_at, m.TrueUpLearningRule.learning_id
            )
        ).all()
        approvals: dict[str, datetime] = {}
        for run in session.scalars(
            select(m.TrueUpAgentRun)
            .where(m.TrueUpAgentRun.agent_name == "learning")
            .where(m.TrueUpAgentRun.action == "approve_rule")
            .order_by(m.TrueUpAgentRun.run_id)
        ):
            for learning_id in run.output_record_ids_json or []:
                approvals.setdefault(learning_id, _utc(run.created_at))
        return cls(
            session=session,
            now=now,
            seed_dir=seed_dir,
            universe=universe,
            controller=controller,
            threshold=Decimal(str(limit)) if limit is not None else None,
            chart={
                a["account_code"]: a["type"] for a in _config(session, "allowed_gl_accounts") or []
            },
            rule_rows=[r for r in rows if r.candidate_rule_json is not None],
            approved_at=approvals,
        )

    def file_entry(self, file_id: str) -> FileEntry | None:
        if self.universe is None:
            return None
        return next((f for f in self.universe.files if f.file_id == file_id), None)

    def file_text(self, entry: FileEntry) -> str | None:
        if entry.file_id not in self.texts:
            try:
                self.texts[entry.file_id] = read_text(self.seed_dir / entry.path)
            except (UnsupportedFile, OSError, ValueError):
                self.texts[entry.file_id] = None
        return self.texts[entry.file_id]

    def source_row(self, source_id: str) -> Any | None:
        for model in (
            m.CompanyContract,
            m.CompanyPurchaseOrder,
            m.CompanyServiceEvidence,
            m.CompanyAPInvoice,
            m.CompanyGLEntry,
            m.CompanyNonPOSpend,
        ):
            row = self.session.get(model, source_id)
            if row is not None:
                return row
        return None

    def rules_active_at(self, moment: datetime) -> list[tuple[str, CandidateRule]]:
        """The rules the Controller had approved, and not yet revoked, at that moment."""
        active = []
        for row in self.rule_rows:
            approved = self.approved_at.get(row.learning_id)
            if approved is None or approved > _utc(moment):
                continue
            revoked = _revoked_at(row)
            if revoked is not None and revoked <= _utc(moment):
                continue
            try:
                active.append(
                    (row.learning_id, CandidateRule.model_validate(row.candidate_rule_json))
                )
            except (ValidationError, ValueError):
                continue
        return active


def _config(session: Session, key: str) -> Any:
    row = session.get(m.CompanyConfig, key)
    return row.config_value_json if row is not None else None


def _revoked_at(row: m.TrueUpLearningRule) -> datetime | None:
    revocation = (row.replay_result_json or {}).get("revocation")
    if not revocation or not revocation.get("at"):
        return None
    return _utc(datetime.fromisoformat(revocation["at"]))


# ---- recording ----------------------------------------------------------------------------------


class _Recorder:
    """Collects the findings of one obligation, or the global ones, and derives its controls."""

    def __init__(self, obligation_id: str | None):
        self.obligation_id = obligation_id
        self.findings: list[Finding] = []
        self._applied: dict[str, str] = {}
        self._skipped: dict[str, str] = {}

    def applied(self, check_id: str, detail: str) -> None:
        self._applied[check_id] = detail

    def skip(self, check_id: str, reason: str) -> None:
        self._skipped[check_id] = reason

    def add(
        self,
        check_id: str,
        severity: Severity,
        message: str,
        *,
        expected: object | None = None,
        actual: object | None = None,
        records: list[str] | tuple[str, ...] = (),
    ) -> None:
        number = 1 + sum(1 for f in self.findings if f.check_id == check_id)
        self.findings.append(
            Finding(
                finding_id=f"{check_id}:{self.obligation_id or 'GLOBAL'}:{number:02d}",
                check_id=check_id,
                severity=severity,
                obligation_id=self.obligation_id,
                record_ids=[r for r in records if r],
                expected=None if expected is None else str(expected),
                actual=None if actual is None else str(actual),
                message=message,
            )
        )

    def critical(self, check_id: str, message: str, **kwargs: Any) -> None:
        self.add(check_id, Severity.CRITICAL, message, **kwargs)

    def warning(self, check_id: str, message: str, **kwargs: Any) -> None:
        self.add(check_id, Severity.WARNING, message, **kwargs)

    def info(self, check_id: str, message: str, **kwargs: Any) -> None:
        self.add(check_id, Severity.INFO, message, **kwargs)

    def controls(self) -> list[Control]:
        controls = []
        for check_id, name in CHECKS.items():
            found = [f for f in self.findings if f.check_id == check_id]
            if check_id in self._applied:
                if any(f.severity == Severity.CRITICAL for f in found):
                    status = ControlStatus.FAIL
                elif found:
                    status = ControlStatus.NOTE
                else:
                    status = ControlStatus.PASS
                detail = self._applied[check_id]
            elif check_id in self._skipped:
                status, detail = ControlStatus.NOT_APPLICABLE, self._skipped[check_id]
            else:
                continue
            controls.append(Control(check_id=check_id, name=name, status=status, detail=detail))
        return controls


def _guarded(rec: _Recorder, check_id: str, run: Callable[[], None]) -> None:
    """A control that cannot run is a failure, never a silent pass."""
    try:
        run()
    except Exception as exc:  # an audit must report, not crash, on odd records
        rec.applied(check_id, "The control could not be performed.")
        rec.critical(check_id, f"The control could not be performed: {type(exc).__name__}: {exc}")


# ---- one obligation -----------------------------------------------------------------------------


@dataclass
class _Case:
    ob: m.TrueUpObligation
    wp: m.TrueUpWorkpaper | None
    inputs: dict[str, Any]
    runs: list[m.TrueUpAgentRun]
    cards: list[m.TrueUpEvidence]
    gl: list[m.CompanyGLEntry]

    @property
    def state(self) -> tuple[e.WorkflowStage, e.NextAction]:
        return (self.ob.workflow_stage, self.ob.next_action)

    @property
    def amount(self) -> Decimal | None:
        return _dec(self.wp.proposed_amount) if self.wp is not None else None

    @property
    def original_amount(self) -> Decimal | None:
        """The amount before any Controller adjustment, which is what policy and Estimation saw."""
        adjustment = self.inputs.get("controller_adjustment")
        if adjustment and adjustment.get("original_amount") is not None:
            return _dec(adjustment["original_amount"])
        return self.amount

    @property
    def drafted(self) -> list[dict[str, Any]] | None:
        payload = self.wp.journal_entry_json if self.wp is not None else None
        return payload["entries"] if isinstance(payload, dict) else None

    def entry(self, entry_type: e.GLEntryType) -> dict[str, Any] | None:
        return next((x for x in self.drafted or [] if x["entry_type"] == entry_type.value), None)

    def ledger(self, entry_type: e.GLEntryType) -> list[m.CompanyGLEntry]:
        return [
            g for g in self.gl if g.entry_type == entry_type and g.status != e.GLEntryStatus.VOIDED
        ]

    def ran(self, agent: str, action: str) -> list[m.TrueUpAgentRun]:
        return [r for r in self.runs if (r.agent_name, r.action) == (agent, action)]

    def proceeded(self) -> bool:
        """Whether an accrual was drafted or posted from this workpaper."""
        return self.drafted is not None or bool(self.ledger(_ACCRUAL))


def _audit_obligation(world: _World, ob: m.TrueUpObligation) -> ObligationAudit:
    session = world.session
    wp = (
        session.get(m.TrueUpWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    )
    case = _Case(
        ob=ob,
        wp=wp,
        inputs=dict((wp.calculation_inputs_json or {}) if wp is not None else {}),
        runs=list(
            session.scalars(
                select(m.TrueUpAgentRun)
                .where(m.TrueUpAgentRun.obligation_id == ob.obligation_id)
                .where(m.TrueUpAgentRun.agent_name != AGENT_NAME)
                .order_by(m.TrueUpAgentRun.run_id)
            )
        ),
        cards=list(
            session.scalars(
                select(m.TrueUpEvidence)
                .where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
                .order_by(m.TrueUpEvidence.evidence_id)
            )
        ),
        gl=list(
            session.scalars(
                select(m.CompanyGLEntry)
                .where(m.CompanyGLEntry.obligation_id == ob.obligation_id)
                .order_by(m.CompanyGLEntry.gl_entry_id)
            )
        ),
    )
    rec = _Recorder(ob.obligation_id)
    for check_id, control in _OBLIGATION_CONTROLS:
        _guarded(rec, check_id, lambda c=control: c(world, case, rec))
    return ObligationAudit(
        obligation_id=ob.obligation_id,
        vendor_id=ob.vendor_id,
        period=ob.period,
        state=f"{ob.workflow_stage.value}/{ob.next_action.value}",
        controls=rec.controls(),
        findings=rec.findings,
    )


# ---- AUD-01 evidence traceability ---------------------------------------------------------------


def _evidence_control(world: _World, case: _Case, rec: _Recorder) -> None:
    wp = case.wp
    sources = list(case.inputs.get("sources") or [])
    documents = [c for c in case.cards if c.source_table == "document"]
    rec.applied(
        "AUD-01",
        f"{len(sources)} cited source rows, {len(documents)} document cards, "
        f"{len(case.cards)} cards in all.",
    )
    if wp is not None:
        if not sources:
            rec.critical(
                "AUD-01",
                "The workpaper cites no source row for its amount.",
                records=[wp.workpaper_id],
            )
        for source_id in sources:
            _trace_source(world, case, rec, source_id)
    for card in documents:
        _trace_card(world, case, rec, card)

    stored = {c.evidence_id for c in case.cards}
    for run in case.runs:
        for record_id in run.output_record_ids_json or []:
            if (
                isinstance(record_id, str)
                and record_id.startswith("EVD-")
                and record_id not in stored
            ):
                rec.critical(
                    "AUD-01",
                    f"Evidence card {record_id} was recorded by {run.agent_name} but no longer "
                    f"exists.",
                    expected=record_id,
                    actual="missing",
                    records=[run.run_id, record_id],
                )


def _trace_source(world: _World, case: _Case, rec: _Recorder, source_id: str) -> None:
    ob, wp = case.ob, case.wp
    row = world.source_row(source_id)
    if row is None:
        card = next(
            (
                c
                for c in case.cards
                if c.evidence_id == source_id and c.status == e.EvidenceCardStatus.VERIFIED
            ),
            None,
        )
        if card is not None:
            if wp is not None and _utc(card.created_at) > _utc(wp.created_at):
                rec.critical(
                    "AUD-01",
                    f"Cited evidence card {card.evidence_id} was created at "
                    f"{_utc(card.created_at).isoformat()}, after the workpaper at "
                    f"{_utc(wp.created_at).isoformat()}.",
                    expected=f"on or before {_utc(wp.created_at).isoformat()}",
                    actual=_utc(card.created_at).isoformat(),
                    records=[wp.workpaper_id, card.evidence_id],
                )
            return
        rec.critical(
            "AUD-01",
            f"The workpaper cites {source_id}, which is not in any company table.",
            expected="an existing source row",
            actual="missing",
            records=[source_id],
        )
        return
    vendor = getattr(row, "vendor_id", None)
    if vendor is not None and vendor != ob.vendor_id:
        rec.critical(
            "AUD-01",
            f"The workpaper cites {source_id}, which belongs to a different vendor.",
            expected=ob.vendor_id,
            actual=vendor,
            records=[source_id],
        )
    known_at = (
        row.created_at
        if isinstance(row, m.CompanyServiceEvidence)
        else row.received_at
        if isinstance(row, m.CompanyAPInvoice)
        else None
    )
    if known_at is not None and wp is not None and _utc(known_at) > _utc(wp.created_at):
        rec.critical(
            "AUD-01",
            f"The workpaper cites {source_id}, which did not exist when the estimate was written.",
            expected=f"on or before {_utc(wp.created_at).isoformat()}",
            actual=_utc(known_at).isoformat(),
            records=[source_id, wp.workpaper_id],
        )
    if isinstance(row, m.CompanyServiceEvidence) and not (
        row.service_start_date <= ob.service_end_date
        and row.service_end_date >= ob.service_start_date
    ):
        rec.warning(
            "AUD-01",
            f"{source_id} covers {row.service_start_date} to {row.service_end_date}, "
            "outside the service period.",
            expected=f"{ob.service_start_date} to {ob.service_end_date}",
            actual=f"{row.service_start_date} to {row.service_end_date}",
            records=[source_id],
        )


def _trace_card(world: _World, case: _Case, rec: _Recorder, card: m.TrueUpEvidence) -> None:
    ob = case.ob
    entry = world.file_entry(card.source_id)
    if world.universe is None:
        rec.warning(
            "AUD-01", "The file manifest could not be read, so document quotes were not re-checked."
        )
        return
    if entry is None:
        rec.critical(
            "AUD-01",
            f"Card {card.evidence_id} cites file {card.source_id}, which is not in the file "
            f"universe.",
            records=[card.evidence_id, card.source_id],
        )
        return
    if entry.vendor_id != ob.vendor_id:
        rec.critical(
            "AUD-01",
            f"Card {card.evidence_id} cites a file of a different vendor.",
            expected=ob.vendor_id,
            actual=entry.vendor_id,
            records=[card.evidence_id, entry.file_id],
        )
    if _utc(entry.available_at) > _utc(card.created_at):
        rec.critical(
            "AUD-01",
            f"Card {card.evidence_id} was written before its source file {entry.name} existed.",
            expected=f"on or after {_utc(entry.available_at).isoformat()}",
            actual=_utc(card.created_at).isoformat(),
            records=[card.evidence_id, entry.file_id],
        )
    text = world.file_text(entry)
    if text is None:
        rec.critical(
            "AUD-01",
            f"The source file {entry.name} for card {card.evidence_id} cannot be re-read.",
            records=[card.evidence_id, entry.file_id],
        )
        return
    quote = _normalize(card.source_excerpt or "")
    if not quote or quote not in _normalize(text):
        rec.critical(
            "AUD-01",
            f"The quote on card {card.evidence_id} does not appear verbatim in {entry.name}.",
            expected="a verbatim quote from the source file",
            actual=(card.source_excerpt or "")[:80],
            records=[card.evidence_id, entry.file_id],
        )


# ---- AUD-02 recomputation -----------------------------------------------------------------------


class _Unrecomputable(Exception):
    pass


def _recomputation_control(world: _World, case: _Case, rec: _Recorder) -> None:
    wp, ob = case.wp, case.ob
    if wp is None:
        rec.skip("AUD-02", "No workpaper was written, so there is no amount to recompute.")
        return
    proposed, original = case.amount, case.original_amount
    rec.applied(
        "AUD-02", f"{wp.estimation_method.value} recomputed from the recorded inputs and sources."
    )

    adjustment = case.inputs.get("controller_adjustment")
    if adjustment:
        if _dec(adjustment.get("adjusted_amount")) != proposed:
            rec.critical(
                "AUD-02",
                "The workpaper amount differs from the amount the Controller adjusted it to.",
                expected=_money(adjustment.get("adjusted_amount")),
                actual=_money(proposed),
                records=[wp.workpaper_id],
            )
        if adjustment.get("decided_by") != world.controller:
            rec.critical(
                "AUD-02",
                "The amount was adjusted by someone other than the configured controller.",
                expected=world.controller,
                actual=adjustment.get("decided_by"),
                records=[wp.workpaper_id],
            )

    try:
        derived = _derive(wp.estimation_method, case.inputs)
    except _Unrecomputable as gap:
        rec.critical(
            "AUD-02", f"The recorded inputs cannot be recomputed: {gap}.", records=[wp.workpaper_id]
        )
        derived = None
    if derived is None and wp.estimation_method not in _FORMULAS:
        rec.info(
            "AUD-02",
            f"{wp.estimation_method.value} has no independent formula, so only the sources were "
            f"checked.",
            records=[wp.workpaper_id],
        )
    if derived is not None and abs(derived - original) > TOLERANCE:
        rec.critical(
            "AUD-02",
            f"The recorded inputs give {_money(derived)}, not the recorded amount "
            f"{_money(original)}.",
            expected=_money(derived),
            actual=_money(original),
            records=[wp.workpaper_id],
        )
    _inputs_match_sources(world, case, rec)

    rules = world.rules_active_at(wp.created_at)
    try:
        fresh = compute(world.session, ob, rules=rules).estimate.amount
    except Exception as exc:  # any failure to re-derive is itself a finding
        rec.warning(
            "AUD-02",
            f"The estimate could not be re-derived from the sources: {exc}.",
            records=[wp.workpaper_id],
        )
        return
    if abs(fresh - original) > TOLERANCE:
        posted = wp.status in _POSTED_WORKPAPER
        rec.add(
            "AUD-02",
            Severity.WARNING if posted else Severity.CRITICAL,
            f"Re-deriving the estimate from the sources and the rules active at the time gives "
            f"{_money(fresh)}, not {_money(original)}."
            + (
                " Either the workpaper was edited or the sources changed after posting."
                if posted
                else ""
            ),
            expected=_money(fresh),
            actual=_money(original),
            records=[wp.workpaper_id],
        )


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _derive_fixed(i: dict[str, Any]) -> Decimal:
    days = Decimal(i["period_days"])
    return _round(
        sum((_dec(s["monthly_rate"]) * s["days"] / days for s in i["segments"]), Decimal(0))
    )


_FORMULAS: dict[e.EstimationMethod, Callable[[dict[str, Any]], Decimal]] = {
    e.EstimationMethod.FIXED_CONTRACT_RATE: _derive_fixed,
    e.EstimationMethod.USAGE_TIMES_RATE: lambda i: _round(
        _dec(i["quantity"]) * _dec(i["unit_rate"])
    ),
    e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE: lambda i: _round(
        _dec(i["received_quantity"]) * _dec(i["unit_price"])
    ),
    e.EstimationMethod.MILESTONE_ACCEPTED_AMOUNT: lambda i: _round(
        min(_dec(i["accepted_amount"]), _dec(i["budget_cap"]))
    ),
    e.EstimationMethod.PREPAID_AMORTIZATION: lambda i: _round(
        _dec(i["paid_amount"]) / Decimal(i["term_months"])
    ),
}


def _derive(method: e.EstimationMethod, inputs: dict[str, Any]) -> Decimal | None:
    formula = _FORMULAS.get(method)
    if formula is None:
        return None
    try:
        return formula(inputs)
    except (KeyError, TypeError, InvalidOperation, ZeroDivisionError, ValueError) as exc:
        raise _Unrecomputable(f"{type(exc).__name__} {exc}") from exc


def _inputs_match_sources(world: _World, case: _Case, rec: _Recorder) -> None:
    """The quantities and rates the workpaper recorded must equal the rows it cites."""
    wp, i = case.wp, case.inputs
    assert wp is not None
    rows = [r for r in (world.source_row(s) for s in i.get("sources") or []) if r is not None]
    usage = [r for r in rows if isinstance(r, m.CompanyServiceEvidence)]
    contract = (
        world.session.get(m.CompanyContract, i["contract_row_id"])
        if i.get("contract_row_id")
        else None
    )
    method = wp.estimation_method
    pairs: list[tuple[str, Decimal | None, Decimal | None]] = []
    try:
        if method == e.EstimationMethod.USAGE_TIMES_RATE:
            confirmed = [r for r in usage if r.evidence_type == e.ServiceEvidenceType.SYSTEM_USAGE]
            pairs.append(
                (
                    "quantity",
                    _dec(i["quantity"]),
                    sum((r.quantity or 0 for r in confirmed), Decimal(0)),
                )
            )
            if contract is not None and contract.base_rate is not None:
                rate = contract.base_rate
                if i.get("step_up_applied") and contract.escalator_percent is not None:
                    rate = rate * (1 + contract.escalator_percent / 100)
                pairs.append(("unit_rate", _dec(i["unit_rate"]), rate))
        elif method == e.EstimationMethod.RECEIVED_QUANTITY_TIMES_PRICE:
            got = [r for r in usage if r.evidence_type == e.ServiceEvidenceType.GOODS_RECEIPT]
            pairs.append(
                (
                    "received_quantity",
                    _dec(i["received_quantity"]),
                    sum((r.quantity or 0 for r in got), Decimal(0)),
                )
            )
        elif method == e.EstimationMethod.MILESTONE_ACCEPTED_AMOUNT:
            got = [
                r for r in usage if r.evidence_type == e.ServiceEvidenceType.MILESTONE_ACCEPTANCE
            ]
            pairs.append(
                (
                    "accepted_amount",
                    _dec(i["accepted_amount"]),
                    sum((r.accepted_amount or 0 for r in got), Decimal(0)),
                )
            )
        elif method == e.EstimationMethod.FIXED_CONTRACT_RATE:
            for segment in i.get("segments") or []:
                if segment.get("contract_row_id"):
                    row = world.session.get(m.CompanyContract, segment["contract_row_id"])
                    if row is not None:
                        pairs.append(("monthly_rate", _dec(segment["monthly_rate"]), row.base_rate))
                elif segment.get("evidence_id"):
                    card = next(
                        (
                            c
                            for c in case.cards
                            if c.evidence_id == segment["evidence_id"]
                            and c.status == e.EvidenceCardStatus.VERIFIED
                        ),
                        None,
                    )
                    if card is not None:
                        pairs.append(
                            (
                                "monthly_rate",
                                _dec(segment["monthly_rate"]),
                                Decimal(str((card.value_json or {})["number"])),
                            )
                        )
        elif method == e.EstimationMethod.PREPAID_AMORTIZATION:
            paid = [r for r in rows if isinstance(r, m.CompanyAPInvoice)]
            if paid:
                pairs.append(("paid_amount", _dec(i["paid_amount"]), paid[0].amount))
    except (KeyError, TypeError, InvalidOperation) as exc:
        rec.critical(
            "AUD-02",
            f"The recorded inputs are incomplete: {type(exc).__name__} {exc}.",
            records=[wp.workpaper_id],
        )
        return
    for name, recorded, source in pairs:
        if (
            recorded is not None
            and source is not None
            and abs(recorded - source) > Decimal("0.000001")
        ):
            rec.critical(
                "AUD-02",
                f"The workpaper records {name} {recorded.normalize():f}, but the cited source row "
                f"says "
                f"{Decimal(source).normalize():f}.",
                expected=f"{Decimal(source).normalize():f}",
                actual=f"{recorded.normalize():f}",
                records=[wp.workpaper_id, *(i.get("sources") or [])],
            )


# ---- AUD-03 journal entries ---------------------------------------------------------------------


def _entries_control(world: _World, case: _Case, rec: _Recorder) -> None:
    wp = case.wp
    if wp is None:
        rec.skip("AUD-03", "No workpaper, so no entry was proposed.")
        return
    amount = case.amount
    rec.applied(
        "AUD-03",
        f"{'Drafted entries' if case.drafted is not None else 'The proposed entry'} and "
        f"{len(case.gl)} ledger rows tested.",
    )
    for name in ("expense_account", "accrual_liability_account"):
        code = getattr(wp, name)
        if code not in world.chart:
            rec.critical(
                "AUD-03",
                f"The workpaper's {name.replace('_', ' ')} {code} is not in the chart of accounts.",
                records=[wp.workpaper_id],
            )

    if case.drafted is None:
        _check_lines(
            world, rec, "The proposed entry", wp.journal_entry_json, amount, wp.workpaper_id
        )
    else:
        _check_drafted(world, case, rec)
    _check_ledger(world, case, rec)
    if wp.estimation_method == e.EstimationMethod.PREPAID_AMORTIZATION:
        _check_prepaid_expensing(world, case, rec)


def _check_lines(
    world: _World,
    rec: _Recorder,
    label: str,
    lines: Any,
    amount: Decimal | None,
    record_id: str,
) -> None:
    try:
        total = assert_balanced(lines)
    except UnbalancedEntryError as exc:
        rec.critical(
            "AUD-03",
            f"{label} is not balanced: {exc}.",
            expected="debits equal credits",
            records=[record_id],
        )
        return
    if amount is not None and abs(total - amount) > TOLERANCE:
        rec.critical(
            "AUD-03",
            f"{label} totals {_money(total)}, not the workpaper amount {_money(amount)}.",
            expected=_money(amount),
            actual=_money(total),
            records=[record_id],
        )
    for line in lines:
        if line.get("account_code") not in world.chart:
            rec.critical(
                "AUD-03",
                f"{label} posts to {line.get('account_code')}, which is not in the chart of "
                f"accounts.",
                expected="an account in the chart",
                actual=line.get("account_code"),
                records=[record_id],
            )


def _check_drafted(world: _World, case: _Case, rec: _Recorder) -> None:
    ob, wp = case.ob, case.wp
    assert wp is not None
    accrual, reversal = case.entry(_ACCRUAL), case.entry(_REVERSAL)
    if accrual is None:
        rec.critical(
            "AUD-03",
            "The workpaper holds drafted entries but no accrual.",
            records=[wp.workpaper_id],
        )
        return
    _check_lines(
        world,
        rec,
        f"Accrual {accrual['entry_id']}",
        accrual["lines"],
        case.amount,
        accrual["entry_id"],
    )
    if accrual["period"] != ob.period:
        rec.critical(
            "AUD-03",
            f"Accrual {accrual['entry_id']} is dated to {accrual['period']}, not the obligation's "
            f"period.",
            expected=ob.period,
            actual=accrual["period"],
            records=[accrual["entry_id"]],
        )
    if wp.estimation_method == e.EstimationMethod.PREPAID_AMORTIZATION:
        if reversal is not None:
            rec.critical(
                "AUD-03",
                "A prepaid amortization must not reverse, but a reversal was drafted.",
                expected="no reversal",
                actual=reversal["entry_id"],
                records=[reversal["entry_id"]],
            )
        return
    if reversal is None:
        rec.critical(
            "AUD-03",
            "The accrual has no reversal, so the expense would be counted again when the invoice "
            "posts.",
            expected="a reversal on the first day of the next period",
            actual="none",
            records=[accrual["entry_id"]],
        )
        return
    following = _next_period(ob.period)
    if reversal["reversal_of"] != accrual["entry_id"] or reversal["period"] != following:
        rec.critical(
            "AUD-03",
            f"Reversal {reversal['entry_id']} does not reverse the accrual into {following}.",
            expected=f"reverses {accrual['entry_id']} in {following}",
            actual=f"reverses {reversal['reversal_of']} in {reversal['period']}",
            records=[reversal["entry_id"]],
        )
    first_day = f"{following}-01"
    if reversal["posting_date"] != first_day:
        rec.critical(
            "AUD-03",
            f"Reversal {reversal['entry_id']} is dated {reversal['posting_date']}, not the first "
            f"day of the next period.",
            expected=first_day,
            actual=reversal["posting_date"],
            records=[reversal["entry_id"]],
        )
    if _mirror(accrual["lines"]) != _shape(reversal["lines"]):
        rec.critical(
            "AUD-03",
            f"Reversal {reversal['entry_id']} is not the exact mirror of the accrual.",
            records=[reversal["entry_id"], accrual["entry_id"]],
        )


def _check_ledger(world: _World, case: _Case, rec: _Recorder) -> None:
    ob, wp = case.ob, case.wp
    assert wp is not None
    accruals = case.ledger(_ACCRUAL)
    if len(accruals) > 1:
        rec.critical(
            "AUD-03",
            f"{len(accruals)} accruals are posted for one obligation.",
            expected="1",
            actual=str(len(accruals)),
            records=[g.gl_entry_id for g in accruals],
        )
    for row in case.gl:
        try:
            total = assert_balanced(row.lines_json)
        except UnbalancedEntryError as exc:
            rec.critical(
                "AUD-03",
                f"Ledger entry {row.gl_entry_id} is not balanced: {exc}.",
                expected="debits equal credits",
                records=[row.gl_entry_id],
            )
            continue
        for line in row.lines_json:
            if line.get("account_code") not in world.chart:
                rec.critical(
                    "AUD-03",
                    f"Ledger entry {row.gl_entry_id} posts to {line.get('account_code')}, which is "
                    f"not in the chart.",
                    records=[row.gl_entry_id],
                )
        drafted = case.entry(row.entry_type)
        if drafted is not None and _shape(drafted["lines"]) != _shape(row.lines_json):
            rec.critical(
                "AUD-03",
                f"Ledger entry {row.gl_entry_id} differs from the entry the workpaper drafted.",
                expected=f"the drafted entry of {_money(_ledger_total_lines(drafted['lines']))}",
                actual=_money(total),
                records=[row.gl_entry_id, wp.workpaper_id],
            )
    posted = ob.accrual_status in (
        e.AccrualStatus.POSTED_SIMULATED,
        e.AccrualStatus.TRUE_UP_COMPLETE,
    )
    if (posted or wp.status in _POSTED_WORKPAPER) and not accruals:
        rec.critical(
            "AUD-03",
            "The obligation is marked posted, but no accrual is in the ledger.",
            expected="one accrual",
            actual="none",
            records=[ob.obligation_id],
        )
    reversals = case.ledger(_REVERSAL)
    for row in reversals:
        source = (
            world.session.get(m.CompanyGLEntry, row.reversal_of_gl_entry_id)
            if row.reversal_of_gl_entry_id
            else None
        )
        if source is None or source.status != e.GLEntryStatus.REVERSED:
            rec.warning(
                "AUD-03",
                f"Reversal {row.gl_entry_id} is posted but the accrual it reverses is not marked "
                f"reversed.",
                records=[row.gl_entry_id],
            )
    drafted_reversal = case.entry(_REVERSAL)
    if (
        drafted_reversal is not None
        and accruals
        and not reversals
        and date.fromisoformat(drafted_reversal["posting_date"]) <= world.now.date()
    ):
        rec.warning(
            "AUD-03",
            f"Reversal {drafted_reversal['entry_id']} was due on "
            f"{drafted_reversal['posting_date']} and is not posted.",
            records=[drafted_reversal["entry_id"]],
        )


def _check_prepaid_expensing(world: _World, case: _Case, rec: _Recorder) -> None:
    """A prepaid amount expensed at once in the ledger overstates expense even if we blocked it."""
    ob, amount = case.ob, case.amount
    assert amount is not None
    ours = {g.gl_entry_id for g in case.gl}
    for row in world.session.scalars(
        select(m.CompanyGLEntry).where(m.CompanyGLEntry.vendor_id == ob.vendor_id)
    ):
        if (
            row.gl_entry_id in ours
            or row.status != e.GLEntryStatus.POSTED
            or row.period > ob.period
        ):
            continue
        expensed = max(
            (
                _dec(line.get("debit", 0))
                for line in row.lines_json or []
                if world.chart.get(line.get("account_code")) == "EXPENSE"
            ),
            default=Decimal(0),
        )
        if expensed <= amount:
            continue
        message = (
            f"Ledger entry {row.gl_entry_id} expensed {_money(expensed)} of a prepaid service at "
            f"once; "
            f"the monthly amortization is {_money(amount)}."
        )
        if case.ledger(_ACCRUAL):
            rec.critical(
                "AUD-03",
                message + " The accrual posted on top double counts it.",
                expected=_money(amount),
                actual=_money(expensed),
                records=[row.gl_entry_id],
            )
        else:
            rec.warning(
                "AUD-03",
                message
                + " No accrual was posted, but the ledger still carries the one-time expense.",
                expected=_money(amount),
                actual=_money(expensed),
                records=[row.gl_entry_id],
            )


def _shape(lines: list[dict[str, Any]]) -> list[tuple[str, Decimal, Decimal]]:
    return sorted(
        (x["account_code"], _dec(x.get("debit", 0)), _dec(x.get("credit", 0))) for x in lines
    )


def _mirror(lines: list[dict[str, Any]]) -> list[tuple[str, Decimal, Decimal]]:
    return sorted(
        (x["account_code"], _dec(x.get("credit", 0)), _dec(x.get("debit", 0))) for x in lines
    )


# ---- AUD-04 policy and approvals ----------------------------------------------------------------

_TIME_VARYING_RULES = ("_pol_04",)


def _approvals_control(world: _World, case: _Case, rec: _Recorder) -> None:
    wp = case.wp
    decisions = [c for c in case.cards if c.evidence_type == e.EvidenceCardType.CONTROLLER_DECISION]
    rec.applied(
        "AUD-04",
        f"{len(decisions)} Controller decision cards and the recorded policy result tested.",
    )
    for card in decisions:
        _trace_decision(world, case, rec, card)
    if wp is None:
        return
    _reperform_policy(world, case, rec)

    approval = wp.controller_decision
    if approval is not None:
        card = next(
            (
                c
                for c in decisions
                if (c.value_json or {}).get("workpaper_id") == wp.workpaper_id
                and (c.value_json or {}).get("decision") == approval.value
            ),
            None,
        )
        if card is None:
            rec.critical(
                "AUD-04",
                f"Workpaper {wp.workpaper_id} shows a Controller {approval.value}, but no decision "
                f"card records it.",
                records=[wp.workpaper_id],
            )
        elif approval in _APPROVING:
            value = card.value_json
            approved = _dec(value.get("adjusted_amount") or value.get("original_amount"))
            if abs(approved - case.amount) > TOLERANCE:
                rec.critical(
                    "AUD-04",
                    f"The workpaper amount {_money(case.amount)} differs from the "
                    f"{_money(approved)} the Controller approved.",
                    expected=_money(approved),
                    actual=_money(case.amount),
                    records=[wp.workpaper_id, card.evidence_id],
                )

    needs_controller = wp.policy_decision == e.PolicyDecision.REQUIRE_CONTROLLER or (
        world.threshold is not None
        and case.original_amount is not None
        and case.original_amount >= world.threshold
    )
    if needs_controller and case.proceeded():
        approving = [
            c
            for c in decisions
            if (c.value_json or {}).get("decision") in {d.value for d in _APPROVING}
            and (c.value_json or {}).get("workpaper_id") == wp.workpaper_id
            and (c.value_json or {}).get("decided_by") == world.controller
        ]
        if not approving:
            rec.critical(
                "AUD-04",
                f"An accrual of {_money(case.original_amount)} needs the Controller's approval and "
                f"none is on record.",
                expected=f"an approval by {world.controller}",
                actual="none",
                records=[wp.workpaper_id],
            )
    if wp.policy_decision == e.PolicyDecision.BLOCK and (
        case.proceeded() or wp.controller_decision in _APPROVING or wp.status in _POSTED_WORKPAPER
    ):
        rec.critical(
            "AUD-04",
            "Policy blocked this accrual, yet it was approved or posted.",
            expected="no approval and no posting",
            actual=f"status {wp.status.value}",
            records=[wp.workpaper_id],
        )


def _trace_decision(world: _World, case: _Case, rec: _Recorder, card: m.TrueUpEvidence) -> None:
    value = card.value_json or {}
    backing = [
        r
        for r in case.ran("controller_workspace", "record_decision")
        if card.evidence_id in (r.output_record_ids_json or [])
    ]
    if not backing:
        rec.critical(
            "AUD-04",
            f"Decision card {card.evidence_id} has no Controller Workspace run behind it.",
            expected="a recorded decision run",
            actual="none",
            records=[card.evidence_id],
        )
    if value.get("decided_by") != world.controller or card.source_id != value.get("decided_by"):
        rec.critical(
            "AUD-04",
            f"Decision card {card.evidence_id} was made by {value.get('decided_by')}, "
            "not the configured controller.",
            expected=world.controller,
            actual=value.get("decided_by"),
            records=[card.evidence_id],
        )


def _reperform_policy(world: _World, case: _Case, rec: _Recorder) -> None:
    ob, wp = case.ob, case.wp
    assert wp is not None
    if wp.policy_decision == e.PolicyDecision.NOT_RUN:
        if case.proceeded() or wp.status in (e.WorkpaperStatus.APPROVED, *_POSTED_WORKPAPER):
            rec.critical(
                "AUD-04",
                "The accrual was approved or drafted but policy never ran.",
                expected="a policy decision",
                actual=e.PolicyDecision.NOT_RUN.value,
                records=[wp.workpaper_id],
            )
        return
    if not case.ran("policy", "verify_policy"):
        rec.critical(
            "AUD-04",
            f"Workpaper {wp.workpaper_id} carries a policy decision but no policy run is logged.",
            records=[wp.workpaper_id],
        )
    adjusted = bool(case.inputs.get("controller_adjustment"))
    lines = wp.journal_entry_json
    if isinstance(lines, dict):
        lines = (case.entry(_ACCRUAL) or {}).get("lines", [])
    view = SimpleNamespace(
        **{c.name: getattr(wp, c.name) for c in wp.__table__.columns},
    )
    view.proposed_amount = case.original_amount
    view.journal_entry_json = lines
    session = world.session
    config = policy_agent._load_config(session)
    context = policy_agent.Context(
        config=config,
        obligation=ob,
        workpaper=view,
        po=session.get(m.CompanyPurchaseOrder, ob.po_id) if ob.po_id else None,
        gl_entries=list(
            session.scalars(
                select(m.CompanyGLEntry).where(m.CompanyGLEntry.vendor_id == ob.vendor_id)
            )
        ),
    )
    skipped = set(_TIME_VARYING_RULES) | ({"_pol_05"} if adjusted else set())
    results = [r(context) for r in policy_agent._RULES if r.__name__ not in skipped]
    decision = next(
        d
        for d in policy_agent._PRECEDENCE
        if d == e.PolicyDecision.PERMIT or policy_agent._has(results, d)
    )
    if decision != wp.policy_decision:
        hits = ", ".join(r.rule_id for r in results if r.status == "HIT") or "no rule"
        rec.critical(
            "AUD-04",
            f"Re-running the policy rules gives {decision.value} ({hits}), not the recorded "
            f"{wp.policy_decision.value}.",
            expected=decision.value,
            actual=wp.policy_decision.value,
            records=[wp.workpaper_id],
        )


# ---- AUD-05 workflow integrity ------------------------------------------------------------------


def _reachable(start: tuple[Any, Any], goal: tuple[Any, Any]) -> bool:
    if start == goal:
        return True
    graph = allowed_transitions()
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in graph.get(queue.popleft(), ()):
            if nxt == goal:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _start_state(run: m.TrueUpAgentRun) -> tuple[e.WorkflowStage, e.NextAction] | None:
    if (run.agent_name, run.action) == ("controller_workspace", "record_decision"):
        for fact in run.facts_used_json or []:
            if isinstance(fact, dict) and fact.get("from_state"):
                stage, action = fact["from_state"].split("/")
                return e.WorkflowStage(stage), e.NextAction(action)
        return None
    return _STARTS_AT.get((run.agent_name, run.action))


def _workflow_control(world: _World, case: _Case, rec: _Recorder) -> None:
    ob, wp = case.ob, case.wp
    graph = allowed_transitions()
    known = set(graph) | {s for targets in graph.values() for s in targets}
    stops = [(run, state) for run in case.runs if (state := _start_state(run)) is not None]
    rec.applied("AUD-05", f"{len(stops)} logged steps checked against the workflow graph.")
    if case.state not in known:
        rec.critical(
            "AUD-05",
            f"{ob.workflow_stage.value}/{ob.next_action.value} is not a state of the workflow.",
            records=[ob.obligation_id],
        )
        return
    previous: tuple[e.WorkflowStage, e.NextAction] = INITIAL
    for run, state in stops:
        if not _reachable(previous, state):
            rec.critical(
                "AUD-05",
                f"{run.agent_name} ran {run.action} at {state[0].value}/{state[1].value}, which "
                f"the "
                f"workflow cannot reach from {previous[0].value}/{previous[1].value}.",
                expected=f"a state reachable from {previous[0].value}/{previous[1].value}",
                actual=f"{state[0].value}/{state[1].value}",
                records=[run.run_id],
            )
        previous = state
    if not _reachable(previous, case.state):
        rec.critical(
            "AUD-05",
            f"The obligation is at {ob.workflow_stage.value}/{ob.next_action.value}, which the "
            f"last "
            f"logged step ({previous[0].value}/{previous[1].value}) cannot lead to.",
            expected=f"a state reachable from {previous[0].value}/{previous[1].value}",
            actual=f"{ob.workflow_stage.value}/{ob.next_action.value}",
            records=[ob.obligation_id],
        )
    _check_order(case, rec)
    _state_needs_evidence(case, rec, wp)


_REQUIRES: dict[tuple[e.WorkflowStage, e.NextAction], tuple[str, str, str]] = {
    (_S.GATHERING_EVIDENCE, _A.GATHER_EVIDENCE): (
        "invoice_lookup",
        "search_ap",
        "an invoice search",
    ),
    (_S.CLASSIFYING, _A.CLASSIFY): ("invoice_lookup", "search_ap", "an invoice search"),
    (_S.ESTIMATING, _A.ESTIMATE): ("classification", "classify_purchase", "a classification"),
    (_S.ESTIMATING, _A.VERIFY_POLICY): ("estimation", "estimate_accrual", "an estimate"),
    (_S.READY_TO_DRAFT, _A.DRAFT_ENTRY): ("policy", "verify_policy", "a policy decision"),
    (_S.AWAITING_ACTUAL_INVOICE, _A.WAIT_FOR_INVOICE): (
        "journal_entry_service",
        "draft_entry",
        "drafted entries",
    ),
    (_S.RECONCILING, _A.MATCH_AND_TRUE_UP): (
        "reconciliation",
        "match_invoice",
        "a matched invoice",
    ),
    (_S.RECONCILING, _A.EVALUATE_LEARNING): ("reconciliation", "reconcile", "a reconciliation"),
    (_S.CLOSED, _A.NONE): ("reconciliation", "reconcile", "a reconciliation"),
}
# Each of these runs at most once per workpaper, and always after the ones before it.
_ORDER = {
    "verify_policy": 1,
    "draft_entry": 3,
    "post_simulated": 4,
    "match_invoice": 5,
    "reconcile": 6,
}


def _state_needs_evidence(case: _Case, rec: _Recorder, wp: m.TrueUpWorkpaper | None) -> None:
    stage, action = case.state
    ob = case.ob

    def need(condition: bool, what: str) -> None:
        if not condition:
            rec.critical(
                "AUD-05",
                f"The obligation is at {stage.value}/{action.value} without {what}.",
                expected=what,
                actual="none",
                records=[ob.obligation_id],
            )

    required = _REQUIRES.get(case.state)
    if required is not None:
        need(bool(case.ran(required[0], required[1])), required[2])
    if case.state == (_S.READY_TO_DRAFT, _A.DRAFT_ENTRY):
        need(wp is not None and wp.status == e.WorkpaperStatus.APPROVED, "an approved workpaper")
    if case.state == (_S.AWAITING_ACTUAL_INVOICE, _A.WAIT_FOR_INVOICE):
        need(case.drafted is not None, "drafted entries in the workpaper")
    if case.state == (_S.CLOSED_NO_ACCRUAL, _A.NONE):
        need(
            bool(
                case.ran("invoice_lookup", "search_ap")
                or case.ran("controller_workspace", "record_decision")
            ),
            "an invoice search or a Controller decision",
        )
        need(not case.ledger(_ACCRUAL), "no accrual in the ledger")


def _check_order(case: _Case, rec: _Recorder) -> None:
    last: dict[str, m.TrueUpAgentRun] = {}
    for run in case.runs:
        rank = _ORDER.get(run.action)
        if rank is None or not run.workpaper_id:
            continue
        prior = last.get(run.workpaper_id)
        if prior is not None and rank <= _ORDER[prior.action]:
            rec.critical(
                "AUD-05",
                f"{run.agent_name} ran {run.action} on {run.workpaper_id} after {prior.action}, "
                "which is out of order.",
                expected=f"a step after {prior.action}",
                actual=run.action,
                records=[run.run_id, prior.run_id],
            )
        last[run.workpaper_id] = run


# ---- AUD-06 cutoff and duplicates ---------------------------------------------------------------


def _cutoff_control(world: _World, case: _Case, rec: _Recorder) -> None:
    ob = case.ob
    accruals = case.ledger(_ACCRUAL)
    rec.applied("AUD-06", f"{len(accruals)} posted accruals tested for cutoff and duplication.")
    for row in accruals:
        early = reconciliation_agent.matching_invoices(world.session, ob, now=_utc(row.created_at))
        if early:
            rec.critical(
                "AUD-06",
                f"AP invoice {early[0].invoice_id} had already been received when accrual "
                f"{row.gl_entry_id} posted, so the expense is counted twice.",
                expected="no matching AP invoice at posting time",
                actual=", ".join(i.invoice_id for i in early),
                records=[row.gl_entry_id, *(i.invoice_id for i in early)],
            )
    if not accruals:
        return
    twins = world.session.scalars(
        select(m.TrueUpObligation).where(
            m.TrueUpObligation.vendor_id == ob.vendor_id,
            m.TrueUpObligation.period == ob.period,
            m.TrueUpObligation.obligation_id != ob.obligation_id,
        )
    ).all()
    for other in twins:
        if (other.contract_id, other.po_id, other.non_po_group_key) != (
            ob.contract_id,
            ob.po_id,
            ob.non_po_group_key,
        ):
            continue
        posted = world.session.scalars(
            select(m.CompanyGLEntry).where(
                m.CompanyGLEntry.obligation_id == other.obligation_id,
                m.CompanyGLEntry.entry_type == _ACCRUAL,
                m.CompanyGLEntry.status.in_(_LEDGER_LIVE),
            )
        ).all()
        if posted:
            rec.critical(
                "AUD-06",
                f"{other.obligation_id} also accrued the same vendor, period and source.",
                expected="one accrual",
                actual="two",
                records=[other.obligation_id, posted[0].gl_entry_id],
            )


# ---- AUD-07 reconciliation ----------------------------------------------------------------------


def _reconciliation_control(world: _World, case: _Case, rec: _Recorder) -> None:
    ob, wp = case.ob, case.wp
    record = case.inputs.get("reconciliation")
    if wp is None or not record:
        rec.skip("AUD-07", "No invoice has been reconciled against this accrual yet.")
        return
    rec.applied(
        "AUD-07", f"The reconciliation of {', '.join(record['invoice_ids'])} was re-performed."
    )
    session = world.session
    invoices = [session.get(m.CompanyAPInvoice, i) for i in record["invoice_ids"]]
    missing = [i for i, inv in zip(record["invoice_ids"], invoices, strict=True) if inv is None]
    if missing:
        rec.critical(
            "AUD-07",
            f"The reconciliation cites invoices that do not exist: {', '.join(missing)}.",
            records=missing,
        )
        return
    usable = [
        inv
        for inv in invoices
        if inv.status not in _EXCLUDED_INVOICE and not inv.credit_flag and not inv.duplicate_flag
    ]
    accrued = case.original_amount
    actual = sum((_dec(inv.amount) for inv in usable), Decimal(0))
    for name, recorded, expected in (
        ("accrued", record["accrued"], accrued),
        ("actual", record["actual"], actual),
        ("variance", record["variance"], actual - accrued),
    ):
        if abs(_dec(recorded) - expected) > TOLERANCE:
            rec.critical(
                "AUD-07",
                f"The reconciliation records {name} {_money(recorded)}, but the records give "
                f"{_money(expected)}.",
                expected=_money(expected),
                actual=_money(recorded),
                records=[wp.workpaper_id, *record["invoice_ids"]],
            )
    for row in case.ledger(_ACCRUAL):
        if abs(_ledger_total(row) - accrued) > TOLERANCE:
            rec.critical(
                "AUD-07",
                f"The ledger accrual {row.gl_entry_id} is {_money(_ledger_total(row))}, not the "
                f"{_money(accrued)} that was reconciled.",
                expected=_money(accrued),
                actual=_money(_ledger_total(row)),
                records=[row.gl_entry_id],
            )
    diagnosis = reconciliation_agent._diagnose(
        wp.estimation_method,
        case.inputs,
        usable,
        accrued,
        actual,
        reconciliation_agent._rate_candidates(session, ob),
    )
    cause = diagnosis.root_cause.value if diagnosis.root_cause else None
    if cause != record.get("root_cause") or diagnosis.accepted != record.get("invoice_accepted"):
        rec.critical(
            "AUD-07",
            f"Re-diagnosing the variance gives {cause or 'a match'}, not the recorded "
            f"{record.get('root_cause') or 'match'}.",
            expected=cause or "MATCH",
            actual=record.get("root_cause") or "MATCH",
            records=[wp.workpaper_id],
        )
    reconciled_at = _utc(datetime.fromisoformat(record["reconciled_at"]))
    matching = {
        i.invoice_id for i in reconciliation_agent.matching_invoices(session, ob, now=reconciled_at)
    }
    for invoice_id in set(record["invoice_ids"]) - matching:
        rec.critical(
            "AUD-07",
            f"Invoice {invoice_id} was reconciled but does not match the obligation's vendor, "
            f"window and references.",
            records=[invoice_id],
        )
    for invoice_id in matching - set(record["invoice_ids"]):
        rec.warning(
            "AUD-07",
            f"Invoice {invoice_id} matches the obligation but was left out of the reconciliation.",
            records=[invoice_id],
        )
    target = reconciliation_agent._route(
        diagnosis,
        actual - accrued,
        reconciliation_agent._de_minimis(session),
        any(inv.currency != wp.currency for inv in usable),
    )
    reconcile_ids = [r.run_id for r in case.ran("reconciliation", "reconcile")]
    moved_on = bool(reconcile_ids) and any(r.run_id > max(reconcile_ids) for r in case.runs)
    if case.state != (e.WorkflowStage(target[0]), e.NextAction(target[1])) and not moved_on:
        rec.critical(
            "AUD-07",
            f"A {cause or 'match'} should route to {target[0].value}/{target[1].value}, but the "
            f"obligation is at {ob.workflow_stage.value}/{ob.next_action.value}.",
            expected=f"{target[0].value}/{target[1].value}",
            actual=f"{ob.workflow_stage.value}/{ob.next_action.value}",
            records=[ob.obligation_id],
        )


def _ledger_total(row: m.CompanyGLEntry) -> Decimal:
    return _ledger_total_lines(row.lines_json or [])


def _ledger_total_lines(lines: list[dict[str, Any]]) -> Decimal:
    return sum((_dec(line.get("debit", 0)) for line in lines), Decimal(0))


# ---- AUD-08 learning rules ----------------------------------------------------------------------


def _learning_control(world: _World, case: _Case, rec: _Recorder) -> None:
    wp = case.wp
    applied = case.inputs.get("rules_applied") or []
    if wp is None:
        rec.skip("AUD-08", "No workpaper, so no rule could have been applied.")
        return
    rec.applied("AUD-08", f"{len(applied)} learned rules applied to this estimate.")
    active = {learning_id for learning_id, _ in world.rules_active_at(wp.created_at)}
    for entry in applied:
        learning_id = entry.get("learning_id")
        if learning_id not in active:
            rec.critical(
                "AUD-08",
                f"The estimate applied rule {learning_id}, which was not an approved, active rule "
                f"when it was written.",
                expected="a rule approved by the Controller and not revoked",
                actual=learning_id,
                records=[wp.workpaper_id, str(learning_id)],
            )
    if case.inputs.get("step_up_applied") and not applied:
        rec.critical(
            "AUD-08",
            "An escalator step-up was applied without any approved rule behind it.",
            expected="a rule in rules_applied",
            actual="none",
            records=[wp.workpaper_id],
        )


def _rules_control(world: _World, rec: _Recorder) -> None:
    rows = world.rule_rows
    rec.applied("AUD-08", f"{len(rows)} learned rules examined.")
    vendors = [(v.vendor_id, v.vendor_name) for v in world.session.scalars(select(m.CompanyVendor))]
    for row in rows:
        lid = row.learning_id
        if row.status != e.LearningStatus.ACTIVE:
            if row.status == e.LearningStatus.REVOKED and _revoked_at(row) is None:
                rec.warning(
                    "AUD-08", f"Rule {lid} is revoked but records no revocation.", records=[lid]
                )
            continue
        if row.approved_by != world.controller or lid not in world.approved_at:
            rec.critical(
                "AUD-08",
                f"Active rule {lid} has no approval by the configured controller on record.",
                expected=f"approved by {world.controller}",
                actual=row.approved_by or "no approval",
                records=[lid],
            )
        replay = row.replay_result_json or {}
        if not replay.get("passed") or not all(
            (replay.get("criteria") or {"missing": False}).values()
        ):
            rec.critical(
                "AUD-08",
                f"Active rule {lid} has no passing replay behind it.",
                expected="a passing replay",
                actual="none" if not replay else "failed",
                records=[lid],
            )
        try:
            rule = CandidateRule.model_validate(row.candidate_rule_json)
            reject_vendor_references(rule, vendors)
        except (ValidationError, BiasGuardError, ValueError) as exc:
            rec.critical(
                "AUD-08",
                f"Active rule {lid} names a vendor or is malformed: {type(exc).__name__}.",
                records=[lid],
            )
            continue
        life = rule.lifecycle
        if life is None:
            rec.warning("AUD-08", f"Active rule {lid} has no lifecycle record.", records=[lid])
        elif life.contradictions >= 1:
            rec.critical(
                "AUD-08",
                f"Active rule {lid} was contradicted by a true-up and must have been revoked.",
                expected=e.LearningStatus.REVOKED.value,
                actual=row.status.value,
                records=[lid],
            )
        elif life.stage == "CONFIRMED" and life.uses < MIN_CONFIRMATIONS:
            rec.critical(
                "AUD-08",
                f"Rule {lid} is marked confirmed after {life.uses} true-ups, fewer than "
                f"{MIN_CONFIRMATIONS}.",
                expected=str(MIN_CONFIRMATIONS),
                actual=str(life.uses),
                records=[lid],
            )


# ---- AUD-10 verified handoffs -------------------------------------------------------------------

_HOLD_LABELS = frozenset(
    {
        "AWAITING_OUTREACH/SEND_OUTREACH",
        "AWAITING_CONTROLLER/CONTROLLER_REVIEW",
        "BLOCKED/CONTROLLER_REVIEW",
    }
)
_ACTION_ONLY = frozenset({"POST_ACCRUAL", "APPROVE_RULE"})


def _verifier_control(world: _World, case: _Case, rec: _Recorder) -> None:
    """Every move the obligation made has a verifier record, and only a PERMIT moved it on."""
    rows = [r for r in case.runs if (r.agent_name, r.action) == ("verifier", "verify_handoff")]
    if not rows:
        rec.skip("AUD-10", "The close ran without the verifier, so no handoff was verified.")
        return
    rec.applied("AUD-10", f"{len(rows)} verified handoffs chained to the resting state.")
    previous: str | None = None
    for run in rows:
        facts = [f for f in run.facts_used_json or [] if isinstance(f, dict)]
        routing = next((f for f in facts if f.get("kind") == "routing"), None)
        result = next((f for f in facts if f.get("kind") == "verification_result"), None)
        proposal = next((f for f in facts if f.get("kind") == "action_proposal"), {})
        if routing is None or result is None:
            rec.critical(
                "AUD-10",
                f"Verifier run {run.run_id} carries no routing or result.",
                records=[run.run_id],
            )
            continue
        action = (proposal.get("proposal") or {}).get("action_type")
        if previous is not None and routing["from"] != previous:
            rec.critical(
                "AUD-10",
                f"The obligation moved from {previous} to {routing['from']} without a verified "
                "handoff.",
                expected=previous,
                actual=routing["from"],
                records=[run.run_id],
            )
        verdict = result["result"]["verdict"]
        if (
            action not in _ACTION_ONLY
            and routing["routed"] not in _HOLD_LABELS
            and verdict != "PERMIT"
        ):
            rec.critical(
                "AUD-10",
                f"The obligation was moved to {routing['routed']} although the verifier answered "
                f"{verdict}.",
                expected="PERMIT",
                actual=verdict,
                records=[run.run_id],
            )
        previous = routing["routed"]
    current = f"{case.ob.workflow_stage.value}/{case.ob.next_action.value}"
    if previous is not None and previous != current:
        rec.critical(
            "AUD-10",
            f"The obligation is at {current}, but the last verified handoff left it at {previous}.",
            expected=previous,
            actual=current,
            records=[case.ob.obligation_id],
        )


# ---- AUD-09 completeness ------------------------------------------------------------------------


def _completeness_control(world: _World, case: _Case, rec: _Recorder) -> None:
    ob = case.ob
    rec.applied("AUD-09", f"{len(case.runs)} logged runs and the resting state tested.")
    terminal = case.state[0] in (_S.CLOSED, _S.CLOSED_NO_ACCRUAL)
    if case.state == (_S.DETECTED, _A.SEARCH_AP):
        rec.warning(
            "AUD-09",
            "The obligation was detected but no agent has started it.",
            records=[ob.obligation_id],
        )
    elif not terminal and not ob.assigned_agent:
        rec.warning(
            "AUD-09",
            "The obligation is open and no agent or person owns it.",
            records=[ob.obligation_id],
        )
    for run in case.runs:
        if run.status != e.AgentRunStatus.FAILED:
            continue
        resolved = any(
            r.run_id > run.run_id
            and (r.agent_name, r.action) == (run.agent_name, run.action)
            and r.status != e.AgentRunStatus.FAILED
            for r in case.runs
        )
        if not resolved:
            rec.critical(
                "AUD-09",
                f"{run.agent_name} failed at {run.action} and no later run resolved it.",
                records=[run.run_id],
            )


def _period_control(world: _World, period: str, rec: _Recorder) -> None:
    """Every contract and purchase order in force has an obligation, unless Detection skipped it."""
    session = world.session
    year, month = (int(p) for p in period.split("-"))
    first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    obligations = session.scalars(
        select(m.TrueUpObligation).where(m.TrueUpObligation.period == period)
    ).all()
    have_contracts = {o.contract_id for o in obligations if o.contract_id}
    have_pos = {o.po_id for o in obligations if o.po_id}
    detections = session.scalars(
        select(m.TrueUpAgentRun)
        .where(m.TrueUpAgentRun.agent_name == "detection")
        .where(m.TrueUpAgentRun.action == "detect_obligations")
    ).all()
    skipped = {
        f.get("ref")
        for run in detections
        for f in run.facts_used_json or []
        if f.get("decision") == "skipped"
    }
    inactive = {v.vendor_id for v in session.scalars(select(m.CompanyVendor)) if not v.is_active}
    rec.applied(
        "AUD-09", f"Contracts and purchase orders in force in {period} matched to obligations."
    )

    existing = {o.obligation_id for o in obligations}
    for run in detections:
        for opened in run.output_record_ids_json or []:
            if period in opened and opened not in existing:
                rec.critical(
                    "AUD-09",
                    f"Obligation {opened} was opened by Detection and no longer exists.",
                    records=[opened, run.run_id],
                )

    def overlaps(start: date | None, end: date | None) -> bool:
        return (start is None or start <= last) and (end is None or end >= first)

    versions: dict[str, list[m.CompanyContract]] = {}
    for contract in session.scalars(select(m.CompanyContract)):
        versions.setdefault(contract.contract_id, []).append(contract)
    for contract_id, rows in versions.items():
        live = [
            v
            for v in rows
            if overlaps(v.effective_start_date, v.effective_end_date)
            and v.status in CONTRACT_STATUSES_IN_FORCE
        ]
        if (
            live
            and contract_id not in have_contracts
            and contract_id not in skipped
            and rows[-1].vendor_id not in inactive
        ):
            rec.critical(
                "AUD-09",
                f"Contract {contract_id} is in force in {period} but has no obligation.",
                expected="an obligation",
                actual="none",
                records=[contract_id],
            )
    for po in session.scalars(
        select(m.CompanyPurchaseOrder).order_by(m.CompanyPurchaseOrder.po_id)
    ):
        if po.status not in PO_STATUSES_TO_ACCRUE or not overlaps(
            po.service_start_date, po.service_end_date
        ):
            continue
        covered = po.po_id in have_pos or (po.contract_id and po.contract_id in have_contracts)
        if not covered and po.po_id not in skipped and po.vendor_id not in inactive:
            rec.critical(
                "AUD-09",
                f"Purchase order {po.po_id} is in force in {period} but has no obligation.",
                expected="an obligation",
                actual="none",
                records=[po.po_id],
            )


_OBLIGATION_CONTROLS: list[tuple[str, Callable[[_World, _Case, _Recorder], None]]] = [
    ("AUD-01", _evidence_control),
    ("AUD-02", _recomputation_control),
    ("AUD-03", _entries_control),
    ("AUD-04", _approvals_control),
    ("AUD-05", _workflow_control),
    ("AUD-06", _cutoff_control),
    ("AUD-07", _reconciliation_control),
    ("AUD-08", _learning_control),
    ("AUD-09", _completeness_control),
    ("AUD-10", _verifier_control),
]


# ---- summary and log ----------------------------------------------------------------------------


def llm_narrator(facts: dict[str, Any]) -> str:
    return llm.complete(PROMPT_PATH.read_text().replace("{{FACTS}}", json.dumps(facts, indent=2)))


def _facts(
    period: str | None,
    audits: list[ObligationAudit],
    counts: dict[str, int],
    findings: list[Finding],
) -> dict[str, Any]:
    return {
        "period": period,
        "obligations_tested": len(audits),
        "findings_by_severity": counts,
        "findings": [
            {
                "check_id": f.check_id,
                "severity": f.severity.value,
                "obligation_id": f.obligation_id,
                "message": f.message,
                "expected": f.expected,
                "actual": f.actual,
            }
            for f in findings[:12]
        ],
    }


def _narrate(
    facts: dict[str, Any], narrator: Narrator | None
) -> tuple[str, Literal["template", "llm"], str | None]:
    template = _template(facts)
    if narrator is None:
        if not llm.available():
            return template, "template", "LLM unavailable; used the deterministic summary."
        narrator = llm_narrator
    try:
        text = narrator(facts).strip()
    except llm.LLMError as exc:
        return template, "template", f"LLM summary failed: {exc}"
    if not text:
        return template, "template", "LLM returned an empty summary."
    invented = _numbers(text) - _numbers(json.dumps(facts))
    if invented:
        listed = ", ".join(format(n, "f") for n in sorted(invented))
        return template, "template", f"LLM summary rejected: numbers not in the facts: {listed}."
    return text, "llm", None


def _template(facts: dict[str, Any]) -> str:
    counts = facts["findings_by_severity"]
    scope = facts["period"] or "the selected obligations"
    tested = facts["obligations_tested"]
    noun = _plural(tested, "obligation")
    head = f"The Auditor re-performed the controls on {tested} {noun} for {scope}."
    critical = [f for f in facts["findings"] if f["severity"] == Severity.CRITICAL.value]
    if not critical:
        tail = (
            f"No critical findings; {counts['WARNING']} {_plural(counts['WARNING'], 'warning')} "
            f"and {counts['INFO']} {_plural(counts['INFO'], 'note')} remain."
        )
    else:
        named = ", ".join(
            sorted(
                {f"{f['check_id']} on {f['obligation_id'] or 'the whole close'}" for f in critical}
            )
        )
        many = counts["CRITICAL"]
        tail = f"{many} critical {_plural(many, 'finding')} need the Controller: {named}."
    return f"{head} {tail}"


_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[Decimal]:
    found = set()
    for token in _NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def _log(session: Session, report: AuditReport, now: datetime) -> str:
    critical = report.counts[Severity.CRITICAL.value]
    run = AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="audit_close",
        status=e.AgentRunStatus.ESCALATED if critical else e.AgentRunStatus.COMPLETED,
        decision_summary=report.summary,
        output_summary=(
            f"{critical} critical, {report.counts[Severity.WARNING.value]} warning, "
            f"{report.counts[Severity.INFO.value]} info findings."
        ),
        at=now,
        facts_used=[report.model_dump(mode="json")],
        uncertainties=[f.message for f in report.findings if f.severity != Severity.CRITICAL]
        or None,
        input_record_ids=[o.obligation_id for o in report.obligations],
        output_record_ids=[],
    )
    return run.run_id


# ---- small helpers ------------------------------------------------------------------------------


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else f"{noun}s"


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


def _money(value: object) -> str:
    return f"{_dec(value):.2f}"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).lower()).strip()


def _next_period(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    return f"{year + month // 12}-{month % 12 + 1:02d}"
