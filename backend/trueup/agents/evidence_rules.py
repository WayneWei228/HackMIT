"""Offline baseline extractor for the Evidence agent: regular expressions over the file text.

It returns the same `DocumentFacts` as the language-model extractor, so the same grounding checks
apply. It reads only the document text it is given and the case's vendor name. Nothing here reads
an answer key, and every fact carries a verbatim quote from the document.
"""

from __future__ import annotations

import re
from decimal import Decimal

from trueup.agents.evidence_agent import DocumentFacts, Fact, FactKey
from trueup.ingest.manifest import CaseEntry, FileEntry

_MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}
_MONTH = "|".join(_MONTHS)
_MONEY = r"\$\s?(\d[\d,]*(?:\.\d+)?)"
_DATE = re.compile(rf"\b({_MONTH}) (\d{{1,2}}), (\d{{4}})\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9$\"'])")
_QUOTED_REPLY = re.compile(r"^(>|On .+ wrote:?$)")
_GAP_WORDS = re.compile(
    r"only covers|do not have|don't have|not yet|incomplete|cannot be finalized|is missing",
    re.IGNORECASE,
)


def rule_extractor(case: CaseEntry, entry: FileEntry, text: str) -> DocumentFacts:
    """Pull the facts a close needs out of one document, by document kind."""
    handler = _BY_KIND.get(entry.kind)
    facts = handler(case, text) if handler else []
    return DocumentFacts(vendor_name=case.vendor_name, facts=facts)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(_flat(text)) if s.strip()]


def _number(raw: str) -> Decimal:
    return Decimal(raw.replace(",", ""))


def _iso(match: re.Match[str]) -> str:
    return f"{int(match.group(3)):04d}-{_MONTHS[match.group(1)]:02d}-{int(match.group(2)):02d}"


def _fact(
    key: FactKey,
    label: str,
    value_text: str,
    quote: str,
    *,
    number: Decimal | None = None,
    unit: str | None = None,
    date: str | None = None,
) -> Fact:
    return Fact(
        key=key,
        label=label,
        value_text=value_text,
        number=number,
        unit=unit,
        date=date,
        quote=quote,
    )


def _money_fact(key: FactKey, label: str, amount: str, quote: str, unit: str = "USD") -> Fact:
    return _fact(key, label, f"${amount}", quote, number=_number(amount), unit=unit)


def _agreement(case: CaseEntry, text: str) -> list[Fact]:
    facts: list[Fact] = []
    for sentence in _sentences(text):
        for match in re.finditer(rf"{_MONEY}\s+(?:per|a|each)\s+month", sentence):
            facts.append(
                _money_fact(
                    FactKey.MONTHLY_FEE, "Monthly fee", match.group(1), sentence, "USD/month"
                )
            )
        for match in re.finditer(
            rf"{_MONEY}\s+per\s+((?:[A-Za-z]+\s+)?(?:unit|call|request|token|seat|hour))\b",
            sentence,
        ):
            facts.append(
                _money_fact(
                    FactKey.UNIT_RATE, "Unit rate", match.group(1), sentence, match.group(2)
                )
            )
        change = _DATE.search(sentence)
        if (
            change
            and "$" in sentence
            and re.search(r"effective|commencing|beginning", sentence, re.I)
        ):
            facts.append(
                _fact(
                    FactKey.EFFECTIVE_DATE,
                    "Price change effective",
                    change.group(0),
                    sentence,
                    date=_iso(change),
                )
            )
        term = re.search(rf"{_MONEY}\s+for the\s+(\d+)[- ]month", sentence)
        if term:
            facts.append(
                _money_fact(FactKey.ORDER_TOTAL, "Fee for the term", term.group(1), sentence)
            )
            facts.append(
                _fact(
                    FactKey.TERM_MONTHS,
                    "Term length",
                    f"{term.group(2)}-month",
                    sentence,
                    number=Decimal(term.group(2)),
                    unit="months",
                )
            )
    months = re.search(r"\b(\d+) months\b", _flat(text))
    if months and re.search(r"in advance", text, re.IGNORECASE):
        facts.append(
            _fact(
                FactKey.PREPAID_SERVICE_MONTHS,
                "Prepaid service months",
                months.group(0),
                months.group(0),
                number=Decimal(months.group(1)),
                unit="months",
            )
        )
    return facts


def _purchase_order(case: CaseEntry, text: str) -> list[Fact]:
    flat = _flat(text)
    facts: list[Fact] = []
    total = re.search(rf"Approved total {_MONEY}", flat)
    if total:
        facts.append(
            _money_fact(FactKey.ORDER_TOTAL, "Approved total", total.group(1), total.group(0))
        )
    line = re.search(r"(\d+) \$(\d[\d,]*\.\d\d) \$(\d[\d,]*\.\d\d)", flat)
    if line:
        facts.append(
            _fact(
                FactKey.ORDERED_QUANTITY,
                "Quantity ordered",
                line.group(1),
                line.group(0),
                number=Decimal(line.group(1)),
                unit="units",
            )
        )
        facts.append(
            _money_fact(FactKey.UNIT_RATE, "Unit price", line.group(2), line.group(0), "USD/unit")
        )
    return facts


def _campaign_order(case: CaseEntry, text: str) -> list[Fact]:
    budget = re.search(rf"Not-to-exceed budget {_MONEY}", _flat(text))
    if budget is None:
        return []
    return [
        _money_fact(
            FactKey.BUDGET_CEILING, "Not-to-exceed budget", budget.group(1), budget.group(0)
        )
    ]


def _delivery(case: CaseEntry, text: str) -> list[Fact]:
    flat = _flat(text)
    facts: list[Fact] = []
    budget = re.search(rf"Budget {_MONEY}", flat)
    if budget:
        facts.append(
            _money_fact(FactKey.BUDGET_CEILING, "Budget", budget.group(1), budget.group(0))
        )
    delivered = re.search(rf"Delivered to date {_MONEY}", flat)
    if delivered:
        facts.append(
            _money_fact(
                FactKey.DELIVERED_AMOUNT,
                "Delivered to date",
                delivered.group(1),
                delivered.group(0),
            )
        )
    return facts


def _receipt(case: CaseEntry, text: str) -> list[Fact]:
    flat = _flat(text)
    facts: list[Fact] = []
    counts = re.search(r"(\d+) (\d+) (\d+) Accepted value of goods received", flat)
    if counts:
        facts.append(
            _fact(
                FactKey.ORDERED_QUANTITY,
                "Quantity ordered",
                counts.group(1),
                counts.group(0),
                number=Decimal(counts.group(1)),
                unit="units",
            )
        )
        facts.append(
            _fact(
                FactKey.RECEIVED_QUANTITY,
                "Quantity received",
                counts.group(2),
                counts.group(0),
                number=Decimal(counts.group(2)),
                unit="units",
            )
        )
    accepted = re.search(rf"Accepted value of goods received: {_MONEY}", flat)
    if accepted:
        facts.append(
            _money_fact(
                FactKey.DELIVERED_AMOUNT,
                "Accepted value received",
                accepted.group(1),
                accepted.group(0),
            )
        )
    return facts


def _usage(case: CaseEntry, text: str) -> list[Fact]:
    flat = _flat(text)
    facts: list[Fact] = []
    units = re.search(r"Units to date (\d[\d,]*)", flat)
    if units:
        facts.append(
            _fact(
                FactKey.USAGE_QUANTITY,
                "Usage to date",
                units.group(1),
                units.group(0),
                number=_number(units.group(1)),
                unit="units",
            )
        )
    year = re.search(r"\b(20\d\d)\b", flat)
    through = re.search(rf"data through ({_MONTH}) (\d{{1,2}})", flat)
    if through and year:
        day = f"{year.group(1)}-{_MONTHS[through.group(1)]:02d}-{int(through.group(2)):02d}"
        facts.append(
            _fact(
                FactKey.USAGE_COVERAGE_END,
                "Usage data runs through",
                through.group(0),
                through.group(0),
                date=day,
            )
        )
    gap = re.search(r"PARTIAL - data through [A-Za-z]+ \d+", flat)
    if gap:
        facts.append(
            _fact(FactKey.EVIDENCE_GAP, "Usage export is incomplete", "PARTIAL", gap.group(0))
        )
    return facts


def _email(case: CaseEntry, text: str) -> list[Fact]:
    facts: list[Fact] = []
    for raw in text.splitlines():
        line = raw.strip()
        if _QUOTED_REPLY.match(line):
            break
        if not line or line.startswith(("From:", "To:", "Date:", "Subject:")):
            continue
        for sentence in _sentences(line):
            usage = re.search(r"(\d[\d,]*) (API calls|API units|units)\b", sentence)
            if usage and "December" in sentence:
                facts.append(
                    _fact(
                        FactKey.USAGE_QUANTITY,
                        "Usage reported by the owner",
                        usage.group(1),
                        sentence,
                        number=_number(usage.group(1)),
                        unit=usage.group(2),
                    )
                )
            elif _GAP_WORDS.search(sentence):
                facts.append(_fact(FactKey.EVIDENCE_GAP, "Evidence gap", sentence, sentence))
    return facts


def _invoice(case: CaseEntry, text: str) -> list[Fact]:
    total = re.search(rf"Total due: {_MONEY}", _flat(text))
    if total is None:
        return []
    return [_money_fact(FactKey.INVOICE_AMOUNT, "Invoice total", total.group(1), total.group(0))]


def _payment(case: CaseEntry, text: str) -> list[Fact]:
    facts: list[Fact] = []
    for sentence in _sentences(text):
        paid = re.search(rf"paid {_MONEY}", sentence)
        if paid:
            facts.append(_money_fact(FactKey.PAID_AMOUNT, "Amount paid", paid.group(1), sentence))
    return facts


def _prior(case: CaseEntry, text: str) -> list[Fact]:
    facts: list[Fact] = []
    for sentence in _sentences(text):
        accrued = re.search(rf"accrued(?: and invoiced)?(?: at| the delivered)? {_MONEY}", sentence)
        if accrued:
            facts.append(
                _money_fact(FactKey.PRIOR_ACCRUAL, "Prior accrual", accrued.group(1), sentence)
            )
    for row in re.finditer(rf"(20\d\d-\d\d) \| {_MONEY} \| {_MONEY}", _flat(text)):
        facts.append(
            _money_fact(
                FactKey.PRIOR_ACCRUAL, f"Accrued for {row.group(1)}", row.group(2), row.group(0)
            )
        )
    return facts


def _policy(case: CaseEntry, text: str) -> list[Fact]:
    facts: list[Fact] = []
    for sentence in _sentences(text):
        threshold = re.search(rf"{_MONEY} or more", sentence)
        if threshold:
            facts.append(
                _money_fact(
                    FactKey.CAPITALIZATION_THRESHOLD,
                    "Capitalization threshold",
                    threshold.group(1),
                    sentence,
                )
            )
        life = re.search(r"straight-line over (\d+) months", sentence)
        if life:
            facts.append(
                _fact(
                    FactKey.TREATMENT,
                    "Depreciation treatment",
                    life.group(0),
                    sentence,
                    number=Decimal(life.group(1)),
                    unit="months",
                )
            )
    return facts


def _ledger(case: CaseEntry, text: str) -> list[Fact]:
    facts: list[Fact] = []
    vendor = case.vendor_name.lower()
    for raw in text.splitlines():
        line = _flat(raw)
        expensed = re.search(r"Expense [^()|]*? in full", line)
        if vendor in line.lower() and expensed and "MANUAL_ADJUSTMENT" in line:
            amount = re.search(_MONEY, line)
            facts.append(
                _fact(
                    FactKey.TREATMENT,
                    "Whole amount expensed at once",
                    expensed.group(0),
                    line,
                    number=_number(amount.group(1)) if amount else None,
                    unit="USD",
                )
            )
    return facts


_BY_KIND = {
    "agreement": _agreement,
    "po": _purchase_order,
    "order": _campaign_order,
    "delivery": _delivery,
    "receipt": _receipt,
    "usage": _usage,
    "email": _email,
    "invoice": _invoice,
    "payment": _payment,
    "prior": _prior,
    "policy": _policy,
    "gl": _ledger,
}
