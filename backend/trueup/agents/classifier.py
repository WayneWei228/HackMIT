"""Agent 4: classify each PO line as fixed/dynamic and recurring/one-time.

The deterministic rules over the PO columns are the authority. Jev reads the
free-text line description as an independent second opinion. When the two
disagree, or the columns contradict each other, a human is flagged and we
suggest what the row should say. Results are cached by a hash of the row so an
unchanged row never calls Jev twice.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy.orm import Session

from trueup.db import LineClassification, POHeader, POLine
from trueup.gateway import jev
from trueup.schemas import Classification, ClassificationResult

JEV_MIN_CONFIDENCE = 0.8

_AMOUNT_Q: jev.Question = (
    "Is the amount billed for this purchase the same every time, or does it change with "
    "usage, quantity or activity?",
    {"fixed": "Same agreed amount each time", "dynamic": "Amount varies with usage or activity"},
)
_CADENCE_Q: jev.Question = (
    "Does this purchase repeat on a schedule, or is it a single purchase?",
    {"recurring": "Repeats each month or period", "one_time": "Happens once"},
)


def _window_months(valid_from: str | None, valid_to: str | None) -> int:
    if not valid_from or not valid_to:
        return 0
    start, end = date.fromisoformat(valid_from), date.fromisoformat(valid_to)
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def classify_rules(header: POHeader, line: POLine) -> Classification:
    """Pure logic over the non-text columns."""
    amount_type = "dynamic" if line.item_category in {"B", "E"} else "fixed"
    recurring = (
        header.order_type == "FO"
        or line.contract_id is not None
        or _window_months(line.valid_from, line.valid_to) >= 2
    )
    return Classification(amount_type=amount_type, cadence="recurring" if recurring else "one_time")


def find_contradictions(header: POHeader, line: POLine) -> list[str]:
    """Deterministic checks that the columns do not disagree with each other."""
    found: list[str] = []
    if line.item_category in {"B", "E"} and not (line.valid_from and line.valid_to):
        found.append("blanket item category has no validity dates")
    if header.order_type == "FO" and not (line.valid_from and line.valid_to):
        found.append("framework order has no validity dates")
    if line.item_category == "" and (line.valid_from or line.contract_id):
        found.append("standard material line carries validity dates or a contract id")
    if line.item_category == "P" and line.contract_id and (line.quantity_ordered or 1) > 1:
        found.append("recurring service line orders a quantity above 1")
    if (
        line.quantity_billed
        and line.quantity_ordered
        and line.quantity_billed > line.quantity_ordered
    ):
        found.append("quantity billed exceeds quantity ordered")
    return found


def row_hash(header: POHeader, line: POLine) -> str:
    payload = {
        "order_type": header.order_type,
        "item_category": line.item_category,
        "qty_ordered": line.quantity_ordered,
        "unit_price_cents": line.unit_price_cents,
        "valid_from": line.valid_from,
        "valid_to": line.valid_to,
        "contract_id": line.contract_id,
        "description": line.line_description,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def reconcile(
    po_line_id: str,
    rules: Classification,
    contradictions: list[str],
    jev_answer: Classification | None,
    jev_confidence: float | None,
) -> ClassificationResult:
    """Compare the rules answer with Jev's and decide whether a human must look."""
    disagree = jev_answer is not None and jev_answer != rules
    low_confidence = jev_confidence is not None and jev_confidence < JEV_MIN_CONFIDENCE
    suggested = jev_answer if disagree and not low_confidence else None
    return ClassificationResult(
        po_line_id=po_line_id,
        rules=rules,
        jev=jev_answer,
        jev_confidence=jev_confidence,
        final=rules,
        agreed=not disagree,
        needs_human=disagree or bool(contradictions),
        contradictions=contradictions,
        suggested=suggested,
    )


def _ask_jev(line: POLine) -> tuple[Classification | None, float | None]:
    if not jev.available():
        return None, None
    try:
        answers = jev.classify(
            {"line_description": line.line_description},
            {"amount_type": _AMOUNT_Q, "cadence": _CADENCE_Q},
        )
    except jev.JevError:
        return None, None
    answer = Classification(
        amount_type=answers["amount_type"].choice, cadence=answers["cadence"].choice
    )
    confidence = min(answers["amount_type"].confidence, answers["cadence"].confidence)
    return answer, confidence


def classify_line(session: Session, po_line_id: str, use_jev: bool = True) -> ClassificationResult:
    line = session.get(POLine, po_line_id)
    if line is None:
        raise ValueError(f"PO line {po_line_id} not found")
    header = session.get(POHeader, line.po_number)
    digest = row_hash(header, line)

    cached = session.get(LineClassification, po_line_id)
    if cached is not None and cached.row_hash == digest:
        return ClassificationResult(
            po_line_id=po_line_id,
            rules=Classification(**cached.rules_json),
            jev=Classification(**cached.jev_json["answer"]) if cached.jev_json else None,
            jev_confidence=cached.jev_json["confidence"] if cached.jev_json else None,
            final=Classification(**cached.final_json["final"]),
            agreed=cached.agreed,
            needs_human=cached.needs_human,
            contradictions=cached.contradictions_json,
            suggested=(
                Classification(**cached.final_json["suggested"])
                if cached.final_json.get("suggested")
                else None
            ),
        )

    rules = classify_rules(header, line)
    contradictions = find_contradictions(header, line)
    jev_answer, jev_conf = _ask_jev(line) if use_jev else (None, None)
    result = reconcile(po_line_id, rules, contradictions, jev_answer, jev_conf)

    row = cached or LineClassification(po_line_id=po_line_id)
    row.row_hash = digest
    row.rules_json = rules.model_dump()
    row.jev_json = (
        {"answer": jev_answer.model_dump(), "confidence": jev_conf} if jev_answer else None
    )
    row.final_json = {
        "final": result.final.model_dump(),
        "suggested": result.suggested.model_dump() if result.suggested else None,
    }
    row.agreed = result.agreed
    row.needs_human = result.needs_human
    row.contradictions_json = contradictions
    session.merge(row)
    session.flush()
    return result
