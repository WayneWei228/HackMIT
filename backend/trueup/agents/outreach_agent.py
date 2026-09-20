"""Outreach agent: ask the right owner for missing information and read the reply.

There is no messages table, so a request and its reply are `trueup_evidence` cards of type
OUTREACH_RESPONSE. The recipient comes from the ownership map in `company_config`, never from a
vendor. A language model drafts the email and reads the reply, but code guards both ends: a draft
with a currency figure or an unsupplied number falls back to a template, and a quantity or date
from a reply is kept only if it appears verbatim in the reply text.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import cast

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.gateway import llm
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog
from trueup.store.workflow import IllegalTransitionError, advance

AGENT_NAME = "outreach"
DRAFT_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "outreach_draft.md"
PARSE_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "outreach_parse.md"
DEFAULT_DEADLINE_DAYS = 5
DEADLINE_CONFIG_KEY = "outreach_deadline_days"
SOURCE_TABLE = "outreach"
AT_OUTREACH = (e.WorkflowStage.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH)
_DRAFT_SYSTEM = "You write brief, factual finance emails. You never state money amounts."
_PARSE_SYSTEM = "You extract facts from a short reply. You never guess or compute a value."


class OutreachError(RuntimeError):
    """The request cannot be sent or answered as asked."""


class Topic(StrEnum):
    USAGE_CONFIRMATION = "USAGE_CONFIRMATION"
    SERVICE_CONFIRMATION = "SERVICE_CONFIRMATION"
    RATE_CONFIRMATION = "RATE_CONFIRMATION"
    IN_SERVICE_DATE = "IN_SERVICE_DATE"


TOPIC_BY_STATUS = {
    e.EvidenceStatus.MISSING_USAGE: Topic.USAGE_CONFIRMATION,
    e.EvidenceStatus.MISSING_SERVICE_CONFIRMATION: Topic.SERVICE_CONFIRMATION,
    e.EvidenceStatus.MISSING_RATE: Topic.RATE_CONFIRMATION,
}
OWNER_FIELD = {
    Topic.USAGE_CONFIRMATION: "service_owner_id",
    Topic.SERVICE_CONFIRMATION: "service_owner_id",
    Topic.IN_SERVICE_DATE: "service_owner_id",
    Topic.RATE_CONFIRMATION: "procurement_owner_id",
}
ROLE_LABEL = {"service_owner_id": "SERVICE_OWNER", "procurement_owner_id": "PROCUREMENT_OWNER"}
ASK = {
    Topic.USAGE_CONFIRMATION: "the total usage for the full service period, with its unit",
    Topic.SERVICE_CONFIRMATION: "whether the goods or services were received, and when",
    Topic.RATE_CONFIRMATION: "the rate we are being charged, and any amendment that changes it",
    Topic.IN_SERVICE_DATE: "the date each item received was placed in service",
}


class DraftFacts(BaseModel):
    vendor_name: str
    recipient_name: str
    recipient_role: str
    topic: Topic
    ask: str
    service_start: date
    service_end: date
    received_through: date | None
    reply_by: date

    def rendered(self) -> dict[str, str]:
        out = {
            "vendor": self.vendor_name,
            "recipient": self.recipient_name,
            "recipient role": self.recipient_role,
            "what we need": self.ask,
            "service period": f"{_long(self.service_start)} through {_long(self.service_end)}",
            "please reply by": _long(self.reply_by),
        }
        if self.received_through:
            out["data we already have through"] = _long(self.received_through)
        return out


class Draft(BaseModel):
    subject: str
    body: str


class ParsedReply(BaseModel):
    resolved: bool
    service_received: bool | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    in_service_date: str | None = None
    reason: str = ""


class SentRequest(BaseModel):
    obligation_id: str
    outreach_key: str
    topic: Topic
    evidence_id: str
    recipient_person_id: str
    recipient_email: str | None
    subject: str
    body: str
    sent_at: datetime
    due_at: datetime
    drafted_by: str
    created: bool


class ReplyResult(BaseModel):
    obligation_id: str
    outreach_key: str
    topic: Topic
    resolved: bool
    service_received: bool | None
    quantity: Decimal | None
    unit: str | None
    in_service_date: date | None
    routed_stage: e.WorkflowStage
    next_action: e.NextAction
    evidence_id: str
    parsed_by: str
    uncertainties: list[str]


class ExpiredRequest(BaseModel):
    obligation_id: str
    outreach_key: str
    due_at: datetime
    routed_stage: e.WorkflowStage | None
    reason: str


Drafter = Callable[[DraftFacts], Draft]
Parser = Callable[[str, Topic, list[str]], ParsedReply]
Responder = Callable[[str, datetime], str | None]


def send_outreach(
    session: Session,
    obligation_id: str,
    *,
    now: datetime,
    topic: Topic | str | None = None,
    drafter: Drafter | None = None,
) -> SentRequest:
    obligation = _at_outreach(session, obligation_id)
    topic = _topic(obligation, topic)
    key = f"{obligation.vendor_id.removeprefix('VEN-')}-{obligation.period}-{topic.value}"
    existing = _open_request(session, obligation_id, key)
    if existing is not None:
        return _sent_from(existing, created=False)

    person, notes = _recipient(session, obligation, topic)
    facts = _draft_facts(session, obligation, topic, person, now)
    draft, drafted_by = _draft(facts, drafter, notes)
    due_at = _utc(now) + timedelta(days=_deadline_days(session))
    number = 1 + sum(1 for c in _cards(session, key=key) if _direction(c) == "REQUEST")
    card = m.TrueUpEvidence(
        evidence_id=f"EVD-OUT-{key}-REQ-{number:02d}",
        obligation_id=obligation_id,
        evidence_type=e.EvidenceCardType.OUTREACH_RESPONSE,
        source_table=SOURCE_TABLE,
        source_id=key,
        fact=f"Asked {person['name']} ({facts.recipient_role}) for {facts.ask}",
        value_json={
            "direction": "REQUEST",
            "outreach_key": key,
            "topic": topic.value,
            "recipient_person_id": person["person_id"],
            "recipient_email": person.get("email"),
            "subject": draft.subject,
            "body": draft.body,
            "sent_at": _utc(now).isoformat(),
            "due_at": due_at.isoformat(),
            "drafted_by": drafted_by,
        },
        source_excerpt=draft.body,
        confidence=Decimal("0.00"),
        status=e.EvidenceCardStatus.PENDING,
        created_by_agent=AGENT_NAME,
        created_at=now,
    )
    session.add(card)
    session.flush()
    _log(
        session,
        obligation,
        "send_outreach",
        e.AgentRunStatus.COMPLETED,
        f"Asked {person['name']} for {facts.ask} ({topic.value}).",
        f"Outreach {key} sent; reply due {_long(due_at.date())}.",
        [{"topic": topic.value, "recipient": person["person_id"], "drafted_by": drafted_by}],
        notes,
        [obligation_id],
        [card.evidence_id],
        now,
    )
    return _sent_from(card, created=True)


def process_reply(
    session: Session,
    obligation_id: str,
    reply_text: str,
    *,
    now: datetime,
    parser: Parser | None = None,
) -> ReplyResult:
    obligation = _at_outreach(session, obligation_id)
    request = _latest_open_request(session, obligation_id)
    if request is None:
        raise OutreachError(f"{obligation_id} has no open outreach request to answer")
    topic = Topic(request.value_json["topic"])
    key = request.source_id
    units = _known_units(session, obligation)
    uncertainties: list[str] = []

    parsed, parsed_by = _parse(reply_text, topic, units, parser, uncertainties)
    quantity, unit, given_date = _ground(parsed, reply_text, units, uncertainties)
    resolved = parsed.resolved and _requirement_met(topic, parsed, quantity, given_date)
    if not resolved:
        uncertainties.append(parsed.reason or "The reply does not give the requested information.")

    to_estimate = resolved and parsed.service_received is not False
    if resolved and not to_estimate:
        uncertainties.append("The owner reports the service was not received.")
    target = (
        (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE)
        if to_estimate
        else (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)
    )

    number = 1 + sum(1 for c in _cards(session, key=key) if _direction(c) == "RESPONSE")
    value = {
        "direction": "RESPONSE",
        "outreach_key": key,
        "topic": topic.value,
        "resolved": resolved,
        "service_received": parsed.service_received,
        "quantity": None if quantity is None else format(quantity, "f"),
        "unit": unit,
        "in_service_date": None if given_date is None else given_date.isoformat(),
        "reason": parsed.reason,
        "parsed_by": parsed_by,
        "recipient_person_id": request.value_json["recipient_person_id"],
        "replied_at": _utc(now).isoformat(),
    }
    card = m.TrueUpEvidence(
        evidence_id=f"EVD-OUT-{key}-RSP-{number:02d}",
        obligation_id=obligation_id,
        evidence_type=e.EvidenceCardType.OUTREACH_RESPONSE,
        source_table=SOURCE_TABLE,
        source_id=key,
        fact=_reply_fact(topic, resolved, quantity, unit, given_date, parsed.service_received),
        value_json=value,
        source_excerpt=reply_text.strip()[:1000],
        confidence=Decimal("1.00") if resolved else Decimal("0.00"),
        status=e.EvidenceCardStatus.VERIFIED if resolved else e.EvidenceCardStatus.PENDING,
        created_by_agent=AGENT_NAME,
        created_at=now,
    )
    session.add(card)
    _close(request, "ANSWERED", now)
    session.flush()
    advance(obligation, *target, AGENT_NAME, at=now)
    _log(
        session,
        obligation,
        "process_reply",
        e.AgentRunStatus.COMPLETED if to_estimate else e.AgentRunStatus.ESCALATED,
        f"Read the reply to {key}: {'resolved' if resolved else 'not resolved'}, "
        f"routed to {target[0].value}/{target[1].value}.",
        card.fact,
        [value],
        uncertainties or None,
        [request.evidence_id],
        [card.evidence_id],
        now,
    )
    return ReplyResult(
        obligation_id=obligation_id,
        outreach_key=key,
        topic=topic,
        resolved=resolved,
        service_received=parsed.service_received,
        quantity=quantity,
        unit=unit,
        in_service_date=given_date,
        routed_stage=obligation.workflow_stage,
        next_action=obligation.next_action,
        evidence_id=card.evidence_id,
        parsed_by=parsed_by,
        uncertainties=uncertainties,
    )


def poll_replies(
    session: Session, *, now: datetime, responder: Responder, parser: Parser | None = None
) -> list[ReplyResult]:
    """Ask the responder about every open request and process each reply that has arrived."""
    requests = [c for c in _cards(session) if _is_open_request(c)]
    results = []
    for card in sorted(requests, key=lambda c: c.created_at):
        text = responder(card.source_id, now)
        if text:
            results.append(process_reply(session, card.obligation_id, text, now=now, parser=parser))
    return results


def expire_overdue(session: Session, *, now: datetime) -> list[ExpiredRequest]:
    """Escalate every open request whose deadline has passed to the Controller."""
    expired = []
    for card in [c for c in _cards(session) if _is_open_request(c)]:
        due_at = datetime.fromisoformat(card.value_json["due_at"])
        if due_at > _utc(now):
            continue
        obligation = session.get(m.TrueUpObligation, card.obligation_id)
        _close(card, "EXPIRED", now)
        routed = None
        reason = f"No reply by {_long(due_at.date())}; escalated to the Controller."
        if (obligation.workflow_stage, obligation.next_action) == AT_OUTREACH:
            advance(
                obligation,
                e.WorkflowStage.AWAITING_CONTROLLER,
                e.NextAction.CONTROLLER_REVIEW,
                AGENT_NAME,
                at=now,
            )
            routed = obligation.workflow_stage
        else:
            reason = f"No reply by {_long(due_at.date())}; the obligation had already moved on."
        session.flush()
        _log(
            session,
            obligation,
            "expire_request",
            e.AgentRunStatus.ESCALATED,
            reason,
            f"Request {card.evidence_id} superseded.",
            [{"outreach_key": card.source_id, "due_at": card.value_json["due_at"]}],
            [reason],
            [card.evidence_id],
            [card.evidence_id],
            now,
        )
        expired.append(
            ExpiredRequest(
                obligation_id=obligation.obligation_id,
                outreach_key=card.source_id,
                due_at=due_at,
                routed_stage=routed,
                reason=reason,
            )
        )
    return expired


def llm_drafter(facts: DraftFacts) -> Draft:
    lines = "\n".join(f"- {name}: {value}" for name, value in facts.rendered().items())
    prompt = DRAFT_PROMPT.read_text().replace("{{FACTS}}", lines)
    return cast(Draft, llm.complete_json(prompt, Draft, system=_DRAFT_SYSTEM))


def template_draft(facts: DraftFacts) -> Draft:
    first = facts.recipient_name.split()[0]
    start, end = _long(facts.service_start), _long(facts.service_end)
    have = (
        f" We already have data through {_long(facts.received_through)}."
        if facts.received_through
        else ""
    )
    month = f"{calendar.month_name[facts.service_end.month]} {facts.service_end.year}"
    body = (
        f"Hi {first},\n\nWe are closing the books for {month}. For {facts.vendor_name} we need "
        f"{facts.ask}, covering {start} through {end}.{have} Could you reply by "
        f"{_long(facts.reply_by)}?\n\nThank you,\nFinance Operations"
    )
    return Draft(subject=f"{facts.vendor_name}: information needed for month-end", body=body)


def check_draft(draft: Draft, facts: DraftFacts) -> str | None:
    """Return why a draft is not allowed to be sent, or None when it is fine."""
    text = f"{draft.subject}\n{draft.body}"
    if _CURRENCY.search(text):
        return "it states a currency figure"
    allowed = _numbers(" ".join(_supplied_text(facts)))
    extra = sorted(_numbers(text) - allowed)
    if extra:
        return f"it states a number that was not supplied ({extra[0]})"
    return None


def llm_parser(reply: str, topic: Topic, units: list[str]) -> ParsedReply:
    prompt = (
        PARSE_PROMPT.read_text()
        .replace("{{TOPIC}}", topic.value)
        .replace("{{QUESTION}}", ASK[topic])
        .replace("{{UNITS}}", ", ".join(units) or "none")
        .replace("{{REPLY}}", reply)
    )
    return cast(ParsedReply, llm.complete_json(prompt, ParsedReply, system=_PARSE_SYSTEM))


def rule_parser(reply: str, topic: Topic, units: list[str]) -> ParsedReply:
    """Offline reader: a quantity followed by one of the vendor's known units."""
    if topic == Topic.USAGE_CONFIRMATION:
        for unit in [*units, "unit"]:
            words = r"[ _-]?".join(re.escape(w) for w in unit.lower().split("_"))
            hit = re.search(rf"(\d[\d,]*(?:\.\d+)?)\s*{words}s?\b", reply, re.IGNORECASE)
            if hit:
                return ParsedReply(
                    resolved=True,
                    quantity=Decimal(hit.group(1).replace(",", "")),
                    unit=unit.upper(),
                    reason="The reply states a quantity and its unit.",
                )
        return ParsedReply(resolved=False, reason="No quantity with a known unit in the reply.")
    return ParsedReply(resolved=False, reason="No language model is available to read this reply.")


# --- helpers -------------------------------------------------------------------------------

_CURRENCY = re.compile(r"[$€£¥]|\b(?:usd|eur|gbp|dollars?|cents?)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def _numbers(text: str) -> set[Decimal]:
    return {Decimal(token.replace(",", "")) for token in _NUMBER.findall(text)}


def _long(value: date) -> str:
    return f"{calendar.month_name[value.month]} {value.day}, {value.year}"


def _supplied_text(facts: DraftFacts) -> list[str]:
    dates = [facts.service_start, facts.service_end, facts.reply_by, facts.received_through]
    return [d.isoformat() + " " + _long(d) for d in dates if d] + [facts.vendor_name]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _config(session: Session, key: str):
    row = session.get(m.CompanyConfig, key)
    return None if row is None else row.config_value_json


def _at_outreach(session: Session, obligation_id: str) -> m.TrueUpObligation:
    obligation = session.get(m.TrueUpObligation, obligation_id)
    if obligation is None:
        raise LookupError(f"unknown obligation {obligation_id}")
    state = (obligation.workflow_stage, obligation.next_action)
    if state != AT_OUTREACH:
        raise IllegalTransitionError(
            f"{obligation_id} is at {state[0]}/{state[1]}, not AWAITING_OUTREACH/SEND_OUTREACH"
        )
    return obligation


def _topic(obligation: m.TrueUpObligation, explicit: Topic | str | None) -> Topic:
    if explicit is not None:
        return Topic(explicit)
    topic = TOPIC_BY_STATUS.get(obligation.evidence_status)
    if topic is None:
        raise OutreachError(
            f"{obligation.obligation_id} has evidence status {obligation.evidence_status.value}; "
            "say what to ask with an explicit topic"
        )
    return topic


def _recipient(
    session: Session, obligation: m.TrueUpObligation, topic: Topic
) -> tuple[dict, list[str]]:
    ownership = _config(session, "ownership_map") or {}
    field = OWNER_FIELD[topic]
    entry = (ownership.get("vendors") or {}).get(obligation.vendor_id) or {}
    person_id, notes = entry.get(field), []
    if person_id is None:
        person_id = ownership.get("default_ap_owner")
        notes.append(f"No {ROLE_LABEL[field]} is mapped for the vendor; used the default AP owner.")
    people = {p["person_id"]: p for p in _config(session, "people") or []}
    if person_id not in people:
        raise OutreachError(f"the ownership map points at an unknown person {person_id!r}")
    person = dict(people[person_id])
    person["role_label"] = ROLE_LABEL[field]
    return person, notes


def _deadline_days(session: Session) -> int:
    value = str(_config(session, DEADLINE_CONFIG_KEY))
    return int(value) if value.isdigit() else DEFAULT_DEADLINE_DAYS


def _draft_facts(
    session: Session, obligation: m.TrueUpObligation, topic: Topic, person: dict, now: datetime
) -> DraftFacts:
    vendor = session.get(m.CompanyVendor, obligation.vendor_id)
    received = session.scalars(
        select(m.CompanyServiceEvidence.service_end_date).where(
            m.CompanyServiceEvidence.vendor_id == obligation.vendor_id,
            m.CompanyServiceEvidence.service_start_date <= obligation.service_end_date,
            m.CompanyServiceEvidence.service_end_date >= obligation.service_start_date,
        )
    ).all()
    return DraftFacts(
        vendor_name=vendor.vendor_name,
        recipient_name=person["name"],
        recipient_role=person["role_label"],
        topic=topic,
        ask=ASK[topic],
        service_start=obligation.service_start_date,
        service_end=obligation.service_end_date,
        received_through=max(received, default=None),
        reply_by=(_utc(now) + timedelta(days=_deadline_days(session))).date(),
    )


def _draft(facts: DraftFacts, drafter: Drafter | None, notes: list[str]) -> tuple[Draft, str]:
    chosen = drafter or (llm_drafter if llm.available() else None)
    if chosen is None:
        notes.append("No language model is configured; used the template draft.")
    else:
        try:
            candidate = chosen(facts)
        except llm.LLMError as exc:
            notes.append(f"The model draft failed ({exc}); used the template draft.")
        else:
            problem = check_draft(candidate, facts)
            if problem is None:
                return candidate, "llm" if drafter is None else "custom"
            notes.append(f"The model draft was rejected because {problem}; used the template.")
    return template_draft(facts), "template"


def _cards(
    session: Session, obligation_id: str | None = None, key: str | None = None
) -> list[m.TrueUpEvidence]:
    query = select(m.TrueUpEvidence).where(
        m.TrueUpEvidence.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE,
        m.TrueUpEvidence.source_table == SOURCE_TABLE,
    )
    if obligation_id is not None:
        query = query.where(m.TrueUpEvidence.obligation_id == obligation_id)
    if key is not None:
        query = query.where(m.TrueUpEvidence.source_id == key)
    return list(session.scalars(query.order_by(m.TrueUpEvidence.evidence_id)))


def _direction(card: m.TrueUpEvidence) -> str | None:
    return (card.value_json or {}).get("direction")


def _is_open_request(card: m.TrueUpEvidence) -> bool:
    return _direction(card) == "REQUEST" and card.status == e.EvidenceCardStatus.PENDING


def _open_request(session: Session, obligation_id: str, key: str) -> m.TrueUpEvidence | None:
    found = [c for c in _cards(session, obligation_id, key) if _is_open_request(c)]
    return found[-1] if found else None


def _latest_open_request(session: Session, obligation_id: str) -> m.TrueUpEvidence | None:
    found = [c for c in _cards(session, obligation_id) if _is_open_request(c)]
    return max(found, key=lambda c: c.evidence_id) if found else None


def _close(card: m.TrueUpEvidence, reason: str, now: datetime) -> None:
    card.status = e.EvidenceCardStatus.SUPERSEDED
    card.value_json = {
        **card.value_json,
        "closed_reason": reason,
        "closed_at": _utc(now).isoformat(),
    }


def _sent_from(card: m.TrueUpEvidence, *, created: bool) -> SentRequest:
    v = card.value_json
    return SentRequest(
        obligation_id=card.obligation_id,
        outreach_key=v["outreach_key"],
        topic=Topic(v["topic"]),
        evidence_id=card.evidence_id,
        recipient_person_id=v["recipient_person_id"],
        recipient_email=v.get("recipient_email"),
        subject=v["subject"],
        body=v["body"],
        sent_at=datetime.fromisoformat(v["sent_at"]),
        due_at=datetime.fromisoformat(v["due_at"]),
        drafted_by=v["drafted_by"],
        created=created,
    )


def _known_units(session: Session, obligation: m.TrueUpObligation) -> list[str]:
    units = session.scalars(
        select(m.CompanyServiceEvidence.unit)
        .where(
            m.CompanyServiceEvidence.vendor_id == obligation.vendor_id,
            m.CompanyServiceEvidence.unit.is_not(None),
        )
        .distinct()
    )
    return sorted(units)


def _parse(
    reply: str, topic: Topic, units: list[str], parser: Parser | None, notes: list[str]
) -> tuple[ParsedReply, str]:
    if parser is not None:
        return parser(reply, topic, units), "custom"
    if llm.available():
        try:
            return llm_parser(reply, topic, units), "llm"
        except llm.LLMError as exc:
            notes.append(f"The model could not read the reply ({exc}); used the offline reader.")
    else:
        notes.append("No language model is configured; used the offline reader.")
    return rule_parser(reply, topic, units), "rules"


def _ground(
    parsed: ParsedReply, reply: str, units: list[str], notes: list[str]
) -> tuple[Decimal | None, str | None, date | None]:
    quantity, unit, given = parsed.quantity, parsed.unit, None
    if quantity is not None and quantity not in _numbers(reply):
        notes.append(f"Dropped quantity {quantity}: it is not in the reply text.")
        quantity = None
    if unit is not None:
        code = re.sub(r"[^A-Z0-9]+", "_", unit.upper()).strip("_")
        known = next((u for u in units if u in (code, code.removesuffix("S"))), None)
        if known is None:
            notes.append(f"Dropped unit {unit!r}: it is not a known unit for this vendor.")
        unit = known
    if parsed.in_service_date is not None:
        try:
            candidate = date.fromisoformat(parsed.in_service_date)
        except ValueError:
            notes.append(f"Dropped date {parsed.in_service_date!r}: not a valid date.")
        else:
            if _date_in_text(candidate, reply):
                given = candidate
            else:
                notes.append(f"Dropped date {candidate}: it is not in the reply text.")
    return quantity, unit, given


def _date_in_text(value: date, text: str) -> bool:
    lowered = text.lower()
    if value.isoformat() in lowered:
        return True
    names = {calendar.month_name[value.month].lower(), calendar.month_abbr[value.month].lower()}
    day = rf"\b0?{value.day}(?:st|nd|rd|th)?\b"
    named = any(re.search(rf"\b{n}\b", lowered) for n in names) and re.search(day, lowered)
    slashed = re.search(rf"\b0?{value.month}/0?{value.day}\b", lowered)
    if not (named or slashed):
        return False
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", lowered))
    return not years or str(value.year) in years


def _requirement_met(
    topic: Topic, parsed: ParsedReply, quantity: Decimal | None, given: date | None
) -> bool:
    if topic == Topic.USAGE_CONFIRMATION:
        return quantity is not None
    if topic == Topic.SERVICE_CONFIRMATION:
        return parsed.service_received is not None
    if topic == Topic.IN_SERVICE_DATE:
        return given is not None
    return True


def _reply_fact(
    topic: Topic,
    resolved: bool,
    quantity: Decimal | None,
    unit: str | None,
    given: date | None,
    received: bool | None,
) -> str:
    if not resolved:
        return f"Owner reply to {topic.value}: not enough to act on"
    if quantity is not None:
        return f"Owner reply to {topic.value}: {format(quantity, 'f')} {unit or ''}".rstrip()
    if given is not None:
        return f"Owner reply to {topic.value}: placed in service {given.isoformat()}"
    if received is not None:
        return f"Owner reply to {topic.value}: service received is {str(received).lower()}"
    return f"Owner reply to {topic.value}: confirmed"


def _log(
    session: Session,
    obligation: m.TrueUpObligation,
    action: str,
    status: e.AgentRunStatus,
    decision: str,
    output: str,
    facts: list,
    uncertainties: list[str] | None,
    inputs: list[str],
    outputs: list[str],
    now: datetime,
) -> None:
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action=action,
        status=status,
        decision_summary=decision,
        output_summary=output,
        at=now,
        obligation_id=obligation.obligation_id,
        facts_used=facts,
        uncertainties=uncertainties or None,
        input_record_ids=inputs,
        output_record_ids=outputs,
    )
