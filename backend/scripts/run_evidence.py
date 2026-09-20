"""Run Ingestion then Evidence for every case: python scripts/run_evidence.py [--judge llm].

The default runs offline: the rule judge picks files and the regex extractor reads them.
`--judge all` reads every visible file, which scores the extractor without the file picking.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents import evidence_agent, evidence_rules, ingestion  # noqa: E402
from trueup.agents.evidence_agent import EvidenceError, EvidenceResult, FactKey  # noqa: E402

K = FactKey
# (label, acceptable keys, number, date). Amounts checked against the seed documents themselves.
EXPECTED: dict[str, list[tuple[str, set[FactKey], Decimal | None, str | None]]] = {
    "Mintlify": [
        ("monthly fee $1,400 after the amendment", {K.MONTHLY_FEE}, Decimal("1400"), None),
        ("amendment effective 2026-12-01", {K.EFFECTIVE_DATE, K.MONTHLY_FEE}, None, "2026-12-01"),
    ],
    "OpenAI": [
        ("stepped-up rate $0.02 per unit", {K.UNIT_RATE}, Decimal("0.02"), None),
        ("usage to date 576,000 units", {K.USAGE_QUANTITY}, Decimal("576000"), None),
        ("usage data incomplete", {K.EVIDENCE_GAP}, None, None),
    ],
    "ASUS": [
        ("25 laptops ordered", {K.ORDERED_QUANTITY}, Decimal("25"), None),
        ("20 laptops received", {K.RECEIVED_QUANTITY}, Decimal("20"), None),
        ("unit price $1,600", {K.UNIT_RATE}, Decimal("1600"), None),
    ],
    "CASE-ASUS-2026-12-02": [
        ("25 laptops ordered", {K.ORDERED_QUANTITY}, Decimal("25"), None),
        ("unit price $1,600", {K.UNIT_RATE}, Decimal("1600"), None),
    ],
    "Meta": [
        ("budget ceiling $30,000", {K.BUDGET_CEILING}, Decimal("30000"), None),
        ("delivered to date $24,700", {K.DELIVERED_AMOUNT}, Decimal("24700"), None),
    ],
    "Notability": [
        (
            "prepaid amount $21,600",
            {K.PAID_AMOUNT, K.INVOICE_AMOUNT, K.ORDER_TOTAL},
            Decimal("21600"),
            None,
        ),
        ("12 service months", {K.PREPAID_SERVICE_MONTHS, K.TERM_MONTHS}, Decimal("12"), None),
    ],
}


def select_all(case, cards):
    return [
        ingestion.FileDecision(file_id=c.entry.file_id, selected=True, reason="every file")
        for c in cards
    ]


def _hit(result: EvidenceResult, keys: set[FactKey], number: Decimal | None, date: str | None):
    for card in result.cards:
        if card.value_json["key"] not in {k.value for k in keys}:
            continue
        if number is not None and Decimal(card.value_json["number"] or "NaN") != number:
            continue
        if date is not None and card.value_json["date"] != date:
            continue
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", choices=["rule", "llm", "all"], default="rule")
    parser.add_argument("--extractor", choices=["rule", "llm"], default="rule")
    parser.add_argument("--seed-dir", type=Path, default=ingestion.SEED_DIR)
    args = parser.parse_args()

    judge = {"llm": ingestion.llm_judge, "rule": ingestion.rule_judge, "all": select_all}[
        args.judge
    ]
    extractor = (
        evidence_agent.llm_extractor if args.extractor == "llm" else evidence_rules.rule_extractor
    )
    universe = ingestion.load_universe(args.seed_dir)
    hits = total = 0
    print(f"ingestion judge={args.judge}  extractor={args.extractor}")
    for case in universe.cases:
        picked = ingestion.ingest(
            universe, case.case_id, now=universe.as_of, seed_dir=args.seed_dir, judge=judge
        )
        try:
            result = evidence_agent.collect_evidence(
                universe, picked, now=universe.as_of, seed_dir=args.seed_dir, extractor=extractor
            )
        except EvidenceError as exc:
            sys.exit(str(exc))
        names = {f.file_id: f.name for f in universe.for_case(case.case_id)}
        print(f"\n== {case.title}: {len(picked.selected)} files selected")
        for file in result.files:
            print(f"  {file.name}: {file.facts_kept} kept, {file.facts_dropped} dropped")
        for card in result.cards:
            quote = " ".join(card.source_excerpt.split())[:60]
            print(f"    {card.value_json['key']:<24} {card.fact}  | {quote}")
        for drop in result.dropped:
            print(f"    DROPPED {drop.key.value} from {names[drop.file_id]}: {drop.reason}")
        for label, keys, number, date in EXPECTED.get(
            case.case_id, EXPECTED.get(case.vendor_name, [])
        ):
            ok = _hit(result, keys, number, date)
            hits += ok
            total += 1
            print(f"  expected {'HIT ' if ok else 'MISS'} {label}")
    print(f"\nexpected facts found: {hits} of {total}")


if __name__ == "__main__":
    main()
