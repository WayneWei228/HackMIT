"""Audit the December close: python scripts/run_auditor.py.

Builds the six demo cases through the real agents, audits the result, then plants three defects
and shows the Auditor catch each one. Offline: no model and no keys.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json  # noqa: E402

from sqlalchemy import select  # noqa: E402

from trueup.agents import evidence_agent, ingestion  # noqa: E402
from trueup.agents.auditor_agent import AuditReport, Severity, audit  # noqa: E402
from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.controller_workspace import controller_id, decide  # noqa: E402
from trueup.agents.detection_agent import detect  # noqa: E402
from trueup.agents.estimation_agent import estimate  # noqa: E402
from trueup.agents.evidence_agent import DocumentFacts, Fact, FactKey  # noqa: E402
from trueup.agents.invoice_lookup_agent import lookup  # noqa: E402
from trueup.agents.journal_entry_service import (  # noqa: E402
    draft_entry,
    post_due_reversals,
    post_simulated,
)
from trueup.agents.learning_agent import (  # noqa: E402
    approve_rule,
    evaluate,
    record_outcome,
    run_learning_loop,
)
from trueup.agents.outreach_agent import poll_replies, send_outreach  # noqa: E402
from trueup.agents.policy_agent import enforce  # noqa: E402
from trueup.agents.reconciliation_agent import collect_arrivals, reconcile  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store import models as m  # noqa: E402
from trueup.store.workflow import advance  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
OPENAI_REPLY_AT = "2027-01-02T10:00:00Z"
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
OPENAI = "OBL-OPENAI-2026-12"
_DOLLARS = __import__("re").compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")


def first_dollar_line(case, entry, text: str) -> DocumentFacts:
    """A plain offline extractor: the first line of each file that states a dollar amount."""
    for line in text.splitlines():
        found = _DOLLARS.search(line)
        if found:
            return DocumentFacts(
                vendor_name=case.vendor_name,
                service_period=case.period,
                facts=[
                    Fact(
                        key=FactKey.OTHER,
                        label=entry.name,
                        value_text=found.group(0),
                        number=Decimal(found.group(1).replace(",", "")),
                        quote=line.strip(),
                    )
                ],
            )
    return DocumentFacts(vendor_name=case.vendor_name, service_period=case.period, facts=[])


def stage(session, oid: str) -> str:
    ob = session.get(m.TrueUpObligation, oid)
    return f"{ob.workflow_stage.value}/{ob.next_action.value}"


def build_closed_state(sim, session) -> list[str]:
    """Run the December close and January true-up through the public agents."""
    universe = ingestion.load_universe()
    day_one = sim.now()
    run_learning_loop(session, now=day_one)
    candidate = session.scalars(
        select(m.TrueUpLearningRule).where(
            m.TrueUpLearningRule.status == e.LearningStatus.REPLAY_PASSED
        )
    ).one()
    approve_rule(session, candidate.learning_id, decided_by=controller_id(session), now=day_one)

    sim.advance_to(CLOSE)
    opened = detect(session, PERIOD, now=CLOSE).opened
    for oid in opened:
        lookup(session, oid, now=CLOSE)
        ob = session.get(m.TrueUpObligation, oid)
        if (ob.workflow_stage, ob.next_action) == (
            e.WorkflowStage.GATHERING_EVIDENCE,
            e.NextAction.GATHER_EVIDENCE,
        ):
            case_id = "CASE-" + oid.removeprefix("OBL-")
            picked = ingestion.ingest(
                universe, case_id, now=CLOSE, judge=ingestion.rule_judge, session=session
            )
            evidence_agent.collect_evidence(
                universe,
                picked,
                now=CLOSE,
                session=session,
                obligation_id=oid,
                extractor=first_dollar_line,
            )
            # TEMPORARY stand-in for the orchestrator, which will move evidence along.
            advance(
                ob, e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY, "orchestrator", at=CLOSE
            )
        classify(session, oid, now=CLOSE)
        estimate(session, oid, now=CLOSE)

    send_outreach(session, OPENAI, now=CLOSE)
    for oid in opened:
        if stage(session, oid) == "ESTIMATING/VERIFY_POLICY":
            enforce(session, oid, now=CLOSE)
    controller = controller_id(session)
    for oid in opened:
        if stage(session, oid) == "AWAITING_CONTROLLER/CONTROLLER_REVIEW":
            decide(
                session,
                oid,
                e.ControllerDecision.APPROVE,
                now=CLOSE,
                decided_by=controller,
                notes="Reviewed the receipt and the PO; the amount is supported.",
            )
    for oid in opened:
        if stage(session, oid) == "READY_TO_DRAFT/DRAFT_ENTRY":
            draft_entry(session, oid, now=CLOSE)
            post_simulated(session, oid, now=CLOSE)

    sim.advance_to(OPENAI_REPLY_AT)
    reply_at = sim.now()
    poll_replies(
        session, now=reply_at, responder=lambda key, now: sim.reply_to_outreach(key, session)
    )
    estimate(session, OPENAI, now=reply_at)
    enforce(session, OPENAI, now=reply_at)
    draft_entry(session, OPENAI, now=reply_at)
    post_simulated(session, OPENAI, now=reply_at)

    sim.advance_to(JANUARY)
    post_due_reversals(session, now=JANUARY)
    for oid in collect_arrivals(session, now=JANUARY):
        reconcile(session, oid, now=JANUARY)
        if stage(session, oid) == "RECONCILING/EVALUATE_LEARNING":
            evaluate(session, oid, now=JANUARY)
        record_outcome(session, oid, now=JANUARY)
    return opened


def snapshot(session) -> dict[str, list[str]]:
    """Every row of every table except the append-only run log."""
    rows = {}
    for table in m.Base.metadata.sorted_tables:
        if table.name != "trueup_agent_runs":
            found = session.execute(select(table)).all()
            rows[table.name] = sorted(json.dumps([str(v) for v in row]) for row in found)
    return rows


def show(report: AuditReport) -> None:
    tested = sum(c.status.value != "NOT_APPLICABLE" for o in report.obligations for c in o.controls)
    print(f"AUDIT OF {report.period} as of {report.audited_at:%Y-%m-%d}")
    print(f"{len(report.obligations)} obligations, {tested} controls performed")
    print(f"  {report.summary}\n")
    for audited in report.obligations:
        print(f"{audited.obligation_id}  {audited.state}")
        print("  " + "  ".join(f"{c.check_id} {c.status.value}" for c in audited.controls))
        for f in audited.findings:
            print(f"  {f.check_id}  {f.severity.value:8} {f.message}")
    if report.findings and any(f.obligation_id is None for f in report.findings):
        print("Close-wide")
        for f in (f for f in report.findings if f.obligation_id is None):
            print(f"  {f.check_id}  {f.severity.value:8} {f.message}")
    print()


def caught(report: AuditReport, check_id: str, obligation_id: str, needle: str = "") -> bool:
    return any(
        f.check_id == check_id
        and f.obligation_id == obligation_id
        and f.severity == Severity.CRITICAL
        and needle in f.message
        for f in report.findings
    )


def main() -> None:
    sim = Simulator.initialize()
    results: list[tuple[str, bool]] = []
    with sim.session() as session:
        build_closed_state(sim, session)
        session.commit()
        before, runs = snapshot(session), len(session.scalars(select(m.TrueUpAgentRun)).all())

        print("== The December close, audited (January 31) ==\n")
        report = audit(session, now=JANUARY, period=PERIOD)
        show(report)
        session.commit()
        notability = report.for_obligation("OBL-NOTABILITY-2026-12")
        results.append(
            (
                "the close has six obligations and one critical finding: Notability's double count",
                len(report.obligations) == 6 and report.counts["CRITICAL"] == 1,
            )
        )
        results.append(
            (
                "Notability's one-time expense in the seed is a critical AUD-03 double count",
                any(
                    f.check_id == "AUD-03"
                    and f.severity == Severity.CRITICAL
                    and "GL-NOTABILITY-2026-12-MANUAL" in f.message
                    for f in notability.findings
                ),
            )
        )
        rows = len(session.scalars(select(m.TrueUpAgentRun)).all())
        results.append(
            (
                "the audit changed no table and added one run row",
                snapshot(session) == before and rows == runs + 1,
            )
        )

        print("== Defect 1: ASUS amount edited after the Controller approved it ==")
        asus = session.get(m.TrueUpObligation, "OBL-ASUS-2026-12")
        session.get(m.TrueUpWorkpaper, asus.current_workpaper_id).proposed_amount = Decimal(
            "33000.00"
        )
        session.flush()
        planted = audit(session, now=JANUARY, period=PERIOD, persist=False)
        show_new(planted, report)
        results.append(
            (
                "the edited ASUS amount is caught by AUD-02 and AUD-04",
                caught(planted, "AUD-02", asus.obligation_id, "32000.00")
                and caught(planted, "AUD-04", asus.obligation_id, "the Controller approved"),
            )
        )
        session.rollback()

        print("== Defect 2: Mintlify's drafted accrual no longer balances ==")
        mintlify = session.get(m.TrueUpObligation, "OBL-MINTLIFY-2026-12")
        wp = session.get(m.TrueUpWorkpaper, mintlify.current_workpaper_id)
        payload = json.loads(json.dumps(wp.journal_entry_json))
        payload["entries"][0]["lines"][0]["debit"] = "1500.00"
        wp.journal_entry_json = payload
        session.flush()
        planted = audit(session, now=JANUARY, period=PERIOD, persist=False)
        show_new(planted, report)
        results.append(
            (
                "the unbalanced Mintlify entry is caught by AUD-03",
                caught(planted, "AUD-03", mintlify.obligation_id, "is not balanced"),
            )
        )
        session.rollback()

        print("== Defect 3: Notability accrued on top of the one-time expense ==")
        nota = session.get(m.TrueUpObligation, "OBL-NOTABILITY-2026-12")
        wp = session.get(m.TrueUpWorkpaper, nota.current_workpaper_id)
        nota.accrual_status = e.AccrualStatus.POSTED_SIMULATED
        session.add(
            m.CompanyGLEntry(
                gl_entry_id="JE-NOTABILITY-ON-TOP",
                period=PERIOD,
                posting_date=CLOSE.date(),
                vendor_id=nota.vendor_id,
                obligation_id=nota.obligation_id,
                entry_type=e.GLEntryType.ACCRUAL,
                status=e.GLEntryStatus.POSTED,
                description="[Simulated TrueUp posting] planted defect",
                lines_json=[
                    {"account_code": wp.expense_account, "debit": "1800.00", "credit": "0.00"},
                    {
                        "account_code": wp.accrual_liability_account,
                        "debit": "0.00",
                        "credit": "1800.00",
                    },
                ],
                source_workpaper_id=wp.workpaper_id,
                reversal_of_gl_entry_id=None,
                created_at=CLOSE,
            )
        )
        session.flush()
        planted = audit(session, now=JANUARY, period=PERIOD, persist=False)
        show_new(planted, report)
        results.append(
            (
                "Notability's accrual on top of the one-time expense is a critical double count",
                caught(planted, "AUD-03", nota.obligation_id, "double counts"),
            )
        )
        session.rollback()

    print("EXPECTED")
    for label, ok in results:
        print(f"  {label:80} [{'hit' if ok else 'MISS'}]")
    hits = sum(ok for _, ok in results)
    print(f"\n{hits}/{len(results)} expected outcomes matched")
    if hits != len(results):
        sys.exit(1)


def show_new(planted: AuditReport, clean: AuditReport) -> None:
    """Print only what the planted defect added to the clean audit."""
    known = {f.finding_id + f.message for f in clean.findings}
    for f in planted.findings:
        if f.finding_id + f.message not in known:
            who = f.obligation_id or "close-wide"
            print(f"  {f.check_id}  {f.severity.value:8} {who}: {f.message}")
    print()


if __name__ == "__main__":
    main()
