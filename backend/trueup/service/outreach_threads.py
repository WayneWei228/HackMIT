"""The email threads of a case, read from the outreach cards and the run rows that wrote them.

There is no messages table. A request and its reply are `trueup_evidence` cards, and the agent
that sent or read each one logged a run row. Everything here is read back from those rows, so a
case that never needed outreach has no threads. Every message is synthetic: nothing is sent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.service import models as v
from trueup.service import runlog
from trueup.store import enums as e
from trueup.store import models as m

SENDER = v.Party(name="Finance Operations", role="Finance")
_OWNER_ROLE_LABELS = {"VENDOR_BILLING": "VENDOR_CONTACT"}
_FACTS = ("quantity", "unit", "in_service_date", "service_received", "corrected_amount")
_OUTREACH_FROM = "AWAITING_OUTREACH/SEND_OUTREACH"


def threads_for(
    session: Session, ob: m.TrueUpObligation, runs: list[m.TrueUpAgentRun], *, now: datetime
) -> list[v.OutreachThread]:
    cards = _outreach_cards(session, ob.obligation_id)
    by_key: dict[str, list[m.TrueUpEvidence]] = {}
    for card in cards:
        by_key.setdefault(card.source_id, []).append(card)
    directory = _directory(session)
    return [
        _thread(key, group, ob.obligation_id, directory, runs, now)
        for key, group in sorted(by_key.items())
    ]


def _outreach_cards(session: Session, obligation_id: str) -> list[m.TrueUpEvidence]:
    return list(
        session.scalars(
            select(m.TrueUpEvidence)
            .where(
                m.TrueUpEvidence.obligation_id == obligation_id,
                m.TrueUpEvidence.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE,
                m.TrueUpEvidence.source_table == "outreach",
            )
            .order_by(m.TrueUpEvidence.evidence_id)
        )
    )


def _directory(session: Session) -> dict[str, dict[str, Any]]:
    """Everyone an email can be addressed to, by id, and whether they work outside the company."""
    people = session.get(m.CompanyConfig, "people")
    contacts = session.get(m.CompanyConfig, "vendor_contacts")
    found = {
        p["person_id"]: {**p, "kind": "INTERNAL_OWNER"} for p in people.config_value_json or []
    }
    for contact in (contacts.config_value_json or {}).values() if contacts else []:
        found[contact["person_id"]] = {**contact, "kind": "VENDOR_CONTACT"}
    return found


def _thread(
    key: str,
    cards: list[m.TrueUpEvidence],
    obligation_id: str,
    directory: dict[str, dict[str, Any]],
    runs: list[m.TrueUpAgentRun],
    now: datetime,
) -> v.OutreachThread:
    requests = [c for c in cards if _direction(c) == "REQUEST"]
    replies = [c for c in cards if _direction(c) == "RESPONSE"]
    latest = requests[-1] if requests else None
    person = _person(latest, directory) if latest else None
    subject = (latest.value_json or {}).get("subject", "") if latest else ""
    messages = [_message(c, directory, runs, subject) for c in cards]
    messages.sort(key=lambda msg: (msg.at, 0 if msg.direction == "OUT" else 1))
    last_reply = replies[-1] if replies else None
    return v.OutreachThread(
        thread_id=key,
        topic=(cards[0].value_json or {}).get("topic", ""),
        obligation_id=obligation_id,
        simulated=True,
        status=_status(latest, last_reply, now),
        sent_at=_z((latest.value_json or {}).get("sent_at")) if latest else None,
        due_at=_z((latest.value_json or {}).get("due_at")) if latest else None,
        waiting_on=(
            v.WaitingOn(name=person["name"], role=person["role"], kind=person["kind"])
            if person is not None and latest is not None and _is_open(latest)
            else None
        ),
        messages=messages,
        parsed=_parsed(last_reply),
        verification=_verification(last_reply, runs) if last_reply is not None else None,
    )


def _direction(card: m.TrueUpEvidence) -> str | None:
    return (card.value_json or {}).get("direction")


def _is_open(card: m.TrueUpEvidence) -> bool:
    return card.status == e.EvidenceCardStatus.PENDING


def _status(request: m.TrueUpEvidence | None, reply: m.TrueUpEvidence | None, now: datetime) -> str:
    if request is None:
        return "DRAFTED"
    if reply is not None and reply.created_at >= request.created_at:
        return "REPLIED" if (reply.value_json or {}).get("resolved") else "INSUFFICIENT"
    reason = (request.value_json or {}).get("closed_reason")
    due = (request.value_json or {}).get("due_at")
    if reason == "EXPIRED" or (due and _is_open(request) and _aware(due) < _aware(now)):
        return "OVERDUE"
    return "SENT"


def _z(value: str | None) -> str | None:
    return None if value is None else runlog.iso(_aware(value))


def _aware(value: str | datetime) -> datetime:
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _person(card: m.TrueUpEvidence, directory: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    value = card.value_json or {}
    found = directory.get(value.get("recipient_person_id", ""))
    if found is not None:
        return found
    role = _OWNER_ROLE_LABELS.get(value.get("recipient_role", ""), "INTERNAL_OWNER")
    name = value.get("recipient_name")
    return {"name": name, "role": value.get("recipient_role"), "kind": role} if name else None


def _run_for(card: m.TrueUpEvidence, runs: list[m.TrueUpAgentRun]) -> m.TrueUpAgentRun | None:
    return next(
        (
            r
            for r in runs
            if r.agent_name == "outreach" and card.evidence_id in (r.output_record_ids_json or [])
        ),
        None,
    )


def _message(
    card: m.TrueUpEvidence,
    directory: dict[str, dict[str, Any]],
    runs: list[m.TrueUpAgentRun],
    request_subject: str,
) -> v.ThreadMessage:
    value = card.value_json or {}
    person = _person(card, directory) or {"name": "Unknown", "role": ""}
    party = v.Party(name=person["name"], role=person["role"])
    run = _run_for(card, runs)
    if _direction(card) == "REQUEST":
        return v.ThreadMessage(
            direction="OUT",
            from_=SENDER,
            to=party,
            subject=value.get("subject", ""),
            body=value.get("body", ""),
            at=_z(value.get("sent_at")) or runlog.iso(card.created_at),
            method="LLM" if value.get("drafted_by") == "llm" else "TEMPLATE",
            run_id=runlog.run_number(run.run_id) if run else None,
            evidence_id=card.evidence_id,
        )
    return v.ThreadMessage(
        direction="IN",
        from_=party,
        to=SENDER,
        subject=f"Re: {request_subject}" if request_subject else "Re:",
        body=card.source_excerpt or card.fact,
        at=_z(value.get("replied_at")) or runlog.iso(card.created_at),
        method="SCRIPTED_REPLY",
        run_id=runlog.run_number(run.run_id) if run else None,
        evidence_id=card.evidence_id,
    )


def _parsed(reply: m.TrueUpEvidence | None) -> v.ThreadParsed | None:
    if reply is None:
        return None
    value = reply.value_json or {}
    facts = {name: str(value[name]) for name in _FACTS if value.get(name) is not None}
    return v.ThreadParsed(
        resolved=bool(value.get("resolved")), facts=facts, note=value.get("reason") or reply.fact
    )


def _verification(
    reply: m.TrueUpEvidence, runs: list[m.TrueUpAgentRun]
) -> v.LogVerification | None:
    """The gate the reply's handoff passed: the verifier row logged just before the reply's run."""
    reading = _run_for(reply, runs)
    if reading is None:
        return None
    before = [r for r in runs if runlog.run_number(r.run_id) < runlog.run_number(reading.run_id)]
    for row in reversed(before):
        routing = runlog._routing(row)
        if row.agent_name == "verifier" and routing and routing.get("from") == _OUTREACH_FROM:
            return runlog.verification_of(row)
    return None
