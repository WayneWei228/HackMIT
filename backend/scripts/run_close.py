"""The whole December 2026 close, offline: python scripts/run_close.py.

Day one grades the closed history and the Controller approves the escalator rule that replay
proved. At month end the orchestrator detects five obligations and drives each through Invoice
Lookup, Ingestion and Evidence, Classification, Estimation and Policy until it rests. Then the
clock moves through January: OpenAI's reply, reversals, late invoices, reconciliation and learning.
The Controller is a script; the orchestrator approves nothing itself. No language model is used.
"""

from __future__ import annotations

import dataclasses
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from trueup.agents import fallback_estimation  # noqa: E402
from trueup.agents.controller_workspace import controller_id  # noqa: E402
from trueup.close_orchestrator import CloseReport, Step, run_month_end_close  # noqa: E402
from trueup.demo_controller import ScriptedController  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store import models as m  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
VENDOR_REPLY = datetime(2027, 2, 4, tzinfo=UTC)
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


def cause(o) -> str:
    if o.root_cause:
        return o.root_cause
    return f"{o.resolved_root_cause} (fixed)" if o.resolved_root_cause else "-"


def print_table(report: CloseReport) -> None:
    header = (
        f"{'vendor':11} {'accrual':>10} {'invoice':>10} {'variance':>10}  {'cause':26} final stage"
    )
    print(header)
    for o in report.obligations:
        accrual = "-" if o.accrued is None else f"{o.accrued}"
        invoice = "-" if o.invoice is None else f"{o.invoice}"
        variance = "-" if o.variance is None else f"{o.variance}"
        print(
            f"{o.vendor_name:11} {accrual:>10} {invoice:>10} {variance:>10}  "
            f"{cause(o):26} {o.workflow_stage.value}"
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


def openai_road(*, reply: bool, taught: bool):
    """One close where OpenAI's owner does or does not reply and the escalator rule is or is not
    approved on day one. Without a reply the company's wait passes and the fallback estimates."""
    sim = Simulator.initialize()
    if not reply:
        sim.reply_to_outreach = lambda *args, **kwargs: None
    with sim.session() as session:
        controller = ScriptedController(
            controller_id(session), approve_vendors=["VEN-OPENAI"], approve_rules=taught
        )
        run_month_end_close(session, PERIOD, now=CLOSE, simulator=sim, controller=controller)
        report = run_month_end_close(
            session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=JANUARY
        )
        return report.outcome(OPENAI)


ASUS_B = f"OBL-ASUS-{PERIOD}-02"
ASUS_ROADS = {
    (True, True): ("32000.00", "OWNER_CONFIRMED_QUANTITY"),
    (False, True): ("32000.00", "TYPICAL_ORDER_AVERAGE"),
    (False, False): ("19200.00", "CONSERVATIVE_ESTIMATE"),
}


def asus_road(*, reply: bool, history: bool):
    """The receipt-less ASUS order: the owner replies, or no reply comes and the estimate uses
    the vendor's earlier receipts (or, with none on record, the policy's conservative share)."""
    sim = Simulator.initialize()
    if not reply:
        sim.reply_to_outreach = lambda *args, **kwargs: None
    original = fallback_estimation.receipt_facts
    if not history:
        fallback_estimation.receipt_facts = lambda *a, **k: dataclasses.replace(
            original(*a, **k), history=()
        )
    try:
        with sim.session() as session:
            controller = ScriptedController(controller_id(session), approve_vendors=["VEN-ASUS"])
            run_month_end_close(session, PERIOD, now=CLOSE, simulator=sim, controller=controller)
            report = run_month_end_close(
                session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=JANUARY
            )
            ob = session.get(m.TrueUpObligation, ASUS_B)
            inputs = session.get(m.TrueUpWorkpaper, ob.current_workpaper_id).calculation_inputs_json
            return report.outcome(ASUS_B), inputs
    finally:
        fallback_estimation.receipt_facts = original


def asus_road_ok(result, reply: bool, history: bool) -> bool:
    outcome, inputs = result
    accrued, marker = ASUS_ROADS[(reply, history)]
    found = inputs.get("evidence_basis") if reply else inputs["fallback"]["method"]
    return (
        outcome.accrued == Decimal(accrued)
        and found == marker
        and "25" != inputs["received_quantity"]
    )


ROADS = {
    (True, False): ("14880.00", "18600.00", "MISSED_ESCALATOR"),
    (False, True): ("18795.79", "18600.00", "INCOMPLETE_DATA_EXTRAPOLATION"),
    (False, False): ("15036.63", "18600.00", "INCOMPLETE_DATA_EXTRAPOLATION"),
}


def road_label(reply: bool, taught: bool) -> str:
    accrued, _, cause_ = ROADS[(reply, taught)]
    how = "the owner replies" if reply else "no reply comes and the projection is used"
    rule = "the rule is approved" if taught else "the rule is not approved"
    return f"OpenAI: {how}, {rule}: accrues {accrued}, graded {cause_}"


def road_ok(outcome, reply: bool, taught: bool) -> bool:
    accrued, invoice, cause_ = ROADS[(reply, taught)]
    return (
        outcome.accrued == Decimal(accrued)
        and outcome.invoice == Decimal(invoice)
        and (outcome.root_cause or outcome.resolved_root_cause) == cause_
    )


def main() -> None:
    sim = Simulator.initialize()
    results: list[tuple[str, bool]] = []

    def check(label: str, ok: bool) -> None:
        results.append((label, ok))

    with sim.session() as session:
        controller = ScriptedController(
            controller_id(session), approve_vendors=["VEN-ASUS"], dispute_vendors=["VEN-META"]
        )
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

        print(
            f"\nJANUARY AND THE VENDOR'S REPLY (through {VENDOR_REPLY:%Y-%m-%d}): "
            "the clock moves a day at a time"
        )
        actuals = run_month_end_close(
            session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=VENDOR_REPLY
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
            session, PERIOD, now=CLOSE, simulator=sim, controller=controller, through=VENDOR_REPLY
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
        dispute_sent = [
            s for s in actuals.steps if s.obligation_id == META and "INVOICE_DISPUTE" in s.note
        ]
        vendor_reply = [
            s
            for s in actuals.steps
            if s.obligation_id == META and s.action == "process_reply" and s.note == "resolved"
        ]
        check(
            "Meta's 30000.00 invoice is flagged, the Controller raises it, the vendor's email "
            "answers and the corrected 24700.00 invoice closes it at zero variance",
            meta.resolved_root_cause == "SOURCE_DATA_ERROR"
            and meta.invoice == Decimal("24700.00")
            and meta.variance == Decimal("0.00")
            and meta.workflow_stage == e.WorkflowStage.CLOSED
            and len(dispute_sent) == 1
            and len(vendor_reply) == 1
            and META not in actuals.controller_queue,
        )
        check(
            "Notability proposes 1800.00 and waits for the Controller, who can approve it",
            note.policy_decision == e.PolicyDecision.REQUIRE_CONTROLLER
            and note.workflow_stage == e.WorkflowStage.AWAITING_CONTROLLER
            and note.accrual_status == e.AccrualStatus.PENDING_APPROVAL
            and NOTABILITY in actuals.controller_queue,
        )
        no_receipt_close = at_close.outcome(ASUS_B)
        no_receipt = actuals.outcome(ASUS_B)
        check(
            "ASUS with the goods receipt missing waits for its owner at close, then accrues "
            "32000.00 on the owner's confirmed count and never on the 25 ordered",
            no_receipt_close.accrued is None
            and no_receipt_close.workflow_stage == e.WorkflowStage.AWAITING_OUTREACH
            and no_receipt.accrued == Decimal("32000.00")
            and no_receipt.workflow_stage == e.WorkflowStage.AWAITING_ACTUAL_INVOICE,
        )
        check(
            "the orchestrator approved nothing: three Controller decisions, one rule approval",
            len(decisions) == 3 and len(rule_approvals) == 1,
        )
        check(
            "five accruals were reversed and the rule is confirmed once",
            reversals == 5 and rule is not None and rule.uses == 1,
        )
        check(
            "running the close again changes nothing",
            before == after and not actuals.errors and not at_close.errors,
        )

    print("\nOPENAI'S THREE OTHER ROADS (fresh closes, only OpenAI decided by the Controller)")
    for reply, taught in ((True, False), (False, True), (False, False)):
        outcome = openai_road(reply=reply, taught=taught)
        print(
            f"  reply={str(reply):5} rule={str(taught):5} accrued {outcome.accrued} "
            f"invoiced {outcome.invoice} variance {outcome.variance} "
            f"{outcome.root_cause or outcome.resolved_root_cause or '-'}"
        )
        results.append((road_label(reply, taught), road_ok(outcome, reply, taught)))

    print("\nASUS WITH THE GOODS RECEIPT MISSING (fresh closes, the Controller approves ASUS)")
    for reply, history in ASUS_ROADS:
        result = asus_road(reply=reply, history=history)
        how = "the owner replies" if reply else "no reply comes"
        past = (
            "" if reply else (", earlier receipts on record" if history else ", no earlier receipt")
        )
        accrued, marker = ASUS_ROADS[(reply, history)]
        print(f"  {how}{past}: accrued {result[0].accrued} by {marker}")
        results.append(
            (
                f"ASUS receipt-less: {how}{past}: accrues {accrued} by {marker}",
                asus_road_ok(result, reply, history),
            )
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
