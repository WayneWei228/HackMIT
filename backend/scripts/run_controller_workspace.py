"""Run the close to the Controller review: python scripts/run_controller_workspace.py."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from trueup.agents import controller_workspace as cw  # noqa: E402
from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.detection_agent import detect  # noqa: E402
from trueup.agents.estimation_agent import estimate  # noqa: E402
from trueup.agents.invoice_lookup_agent import lookup  # noqa: E402
from trueup.agents.journal_entry_service import draft_entry, post_simulated  # noqa: E402
from trueup.agents.policy_agent import enforce  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store import models as m  # noqa: E402
from trueup.store.workflow import advance  # noqa: E402

PERIOD = "2026-12"
NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
ASUS, NOTABILITY = "OBL-ASUS-2026-12", "OBL-NOTABILITY-2026-12"


def run_chain(session) -> None:
    detect(session, PERIOD, now=NOW)
    for ob in list(session.scalars(select(m.TrueUpObligation))):
        lookup(session, ob.obligation_id, now=NOW)
        # TEMPORARY: the orchestrator will move the obligation from evidence to classification.
        advance(
            ob, e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY, "orchestrator-stand-in", at=NOW
        )
        classify(session, ob.obligation_id, now=NOW)
        estimate(session, ob.obligation_id, now=NOW)
        if (ob.workflow_stage, ob.next_action) == (
            e.WorkflowStage.ESTIMATING,
            e.NextAction.VERIFY_POLICY,
        ):
            enforce(session, ob.obligation_id, now=NOW)


def main() -> None:
    sim = Simulator.initialize()
    sim.advance_to("2026-12-31T23:00:00Z")
    results: list[tuple[str, bool]] = []
    with sim.session() as session:
        run_chain(session)
        controller = cw.controller_id(session)

        print(f"Review queue at {NOW:%Y-%m-%d} (controller {controller}):")
        queue = cw.review_queue(session, now=NOW)
        for n, item in enumerate(queue, start=1):
            amount = f"{item.amount}" if item.amount is not None else "no estimate"
            allowed = ", ".join(d.value for d in item.allowed_decisions)
            flag = "BLOCKED" if item.blocked else "REVIEW"
            print(f"  {n}. {item.vendor_name:11} {amount:>10} {flag}")
            print(f"     why: {item.reason}")
            print(f"     may: {allowed}")
        results.append(
            (
                "queue is Notability then ASUS",
                [i.obligation_id for i in queue] == [NOTABILITY, ASUS],
            )
        )

        packet = cw.build_packet(session, ASUS, now=NOW)
        print(f"\nASUS packet ({packet.narrative_source} narrative):")
        print(f"  {packet.narrative}")
        if packet.narrative_note:
            print(f"  note: {packet.narrative_note}")
        print(f"  recommendation: {packet.recommendation}")

        approved = cw.decide(
            session,
            ASUS,
            e.ControllerDecision.APPROVE,
            now=NOW,
            decided_by=controller,
            notes="20 of 25 units received and accepted; accrue the received quantity.",
        )
        print(
            f"\nASUS approved -> {approved.routed_stage.value}/{approved.next_action.value}, "
            f"workpaper {approved.workpaper_status.value}, amount {approved.amount}"
        )
        results.append(
            (
                "ASUS approve routes to READY_TO_DRAFT",
                (approved.routed_stage, approved.next_action)
                == (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY),
            )
        )

        drafted = draft_entry(session, ASUS, now=NOW)
        posted = post_simulated(session, ASUS, now=NOW)
        entry_ids = [x["entry_id"] for x in drafted.entries]
        print(f"  drafted {entry_ids} (approved by {drafted.approved_by})")
        print(f"  posted  {posted.model_dump(mode='json')}")
        obligation = session.get(m.TrueUpObligation, ASUS)
        results.append(
            (
                "ASUS entry drafted and posted",
                drafted.approved_by == "controller"
                and obligation.accrual_status == e.AccrualStatus.POSTED_SIMULATED,
            )
        )

        try:
            cw.decide(
                session,
                NOTABILITY,
                e.ControllerDecision.APPROVE,
                now=NOW,
                decided_by=controller,
                notes="Approve it.",
            )
            refused = False
        except cw.DecisionNotAllowedError as exc:
            refused = True
            print(f"\nNotability approve refused: {exc}")
        results.append(("Notability approve is refused", refused))

        asked = cw.decide(
            session,
            NOTABILITY,
            e.ControllerDecision.REQUEST_MORE_EVIDENCE,
            now=NOW,
            decided_by=controller,
            notes="Show the GL entry that expensed the full annual fee.",
        )
        print(f"Notability more evidence -> {asked.routed_stage.value}/{asked.next_action.value}")
        results.append(
            (
                "Notability request more evidence goes to GATHER_EVIDENCE",
                asked.routed_stage == e.WorkflowStage.GATHERING_EVIDENCE,
            )
        )
        remaining = [i.obligation_id for i in cw.review_queue(session, now=NOW)]
        results.append(("queue is empty afterwards", remaining == []))

    print("\nEXPECTED")
    for label, ok in results:
        print(f"  {label:58} [{'hit' if ok else 'MISS'}]")
    hits = sum(ok for _, ok in results)
    print(f"{hits}/{len(results)} expected outcomes matched")


if __name__ == "__main__":
    main()
