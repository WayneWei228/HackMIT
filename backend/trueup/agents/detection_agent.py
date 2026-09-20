"""Detection agent: open one obligation per accrual candidate for a live period.

Scans the structured company tables (contracts, purchase orders, non-PO spend) and opens a
`trueup_obligations` row at (SEARCHING_AP, SEARCH_AP), the state the Invoice Lookup agent expects.
Rules read structured fields only and never branch on a vendor. No language model is involved.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.enums import AgentRunStatus
from trueup.store.integrity import AgentRunLog
from trueup.store.workflow import advance

AGENT_NAME = "detection"
ACTION = "detect_obligations"
CONTRACT_STATUSES_IN_FORCE = (e.ContractStatus.ACTIVE, e.ContractStatus.SUPERSEDED)
PO_STATUSES_TO_ACCRUE = (e.POStatus.APPROVED, e.POStatus.OPEN, e.POStatus.AMENDED)
NON_PO_STATUSES_TO_ACCRUE = (e.TransactionStatus.PENDING, e.TransactionStatus.SETTLED)
INITIAL_RISK = "LOW"


class PeriodNotDetectableError(ValueError):
    """Raised for a period that is unknown, closed, or has not started yet."""


class SkippedCandidate(BaseModel):
    kind: str
    ref: str
    vendor_id: str | None
    reason: str
    obligation_id: str | None = None


class DetectionResult(BaseModel):
    period: str
    opened: list[str]
    skipped: list[SkippedCandidate]


@dataclass
class _Candidate:
    vendor_id: str
    contract_id: str | None = None
    po_id: str | None = None
    non_po_group_key: str | None = None
    start: date | None = None
    end: date | None = None
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.vendor_id,
            self.contract_id or "",
            self.po_id or "",
            self.non_po_group_key or "",
        )


def detect(session: Session, period: str, *, now: datetime) -> DetectionResult:
    first, last = _period_bounds(session, period, now)
    skipped: list[SkippedCandidate] = []
    inactive = {
        v.vendor_id
        for v in session.scalars(select(m.CompanyVendor).where(~m.CompanyVendor.is_active))
    }

    candidates = _contract_candidates(session, first, last, skipped)
    _attach_purchase_orders(session, candidates, first, last, skipped)
    candidates += _non_po_candidates(session, period, skipped)

    ready: list[_Candidate] = []
    for candidate in sorted(candidates, key=_Candidate.sort_key):
        if candidate.vendor_id in inactive:
            skipped.append(_skip(candidate, "The vendor is inactive."))
        else:
            ready.append(candidate)

    opened: list[str] = []
    facts: list[dict] = []
    used_ids = set(session.scalars(select(m.TrueUpObligation.obligation_id)))
    for candidate in ready:
        existing = _existing(session, period, candidate)
        if existing is not None:
            skipped.append(
                _skip(candidate, "An obligation already exists for this candidate.", existing)
            )
            continue
        obligation = _open(session, candidate, period, first, last, used_ids, now)
        opened.append(obligation.obligation_id)
        facts.append(_fact(candidate, "opened", obligation.obligation_id, candidate.notes))
    facts += [
        {
            "kind": s.kind,
            "ref": s.ref,
            "vendor_id": s.vendor_id,
            "decision": "skipped",
            "reason": s.reason,
        }
        for s in skipped
    ]

    _log(session, period, opened, skipped, facts, ready, now)
    return DetectionResult(period=period, opened=opened, skipped=skipped)


def _period_bounds(session: Session, period: str, now: datetime) -> tuple[date, date]:
    config = session.get(m.CompanyConfig, "accounting_periods")
    entry = (config.config_value_json if config else {}).get(period)
    if entry is None:
        raise PeriodNotDetectableError(f"{period} is not an accounting period")
    if entry.get("status") != "OPEN":
        raise PeriodNotDetectableError(f"{period} is {entry.get('status')}; only open periods")
    year, month = (int(part) for part in period.split("-"))
    first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if now.date() < first:
        raise PeriodNotDetectableError(f"{period} has not started at {now.date().isoformat()}")
    return first, last


def _overlaps(start: date | None, end: date | None, first: date, last: date) -> bool:
    return (start is None or start <= last) and (end is None or end >= first)


def _hull(candidate: _Candidate, start: date | None, end: date | None) -> None:
    if candidate.start is None and not candidate.sources:
        candidate.start, candidate.end = start, end
    else:
        candidate.start = None if None in (candidate.start, start) else min(candidate.start, start)
        candidate.end = None if None in (candidate.end, end) else max(candidate.end, end)


def _contract_candidates(
    session: Session, first: date, last: date, skipped: list[SkippedCandidate]
) -> list[_Candidate]:
    rows = session.scalars(
        select(m.CompanyContract).order_by(
            m.CompanyContract.contract_id, m.CompanyContract.contract_version
        )
    ).all()
    by_contract: dict[str, list[m.CompanyContract]] = {}
    for row in rows:
        by_contract.setdefault(row.contract_id, []).append(row)

    candidates = []
    for contract_id, versions in by_contract.items():
        vendor_id = versions[-1].vendor_id
        overlapping = [
            v
            for v in versions
            if _overlaps(v.effective_start_date, v.effective_end_date, first, last)
        ]
        if not overlapping:
            skipped.append(
                SkippedCandidate(
                    kind="contract",
                    ref=contract_id,
                    vendor_id=vendor_id,
                    reason="No version's window overlaps the period.",
                )
            )
            continue
        in_force = [v for v in overlapping if v.status in CONTRACT_STATUSES_IN_FORCE]
        if not in_force:
            skipped.append(
                SkippedCandidate(
                    kind="contract",
                    ref=contract_id,
                    vendor_id=vendor_id,
                    reason=f"Every overlapping version is {overlapping[-1].status}.",
                )
            )
            continue
        candidate = _Candidate(vendor_id=vendor_id, contract_id=contract_id)
        for version in in_force:
            _hull(candidate, version.effective_start_date, version.effective_end_date)
            candidate.sources.append(version.contract_row_id)
        candidate.notes.append(
            "versions considered: " + ", ".join(f"v{v.contract_version}" for v in in_force)
        )
        candidates.append(candidate)
    return candidates


def _attach_purchase_orders(
    session: Session,
    candidates: list[_Candidate],
    first: date,
    last: date,
    skipped: list[SkippedCandidate],
) -> None:
    by_contract = {c.contract_id: c for c in candidates if c.contract_id}
    pos = session.scalars(
        select(m.CompanyPurchaseOrder).order_by(m.CompanyPurchaseOrder.po_id)
    ).all()
    for po in pos:
        if po.status not in PO_STATUSES_TO_ACCRUE:
            skipped.append(
                SkippedCandidate(
                    kind="purchase_order",
                    ref=po.po_id,
                    vendor_id=po.vendor_id,
                    reason=f"The purchase order is {po.status}.",
                )
            )
            continue
        if not _overlaps(po.service_start_date, po.service_end_date, first, last):
            skipped.append(
                SkippedCandidate(
                    kind="purchase_order",
                    ref=po.po_id,
                    vendor_id=po.vendor_id,
                    reason="The service window does not overlap the period.",
                )
            )
            continue
        shared = by_contract.get(po.contract_id) if po.contract_id else None
        if shared is not None and shared.po_id is None:
            shared.po_id = po.po_id
            _hull(shared, po.service_start_date, po.service_end_date)
            shared.sources.append(po.po_id)
            shared.notes.append(f"shares contract {po.contract_id} with {po.po_id}")
            continue
        candidate = _Candidate(
            vendor_id=po.vendor_id,
            contract_id=po.contract_id if shared is None else None,
            po_id=po.po_id,
            start=po.service_start_date,
            end=po.service_end_date,
            sources=[po.po_id],
        )
        if shared is not None:
            candidate.notes.append(f"contract {po.contract_id} is carried by {shared.po_id}")
        candidates.append(candidate)


def _non_po_candidates(
    session: Session, period: str, skipped: list[SkippedCandidate]
) -> list[_Candidate]:
    rows = session.scalars(
        select(m.CompanyNonPOSpend)
        .where(m.CompanyNonPOSpend.month == period)
        .order_by(m.CompanyNonPOSpend.non_po_spend_id)
    ).all()
    groups: dict[tuple[str, str, str], list[m.CompanyNonPOSpend]] = {}
    for row in rows:
        reason = None
        if row.is_accrued:
            reason = "Already accrued."
        elif row.ap_invoice_id is not None:
            reason = "Already invoiced in AP."
        elif row.transaction_status not in NON_PO_STATUSES_TO_ACCRUE:
            reason = f"The transaction is {row.transaction_status}."
        elif row.vendor_id is None:
            reason = "The merchant is not mapped to a vendor."
        if reason:
            skipped.append(
                SkippedCandidate(
                    kind="non_po_spend",
                    ref=row.non_po_spend_id,
                    vendor_id=row.vendor_id,
                    reason=reason,
                )
            )
            continue
        groups.setdefault((row.vendor_id, row.spend_source, row.gl_account), []).append(row)

    candidates = []
    for (vendor_id, source, gl_account), members in groups.items():
        candidates.append(
            _Candidate(
                vendor_id=vendor_id,
                non_po_group_key=f"{source}:{vendor_id}:{gl_account}",
                sources=[r.non_po_spend_id for r in members],
            )
        )
    return candidates


def _existing(session: Session, period: str, c: _Candidate) -> str | None:
    return session.scalars(
        select(m.TrueUpObligation.obligation_id).where(
            m.TrueUpObligation.vendor_id == c.vendor_id,
            m.TrueUpObligation.period == period,
            m.TrueUpObligation.contract_id.is_(c.contract_id)
            if c.contract_id is None
            else m.TrueUpObligation.contract_id == c.contract_id,
            m.TrueUpObligation.po_id.is_(c.po_id)
            if c.po_id is None
            else m.TrueUpObligation.po_id == c.po_id,
            m.TrueUpObligation.non_po_group_key.is_(c.non_po_group_key)
            if c.non_po_group_key is None
            else m.TrueUpObligation.non_po_group_key == c.non_po_group_key,
        )
    ).first()


def _obligation_id(vendor_id: str, period: str, used: set[str]) -> str:
    base = f"OBL-{vendor_id.removeprefix('VEN-')}-{period}"
    candidate, n = base, 1
    while candidate in used:
        n += 1
        candidate = f"{base}-{n:02d}"
    used.add(candidate)
    return candidate


def _open(
    session: Session,
    c: _Candidate,
    period: str,
    first: date,
    last: date,
    used_ids: set[str],
    now: datetime,
) -> m.TrueUpObligation:
    start = first if c.start is None else max(first, c.start)
    end = last if c.end is None else min(last, c.end)
    obligation = m.TrueUpObligation(
        obligation_id=_obligation_id(c.vendor_id, period, used_ids),
        vendor_id=c.vendor_id,
        period=period,
        contract_id=c.contract_id,
        po_id=c.po_id,
        non_po_group_key=c.non_po_group_key,
        service_start_date=start,
        service_end_date=end,
        purchase_type=e.PurchaseType.UNKNOWN,
        invoice_status=e.InvoiceStatus.NOT_SEARCHED,
        evidence_status=e.EvidenceStatus.NOT_COLLECTED,
        workflow_stage=e.WorkflowStage.DETECTED,
        next_action=e.NextAction.SEARCH_AP,
        accrual_status=e.AccrualStatus.NOT_STARTED,
        risk_level=INITIAL_RISK,
        opened_at=now,
        updated_at=now,
    )
    session.add(obligation)
    session.flush()
    advance(obligation, e.WorkflowStage.SEARCHING_AP, e.NextAction.SEARCH_AP, AGENT_NAME, at=now)
    return obligation


def _skip(c: _Candidate, reason: str, obligation_id: str | None = None) -> SkippedCandidate:
    ref = c.po_id or c.contract_id or c.non_po_group_key or c.vendor_id
    kind = "purchase_order" if c.po_id else "contract" if c.contract_id else "non_po_spend"
    return SkippedCandidate(
        kind=kind, ref=ref, vendor_id=c.vendor_id, reason=reason, obligation_id=obligation_id
    )


def _fact(c: _Candidate, decision: str, obligation_id: str, notes: list[str]) -> dict:
    return {
        "vendor_id": c.vendor_id,
        "contract_id": c.contract_id,
        "po_id": c.po_id,
        "non_po_group_key": c.non_po_group_key,
        "decision": decision,
        "obligation_id": obligation_id,
        "notes": notes,
    }


def _log(
    session: Session,
    period: str,
    opened: list[str],
    skipped: list[SkippedCandidate],
    facts: list[dict],
    ready: list[_Candidate],
    now: datetime,
) -> None:
    inputs = sorted({source for c in ready for source in c.sources})
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action=ACTION,
        status=AgentRunStatus.COMPLETED,
        decision_summary=(
            f"Opened {len(opened)} obligations for {period}; skipped {len(skipped)} candidates."
        ),
        output_summary="Handing off to Invoice Lookup: " + (", ".join(opened) or "nothing new"),
        at=now,
        facts_used=facts,
        input_record_ids=inputs,
        output_record_ids=opened,
    )
