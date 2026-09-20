"""Estimate the five December obligations at close: python scripts/run_estimation.py."""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents import fallback_estimation  # noqa: E402
from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.estimation_agent import EstimationResult, estimate  # noqa: E402
from trueup.close_orchestrator import walk_to  # noqa: E402
from trueup.learning.testing import activate_escalator_rule  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store import models as m  # noqa: E402
from trueup.store.workflow import advance  # noqa: E402

PERIOD = "2026-12"
CLOSE = "2026-12-31T23:59:00Z"
NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
EXPECTED = {
    "VEN-MINTLIFY": Decimal("1400.00"),
    "VEN-OPENAI": None,
    "VEN-ASUS": Decimal("32000.00"),
    "VEN-META": Decimal("24700.00"),
    "VEN-NOTABILITY": Decimal("1800.00"),
}


def show(vendor_id: str, result: EstimationResult, expected: Decimal | None) -> bool:
    hit = result.amount == expected
    label = "hit" if hit else f"MISS, expected {expected}"
    method = result.method.value if result.method else "-"
    print(
        f"{vendor_id:15} {method:30} {result.expression or '-':26} "
        f"{result.amount if result.amount is not None else '-':>10} -> "
        f"{result.routed_stage.value}/{result.next_action.value}  [{label}]"
    )
    for note in result.warnings + result.conflicts + result.uncertainties:
        print(f"    note: {note}")
    return hit


def main() -> None:
    sim = Simulator.initialize()
    sim.advance_to(CLOSE)
    hits = 0
    with sim.session() as session:
        obligations = {}
        for vendor_id, expected in EXPECTED.items():
            obligation = walk_to(session, vendor_id, PERIOD, now=NOW)
            classify(session, obligation.obligation_id, now=NOW)
            obligations[vendor_id] = obligation
            hits += show(vendor_id, estimate(session, obligation.obligation_id, now=NOW), expected)

        print("\nOpenAI after the outreach reply supplies the complete December usage:")
        obligation = obligations["VEN-OPENAI"]
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
                created_at=NOW,
            )
        )
        session.flush()
        print("  (starting from a taught state: the escalator rule is already active)")
        activate_escalator_rule(session, now=NOW)
        advance(obligation, e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE, "outreach", at=NOW)
        hits += show(
            "VEN-OPENAI", estimate(session, obligation.obligation_id, now=NOW), Decimal("18600.00")
        )

    print("\nOpenAI when the owner never replies (a fresh close; the wait has passed):")
    silent = Simulator.initialize()
    silent.advance_to(CLOSE)
    with silent.session() as session:
        obligation = walk_to(session, "VEN-OPENAI", PERIOD, now=NOW)
        classify(session, obligation.obligation_id, now=NOW)
        estimate(session, obligation.obligation_id, now=NOW)
        print("  (starting from a taught state: the escalator rule is already active)")
        activate_escalator_rule(session, now=NOW)
        advance(
            obligation,
            e.WorkflowStage.ESTIMATING,
            e.NextAction.ESTIMATE_INCOMPLETE,
            "outreach",
            at=NOW,
        )
        result = fallback_estimation.estimate_incomplete(session, obligation.obligation_id, now=NOW)
        workpaper = session.get(m.TrueUpWorkpaper, result.workpaper_id)
        baseline = fallback_estimation.reproduce(session, obligation, workpaper, rules=[])
        for label, amount, expected in (
            ("projected on incomplete data", result.amount, Decimal("18795.79")),
            ("the same projection with no rule", baseline, Decimal("15036.63")),
        ):
            hit = amount == expected
            hits += hit
            print(
                f"  {label:36} {result.method.value} -> {amount}  "
                f"[{'hit' if hit else f'MISS, expected {expected}'}]"
            )
    print(f"\n{hits}/{len(EXPECTED) + 3} expected estimates matched")


if __name__ == "__main__":
    main()
