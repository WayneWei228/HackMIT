"""The whole December 2026 close, offline: python scripts/run_close.py.

Day one grades the closed history and the Controller approves the escalator rule that replay
proved. At month end the orchestrator detects five obligations and drives each through Invoice
Lookup, Ingestion and Evidence, Classification, Estimation and Policy until it rests. Then the
clock moves through January: OpenAI's reply, reversals, late invoices, reconciliation and learning.
The Controller is a script; the orchestrator approves nothing itself. No language model is used.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from trueup.agents.controller_workspace import controller_id  # noqa: E402
from trueup.close_orchestrator import CloseReport, Step, run_month_end_close  # noqa: E402
from trueup.demo_controller import ScriptedController  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store import models as m  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
ASUS, MINTLIFY, OPENAI, META, NOTABILITY = (
    f"OBL-{name}-{PERIOD}" for name in ("ASUS", "MINTLIFY", "OPENAI", "META", "NOTABILITY")
)


def print_timeline(steps: list[Step]) -> None:
    by_obligation: dict[str | None, list[Step]] = defaultdict(list)
    for step in steps:
        key = step.obligation_id
        if key is not None and "-HIST-" in key:
            key = "closed history"
        by_obligation[key].append(step)
    for key in sorted(by_obligation, key=lambda k: (k is None, k or "")):
        print(f"\n  {key or 'playbook rules'}")
        for s in by_obligation[key]:
            move = f"{s.from_state or ''} -> {s.to_state}" if s.to_state else ""
            print(f"    {s.at:%m-%d %H:%M}  {s.agent:<22} {s.action:<20} {move} {s.note}".rstrip())


def print_table(report: CloseReport) -> None:
    header = (
        f"{'vendor':11} {'accrual':>10} {'invoice':>10} {'variance':>10}  {'cause':18} final stage"
    )
    print(header)
    for o in report.obligations:
        accrual = "-" if o.accrued is None else f"{o.accrued}"
        invoice = "-" if o.invoice is None else f"{o.invoice}"
        variance = "-" if o.variance is None else f"{o.variance}"
        print(
            f"{o.vendor_name:11} {accrual:>10} {invoice:>10} {variance:>10}  "
            f"{o.root_cause or '-':18} {o.workflow_stage.value}"
        )


def snapshot(session) -> dict:
    tables = (
        m.TrueUpObligation,
        m.TrueUpEvidence,
        m.TrueUpWorkpaper,
        m.CompanyGLEntry,
        m.TrueUpLearningRule,
    )
    counts = {t.__tablename__: session.scalar(select(func.count()).select_from(t)) for t in tables}
    states = {
        ob.obligation_id: (ob.workflow_stage, ob.next_action)
        for ob in session.scalars(select(m.TrueUpObligation))
    }
    return {"counts": counts, "states": states}


def main() -> None:
    sim = Simulator.initialize()
    results: list[tuple[str, bool]] = []

    def check(label: str, ok: bool) -> None:
        results.append((label, ok))

    with sim.session() as session:
        controller = ScriptedController(controller_id(session), approve_vendors=["VEN-ASUS"])
        print(f"DAY ONE ({sim.now():%Y-%m-%d}) and MONTH END ({CLOSE:%Y-%m-%d})")
        at_close = run_month_end_close(
            session, PERIOD, now=CLOSE, simulator=sim, controller=controller
        )
        print_timeline(at_close.steps)
        print("\nRESTING STATE AT CLOSE")
        for o in at_close.obligations:
            why = o.rested_because or ""
            amount = "no estimate" if o.accrued is None else f"{o.accrued}"
            print(f"  {o.vendor_name:11} {amount:>11}  {o.workflow_stage.value:26} {why[:90]}")

        print(f"\nJANUARY ({JANUARY:%Y-%m-%d}): the clock moves a day at a time")
        actuals = run_month_end_close(
            session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=JANUARY
        )
        print_timeline(actuals.steps)
        print("\nFINAL TABLE")
        print_table(actuals)
        rule = next((r for r in actuals.rules if r.status == e.LearningStatus.ACTIVE), None)
        if rule:
            print(f"\nRULE {rule.learning_id} {rule.status.value}: {rule.description}")
            print(f"  {rule.stage}, confirmed {rule.uses} time(s) by true-ups")

        before = snapshot(session)
        run_month_end_close(
            session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=JANUARY
        )
        after = snapshot(session)

        close_states = {o.obligation_id: o for o in at_close.obligations}
        all_steps = at_close.steps + actuals.steps
        decisions = [s for s in all_steps if s.action == "decide"]
        rule_approvals = [s for s in all_steps if s.action == "approve_rule"]
        reversals = session.scalar(
            select(func.count())
            .select_from(m.CompanyGLEntry)
            .where(m.CompanyGLEntry.gl_entry_id.like("JE-OBL-%-REV"))
        )
        history_misses = [
            s for s in at_close.steps if "-HIST-" in (s.obligation_id or "") and "MISSED" in s.note
        ]
        mint, oa, asus, meta, note = (
            actuals.outcome(oid) for oid in (MINTLIFY, OPENAI, ASUS, META, NOTABILITY)
        )

        check(
            "day one: three history misses graded MISSED_ESCALATOR and one rule approved",
            len(history_misses) >= 2 and len(rule_approvals) == 1,
        )
        check(
            "Mintlify accrues 1400.00 from the amendment and the January invoice matches",
            mint.accrued == Decimal("1400.00")
            and mint.invoice == Decimal("1400.00")
            and mint.workflow_stage == e.WorkflowStage.CLOSED,
        )
        check(
            "OpenAI has no estimate at close and waits on Outreach for complete usage",
            close_states[OPENAI].accrued is None
            and close_states[OPENAI].workflow_stage == e.WorkflowStage.AWAITING_OUTREACH,
        )
        check(
            "OpenAI accrues 18600.00 after the reply because the taught rule is active",
            oa.accrued == Decimal("18600.00")
            and oa.invoice == Decimal("18600.00")
            and oa.workflow_stage == e.WorkflowStage.CLOSED,
        )
        check(
            "ASUS 32000.00 needs the Controller at close, is approved, and matches in January",
            any(s.obligation_id == ASUS and s.action == "decide" for s in at_close.steps)
            and asus.accrued == Decimal("32000.00")
            and asus.invoice == Decimal("32000.00")
            and asus.workflow_stage == e.WorkflowStage.CLOSED,
        )
        check(
            "Meta's 30000.00 January invoice is flagged SOURCE_DATA_ERROR for the Controller",
            meta.root_cause == "SOURCE_DATA_ERROR"
            and meta.invoice == Decimal("30000.00")
            and meta.workflow_stage == e.WorkflowStage.AWAITING_CONTROLLER
            and META in actuals.controller_queue,
        )
        check(
            "Notability is Blocked by POL-08 and nothing is accrued",
            note.workflow_stage == e.WorkflowStage.BLOCKED
            and note.policy_decision == e.PolicyDecision.BLOCK
            and note.accrual_status == e.AccrualStatus.NOT_STARTED
            and NOTABILITY in actuals.controller_queue,
        )
        check(
            "the orchestrator approved nothing: one Controller decision, one rule approval",
            len(decisions) == 1 and len(rule_approvals) == 1,
        )
        check(
            "four accruals were reversed on 1 January and the rule is confirmed once",
            reversals == 4 and rule is not None and rule.uses == 1,
        )
        check(
            "running the close again changes nothing",
            before == after and not actuals.errors and not at_close.errors,
        )

    print("\nEXPECTED")
    for label, ok in results:
        print(f"  {label:92} [{'hit' if ok else 'MISS'}]")
    hits = sum(ok for _, ok in results)
    print(f"\n{hits}/{len(results)} expected outcomes matched")
    if hits != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
