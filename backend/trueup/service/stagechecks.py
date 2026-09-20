"""What a stage received and the checks it ran, composed from the recorded rows and records.

Every body sentence is built from values the agents wrote: the invoice search result, the evidence
cards and their quotes, the classification signals, the workpaper inputs, the policy rules and the
gate results. Which checks appear depends on what was recorded and on the classified purchase
type, so different vendors show different checks. A check with nothing recorded is left out.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.selection_override import AGENT_NAME as OVERRIDE_AGENT
from trueup.service import models as v
from trueup.service.runlog import Trace
from trueup.store import enums as e
from trueup.store import models as m

_PurchaseType = e.PurchaseType


def _money(value: Any) -> str:
    try:
        return f"${Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def _live_document_cards(trace: Trace) -> list[m.TrueUpEvidence]:
    return [
        c
        for c in trace.cards
        if c.source_table == "document" and c.status != e.EvidenceCardStatus.SUPERSEDED
    ]


def _key(card: m.TrueUpEvidence) -> str | None:
    return (card.value_json or {}).get("key") if isinstance(card.value_json, dict) else None


def _value(card: m.TrueUpEvidence) -> str:
    return card.fact.partition(": ")[2].strip().rstrip(",;") or card.fact


def _cards_of(trace: Trace, *keys: str) -> list[m.TrueUpEvidence]:
    return [c for c in _live_document_cards(trace) if _key(c) in keys]


def _seq(trace: Trace, row: m.TrueUpAgentRun | None) -> int | None:
    return trace.seq_of_run.get(row.run_id) if row is not None else None


def _check(
    trace: Trace,
    check_id: str,
    label: str,
    status: str,
    body: str,
    row: m.TrueUpAgentRun | None = None,
    evidence_ids: list[str] | None = None,
) -> v.StageCheck:
    return v.StageCheck(
        check_id=check_id,
        label=label,
        status=status,  # type: ignore[arg-type]
        body=body,
        log_seq=_seq(trace, row),
        evidence_ids=evidence_ids or [],
    )


# ---- what each stage received -----------------------------------------------------------------


def received_for(stage: str, trace: Trace) -> v.StageReceived | None:
    """Describe the handoff this stage got, from the recorded handoff and nothing else."""
    wanted = {
        "Ingestion": ("invoice_lookup", "ingestion"),
        "Evidence": ("ingestion", "evidence"),
        "Obligation": ("evidence", "classification"),
        "Estimation": ("classification", "estimation"),
        "Verification": ("estimation", "policy"),
    }[stage]
    handoff = next(
        (h for h in reversed(trace.handoffs) if (h.from_agent, h.to_agent) == wanted), None
    )
    if handoff is None:
        return None
    record = handoff.payload.get("record") or {}
    summary, counts = _describe(handoff.payload_kind, record)
    return v.StageReceived(
        from_agent=handoff.from_agent,
        handoff_seq=handoff.seq,
        payload_kind=handoff.payload_kind,
        summary=summary,
        counts=counts,
    )


def _describe(kind: str, record: dict[str, Any]) -> tuple[str, dict[str, int]]:
    if kind == "InvoiceLookupResult":
        ignored = sum(
            int(f.get("ignored_other_periods", 0))
            for f in record.get("facts_used") or []
            if isinstance(f, dict)
        )
        matched = 1 if record.get("matched_invoice_id") else 0
        return (
            f"AP search result: {record.get('summary')}",
            {"invoices_matched": matched, "other_period_invoices_ignored": ignored},
        )
    if kind == "IngestionResult":
        files = record.get("files") or []
        chosen = [f for f in files if f["selected"]]
        removed = [f for f in files if f["removed_by_user"]]
        text = f"{len(chosen)} of {len(files)} files selected by {record.get('judge')}"
        if removed:
            text += f", {len(removed)} removed by a person"
        return text, {
            "files_offered": len(files),
            "files_selected": len(chosen),
            "removed_by_user": len(removed),
        }
    if kind == "EvidenceCards":
        cards = record.get("cards") or []
        sources = {c["source_id"] for c in cards}
        quoted = sum(1 for c in cards if c.get("quote"))
        return (
            f"{len(cards)} facts from {len(sources)} selected files, {quoted} with quoted spans",
            {"facts": len(cards), "files": len(sources), "with_quotes": quoted},
        )
    if kind == "Classification":
        signals = record.get("signals") or []
        return (
            f"Classified as {record.get('purchase_type')} from {len(signals)} signals",
            {"signals": len(signals)},
        )
    if kind == "Workpaper":
        inputs = record.get("inputs") or {}
        return (
            f"Workpaper {record.get('workpaper_id')}: {_money(record.get('amount'))} by "
            f"{record.get('method')} from {len(inputs.get('sources') or [])} sources",
            {
                "inputs": len(inputs),
                "sources": len(inputs.get("sources") or []),
                "checks": len(inputs.get("checks") or []),
            },
        )
    return str(record.get("summary") or kind), {}


# ---- the checks each stage ran ----------------------------------------------------------------


def checks_for(stage: str, trace: Trace, session: Session) -> list[v.StageCheck]:
    builders = {
        "Ingestion": _ingestion_checks,
        "Evidence": _evidence_checks,
        "Obligation": _obligation_checks,
        "Estimation": _estimation_checks,
        "Verification": _verification_checks,
    }
    return builders[stage](trace, session)


def _lookup_check(trace: Trace, check_id: str) -> v.StageCheck | None:
    row = trace.latest("invoice_lookup", "search_ap")
    if row is None:
        return None
    found = trace.ob.invoice_status == e.InvoiceStatus.INVOICE_FOUND
    matched = trace.ob.matched_invoice_id
    tail = f" Matched invoice {matched}." if matched else ""
    return _check(
        trace,
        check_id,
        "Search AP for an invoice",
        "FLAG" if found else "PASS",
        f"{row.decision_summary}{tail}",
        row,
    )


def _override_check(trace: Trace, check_id: str) -> v.StageCheck | None:
    row = trace.latest(OVERRIDE_AGENT, "deselect_files")
    if row is None:
        return None
    header = (row.facts_used_json or [{}])[0]
    if header.get("restored") and not header.get("excluded_file_ids"):
        return _check(trace, check_id, "File selection", "INFO", row.decision_summary, row)
    return _check(trace, check_id, "Files removed by a person", "FLAG", row.decision_summary, row)


def _ingestion_checks(trace: Trace, _: Session) -> list[v.StageCheck]:
    checks = []
    lookup = _lookup_check(trace, "ING-AP")
    if lookup:
        checks.append(lookup)
    row = trace.latest("ingestion", "select_files")
    if row is not None:
        files = {f.file_id: f.name for f in trace.universe.files}
        chosen = [d["file_id"] for d in row.facts_used_json or [] if d["selected"]]
        judge = row.decision_summary.rsplit(" using the ", 1)[-1].rstrip(".")
        names = ", ".join(files.get(i, i) for i in chosen) or "none"
        checks.append(
            _check(
                trace,
                "ING-SEL",
                "Files selected",
                "PASS" if chosen else "FLAG",
                f"{judge} selected {len(chosen)} of {len(row.facts_used_json or [])} files: "
                f"{names}.",
                row,
            )
        )
    override = _override_check(trace, "ING-OVR")
    if override:
        checks.append(override)
    return checks


def _evidence_checks(trace: Trace, _: Session) -> list[v.StageCheck]:
    row = trace.latest("evidence", "extract_facts")
    if row is None:
        return []
    cards = _live_document_cards(trace)
    files = {c.source_id for c in cards}
    dropped = [u for u in row.uncertainties_json or [] if str(u).startswith("Dropped")]
    extractor = row.decision_summary.rsplit("Extractor: ", 1)[-1].rstrip(".")
    checks = [
        _check(
            trace,
            "EVI-GROUND",
            "Every fact is quoted from its source",
            "FLAG" if dropped else "PASS",
            f"{len(cards)} facts from {len(files)} files by {extractor}; each quote was "
            f"re-found in its document text. {len(dropped)} dropped as ungrounded.",
            row,
            [c.evidence_id for c in cards],
        )
    ]
    by_key: dict[str, dict[str, m.TrueUpEvidence]] = {}
    for card in cards:
        if _key(card) in (None, "OTHER", "TREATMENT", "EVIDENCE_GAP"):
            continue
        by_key.setdefault(str(_key(card)), {}).setdefault(_value(card), card)
    clashes = {k: vals for k, vals in by_key.items() if len(vals) > 1}
    if clashes:
        listed = "; ".join(f"{k}: {' vs '.join(vals)}" for k, vals in clashes.items())
        ids = [c.evidence_id for vals in clashes.values() for c in vals.values()]
        checks.append(
            _check(
                trace,
                "EVI-CONFLICT",
                "Facts with more than one value",
                "FLAG",
                f"Documents give different values for the same fact ({listed}); Estimation "
                "compares them with the contract table.",
                row,
                ids,
            )
        )
    elif cards:
        checks.append(
            _check(
                trace,
                "EVI-CONFLICT",
                "Facts with more than one value",
                "PASS",
                "No fact kind has two different values across the selected documents.",
                row,
                [c.evidence_id for c in cards],
            )
        )
    kinds = sorted({str(_key(c)) for c in cards if _key(c)})
    if kinds:
        checks.append(
            _check(
                trace,
                "EVI-KINDS",
                "Kinds of fact found",
                "INFO",
                "Found " + ", ".join(kinds) + ".",
                row,
            )
        )
    override = _override_check(trace, "EVI-OVR")
    if override and override.status == "FLAG":
        checks.append(override)
    return checks


def _signals(row: m.TrueUpAgentRun) -> list[dict[str, Any]]:
    return [
        s
        for s in row.facts_used_json or []
        if isinstance(s, dict) and s.get("name") != "cross_check"
    ]


def _obligation_checks(trace: Trace, session: Session) -> list[v.StageCheck]:
    row = trace.latest("classification", "classify_purchase")
    if row is None:
        return []
    ob = trace.ob
    signals = _signals(row)
    because = ", ".join(f"{s['name']}={s['value']}" for s in signals) or "the structural data"
    checks = [
        _check(
            trace,
            "OBL-TYPE",
            "Purchase type",
            "PASS",
            f"Classified as {ob.purchase_type.value} from {because}.",
            row,
        )
    ]
    lookup = _lookup_check(trace, "OBL-AP")
    if lookup:
        checks.append(lookup)
    days = (ob.service_end_date - ob.service_start_date).days + 1
    checks.append(
        _check(
            trace,
            "OBL-WINDOW",
            "Service window",
            "PASS",
            f"The service window runs {ob.service_start_date} to {ob.service_end_date} "
            f"({days} days).",
            row,
        )
    )
    special = _type_check(trace, session, row)
    if special:
        checks.append(special)
    return checks


def _type_check(trace: Trace, session: Session, row: m.TrueUpAgentRun) -> v.StageCheck | None:
    ob = trace.ob
    kind = ob.purchase_type
    if kind == _PurchaseType.FIXED_RECURRING:
        dates = _cards_of(trace, "EFFECTIVE_DATE")
        fees = _cards_of(trace, "MONTHLY_FEE")
        if not fees:
            return None
        listed = ", ".join(f"{_value(c)} ({c.evidence_id})" for c in fees)
        if not dates:
            return _check(
                trace,
                "OBL-AMEND",
                "Amendment effective date",
                "INFO",
                f"No amendment date in the selected documents; fee cards say {listed}.",
                row,
                [c.evidence_id for c in fees],
            )
        effective = _parse_day(_value(dates[0]))
        early = effective is not None and effective <= ob.service_start_date
        return _check(
            trace,
            "OBL-AMEND",
            "Amendment effective date",
            "PASS" if early else "INFO",
            f"A price change is effective {_value(dates[0])}; the period starts "
            f"{ob.service_start_date}. Fee cards: {listed}.",
            row,
            [c.evidence_id for c in [*dates, *fees]],
        )
    if kind == _PurchaseType.USAGE_BASED:
        usage = list(
            session.scalars(
                select(m.CompanyServiceEvidence)
                .where(m.CompanyServiceEvidence.vendor_id == ob.vendor_id)
                .order_by(m.CompanyServiceEvidence.service_end_date)
            )
        )
        current = [u for u in usage if u.service_start_date >= ob.service_start_date]
        if not current:
            return _check(
                trace,
                "OBL-USAGE",
                "Usage completeness",
                "FLAG",
                "No usage report covers this period yet.",
                row,
            )
        last = current[-1]
        full = last.service_end_date >= ob.service_end_date
        return _check(
            trace,
            "OBL-USAGE",
            "Usage completeness",
            "PASS" if full else "FLAG",
            f"The latest usage report ({last.service_evidence_id}) covers "
            f"{last.service_start_date} to {last.service_end_date} with {last.quantity} "
            f"{last.unit or 'units'}; the period ends {ob.service_end_date}.",
            row,
        )
    if kind == _PurchaseType.PREPAID:
        expensed = _cards_of(trace, "TREATMENT")
        months = _cards_of(trace, "PREPAID_SERVICE_MONTHS", "TERM_MONTHS")
        if expensed:
            return _check(
                trace,
                "OBL-DEFER",
                "Already expensed or deferred",
                "FLAG",
                f"The GL shows the whole amount expensed at once ({expensed[0].evidence_id}: "
                f"{_value(expensed[0])}); a prepaid must be deferred over its term.",
                row,
                [c.evidence_id for c in expensed],
            )
        return _check(
            trace,
            "OBL-DEFER",
            "Already expensed or deferred",
            "PASS",
            "No entry in the selected documents expenses the full amount"
            + (f"; the term is {_value(months[0])}." if months else "."),
            row,
            [c.evidence_id for c in months],
        )
    if kind == _PurchaseType.RECEIPT_BASED:
        received = _cards_of(trace, "RECEIVED_QUANTITY")
        ordered = _cards_of(trace, "ORDERED_QUANTITY")
        if not received:
            return None
        partial = bool(ordered) and _value(received[0]) != _value(ordered[0])
        text = f"{_value(received[0])} received" + (
            f" of {_value(ordered[0])} ordered" if ordered else ""
        )
        return _check(
            trace,
            "OBL-RECEIPT",
            "Goods receipt",
            "INFO" if partial else "PASS",
            f"{text} ({received[0].evidence_id}); only what was received is accrued.",
            row,
            [c.evidence_id for c in [*received, *ordered[:1]]],
        )
    if kind == _PurchaseType.MILESTONE_BASED:
        delivered = _cards_of(trace, "DELIVERED_AMOUNT")
        budget = _cards_of(trace, "BUDGET_CEILING")
        if not delivered:
            return None
        text = f"{_value(delivered[0])} delivered"
        if budget:
            text += f" against a budget of {_value(budget[0])}"
        return _check(
            trace,
            "OBL-DELIVERY",
            "Delivery against budget",
            "INFO",
            f"{text} ({delivered[0].evidence_id}).",
            row,
            [c.evidence_id for c in [*delivered, *budget[:1]]],
        )
    return None


def _parse_day(text: str) -> date | None:
    for form in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), form).date()
        except ValueError:
            continue
    return None


_BUILD_LABELS = {
    "coverage_period": "Coverage period",
    "rate_applied": "Rate applied",
    "credits_and_refunds": "Credits and refunds",
    "prepaid_amounts": "Prepaid amounts",
    "partial_period_offsets": "Partial-period offsets",
    "prior_close_comparison": "Comparison to the prior close",
}


def _estimation_checks(trace: Trace, _: Session) -> list[v.StageCheck]:
    row = trace.latest("estimation", "estimate_accrual")
    if row is None:
        return []
    wp = trace.wp
    if wp is None:
        note = "; ".join(str(u) for u in row.uncertainties_json or []) or row.decision_summary
        return [
            _check(trace, "EST-STOP", "Estimate not produced", "FLAG", note, row),
        ]
    inputs = wp.calculation_inputs_json or {}
    sources = ", ".join(inputs.get("sources") or []) or "no sources"
    checks = [
        _check(
            trace,
            "EST-RATE",
            "Amount and method",
            "PASS",
            f"{_money(wp.proposed_amount)} = {wp.calculation_expression} by "
            f"{wp.estimation_method.value}, from {sources}.",
            row,
        )
    ]
    for build in inputs.get("checks") or []:
        name = build["name"]
        if name == "rate_applied":
            continue
        checks.append(
            _check(
                trace,
                f"EST-{name.upper()}",
                _BUILD_LABELS.get(name, name),
                "INFO" if name == "prior_close_comparison" else "PASS",
                str(build["result"]),
                row,
            )
        )
    applied = inputs.get("rules_applied") or []
    if applied:
        ids = ", ".join(r["learning_id"] for r in applied)
        checks.append(
            _check(
                trace,
                "EST-RULE",
                "Learned rule applied",
                "INFO",
                f"An approved rule changed the rate used: {ids}.",
                row,
            )
        )
    for text in [*(inputs.get("conflicts") or []), *(inputs.get("warnings") or [])]:
        checks.append(
            _check(trace, "EST-WARN", "Warning from the estimator", "FLAG", str(text), row)
        )
    return checks


def _verification_checks(trace: Trace, _: Session) -> list[v.StageCheck]:
    row = trace.latest("policy", "verify_policy")
    if row is None:
        return []
    checks = []
    for rule in row.facts_used_json or []:
        if not isinstance(rule, dict) or "rule_id" not in rule:
            continue
        status = {"HIT": "FLAG", "PASS": "PASS"}.get(rule["status"], "INFO")
        checks.append(
            _check(trace, rule["rule_id"], rule["name"], status, rule.get("detail", ""), row)
        )
    gate = next(
        (h for h in reversed(trace.handoffs) if h.from_agent == "policy" and h.verification), None
    )
    if gate is not None and gate.verification is not None:
        result = gate.verification
        checks.append(
            v.StageCheck(
                check_id="VER-GATE",
                label="Verification gate after Policy",
                status="PASS" if result.verdict == "PERMIT" else "FLAG",
                body=(
                    f"{result.passed} of {result.total} controls passed at "
                    f"{gate.stage_from} to {gate.stage_to}: {result.verdict}."
                ),
                log_seq=None,
                evidence_ids=[],
            )
        )
    review = trace.latest("reviewer", "review")
    if review is not None:
        good = review.decision_summary.startswith("APPROVE_RECOMMENDED")
        checks.append(
            _check(
                trace,
                "REV-VERDICT",
                "Reviewer's finding",
                "PASS" if good else "FLAG",
                review.decision_summary,
                review,
            )
        )
    decided = trace.latest("controller_workspace", "record_decision")
    if decided is not None:
        checks.append(
            _check(
                trace,
                "CTL-DECISION",
                "Controller's decision",
                "INFO",
                decided.decision_summary,
                decided,
            )
        )
    return checks
