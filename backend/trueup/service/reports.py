"""Journal, document and vendor-history reads over the existing simulated store.

Story events use immutable run records, never today's workpaper or handoff payload,
so selecting an earlier month cannot reveal a later reconciliation or vendor reply.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.selection_override import latest_override
from trueup.ingest.manifest import FileUniverse
from trueup.service import models as v
from trueup.service import outreach_threads
from trueup.service import readmodels as rm
from trueup.store import enums as e
from trueup.store import models as m


class PeriodsView(BaseModel):
    active_period: str
    current_month: str
    periods: list[str]


class JournalRecord(BaseModel):
    entry_id: str
    obligation_id: str | None
    vendor_id: str | None
    vendor_name: str | None
    period: str
    posting_date: str
    entry_type: str
    status: str
    description: str
    lines: list[v.JournalLine]


class JournalsView(BaseModel):
    journals: list[JournalRecord]
    note: str = "Posted entries in the simulated general ledger. All data is synthetic."


class DocumentRecord(BaseModel):
    file_id: str
    obligation_id: str | None
    vendor_id: str
    vendor_name: str
    period: str
    name: str
    kind: str
    format: str
    size_label: str
    known_from: str
    selected: bool | None
    user_removed: bool
    reason: str | None
    facts: list[v.EvidenceFact]


class DocumentsView(BaseModel):
    documents: list[DocumentRecord]


class StoryEvent(BaseModel):
    id: str
    obligation_id: str
    period: str
    at: str
    kind: str
    agent: str | None = None
    title: str
    summary: str
    payload: dict[str, Any]


class StoryView(BaseModel):
    vendor_id: str
    vendor_name: str
    through: str
    through_at: str
    months: list[str]
    events: list[StoryEvent]


def utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def month_end(period: str) -> datetime:
    year, month = map(int, period.split("-"))
    return datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59, 999999, UTC)


def periods_view(session: Session, *, active_period: str, now: datetime) -> PeriodsView:
    periods = set(session.scalars(select(m.TrueUpObligation.period)))
    periods.update(session.scalars(select(m.CompanyGLEntry.period)))
    current_month = f"{now:%Y-%m}"
    periods.update((active_period, current_month))
    return PeriodsView(
        active_period=active_period,
        current_month=current_month,
        periods=sorted(p for p in periods if p <= current_month),
    )


def journals_view(session: Session, *, period: str | None, now: datetime) -> JournalsView:
    # An accrual turns REVERSED when next month's reversal posts. It was still booked, so it stays.
    booked = (e.GLEntryStatus.POSTED, e.GLEntryStatus.REVERSED)
    query = select(m.CompanyGLEntry).where(m.CompanyGLEntry.status.in_(booked))
    if period:
        query = query.where(m.CompanyGLEntry.period == period)
    vendors = {v.vendor_id: v.vendor_name for v in session.scalars(select(m.CompanyVendor))}
    accounts = rm._accounts(session)
    return JournalsView(
        journals=[
            JournalRecord(
                entry_id=row.gl_entry_id,
                obligation_id=row.obligation_id,
                vendor_id=row.vendor_id,
                vendor_name=vendors.get(row.vendor_id),
                period=row.period,
                posting_date=row.posting_date.isoformat(),
                entry_type=row.entry_type.value,
                status=row.status.value,
                description=row.description,
                lines=rm._lines(row.lines_json, accounts),
            )
            for row in session.scalars(
                query.order_by(m.CompanyGLEntry.posting_date, m.CompanyGLEntry.gl_entry_id)
            )
            if utc(row.created_at) <= utc(now)
        ]
    )


def documents_view(
    session: Session, *, universe: FileUniverse, period: str | None, now: datetime
) -> DocumentsView:
    files = {f.file_id: f for f in universe.files}
    result = []
    for case in universe.cases:
        if period and case.period != period:
            continue
        ob = session.scalar(
            select(m.TrueUpObligation)
            .where(
                m.TrueUpObligation.vendor_id == case.vendor_id,
                m.TrueUpObligation.period == case.period,
            )
            .order_by(m.TrueUpObligation.obligation_id)
        )
        runs = rm._runs(session, ob.obligation_id) if ob else []
        run = rm._latest(runs, "ingestion", "select_files")
        decisions = {d["file_id"]: d for d in (run.facts_used_json or [])} if run else {}
        override = latest_override(session, ob.obligation_id) if ob else None
        removed = override.excluded if override and run and override.run_id > run.run_id else set()
        cards = (
            list(
                session.scalars(
                    select(m.TrueUpEvidence).where(
                        m.TrueUpEvidence.obligation_id == ob.obligation_id,
                        m.TrueUpEvidence.source_table == "document",
                    )
                )
            )
            if ob
            else []
        )
        for file in universe.for_case(case.case_id):
            if utc(file.available_at) > utc(now):
                continue
            decision = decisions.get(file.file_id)
            facts = rm._dedupe_facts(
                [
                    rm._fact(card, files)
                    for card in cards
                    if card.source_id == file.file_id and utc(card.created_at) <= utc(now)
                ]
            )
            result.append(
                DocumentRecord(
                    file_id=file.file_id,
                    obligation_id=ob.obligation_id if ob else None,
                    vendor_id=case.vendor_id,
                    vendor_name=case.vendor_name,
                    period=case.period,
                    name=file.name,
                    kind=file.kind,
                    format=file.format,
                    size_label=file.size_label,
                    known_from=file.available_at.isoformat(),
                    selected=(bool(decision.get("selected")) and file.file_id not in removed)
                    if decision is not None
                    else None,
                    user_removed=file.file_id in removed,
                    reason="Removed by the user"
                    if file.file_id in removed
                    else decision.get("reason")
                    if decision
                    else None,
                    facts=facts,
                )
            )
    return DocumentsView(documents=sorted(result, key=lambda d: (d.vendor_name, d.name)))


def _letters(ob: m.TrueUpObligation, thread: v.OutreachThread) -> list[StoryEvent]:
    """Each email of an outreach thread, whole.

    Only what was fixed when the email was sent or received goes in, so a later reply never
    rewrites an earlier month's story.
    """
    return [
        StoryEvent(
            id=f"letter:{message.evidence_id}",
            obligation_id=ob.obligation_id,
            period=ob.period,
            at=utc(datetime.fromisoformat(message.at)).isoformat(),
            kind="LETTER",
            agent="outreach" if message.direction == "OUT" else None,
            title=message.subject,
            summary=message.body,
            payload={
                "direction": message.direction,
                "from": message.from_.model_dump(),
                "to": message.to.model_dump(),
                "topic": thread.topic,
                "method": message.method,
            },
        )
        for message in thread.messages
    ]


def story_view(
    session: Session, *, vendor_id: str, through: str | None, now: datetime
) -> StoryView | None:
    vendor = session.get(m.CompanyVendor, vendor_id)
    if vendor is None:
        return None
    through = through or f"{now:%Y-%m}"
    cutoff = min(month_end(through), utc(now))
    events = []
    for ob in session.scalars(
        select(m.TrueUpObligation).where(m.TrueUpObligation.vendor_id == vendor_id)
    ):
        events.append(
            StoryEvent(
                id=f"opened:{ob.obligation_id}",
                obligation_id=ob.obligation_id,
                period=ob.period,
                at=utc(ob.opened_at).isoformat(),
                kind="CASE",
                title="Case opened",
                summary=f"Accrual review for {rm.period_label(ob.period)}.",
                payload={"obligation_id": ob.obligation_id, "period": ob.period},
            )
        )
        runs = rm._runs(session, ob.obligation_id)
        for thread in outreach_threads.threads_for(session, ob, runs, now=now):
            events.extend(_letters(ob, thread))
        for run in runs:
            events.append(
                StoryEvent(
                    id=run.run_id,
                    obligation_id=ob.obligation_id,
                    period=ob.period,
                    at=utc(run.created_at).isoformat(),
                    kind="AGENT",
                    agent=run.agent_name,
                    title=run.action.replace("_", " ").capitalize(),
                    summary=run.decision_summary,
                    payload={
                        "run_id": run.run_id,
                        "agent": run.agent_name,
                        "action": run.action,
                        "status": run.status.value,
                        "facts_used": run.facts_used_json,
                        "uncertainties": run.uncertainties_json,
                        "output": run.output_summary,
                        "input_ids": run.input_record_ids_json,
                        "output_ids": run.output_record_ids_json,
                    },
                )
            )
    known = [event for event in events if datetime.fromisoformat(event.at) <= utc(now)]
    return StoryView(
        vendor_id=vendor_id,
        vendor_name=vendor.vendor_name,
        through=through,
        through_at=cutoff.isoformat(),
        months=sorted({event.at[:7] for event in known}),
        events=sorted(
            (event for event in known if datetime.fromisoformat(event.at) <= cutoff),
            key=lambda event: (event.at, event.id),
        ),
    )
