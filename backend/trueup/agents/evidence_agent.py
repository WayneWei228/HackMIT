"""Evidence agent: turn the files Ingestion selected into grounded, typed evidence cards.

The language model reads one selected file at a time and returns facts with exact quotes.
Code then checks every fact against the document text and drops anything it cannot find,
so a card never states something the source does not say. The model never writes a card's
sentence and never computes an amount. Cards are stored only when an obligation exists.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import unicodedata
from collections.abc import Callable
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from trueup.agents.ingestion import SEED_DIR, IngestionResult
from trueup.gateway import llm
from trueup.ingest.manifest import CaseEntry, FileEntry, FileUniverse
from trueup.ingest.readers import UnsupportedFile, read_text
from trueup.store.enums import AgentRunStatus, EvidenceCardStatus, EvidenceCardType
from trueup.store.integrity import AgentRunLog
from trueup.store.models import TrueUpEvidence

AGENT_NAME = "evidence"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "extract_facts.md"
MAX_DOCUMENT_CHARS = 12000
_SYSTEM = (
    "You extract facts from vendor finance documents for an audit trail. "
    "Copy values exactly as written and quote the text you relied on."
)


class EvidenceError(RuntimeError):
    """Raised when evidence cannot be collected, for example when no model is configured."""


class FactKey(StrEnum):
    MONTHLY_FEE = "MONTHLY_FEE"
    UNIT_RATE = "UNIT_RATE"
    EFFECTIVE_DATE = "EFFECTIVE_DATE"
    TERM_MONTHS = "TERM_MONTHS"
    ORDERED_QUANTITY = "ORDERED_QUANTITY"
    RECEIVED_QUANTITY = "RECEIVED_QUANTITY"
    USAGE_QUANTITY = "USAGE_QUANTITY"
    USAGE_COVERAGE_END = "USAGE_COVERAGE_END"
    ORDER_TOTAL = "ORDER_TOTAL"
    BUDGET_CEILING = "BUDGET_CEILING"
    DELIVERED_AMOUNT = "DELIVERED_AMOUNT"
    INVOICE_AMOUNT = "INVOICE_AMOUNT"
    PAID_AMOUNT = "PAID_AMOUNT"
    PRIOR_ACCRUAL = "PRIOR_ACCRUAL"
    PREPAID_SERVICE_MONTHS = "PREPAID_SERVICE_MONTHS"
    CAPITALIZATION_THRESHOLD = "CAPITALIZATION_THRESHOLD"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    TREATMENT = "TREATMENT"
    OTHER = "OTHER"


class Fact(BaseModel):
    key: FactKey
    label: str
    value_text: str
    number: Decimal | None = None
    unit: str | None = None
    date: str | None = None
    quote: str


class DocumentFacts(BaseModel):
    vendor_name: str | None = None
    service_period: str | None = Field(default=None, description="YYYY-MM")
    facts: list[Fact] = Field(default_factory=list)


class EvidenceCard(BaseModel):
    evidence_id: str
    obligation_id: str | None
    evidence_type: EvidenceCardType
    source_table: str
    source_id: str
    fact: str
    value_json: dict[str, str | None]
    source_excerpt: str
    confidence: Decimal
    status: EvidenceCardStatus
    created_by_agent: str
    created_at: dt.datetime


class DroppedFact(BaseModel):
    file_id: str
    key: FactKey
    quote: str
    reason: str


class FileEvidence(BaseModel):
    file_id: str
    name: str
    facts_kept: int
    facts_dropped: int


class EvidenceResult(BaseModel):
    case_id: str
    extractor: str
    cards: list[EvidenceCard]
    dropped: list[DroppedFact]
    files: list[FileEvidence]
    uncertainties: list[str]


Extractor = Callable[[CaseEntry, FileEntry, str], DocumentFacts]

CARD_TYPE_BY_KIND: dict[str, EvidenceCardType] = {
    "agreement": EvidenceCardType.CONTRACT_TERM,
    "policy": EvidenceCardType.CONTRACT_TERM,
    "po": EvidenceCardType.PO_DETAIL,
    "order": EvidenceCardType.PO_DETAIL,
    "usage": EvidenceCardType.SERVICE_USAGE,
    "receipt": EvidenceCardType.SERVICE_RECEIPT,
    "delivery": EvidenceCardType.SERVICE_RECEIPT,
    "invoice": EvidenceCardType.INVOICE,
    "ap": EvidenceCardType.AP_SEARCH,
    "payment": EvidenceCardType.AP_SEARCH,
    "gl": EvidenceCardType.GL_HISTORY,
    "prior": EvidenceCardType.GL_HISTORY,
    "email": EvidenceCardType.OUTREACH_RESPONSE,
}


def card_type_for(kind: str) -> EvidenceCardType:
    return CARD_TYPE_BY_KIND.get(kind, EvidenceCardType.GL_HISTORY)


def collect_evidence(
    universe: FileUniverse,
    ingestion: IngestionResult,
    *,
    now: dt.datetime,
    seed_dir: Path | str = SEED_DIR,
    extractor: Extractor | None = None,
    session: Session | None = None,
    obligation_id: str | None = None,
) -> EvidenceResult:
    if extractor is None:
        if not llm.available():
            raise EvidenceError(
                "No language model is configured and no extractor was given. "
                "Set OPENAI_API_KEY or AWS_BEARER_TOKEN_BEDROCK, or pass an extractor."
            )
        extractor = llm_extractor
    case = next(c for c in universe.cases if c.case_id == ingestion.case_id)
    entries = {f.file_id: f for f in universe.for_case(case.case_id)}
    stem = case.case_id.removeprefix("CASE-")

    cards: list[EvidenceCard] = []
    dropped: list[DroppedFact] = []
    files: list[FileEvidence] = []
    uncertainties: list[str] = []

    for file_id in ingestion.selected:
        entry = entries.get(file_id)
        if entry is None:
            uncertainties.append(f"{file_id} is not in the case file universe")
            continue
        try:
            text = read_text(Path(seed_dir) / entry.path)
        except (UnsupportedFile, OSError, ValueError):
            uncertainties.append(f"{entry.name} could not be read")
            continue
        try:
            extracted = extractor(case, entry, text)
        except llm.LLMError as exc:
            uncertainties.append(f"Extraction failed for {entry.name}: {exc}")
            files.append(
                FileEvidence(file_id=file_id, name=entry.name, facts_kept=0, facts_dropped=0)
            )
            continue

        kept = 0
        for fact in extracted.facts:
            fact = _clear_ungrounded_date(fact, text, uncertainties, entry.name)
            reason = ungrounded_reason(fact, text)
            if reason:
                dropped.append(
                    DroppedFact(file_id=file_id, key=fact.key, quote=fact.quote, reason=reason)
                )
                uncertainties.append(f"Dropped {fact.key.value} from {entry.name}: {reason}")
                continue
            kept += 1
            cards.append(_card(fact, entry, f"EVD-{stem}-{len(cards) + 1:02d}", obligation_id, now))
        if kept == 0:
            uncertainties.append(f"No grounded facts from {entry.name}")
        files.append(
            FileEvidence(
                file_id=file_id,
                name=entry.name,
                facts_kept=kept,
                facts_dropped=len(extracted.facts) - kept,
            )
        )

    result = EvidenceResult(
        case_id=case.case_id,
        extractor=getattr(extractor, "__name__", "custom"),
        cards=cards,
        dropped=dropped,
        files=files,
        uncertainties=uncertainties,
    )
    persisted = session is not None and obligation_id is not None
    if persisted:
        session.add_all(_row(card) for card in cards)
        session.flush()
    if session is not None:
        _log(session, case, ingestion, result, obligation_id, persisted, now)
    return result


def llm_extractor(case: CaseEntry, entry: FileEntry, text: str) -> DocumentFacts:
    document = f"File: {entry.name}\n\n{text[:MAX_DOCUMENT_CHARS]}"
    prompt = (
        PROMPT_PATH.read_text()
        .replace("{{CASE}}", f"{case.title} (vendor {case.vendor_name}, period {case.period})")
        .replace("{{DOCUMENT}}", document)
    )
    return cast(DocumentFacts, llm.complete_json(prompt, DocumentFacts, system=_SYSTEM))


def ungrounded_reason(fact: Fact, text: str) -> str | None:
    """Return why the fact cannot be trusted, or None when the document supports it."""
    document = _normalize(text)
    quote = _normalize(fact.quote)
    if not quote:
        return "no quote"
    if quote not in document:
        return "quote not found in the document"
    if not _normalize(fact.value_text) or _normalize(fact.value_text) not in document:
        return "value text not found in the document"
    if fact.number is not None:
        tokens = _numbers(f"{fact.quote} {fact.value_text}")
        if fact.number not in tokens:
            return "number not found in the quote or value text"
    return None


def _clear_ungrounded_date(fact: Fact, text: str, uncertainties: list[str], name: str) -> Fact:
    if fact.date is None or _date_in_text(fact.date, _normalize(f"{fact.quote} {text}")):
        return fact
    uncertainties.append(f"Cleared date {fact.date} on {fact.key.value} from {name}: not in text")
    return fact.model_copy(update={"date": None})


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def _numbers(text: str) -> set[Decimal]:
    return {Decimal(t) for t in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))}


def _date_in_text(iso: str, normalized: str) -> bool:
    try:
        day = dt.date.fromisoformat(iso)
    except ValueError:
        return False
    if iso in normalized:
        return True
    months = (calendar.month_name[day.month].lower(), calendar.month_abbr[day.month].lower())
    return (
        str(day.year) in normalized
        and any(m in normalized for m in months)
        and re.search(rf"\b0?{day.day}\b", normalized) is not None
    )


def _card(
    fact: Fact,
    entry: FileEntry,
    evidence_id: str,
    obligation_id: str | None,
    now: dt.datetime,
) -> EvidenceCard:
    return EvidenceCard(
        evidence_id=evidence_id,
        obligation_id=obligation_id,
        evidence_type=card_type_for(entry.kind),
        source_table="document",
        source_id=entry.file_id,
        fact=f"{fact.label}: {fact.value_text}",
        value_json={
            "key": fact.key.value,
            "number": None if fact.number is None else str(fact.number),
            "unit": fact.unit,
            "date": fact.date,
            "file": entry.name,
        },
        source_excerpt=fact.quote,
        confidence=Decimal("1.00"),
        status=EvidenceCardStatus.VERIFIED,
        created_by_agent=AGENT_NAME,
        created_at=now,
    )


def _row(card: EvidenceCard) -> TrueUpEvidence:
    assert card.obligation_id is not None
    return TrueUpEvidence(
        evidence_id=card.evidence_id,
        obligation_id=card.obligation_id,
        evidence_type=card.evidence_type,
        source_table=card.source_table,
        source_id=card.source_id,
        fact=card.fact,
        value_json=card.value_json,
        source_excerpt=card.source_excerpt,
        confidence=card.confidence,
        status=card.status,
        created_by_agent=card.created_by_agent,
        created_at=card.created_at,
    )


def _log(
    session: Session,
    case: CaseEntry,
    ingestion: IngestionResult,
    result: EvidenceResult,
    obligation_id: str | None,
    persisted: bool,
    now: dt.datetime,
) -> None:
    kept, gone = len(result.cards), len(result.dropped)
    AgentRunLog(session).append(
        agent_name=AGENT_NAME,
        action="extract_facts",
        status=AgentRunStatus.COMPLETED,
        decision_summary=(
            f"Extracted {kept} grounded facts from {len(result.files)} selected files "
            f"for {case.vendor_name} {case.period}; dropped {gone} ungrounded."
        ),
        output_summary=(
            f"{kept} evidence cards ready for Obligation"
            if persisted
            else f"{kept} evidence cards not stored: no obligation is open yet"
        ),
        at=now,
        obligation_id=obligation_id,
        facts_used=[
            {"evidence_id": c.evidence_id, "file": c.value_json["file"], "fact": c.fact}
            for c in result.cards
        ],
        uncertainties=result.uncertainties or None,
        input_record_ids=ingestion.selected,
        output_record_ids=[c.evidence_id for c in result.cards] if persisted else [],
    )
