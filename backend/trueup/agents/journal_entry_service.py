"""Journal Entry Service: draft an approved workpaper as a balanced accrual and its reversal.

Deterministic, no model. A drafted entry lives in the workpaper's `journal_entry_json`
({"entries": [accrual, reversal?]}) and nothing reaches `company_gl_entries` until it is posted.
Posting is simulated, so every GL row it writes says so in its description.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog, assert_balanced
from trueup.store.types import coerce_money
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "journal_entry_service"
CENT = Decimal("0.01")
SIMULATED_PREFIX = "[Simulated TrueUp posting]"
_APPROVING = (e.ControllerDecision.APPROVE, e.ControllerDecision.APPROVE_WITH_ADJUSTMENT)


class JournalEntryError(ValueError):
    """Base class for refusals; a refused call changes nothing."""


class MissingWorkpaperError(JournalEntryError):
    """The obligation has no workpaper to draft from."""


class NotApprovedError(JournalEntryError):
    """The workpaper is not approved, so no entry may be drafted."""


class ClosedPeriodError(JournalEntryError):
    """The accounting period is closed or unknown."""


class AlreadyDraftedError(JournalEntryError):
    """The workpaper already carries drafted entries."""


class NotDraftedError(JournalEntryError):
    """There is no drafted entry to post."""


class AlreadyPostedError(JournalEntryError):
    """The entry is already in the ledger; posting twice would double count."""


class DraftResult(BaseModel):
    obligation_id: str
    workpaper_id: str
    approved_by: str
    entries: list[dict[str, Any]]


class PostResult(BaseModel):
    obligation_id: str
    gl_entry_id: str


class PostedReversal(BaseModel):
    obligation_id: str
    gl_entry_id: str
    reverses: str
    posting_date: date


class SkippedReversal(BaseModel):
    entry_id: str
    reason: str


class ReversalsResult(BaseModel):
    posted: list[PostedReversal]
    skipped: list[SkippedReversal]


def draft_entry(session: Session, obligation_id: str, *, now: datetime) -> DraftResult:
    """Draft an approved workpaper as an accrual (plus reversal) and wait for the invoice."""
    obligation = _obligation(session, obligation_id)
    state = (obligation.workflow_stage, obligation.next_action)
    if state != (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY):
        raise IllegalTransitionError(
            f"{obligation_id} is at {state[0]}/{state[1]}, not READY_TO_DRAFT/DRAFT_ENTRY"
        )
    workpaper = _workpaper(session, obligation)
    approved_by = _approver(workpaper)
    lines = workpaper.journal_entry_json
    if isinstance(lines, dict):
        raise AlreadyDraftedError(f"{workpaper.workpaper_id} already has drafted entries")
    total = assert_balanced(lines)
    if total != coerce_money(workpaper.proposed_amount):
        raise JournalEntryError(
            f"entry total {total} does not match the approved amount {workpaper.proposed_amount}"
        )
    periods = _periods(session)
    period = _open_period(periods, obligation.period)

    vendor = session.get(m.CompanyVendor, obligation.vendor_id)
    name = vendor.vendor_name if vendor else obligation.vendor_id
    memo = f"Accrual for {name} {obligation.period}, {workpaper.estimation_method.value}"
    accrual = _entry(
        f"JE-{obligation_id}-ACC",
        e.GLEntryType.ACCRUAL,
        obligation.period,
        date.fromisoformat(period["period_end"]),
        f"{memo} (workpaper {workpaper.workpaper_id})",
        [_line(line, memo) for line in lines],
        None,
    )
    entries = [accrual]
    if workpaper.estimation_method != e.EstimationMethod.PREPAID_AMORTIZATION:
        next_period = _next_period(obligation.period)
        entries.append(
            _entry(
                f"JE-{obligation_id}-REV",
                e.GLEntryType.ACCRUAL_REVERSAL,
                next_period,
                _first_day(next_period),
                f"Reversal of {accrual['entry_id']}: {memo}",
                [
                    _line(
                        {
                            "account_code": line["account_code"],
                            "debit": line["credit"],
                            "credit": line["debit"],
                        },
                        f"Reversal: {memo}",
                    )
                    for line in accrual["lines"]
                ],
                accrual["entry_id"],
            )
        )

    workpaper.journal_entry_json = {"entries": entries}
    workpaper.updated_at = now
    obligation.accrual_status = e.AccrualStatus.DRAFTED
    advance(
        obligation,
        e.WorkflowStage.AWAITING_ACTUAL_INVOICE,
        e.NextAction.WAIT_FOR_INVOICE,
        AGENT_NAME,
        at=now,
    )
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="draft_entry",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=(
            f"Drafted {len(entries)} balanced entr{'y' if len(entries) == 1 else 'ies'} "
            f"totalling {total:.2f} from {workpaper.workpaper_id}, approved by {approved_by}."
        ),
        output_summary=", ".join(entry["entry_id"] for entry in entries),
        at=now,
        obligation_id=obligation_id,
        workpaper_id=workpaper.workpaper_id,
        facts_used=[_fact(entry) for entry in entries],
        input_record_ids=[workpaper.workpaper_id],
        output_record_ids=[entry["entry_id"] for entry in entries],
    )
    session.flush()
    return DraftResult(
        obligation_id=obligation_id,
        workpaper_id=workpaper.workpaper_id,
        approved_by=approved_by,
        entries=entries,
    )


def post_simulated(session: Session, obligation_id: str, *, now: datetime) -> PostResult:
    """Write the drafted accrual into the simulated general ledger, once."""
    obligation = _obligation(session, obligation_id)
    workpaper = _workpaper(session, obligation)
    if obligation.accrual_status == e.AccrualStatus.POSTED_SIMULATED:
        raise AlreadyPostedError(f"{obligation_id} is already posted")
    if obligation.accrual_status != e.AccrualStatus.DRAFTED:
        raise NotDraftedError(f"{obligation_id} has no drafted entry to post")
    accrual = _drafted(workpaper, e.GLEntryType.ACCRUAL)
    if session.get(m.CompanyGLEntry, accrual["entry_id"]) is not None:
        raise AlreadyPostedError(f"{accrual['entry_id']} is already in the ledger")
    assert_balanced(accrual["lines"])
    _open_period(_periods(session), accrual["period"])

    session.add(_gl_row(obligation, workpaper, accrual, now))
    obligation.accrual_status = e.AccrualStatus.POSTED_SIMULATED
    workpaper.status = e.WorkpaperStatus.POSTED_SIMULATED
    workpaper.updated_at = now
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="post_simulated",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary=f"Posted {accrual['entry_id']} to the simulated ledger.",
        output_summary=accrual["entry_id"],
        at=now,
        obligation_id=obligation_id,
        workpaper_id=workpaper.workpaper_id,
        facts_used=[_fact(accrual)],
        input_record_ids=[workpaper.workpaper_id, accrual["entry_id"]],
        output_record_ids=[accrual["entry_id"]],
    )
    session.flush()
    return PostResult(obligation_id=obligation_id, gl_entry_id=accrual["entry_id"])


def post_due_reversals(session: Session, *, now: datetime) -> ReversalsResult:
    """Post every drafted reversal dated on or before the clock, once, after its accrual posted."""
    today = _utc_date(now)
    periods = _periods(session)
    posted: list[PostedReversal] = []
    skipped: list[SkippedReversal] = []
    workpapers = session.scalars(
        select(m.TrueUpWorkpaper)
        .where(m.TrueUpWorkpaper.status == e.WorkpaperStatus.POSTED_SIMULATED)
        .order_by(m.TrueUpWorkpaper.workpaper_id)
    ).all()
    for workpaper in workpapers:
        entries = _entries(workpaper)
        reversal = next((x for x in entries if x["entry_type"] == "ACCRUAL_REVERSAL"), None)
        if reversal is None or date.fromisoformat(reversal["posting_date"]) > today:
            continue
        if session.get(m.CompanyGLEntry, reversal["entry_id"]) is not None:
            continue
        accrual_row = session.get(m.CompanyGLEntry, reversal["reversal_of"])
        if accrual_row is None or accrual_row.status != e.GLEntryStatus.POSTED:
            skipped.append(
                SkippedReversal(entry_id=reversal["entry_id"], reason="accrual not posted")
            )
            continue
        try:
            _open_period(periods, reversal["period"])
        except ClosedPeriodError as exc:
            skipped.append(SkippedReversal(entry_id=reversal["entry_id"], reason=str(exc)))
            continue
        obligation = _obligation(session, workpaper.obligation_id)
        session.add(_gl_row(obligation, workpaper, reversal, now))
        accrual_row.status = e.GLEntryStatus.REVERSED
        AgentRunLog(session).append(
            agent_name=AGENT_NAME,
            action="post_reversal",
            status=e.AgentRunStatus.COMPLETED,
            decision_summary=(
                f"Posted {reversal['entry_id']} dated {reversal['posting_date']}, "
                f"reversing {reversal['reversal_of']}."
            ),
            output_summary=reversal["entry_id"],
            at=now,
            obligation_id=obligation.obligation_id,
            workpaper_id=workpaper.workpaper_id,
            facts_used=[_fact(reversal)],
            input_record_ids=[workpaper.workpaper_id, reversal["reversal_of"]],
            output_record_ids=[reversal["entry_id"]],
        )
        posted.append(
            PostedReversal(
                obligation_id=obligation.obligation_id,
                gl_entry_id=reversal["entry_id"],
                reverses=reversal["reversal_of"],
                posting_date=date.fromisoformat(reversal["posting_date"]),
            )
        )
    session.flush()
    return ReversalsResult(posted=posted, skipped=skipped)


def _obligation(session: Session, obligation_id: str) -> m.TrueUpObligation:
    obligation = session.get(m.TrueUpObligation, obligation_id)
    if obligation is None:
        raise JournalEntryError(f"unknown obligation {obligation_id}")
    return obligation


def _workpaper(session: Session, obligation: m.TrueUpObligation) -> m.TrueUpWorkpaper:
    workpaper = (
        session.get(m.TrueUpWorkpaper, obligation.current_workpaper_id)
        if obligation.current_workpaper_id
        else None
    )
    if workpaper is None:
        raise MissingWorkpaperError(f"{obligation.obligation_id} has no workpaper")
    return workpaper


def _approver(workpaper: m.TrueUpWorkpaper) -> str:
    """Return "policy" or "controller", or refuse: an unapproved workpaper never drafts."""
    policy, decision = workpaper.policy_decision, workpaper.controller_decision
    if workpaper.status != e.WorkpaperStatus.APPROVED:
        raise NotApprovedError(
            f"{workpaper.workpaper_id} is {workpaper.status.value}, not APPROVED"
        )
    if policy not in (e.PolicyDecision.PERMIT, e.PolicyDecision.REQUIRE_CONTROLLER):
        raise NotApprovedError(f"{workpaper.workpaper_id} policy decision is {policy.value}")
    if decision in _APPROVING:
        return "controller"
    if decision is None and policy == e.PolicyDecision.PERMIT:
        return "policy"
    raise NotApprovedError(
        f"{workpaper.workpaper_id} needs a Controller approval "
        f"(policy {policy.value}, controller {decision.value if decision else 'none'})"
    )


def _periods(session: Session) -> dict[str, Any]:
    row = session.get(m.CompanyConfig, "accounting_periods")
    return dict(row.config_value_json) if row else {}


def _open_period(periods: dict[str, Any], period: str) -> dict[str, Any]:
    info = periods.get(period)
    if info is None:
        raise ClosedPeriodError(f"accounting period {period} is not configured")
    if info.get("status") != "OPEN":
        raise ClosedPeriodError(f"accounting period {period} is {info.get('status')}")
    return info


def _next_period(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    return f"{year + month // 12}-{month % 12 + 1:02d}"


def _first_day(period: str) -> date:
    year, month = (int(part) for part in period.split("-"))
    return date(year, month, 1)


def _utc_date(moment: datetime) -> date:
    return moment.astimezone(UTC).date() if moment.tzinfo else moment.date()


def _money(value: object) -> str:
    return str(coerce_money(value).quantize(CENT, rounding=ROUND_HALF_UP))


def _line(line: dict[str, Any], memo: str) -> dict[str, str]:
    return {
        "account_code": line["account_code"],
        "debit": _money(line.get("debit", 0)),
        "credit": _money(line.get("credit", 0)),
        "description": line.get("description") or memo,
    }


def _entry(
    entry_id: str,
    entry_type: e.GLEntryType,
    period: str,
    posting_date: date,
    description: str,
    lines: list[dict[str, str]],
    reversal_of: str | None,
) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "entry_type": entry_type.value,
        "period": period,
        "posting_date": posting_date.isoformat(),
        "description": description,
        "lines": lines,
        "reversal_of": reversal_of,
    }


def _entries(workpaper: m.TrueUpWorkpaper) -> list[dict[str, Any]]:
    payload = workpaper.journal_entry_json
    return payload["entries"] if isinstance(payload, dict) else []


def _drafted(workpaper: m.TrueUpWorkpaper, entry_type: e.GLEntryType) -> dict[str, Any]:
    for entry in _entries(workpaper):
        if entry["entry_type"] == entry_type.value:
            return entry
    raise NotDraftedError(f"{workpaper.workpaper_id} has no drafted {entry_type.value} entry")


def _fact(entry: dict[str, Any]) -> dict[str, str]:
    return {
        "entry_id": entry["entry_id"],
        "entry_type": entry["entry_type"],
        "period": entry["period"],
        "posting_date": entry["posting_date"],
        "total": _money(sum((coerce_money(x["debit"]) for x in entry["lines"]), Decimal(0))),
    }


def _gl_row(
    obligation: m.TrueUpObligation,
    workpaper: m.TrueUpWorkpaper,
    entry: dict[str, Any],
    now: datetime,
) -> m.CompanyGLEntry:
    return m.CompanyGLEntry(
        gl_entry_id=entry["entry_id"],
        period=entry["period"],
        posting_date=date.fromisoformat(entry["posting_date"]),
        vendor_id=obligation.vendor_id,
        obligation_id=obligation.obligation_id,
        entry_type=e.GLEntryType(entry["entry_type"]),
        status=e.GLEntryStatus.POSTED,
        description=f"{SIMULATED_PREFIX} {entry['description']}",
        lines_json=entry["lines"],
        source_workpaper_id=workpaper.workpaper_id,
        reversal_of_gl_entry_id=entry["reversal_of"],
        created_at=now,
    )
