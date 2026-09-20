"""Grade December accruals against the January invoices: python scripts/run_reconciliation.py."""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.detection_agent import detect  # noqa: E402
from trueup.agents.estimation_agent import estimate  # noqa: E402
from trueup.agents.invoice_lookup_agent import lookup  # noqa: E402
from trueup.agents.journal_entry_service import draft_entry, post_simulated  # noqa: E402
from trueup.agents.policy_agent import enforce  # noqa: E402
from trueup.agents.reconciliation_agent import collect_arrivals, reconcile  # noqa: E402
from trueup.learning.testing import activate_escalator_rule  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store import models as m  # noqa: E402
from trueup.store.workflow import advance  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
# obligation -> (accrued, actual, root cause, routed stage), or None when no invoice arrives
EXPECTED = {
    "OBL-MINTLIFY-2026-12": ("1400.00", "1400.00", None, "CLOSED"),
    "OBL-OPENAI-2026-12": ("18600.00", "18600.00", None, "CLOSED"),
    "OBL-ASUS-2026-12": ("32000.00", "32000.00", None, "CLOSED"),
    "OBL-META-2026-12": ("24700.00", "30000.00", "SOURCE_DATA_ERROR", "AWAITING_CONTROLLER"),
    "OBL-NOTABILITY-2026-12": None,
}


def stage(session, oid):
    ob = session.get(m.TrueUpObligation, oid)
    return ob.workflow_stage, ob.next_action


def close_december(session):
    """Run the December close far enough to have posted accruals waiting for their invoices."""
    opened = detect(session, PERIOD, now=CLOSE).opened
    for oid in opened:
        lookup(session, oid, now=CLOSE)
        ob = session.get(m.TrueUpObligation, oid)
        # TEMPORARY stand-in for the orchestrator, which will move evidence gathering along.
        if stage(session, oid) == (
            e.WorkflowStage.GATHERING_EVIDENCE,
            e.NextAction.GATHER_EVIDENCE,
        ):
            advance(
                ob, e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY, "orchestrator", at=CLOSE
            )
        classify(session, oid, now=CLOSE)
        estimate(session, oid, now=CLOSE)

    # OpenAI stopped at Outreach for complete usage; the owner's reply supplies it.
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
    print("(starting OpenAI from a taught state: the escalator rule is already active)")
    activate_escalator_rule(session, now=CLOSE)
    advance(
        session.get(m.TrueUpObligation, "OBL-OPENAI-2026-12"),
        e.WorkflowStage.ESTIMATING,
        e.NextAction.ESTIMATE,
        "outreach",
        at=CLOSE,
    )
    estimate(session, "OBL-OPENAI-2026-12", now=CLOSE)

    for oid in opened:
        if stage(session, oid) == (e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY):
            enforce(session, oid, now=CLOSE)

    # The Controller approves ASUS (32,000 is over the review limit).
    asus = session.get(m.TrueUpObligation, "OBL-ASUS-2026-12")
    workpaper = session.get(m.TrueUpWorkpaper, asus.current_workpaper_id)
    workpaper.controller_decision = e.ControllerDecision.APPROVE
    workpaper.status = e.WorkpaperStatus.APPROVED
    advance(asus, e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY, "controller", at=CLOSE)

    for oid in opened:
        if stage(session, oid) == (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY):
            draft_entry(session, oid, now=CLOSE)
            post_simulated(session, oid, now=CLOSE)
    return opened


def main() -> None:
    sim = Simulator.initialize()
    sim.advance_to("2026-12-31T23:00:00Z")
    hits = 0
    with sim.session() as session:
        close_december(session)
        print(f"December close done. Clock moves to {JANUARY:%Y-%m-%d}.\n")
        sim.advance_to(JANUARY)
        ready = collect_arrivals(session, now=JANUARY)
        print(f"Invoices matched for: {', '.join(ready)}\n")
        print(f"{'obligation':24} {'accrued':>10} {'invoice':>10} {'variance':>10}  cause / routed")
        for oid, expected in EXPECTED.items():
            if oid not in ready:
                hit = expected is None
                hits += hit
                print(
                    f"{oid:24} no invoice arrival, stays {stage(session, oid)[0].value}  "
                    f"[{'hit' if hit else 'MISS'}]"
                )
                continue
            r = reconcile(session, oid, now=JANUARY)
            cause = r.root_cause.value if r.root_cause else None
            got = (str(r.accrued), str(r.actual), cause, r.routed_stage.value)
            hit = got == expected
            hits += hit
            print(
                f"{oid:24} {r.accrued:>10} {r.actual:>10} {r.variance:>10}  "
                f"{cause or 'MATCH'} -> {r.routed_stage.value}  [{'hit' if hit else 'MISS'}]"
            )
            print(f"    {r.explanation}")
    print(f"\n{hits}/{len(EXPECTED)} expected outcomes matched")


if __name__ == "__main__":
    main()
