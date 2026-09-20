"""The learning loop end to end: python scripts/run_learning.py.

Day one: grade the closed history, diagnose the misses, propose and replay a rule, and let the
Controller approve it. Then the December close: OpenAI's estimate changes, and January's invoice
confirms it.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.controller_workspace import controller_id  # noqa: E402
from trueup.agents.detection_agent import detect  # noqa: E402
from trueup.agents.estimation_agent import compute, estimate  # noqa: E402
from trueup.agents.invoice_lookup_agent import lookup  # noqa: E402
from trueup.agents.journal_entry_service import draft_entry, post_simulated  # noqa: E402
from trueup.agents.learning_agent import (  # noqa: E402
    approve_rule,
    record_outcome,
    run_learning_loop,
)
from trueup.agents.policy_agent import enforce  # noqa: E402
from trueup.agents.reconciliation_agent import collect_arrivals, reconcile  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store import models as m  # noqa: E402
from trueup.store.workflow import advance  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
OPENAI = "OBL-OPENAI-2026-12"
results: list[tuple[str, bool]] = []


def check(label: str, ok: bool) -> None:
    results.append((label, ok))


def complete_openai_usage(session) -> None:
    """OpenAI's owner has now supplied the full December export."""
    session.add(
        m.CompanyServiceEvidence(
            service_evidence_id="USE-OPENAI-2026-12-FULL",
            vendor_id="VEN-OPENAI",
            contract_id="CON-OPENAI",
            po_id="PO-OPENAI-2026",
            service_start_date=date(2026, 12, 1),
            service_end_date=date(2026, 12, 31),
            evidence_type=e.ServiceEvidenceType.SYSTEM_USAGE,
            quantity=Decimal("930000"),
            unit="API_CALL",
            accepted_amount=None,
            source_system=e.SourceSystem.ENGINEERING_PLATFORM,
            confirmed_by_person_id="ENG-001",
            confirmation_status=e.ConfirmationStatus.OWNER_CONFIRMED,
            created_at=CLOSE,
        )
    )
    session.flush()


def main() -> None:
    sim = Simulator.initialize()
    with sim.session() as session:
        day_one = sim.now()
        print(f"DAY ONE ({day_one:%Y-%m-%d}): grade the closed history against its invoices\n")
        out = run_learning_loop(session, now=day_one)
        print(f"{'period':8} {'accrued':>10} {'invoice':>10} {'variance':>10}  cause")
        for ev in out.evaluated:
            ob = session.get(m.TrueUpObligation, ev.obligation_id)
            print(
                f"{ob.period:8} {ev.accrued:>10} {ev.actual:>10} {ev.variance:>10}  "
                f"{ev.root_cause.value} ({ev.variance_percent}%)"
            )
        matched = [g for g in out.graded if g["root_cause"] is None]
        print(f"({len(matched)} other history accruals matched their invoices)\n")

        (replay,) = out.replayed
        row = session.get(m.TrueUpLearningRule, replay.learning_id)
        rule = row.candidate_rule_json
        print(f"CANDIDATE {replay.learning_id}: {rule['kind']}")
        print(f"  {rule['description']}")
        print(f"  predicate {rule['predicate']}; supported by {len(rule['provenance'])} misses\n")
        print("REPLAY over every graded obligation, without and with the rule")
        print(f"{'period':8} {'before':>10} {'after':>10} {'invoice':>10}  supports the rule")
        for r in replay.rows:
            print(
                f"{r.period:8} {r.before:>10} {r.after:>10} {r.actual:>10}  "
                f"{'yes' if r.supporting else '-'}"
            )
        print(f"  total error {replay.total_error_before} -> {replay.total_error_after}")
        print(f"  criteria {replay.criteria} -> {replay.status.value}\n")

        untouched = [r for r in replay.rows if not r.supporting]
        check(
            "history misses graded MISSED_ESCALATOR (Oct 2960.00, Nov 3120.00)",
            {
                (ev.accrued, ev.actual)
                for ev in out.evaluated
                if ev.root_cause == e.RootCause.MISSED_ESCALATOR
            }
            >= {
                (Decimal("11840.00"), Decimal("14800.00")),
                (Decimal("12480.00"), Decimal("15600.00")),
            },
        )
        check("one candidate proposed and its replay passed", replay.passed)
        check(
            "replay leaves every previously correct estimate unchanged",
            bool(untouched) and all(r.before == r.after == r.actual for r in untouched),
        )

        controller = controller_id(session)
        approve_rule(session, replay.learning_id, decided_by=controller, now=day_one)
        print(f"{controller} approved {replay.learning_id}; it is now ACTIVE.\n")

        sim.advance_to(CLOSE)
        print(f"DECEMBER CLOSE ({CLOSE:%Y-%m-%d}): OpenAI's estimate")
        opened = detect(session, PERIOD, now=CLOSE).opened
        assert OPENAI in opened
        lookup(session, OPENAI, now=CLOSE)
        ob = session.get(m.TrueUpObligation, OPENAI)
        # TEMPORARY stand-in for the orchestrator, which will move evidence gathering along.
        advance(ob, e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY, "orchestrator", at=CLOSE)
        classify(session, OPENAI, now=CLOSE)
        complete_openai_usage(session)
        baseline = compute(session, ob, rules=[]).estimate.amount
        print(f"  without the rule (baseline): {baseline}")
        result = estimate(session, OPENAI, now=CLOSE)
        wp = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)
        applied = wp.calculation_inputs_json["rules_applied"]
        print(f"  with the approved rule:      {result.amount}  ({result.expression})")
        print(f"  rules_applied: {applied}\n")
        check("December baseline without the rule is 14880.00", baseline == Decimal("14880.00"))
        check(
            "December estimate with the approved rule is 18600.00 and records the rule",
            result.amount == Decimal("18600.00")
            and [a["learning_id"] for a in applied] == [replay.learning_id],
        )

        enforce(session, OPENAI, now=CLOSE)
        draft_entry(session, OPENAI, now=CLOSE)
        post_simulated(session, OPENAI, now=CLOSE)

        sim.advance_to(JANUARY)
        print(f"JANUARY ({JANUARY:%Y-%m-%d}): the invoice grades the estimate")
        ready = collect_arrivals(session, now=JANUARY)
        recon = reconcile(session, OPENAI, now=JANUARY) if OPENAI in ready else None
        if recon is not None:
            print(f"  accrued {recon.accrued}, invoiced {recon.actual}, variance {recon.variance}")
            (outcome,) = record_outcome(session, OPENAI, now=JANUARY)
            print(f"  rule outcome {outcome.outcome}: uses {outcome.uses}, {outcome.stage}\n")
            check(
                "January invoice matches 18600.00 and confirms the rule",
                recon.variance == 0 and outcome.outcome == "CONFIRMED" and outcome.uses == 1,
            )
        else:
            check("January invoice matches 18600.00 and confirms the rule", False)

    print("EXPECTED")
    for label, ok in results:
        print(f"  {label:78} [{'hit' if ok else 'MISS'}]")
    hits = sum(ok for _, ok in results)
    print(f"\n{hits}/{len(results)} expected outcomes matched")
    if hits != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
