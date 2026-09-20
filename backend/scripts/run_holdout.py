"""Run the whole close on vendors the pipeline has never seen and score it against a hand key.

    python scripts/run_holdout.py [--extractor rule|llm] [--judge rule|llm|all]
                                  [--seed-dir seed_holdout] [--no-control] [--verbose]

The default is fully offline (rule judge, regex extractor, no model). The five demo vendors run
through exactly the same scoring as a control, so the comparison is one table. A miss is reported
and the run continues: nothing here tunes an agent to make the held-out vendors pass.
Only this script reads the hidden keys (relevance_truth.json, holdout_truth.json).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from trueup.agents import evidence_agent, evidence_rules, ingestion  # noqa: E402
from trueup.agents.controller_workspace import controller_id  # noqa: E402
from trueup.close_orchestrator import (  # noqa: E402
    CloseReport,
    CloseSettings,
    Step,
    run_month_end_close,
)
from trueup.demo_controller import ScriptedController  # noqa: E402
from trueup.gateway import llm  # noqa: E402
from trueup.simulator.files.models import RelevanceTruth  # noqa: E402
from trueup.simulator.files.scoring import score_selection  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import models as m  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
DIMENSIONS = (
    "ingestion",
    "facts (end to end)",
    "facts (extractor alone)",
    "detection",
    "purchase type",
    "method",
    "close: accrual",
    "close: stage",
    "close: controller",
    "final: stage",
    "final: accrual",
    "final: diagnosis",
    "history diagnosis",
    "learning",
)


@dataclass
class Check:
    suite: str
    vendor: str
    dimension: str
    label: str
    ok: bool
    detail: str = ""


@dataclass
class Suite:
    name: str
    seed_dir: Path
    cases: dict[str, dict[str, Any]]
    relevance: RelevanceTruth
    make_sim: Any
    approve_vendors: list[str]
    checks: list[Check] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    def add(self, vendor: str, dimension: str, label: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(self.name, vendor, dimension, label, bool(ok), detail))


# ---- what a careful accountant expects for the five demo vendors (from scripts/run_close.py) ---


def demo_cases() -> dict[str, dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("run_evidence", ROOT / "scripts/run_evidence.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    def facts(vendor: str) -> list[dict[str, Any]]:
        return [
            {
                "label": label,
                "keys": sorted(k.value for k in keys),
                "number": None if number is None else str(number),
                "date": date,
            }
            for label, keys, number, date in module.EXPECTED[vendor]
        ]

    def case(vendor, ptype, method, close, final, history, rule=False, decision=False):
        return {
            "vendor_id": f"VEN-{vendor.upper()}",
            "purchase_type": ptype,
            "method": method,
            "at_close": close,
            "final": final,
            "history": history,
            "rule_expected": rule,
            "facts": facts(vendor),
            "controller_decision": decision,
        }

    clean = {"2026-09": None, "2026-10": None, "2026-11": None}
    match = {"variance": "0.00", "root_cause": None, "stage": "CLOSED"}
    return {
        "CASE-MINTLIFY-2026-12": case(
            "Mintlify", "FIXED_RECURRING", "FIXED_CONTRACT_RATE",
            {"accrual": "1400.00", "stage": "AWAITING_ACTUAL_INVOICE"},
            {"accrued": "1400.00", "invoice": "1400.00", **match}, clean,
        ),
        "CASE-OPENAI-2026-12": case(
            "OpenAI", "USAGE_BASED", "USAGE_TIMES_RATE",
            {"accrual": None, "stage": "AWAITING_OUTREACH"},
            {"accrued": "18600.00", "invoice": "18600.00", **match},
            {p: "MISSED_ESCALATOR" for p in clean}, rule=True,
        ),
        "CASE-ASUS-2026-12": case(
            "ASUS", "RECEIPT_BASED", "RECEIVED_QUANTITY_TIMES_PRICE",
            {"accrual": "32000.00", "stage": "AWAITING_ACTUAL_INVOICE"},
            {"accrued": "32000.00", "invoice": "32000.00", **match}, {}, decision=True,
        ),
        "CASE-META-2026-12": case(
            "Meta", "MILESTONE_BASED", "MILESTONE_ACCEPTED_AMOUNT",
            {"accrual": "24700.00", "stage": "AWAITING_ACTUAL_INVOICE"},
            {"accrued": "24700.00", "invoice": "30000.00", "variance": "5300.00",
             "root_cause": "SOURCE_DATA_ERROR", "stage": "AWAITING_CONTROLLER"}, {},
        ),
        "CASE-NOTABILITY-2026-12": case(
            "Notability", "PREPAID", "PREPAID_AMORTIZATION",
            {"accrual": "1800.00", "stage": "AWAITING_CONTROLLER"},
            {"stage": "AWAITING_CONTROLLER"}, {},
        ),
    }  # fmt: skip


# ---- the two document stages, scored on their own ---------------------------------------------


def select_all(case, cards):
    return [
        ingestion.FileDecision(file_id=c.entry.file_id, selected=True, reason="every file")
        for c in cards
    ]


def _fact_hit(result: evidence_agent.EvidenceResult, fact: dict[str, Any]) -> bool:
    keys = set(fact["keys"])
    for card in result.cards:
        if card.value_json["key"] not in keys:
            continue
        if fact["number"] is not None:
            got = card.value_json["number"]
            if got is None or Decimal(got) != Decimal(fact["number"]):
                continue
        if fact["date"] is not None and card.value_json["date"] != fact["date"]:
            continue
        return True
    return False


def score_documents(suite: Suite, judge, extractor, verbose: bool) -> None:
    universe = ingestion.load_universe(suite.seed_dir)
    suite.report["universe"] = universe
    suite.report["documents"] = {}
    for case in universe.cases:
        truth = suite.cases.get(case.case_id)
        if truth is None:
            continue
        vendor = case.vendor_name
        picked = ingestion.ingest(
            universe, case.case_id, now=universe.as_of, seed_dir=suite.seed_dir, judge=judge
        )
        score = score_selection(picked.selected, suite.relevance, case.case_id)
        names = {f.file_id: f.name for f in universe.for_case(case.case_id)}
        detail = (
            f"selected {len(picked.selected)} of {picked.files_loaded}; "
            f"precision {score['precision']}, recall {score['recall']}, f1 {score['f1']}"
        )
        if score["missed"]:
            detail += "; missed " + ", ".join(names[i] for i in score["missed"])  # type: ignore[union-attr]
        if score["extra"]:
            detail += "; extra " + ", ".join(names[i] for i in score["extra"])  # type: ignore[union-attr]
        suite.add(
            vendor, "ingestion", "every relevant file selected", score["recall"] == 1.0, detail
        )

        picked_all = ingestion.ingest(
            universe, case.case_id, now=universe.as_of, seed_dir=suite.seed_dir, judge=select_all
        )
        for dimension, chosen in (
            ("facts (end to end)", picked),
            ("facts (extractor alone)", picked_all),
        ):
            try:
                result = evidence_agent.collect_evidence(
                    universe,
                    chosen,
                    now=universe.as_of,
                    seed_dir=suite.seed_dir,
                    extractor=extractor,
                )
            except Exception as exc:  # a failing extractor is a miss, not a crash
                for fact in truth["facts"]:
                    suite.add(vendor, dimension, fact["label"], False, f"extractor failed: {exc}")
                continue
            if dimension == "facts (end to end)":
                suite.report["documents"][case.case_id] = (picked, score, result, names)
            for fact in truth["facts"]:
                ok = _fact_hit(result, fact)
                found = ""
                if not ok:
                    keys = set(fact["keys"])
                    same_key = [
                        f"{c.value_json['key']}={c.value_json['number'] or c.value_json['date']}"
                        for c in result.cards
                        if c.value_json["key"] in keys
                    ]
                    found = f"{len(result.cards)} cards; same key: {same_key or 'none'}"
                suite.add(vendor, dimension, fact["label"], ok, found)


# ---- the whole close ---------------------------------------------------------------------------


def run_pipeline(suite: Suite, judge, extractor) -> None:
    sim = suite.make_sim()
    settings = CloseSettings(seed_dir=suite.seed_dir, judge=judge, extractor=extractor)
    try:
        with sim.session() as session:
            controller = ScriptedController(
                controller_id(session), approve_vendors=suite.approve_vendors
            )
            at_close = run_month_end_close(
                session, PERIOD, now=CLOSE, simulator=sim, controller=controller, settings=settings
            )
            actuals = run_month_end_close(
                session, PERIOD, now=CLOSE, simulator=sim, controller=controller,
                through=JANUARY, settings=settings,
            )  # fmt: skip
            types = {
                o.obligation_id: o.purchase_type.value
                for o in session.scalars(select(m.TrueUpObligation))
            }
            methods: dict[str, str] = {}
            for w in session.scalars(
                select(m.TrueUpWorkpaper).order_by(m.TrueUpWorkpaper.created_at)
            ):
                methods[w.obligation_id] = w.estimation_method.value
            history = {
                o.obligation_id: (o.vendor_id, o.period)
                for o in session.scalars(select(m.TrueUpObligation))
                if "-HIST-" in o.obligation_id
            }
    except Exception:
        suite.report["crash"] = traceback.format_exc()
        return
    suite.report.update(
        at_close=at_close, actuals=actuals, types=types, methods=methods, history=history
    )


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def score_pipeline(suite: Suite) -> None:
    universe = suite.report["universe"]
    crash = suite.report.get("crash")
    at_close: CloseReport | None = suite.report.get("at_close")
    actuals: CloseReport | None = suite.report.get("actuals")
    steps: list[Step] = (at_close.steps + actuals.steps) if at_close and actuals else []
    reconcile_notes: dict[tuple[str, str], str] = {}
    for step in steps:
        if step.action == "reconcile" and "-HIST-" in (step.obligation_id or ""):
            vendor_id, period = suite.report["history"][step.obligation_id]
            reconcile_notes[(vendor_id, period)] = step.note.split(":")[0].strip()

    for case in universe.cases:
        truth = suite.cases.get(case.case_id)
        if truth is None:
            continue
        vendor = case.vendor_name
        oid = f"OBL-{case.vendor_id.removeprefix('VEN-')}-{PERIOD}"
        if crash:
            reason = "the run crashed: " + crash.strip().splitlines()[-1]
            for dim, label in (
                ("detection", "obligation opened"),
                ("purchase type", "classified"),
                ("method", "estimation method"),
                ("close: stage", "resting stage at close"),
                ("final: stage", "final resting stage"),
                ("final: accrual", "final accrual"),
            ):
                suite.add(vendor, dim, label, False, reason)
            continue
        try:
            close_out = at_close.outcome(oid)  # type: ignore[union-attr]
            final_out = actuals.outcome(oid)  # type: ignore[union-attr]
        except StopIteration:
            suite.add(vendor, "detection", "obligation opened", False, f"{oid} was never opened")
            continue
        suite.add(vendor, "detection", "obligation opened", True, oid)
        got_type = suite.report["types"].get(oid)
        suite.add(
            vendor, "purchase type", truth["purchase_type"], got_type == truth["purchase_type"],
            f"classified as {got_type}",
        )  # fmt: skip
        got_method = suite.report["methods"].get(oid)
        suite.add(
            vendor, "method", truth["method"], got_method == truth["method"],
            f"workpaper method {got_method or 'none (no workpaper)'}",
        )  # fmt: skip

        expect = truth["at_close"]
        if "accrual" in expect:
            got = _money(close_out.accrued)
            suite.add(
                vendor, "close: accrual", f"accrual at close {expect['accrual']}",
                got == expect["accrual"], f"accrual at close {got}",
            )  # fmt: skip
        suite.add(
            vendor, "close: stage", expect["stage"],
            close_out.workflow_stage.value == expect["stage"],
            f"{close_out.workflow_stage.value}: {close_out.rested_because}",
        )  # fmt: skip
        if truth.get("controller_decision"):
            decided = any(s.obligation_id == oid and s.action == "decide" for s in at_close.steps)  # type: ignore[union-attr]
            suite.add(
                vendor, "close: controller", "sent to the Controller and decided", decided,
                "a Controller decision was recorded" if decided else "no Controller decision step",
            )  # fmt: skip

        final = truth["final"]
        suite.add(
            vendor, "final: stage", final["stage"],
            final_out.workflow_stage.value == final["stage"],
            f"{final_out.workflow_stage.value}: {final_out.rested_because}",
        )  # fmt: skip
        if "accrued" in final:
            got = _money(final_out.accrued)
            suite.add(
                vendor, "final: accrual",
                f"accrual {final['accrued']} against invoice {final['invoice']}",
                got == final["accrued"] and _money(final_out.invoice) == final["invoice"],
                f"accrued {got}, invoiced {_money(final_out.invoice)}",
            )  # fmt: skip
            suite.add(
                vendor, "final: diagnosis",
                f"variance {final['variance']}, cause {final['root_cause']}",
                _money(final_out.variance) == final["variance"]
                and final_out.root_cause == final["root_cause"],
                f"variance {_money(final_out.variance)}, cause {final_out.root_cause}",
            )  # fmt: skip
        for period, cause in truth["history"].items():
            got_cause = reconcile_notes.get((truth["vendor_id"], period), "no true-up recorded")
            expected = cause or "MATCH"
            suite.add(
                vendor, "history diagnosis", f"{period} graded {expected}", got_cause == expected,
                f"graded {got_cause}",
            )  # fmt: skip
        if truth["rule_expected"]:
            active = [r for r in actuals.rules if r.status.value == "ACTIVE"]  # type: ignore[union-attr]
            suite.add(
                vendor, "learning", "an escalator rule is learned, replayed and active",
                bool(active),
                "; ".join(f"{r.learning_id} {r.status.value}" for r in actuals.rules)  # type: ignore[union-attr]
                or "no rule proposed",
            )  # fmt: skip


# ---- printing ----------------------------------------------------------------------------------


def print_case_detail(suite: Suite) -> None:
    universe = suite.report["universe"]
    at_close: CloseReport | None = suite.report.get("at_close")
    actuals: CloseReport | None = suite.report.get("actuals")
    steps = (at_close.steps + actuals.steps) if at_close and actuals else []
    for case in universe.cases:
        if case.case_id not in suite.cases:
            continue
        vendor = case.vendor_name
        oid = f"OBL-{case.vendor_id.removeprefix('VEN-')}-{PERIOD}"
        print(f"\n--- {vendor} ({case.case_id})")
        docs = suite.report["documents"].get(case.case_id)
        if docs:
            picked, score, result, names = docs
            print(
                f"  Ingestion ({picked.judge}): {len(picked.selected)} of "
                f"{picked.files_loaded} selected, "
                f"recall {score['recall']}, precision {score['precision']}"
            )
            for file_id in picked.selected:
                print(f"    kept {names[file_id]}")
            for missed in score["missed"]:  # type: ignore[union-attr]
                print(f"    MISSED relevant {names[missed]}")
            print(f"  Evidence ({result.extractor}): {len(result.cards)} cards")
            for card in result.cards:
                quote = " ".join(card.source_excerpt.split())[:70]
                print(f"    {card.value_json['key']:<22} {card.fact[:46]:<46} | {quote}")
        for step in steps:
            if step.obligation_id == oid and step.agent not in ("orchestrator",):
                move = f"{step.from_state or ''} -> {step.to_state}" if step.to_state else ""
                print(
                    f"  {step.at:%m-%d %H:%M} {step.agent:<20} {step.action:<18} "
                    f"{move} {step.note[:90]}".rstrip()
                )
        for c in suite.checks:
            if c.vendor == vendor and c.dimension not in (
                "facts (end to end)",
                "facts (extractor alone)",
                "ingestion",
            ):
                print(
                    f"  [{'hit ' if c.ok else 'MISS'}] {c.dimension:<18} {c.label}"
                    + ("" if c.ok else f"  <- {c.detail}")
                )


def print_checks(suite: Suite) -> None:
    for c in suite.checks:
        mark = "hit " if c.ok else "MISS"
        print(f"  [{mark}] {c.vendor:<22} {c.dimension:<24} {c.label}")
        if not c.ok and c.detail:
            print(f"         {c.detail}")


def tally(checks: list[Check], dimension: str | None = None) -> tuple[int, int]:
    rows = [c for c in checks if dimension is None or c.dimension == dimension]
    return sum(c.ok for c in rows), len(rows)


def load_suite(name: str, seed_dir: Path) -> Suite:
    truth_file = seed_dir / "holdout_truth.json"
    relevance = RelevanceTruth.model_validate_json((seed_dir / "relevance_truth.json").read_text())
    if truth_file.exists():
        cases = json.loads(truth_file.read_text())["cases"]
        for case in cases.values():
            case.setdefault(
                "controller_decision", bool(case["at_close"].get("controller_decision"))
            )
        approve = ["VEN-LARKSPUR"]
        make_sim = lambda: Simulator.initialize(seed_dir=seed_dir)  # noqa: E731
    else:
        cases = demo_cases()
        approve = ["VEN-ASUS"]
        make_sim = lambda: Simulator.initialize()  # noqa: E731
    return Suite(name, seed_dir, cases, relevance, make_sim, approve)


def resolve(path: str) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate.resolve()
    return (ROOT.parent / path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", choices=["rule", "llm", "all"], default="rule")
    parser.add_argument("--extractor", choices=["rule", "llm"], default="rule")
    parser.add_argument("--seed-dir", default=str(ROOT / "seed_holdout"))
    parser.add_argument("--no-control", action="store_true", help="skip the five demo vendors")
    parser.add_argument(
        "--verbose", action="store_true", help="show per-vendor detail for the demo too"
    )
    args = parser.parse_args()

    if args.judge in ("rule", "all") and args.extractor == "rule":
        for key in ("OPENAI_API_KEY", "AWS_BEARER_TOKEN_BEDROCK"):
            os.environ.pop(key, None)
    elif not llm.available():
        sys.exit(
            "The llm judge and extractor need a model. Set OPENAI_API_KEY or "
            "AWS_BEARER_TOKEN_BEDROCK in your own shell and run again."
        )
    judge = {"llm": ingestion.llm_judge, "rule": ingestion.rule_judge, "all": select_all}[
        args.judge
    ]
    extractor = (
        evidence_agent.llm_extractor if args.extractor == "llm" else evidence_rules.rule_extractor
    )

    suites = [load_suite("held-out", resolve(args.seed_dir))]
    if not args.no_control:
        suites.append(load_suite("demo", ingestion.SEED_DIR))
    print(
        f"ingestion judge={args.judge}  extractor={args.extractor}  "
        "(synthetic data, simulated systems)"
    )
    for suite in suites:
        score_documents(suite, judge, extractor, args.verbose)
        run_pipeline(suite, judge, extractor)
        score_pipeline(suite)
        print(
            f"\n=== {suite.name.upper()} VENDORS: "
            f"{', '.join(c['vendor_id'] for c in suite.cases.values())}"
        )
        if suite.report.get("crash"):
            print("THE RUN CRASHED\n" + suite.report["crash"])
        if suite.name == "held-out" or args.verbose:
            print_case_detail(suite)
        else:
            print_checks(suite)

    held, demo = suites[0], (suites[1] if len(suites) > 1 else None)
    print("\nDEMO vs HELD-OUT (hits / checks)")
    print(f"  {'dimension':<26} {'held-out':>10} {'demo':>10}")
    for dimension in DIMENSIONS:
        h_hit, h_all = tally(held.checks, dimension)
        d_hit, d_all = tally(demo.checks, dimension) if demo else (0, 0)
        if not (h_all or d_all):
            continue
        h_text = f"{h_hit}/{h_all}" if h_all else "-"
        d_text = f"{d_hit}/{d_all}" if d_all else "-"
        print(f"  {dimension:<26} {h_text:>10} {d_text:>10}")
    h_hit, h_all = tally(held.checks)
    d_hit, d_all = tally(demo.checks) if demo else (0, 0)
    print(f"  {'OVERALL':<26} {f'{h_hit}/{h_all}':>10} {f'{d_hit}/{d_all}' if demo else '-':>10}")

    print("\nMISSES ON THE HELD-OUT VENDORS")
    misses = [c for c in held.checks if not c.ok]
    for c in misses:
        print(f"  {c.vendor:<22} {c.dimension:<24} {c.label}")
        if c.detail:
            print(f"      {c.detail}")
    if not misses:
        print("  none")
    if demo:
        print("\nMISSES ON THE DEMO CONTROL")
        demo_misses = [c for c in demo.checks if not c.ok]
        for c in demo_misses:
            print(f"  {c.vendor:<22} {c.dimension:<24} {c.label}")
            if c.detail:
                print(f"      {c.detail}")
        if not demo_misses:
            print("  none")
    print(f"\n{h_hit}/{h_all} held-out checks passed")


if __name__ == "__main__":
    main()
