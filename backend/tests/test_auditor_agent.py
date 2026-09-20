"""The Auditor re-performs a real December close and must catch every planted defect.

The closed state is built once through the public agents (see scripts/run_auditor.py). Each test
plants one defect inside the shared session, audits, and rolls back, so every test starts clean.
"""

import importlib.util
import inspect
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text

from trueup.agents import auditor_agent
from trueup.agents.auditor_agent import CHECKS, ControlStatus, Severity, audit
from trueup.gateway import llm
from trueup.learning.rules import CandidateRule
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import AgentRunLog

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_auditor.py"
spec = importlib.util.spec_from_file_location("run_auditor", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

PERIOD = "2026-12"
ASUS = "OBL-ASUS-2026-12"
META = "OBL-META-2026-12"
MINTLIFY = "OBL-MINTLIFY-2026-12"
NOTABILITY = "OBL-NOTABILITY-2026-12"
OPENAI = "OBL-OPENAI-2026-12"
LIVE = [ASUS, META, MINTLIFY, NOTABILITY, OPENAI]
DEC_31 = datetime(2026, 12, 31, 23, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def built():
    sim = Simulator.initialize()
    with sim.session() as session:
        script.build_closed_state(sim, session)
        session.commit()
        yield session


@pytest.fixture
def session(built):
    yield built
    built.rollback()


def run_audit(session, **kwargs):
    return audit(session, now=script.JANUARY, period=PERIOD, persist=False, **kwargs)


def workpaper(session, obligation_id):
    ob = session.get(m.TrueUpObligation, obligation_id)
    return session.get(m.TrueUpWorkpaper, ob.current_workpaper_id)


def edit_inputs(wp, **changes):
    inputs = json.loads(json.dumps(wp.calculation_inputs_json))
    inputs.update(changes)
    wp.calculation_inputs_json = inputs


def critical(report, check_id, obligation_id):
    return [
        f
        for f in report.findings
        if f.check_id == check_id
        and f.obligation_id == obligation_id
        and f.severity == Severity.CRITICAL
    ]


def caught(report, check_id, obligation_id, needle=""):
    return any(needle in f.message for f in critical(report, check_id, obligation_id))


def snapshot(session):
    rows = {}
    for table in m.Base.metadata.sorted_tables:
        if table.name == "trueup_agent_runs":
            continue
        found = session.execute(select(table)).all()
        rows[table.name] = sorted(json.dumps([str(v) for v in row]) for row in found)
    return rows


# --- the clean close ---------------------------------------------------------------------------


def test_a_clean_close_has_no_critical_finding(session):
    report = run_audit(session)
    assert report.counts["CRITICAL"] == 0 and report.passed
    assert sorted(o.obligation_id for o in report.obligations) == LIVE


def test_the_only_open_item_is_notabilitys_seeded_one_time_expense(session):
    report = run_audit(session)
    (finding,) = report.findings
    assert (finding.check_id, finding.obligation_id, finding.severity) == (
        "AUD-03",
        NOTABILITY,
        Severity.WARNING,
    )
    assert "GL-NOTABILITY-2026-12-MANUAL" in finding.message
    assert (finding.expected, finding.actual) == ("1800.00", "21600.00")


def test_every_control_reports_pass_fail_per_obligation(session):
    report = run_audit(session)
    for audited in report.obligations:
        assert [c.check_id for c in audited.controls] == list(CHECKS)
        assert all(c.status != "FAIL" for c in audited.controls)
    asus = report.for_obligation(ASUS)
    assert [c.status.value for c in asus.controls] == ["PASS"] * (len(CHECKS) - 1) + [
        "NOT_APPLICABLE"
    ]
    notability = {c.check_id: c.status.value for c in report.for_obligation(NOTABILITY).controls}
    assert notability["AUD-03"] == "NOTE" and notability["AUD-07"] == "NOT_APPLICABLE"
    assert {c.check_id for c in report.global_controls} == {"AUD-08", "AUD-09"}


def test_the_audit_reads_five_live_obligations_and_no_history(session):
    report = audit(session, now=script.JANUARY, persist=False)
    assert sorted(o.obligation_id for o in report.obligations) == LIVE
    one = audit(session, now=script.JANUARY, obligation_ids=[ASUS], persist=False)
    assert [o.obligation_id for o in one.obligations] == [ASUS]


def test_the_audit_changes_nothing_and_appends_one_run_row(session):
    before, runs = snapshot(session), session.scalars(select(m.TrueUpAgentRun)).all()
    report = audit(session, now=script.JANUARY, period=PERIOD)
    assert snapshot(session) == before
    added = session.scalars(select(m.TrueUpAgentRun)).all()
    assert len(added) == len(runs) + 1
    row = added[-1]
    assert (row.agent_name, row.action, row.obligation_id) == ("auditor", "audit_close", None)
    assert row.run_id == report.run_id and row.status == e.AgentRunStatus.COMPLETED
    assert json.loads(json.dumps(row.facts_used_json[0]))["counts"] == report.counts


def test_a_second_audit_gives_the_same_findings_and_the_auditor_does_not_audit_itself(session):
    first = audit(session, now=script.JANUARY, period=PERIOD)
    second = audit(session, now=script.JANUARY, period=PERIOD)
    assert [f.model_dump() for f in first.findings] == [f.model_dump() for f in second.findings]
    assert first.counts == second.counts and second.run_id != first.run_id


def test_reports_carry_no_floats(session):
    def has_float(value):
        if isinstance(value, float):
            return True
        if isinstance(value, dict):
            return any(has_float(v) for v in value.values())
        if isinstance(value, list):
            return any(has_float(v) for v in value)
        return False

    assert not has_float(json.loads(run_audit(session).model_dump_json()))


# --- AUD-01 evidence traceability --------------------------------------------------------------


def test_aud01_catches_an_edited_quote(session):
    card = session.scalars(
        select(m.TrueUpEvidence).where(m.TrueUpEvidence.evidence_id == "EVD-MINTLIFY-2026-12-01")
    ).one()
    card.source_excerpt = "The monthly fee is $1,999,999 a month"
    session.flush()
    assert caught(run_audit(session), "AUD-01", MINTLIFY, "does not appear verbatim")


def test_aud01_catches_a_deleted_evidence_card(session):
    card = session.get(m.TrueUpEvidence, "EVD-ASUS-2026-12-01")
    session.delete(card)
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-01", ASUS, "EVD-ASUS-2026-12-01")
    control = report.for_obligation(ASUS).controls[0]
    assert (control.check_id, control.status) == ("AUD-01", ControlStatus.FAIL)


def test_aud01_catches_a_card_older_than_its_source_file(session):
    card = session.get(m.TrueUpEvidence, "EVD-META-2026-12-01")
    card.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    session.flush()
    assert caught(run_audit(session), "AUD-01", META, "before its source file")


@pytest.mark.parametrize(
    ("sources", "needle"),
    [
        (["CON-MINTLIFY-V2", "USE-GHOST"], "not in any company table"),
        (["CON-OPENAI-V1"], "different vendor"),
        ([], "cites no source row"),
    ],
)
def test_aud01_catches_bad_source_citations(session, sources, needle):
    edit_inputs(workpaper(session, MINTLIFY), sources=sources)
    session.flush()
    assert caught(run_audit(session), "AUD-01", MINTLIFY, needle)


def test_aud01_catches_an_estimate_that_cites_data_from_the_future(session):
    workpaper(session, META).created_at = datetime(2026, 12, 1, tzinfo=UTC)
    session.flush()
    assert caught(run_audit(session), "AUD-01", META, "did not exist when the estimate")


def cited_card(session, evidence_id, created_at):
    wp = workpaper(session, MINTLIFY)
    base = session.get(m.TrueUpEvidence, "EVD-MINTLIFY-2026-12-01")
    session.add(
        m.TrueUpEvidence(
            evidence_id=evidence_id,
            obligation_id=MINTLIFY,
            evidence_type=e.EvidenceCardType.CONTRACT_TERM,
            source_table="document",
            source_id=base.source_id,
            fact="MONTHLY_FEE: 1400.00",
            value_json={"key": "MONTHLY_FEE", "number": "1400.00"},
            source_excerpt=base.source_excerpt,
            confidence=Decimal("1.00"),
            status=e.EvidenceCardStatus.VERIFIED,
            created_by_agent="evidence",
            created_at=created_at,
        )
    )
    sources = list(wp.calculation_inputs_json.get("sources") or [])
    edit_inputs(wp, sources=[evidence_id] + sources)
    session.flush()
    return wp


def test_aud01_catches_a_card_created_after_the_workpaper(session):
    cited_card(session, "EVD-LATE-01", DEC_31 + timedelta(days=2))
    assert caught(run_audit(session), "AUD-01", MINTLIFY, "card EVD-LATE-01")
    assert caught(run_audit(session), "AUD-01", MINTLIFY, "after the workpaper")


def test_aud01_allows_a_card_created_before_the_workpaper(session):
    wp = workpaper(session, MINTLIFY)
    cited_card(session, "EVD-EARLY-01", wp.created_at - timedelta(days=1))
    report = run_audit(session)
    assert not critical(report, "AUD-01", MINTLIFY)


# --- AUD-02 recomputation ----------------------------------------------------------------------


def test_aud02_catches_an_amount_edited_after_approval(session):
    workpaper(session, ASUS).proposed_amount = Decimal("33000.00")
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-02", ASUS, "give 32000.00, not the recorded amount 33000.00")
    assert caught(report, "AUD-03", ASUS)
    assert caught(report, "AUD-04", ASUS, "the Controller approved")


def test_aud02_catches_a_quantity_that_the_source_row_does_not_support(session):
    edit_inputs(workpaper(session, OPENAI), quantity="830000")
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-02", OPENAI, "cited source row says 930000")
    assert caught(report, "AUD-02", OPENAI, "give 16600.00")


def test_aud02_catches_a_rate_that_is_not_the_contracts(session):
    edit_inputs(workpaper(session, OPENAI), unit_rate="0.03")
    session.flush()
    assert caught(run_audit(session), "AUD-02", OPENAI, "unit_rate")


def test_aud02_catches_a_controller_adjustment_by_anyone_else(session):
    wp = workpaper(session, ASUS)
    edit_inputs(
        wp,
        controller_adjustment={
            "original_amount": "32000.00",
            "adjusted_amount": "32000.00",
            "decided_by": "AP-001",
        },
    )
    session.flush()
    assert caught(
        run_audit(session), "AUD-02", ASUS, "someone other than the configured controller"
    )


# --- AUD-03 journal entries --------------------------------------------------------------------


def test_aud03_catches_an_unbalanced_drafted_entry(session):
    wp = workpaper(session, MINTLIFY)
    payload = json.loads(json.dumps(wp.journal_entry_json))
    payload["entries"][0]["lines"][0]["debit"] = "1500.00"
    wp.journal_entry_json = payload
    session.flush()
    assert caught(run_audit(session), "AUD-03", MINTLIFY, "is not balanced")


def test_aud03_catches_an_unbalanced_ledger_row_that_bypassed_the_orm_guard(session):
    lines = [
        {"account_code": "610100", "debit": "1400.00", "credit": "0.00", "description": "x"},
        {"account_code": "210100", "debit": "0.00", "credit": "1300.00", "description": "x"},
    ]
    session.execute(
        text("UPDATE company_gl_entries SET lines_json = :j WHERE gl_entry_id = :i"),
        {"j": json.dumps(lines), "i": "JE-OBL-MINTLIFY-2026-12-ACC"},
    )
    session.expire_all()
    assert caught(
        run_audit(session), "AUD-03", MINTLIFY, "JE-OBL-MINTLIFY-2026-12-ACC is not balanced"
    )


def test_aud03_catches_a_missing_reversal(session):
    wp = workpaper(session, MINTLIFY)
    payload = json.loads(json.dumps(wp.journal_entry_json))
    payload["entries"] = [x for x in payload["entries"] if x["entry_type"] == "ACCRUAL"]
    wp.journal_entry_json = payload
    session.flush()
    assert caught(run_audit(session), "AUD-03", MINTLIFY, "no reversal")


def test_aud03_catches_an_account_that_is_not_in_the_chart(session):
    workpaper(session, MINTLIFY).expense_account = "999999"
    session.flush()
    assert caught(run_audit(session), "AUD-03", MINTLIFY, "999999")


def test_aud03_catches_a_second_posting_for_one_obligation(session):
    wp = workpaper(session, OPENAI)
    lines = [
        {"account_code": "610200", "debit": "18600.00", "credit": "0.00", "description": "dup"},
        {"account_code": "210100", "debit": "0.00", "credit": "18600.00", "description": "dup"},
    ]
    session.add(
        m.CompanyGLEntry(
            gl_entry_id="JE-DUPLICATE",
            period=PERIOD,
            posting_date=date(2026, 12, 31),
            vendor_id="VEN-OPENAI",
            obligation_id=OPENAI,
            entry_type=e.GLEntryType.ACCRUAL,
            status=e.GLEntryStatus.POSTED,
            description="duplicate",
            lines_json=lines,
            source_workpaper_id=wp.workpaper_id,
            reversal_of_gl_entry_id=None,
            created_at=DEC_31,
        )
    )
    session.flush()
    assert caught(run_audit(session), "AUD-03", OPENAI, "2 accruals are posted")


def test_aud03_calls_a_prepaid_that_was_also_posted_a_double_count(session):
    ob = session.get(m.TrueUpObligation, NOTABILITY)
    wp = workpaper(session, NOTABILITY)
    ob.accrual_status = e.AccrualStatus.POSTED_SIMULATED
    session.add(
        m.CompanyGLEntry(
            gl_entry_id="JE-NOTABILITY-ON-TOP",
            period=PERIOD,
            posting_date=date(2026, 12, 31),
            vendor_id="VEN-NOTABILITY",
            obligation_id=NOTABILITY,
            entry_type=e.GLEntryType.ACCRUAL,
            status=e.GLEntryStatus.POSTED,
            description="on top",
            lines_json=[
                {"account_code": wp.expense_account, "debit": "1800.00", "credit": "0.00"},
                {
                    "account_code": wp.accrual_liability_account,
                    "debit": "0.00",
                    "credit": "1800.00",
                },
            ],
            source_workpaper_id=ob.current_workpaper_id,
            reversal_of_gl_entry_id=None,
            created_at=DEC_31,
        )
    )
    session.flush()
    assert caught(run_audit(session), "AUD-03", NOTABILITY, "double counts")


# --- AUD-04 policy and approvals ---------------------------------------------------------------


def test_aud04_catches_a_forged_policy_decision(session):
    workpaper(session, ASUS).policy_decision = e.PolicyDecision.PERMIT
    session.flush()
    assert caught(
        run_audit(session), "AUD-04", ASUS, "REQUIRE_CONTROLLER (POL-01), not the recorded PERMIT"
    )


def test_aud04_catches_an_approval_with_no_decision_on_record(session):
    workpaper(session, MINTLIFY).controller_decision = e.ControllerDecision.APPROVE
    session.flush()
    assert caught(run_audit(session), "AUD-04", MINTLIFY, "no decision card records it")


def test_aud04_catches_a_forged_controller_decision_card(session):
    wp = workpaper(session, MINTLIFY)
    session.add(
        m.TrueUpEvidence(
            evidence_id="EVD-FORGED-CTL-01",
            obligation_id=MINTLIFY,
            evidence_type=e.EvidenceCardType.CONTROLLER_DECISION,
            source_table="controller",
            source_id="AP-001",
            fact="Controller decision: APPROVE",
            value_json={
                "decision": "APPROVE",
                "decided_by": "AP-001",
                "workpaper_id": wp.workpaper_id,
                "original_amount": "1400.00",
                "adjusted_amount": None,
            },
            source_excerpt=None,
            confidence=Decimal("1.00"),
            status=e.EvidenceCardStatus.VERIFIED,
            created_by_agent="controller_workspace",
            created_at=DEC_31,
        )
    )
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-04", MINTLIFY, "no Controller Workspace run behind it")
    assert caught(report, "AUD-04", MINTLIFY, "not the configured controller")


def test_aud04_catches_an_above_threshold_accrual_whose_approval_was_erased(session):
    card = session.get(m.TrueUpEvidence, "EVD-OBL-ASUS-2026-12-CTL-01")
    session.delete(card)
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-04", ASUS, "needs the Controller's approval")
    assert caught(report, "AUD-01", ASUS, "EVD-OBL-ASUS-2026-12-CTL-01")


def test_aud04_catches_an_approval_of_something_policy_blocked(session):
    wp = workpaper(session, NOTABILITY)
    wp.controller_decision = e.ControllerDecision.APPROVE
    wp.status = e.WorkpaperStatus.APPROVED
    session.flush()
    assert caught(run_audit(session), "AUD-04", NOTABILITY, "Policy blocked this accrual")


# --- AUD-05 workflow integrity -----------------------------------------------------------------


def test_aud05_catches_a_stage_forced_to_closed_by_hand(session):
    ob = session.get(m.TrueUpObligation, NOTABILITY)
    ob.workflow_stage, ob.next_action = e.WorkflowStage.CLOSED, e.NextAction.NONE
    session.flush()
    assert caught(run_audit(session), "AUD-05", NOTABILITY, "without a reconciliation")


def test_aud05_catches_a_state_that_is_not_in_the_workflow(session):
    ob = session.get(m.TrueUpObligation, MINTLIFY)
    ob.workflow_stage, ob.next_action = e.WorkflowStage.CLOSED, e.NextAction.ESTIMATE
    session.flush()
    assert caught(run_audit(session), "AUD-05", MINTLIFY, "is not a state of the workflow")


def test_aud05_catches_an_agent_that_acted_on_a_workpaper_out_of_order(session):
    AgentRunLog(session).append(
        agent_name="policy",
        action="verify_policy",
        status=e.AgentRunStatus.COMPLETED,
        decision_summary="late",
        output_summary="late",
        at=script.JANUARY,
        obligation_id=META,
        workpaper_id=workpaper(session, META).workpaper_id,
    )
    session.flush()
    assert caught(run_audit(session), "AUD-05", META, "verify_policy on WP-OBL-META-2026-12-01")


def test_aud05_catches_a_stage_that_skipped_a_step(session):
    ob = session.get(m.TrueUpObligation, OPENAI)
    ob.workflow_stage, ob.next_action = e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY
    session.flush()
    workpaper(session, OPENAI).status = e.WorkpaperStatus.AWAITING_POLICY
    session.flush()
    assert caught(run_audit(session), "AUD-05", OPENAI, "without an approved workpaper")


# --- AUD-06 cutoff and duplicates --------------------------------------------------------------


def test_aud06_catches_an_invoice_that_was_already_in_ap_when_the_accrual_posted(session):
    session.add(
        m.CompanyAPInvoice(
            invoice_id="INV-MINTLIFY-EARLY",
            vendor_id="VEN-MINTLIFY",
            invoice_number="EARLY-1",
            invoice_date=date(2026, 12, 15),
            received_at=datetime(2026, 12, 20, tzinfo=UTC),
            service_start_date=date(2026, 12, 1),
            service_end_date=date(2026, 12, 31),
            amount=Decimal("1400.00"),
            currency="USD",
            po_id=None,
            contract_id=None,
            status=e.APInvoiceStatus.POSTED,
            duplicate_flag=False,
            credit_flag=False,
            description="Early December invoice",
            line_items_json=None,
            created_at=DEC_31,
            updated_at=DEC_31,
        )
    )
    session.flush()
    assert caught(run_audit(session), "AUD-06", MINTLIFY, "INV-MINTLIFY-EARLY")


def test_aud06_catches_two_obligations_that_accrued_the_same_source(session):
    original = session.get(m.TrueUpObligation, MINTLIFY)
    twin = m.TrueUpObligation(
        **{
            c.name: getattr(original, c.name)
            for c in original.__table__.columns
            if c.name != "obligation_id"
        },
        obligation_id="OBL-MINTLIFY-2026-12-02",
    )
    session.add(twin)
    session.flush()
    session.add(
        m.CompanyGLEntry(
            gl_entry_id="JE-TWIN-ACC",
            period=PERIOD,
            posting_date=date(2026, 12, 31),
            vendor_id="VEN-MINTLIFY",
            obligation_id="OBL-MINTLIFY-2026-12-02",
            entry_type=e.GLEntryType.ACCRUAL,
            status=e.GLEntryStatus.POSTED,
            description="twin",
            lines_json=[
                {"account_code": "610100", "debit": "1400.00", "credit": "0.00"},
                {"account_code": "210100", "debit": "0.00", "credit": "1400.00"},
            ],
            source_workpaper_id=original.current_workpaper_id,
            reversal_of_gl_entry_id=None,
            created_at=DEC_31,
        )
    )
    session.flush()
    assert caught(run_audit(session), "AUD-06", MINTLIFY, "OBL-MINTLIFY-2026-12-02")


# --- AUD-07 reconciliation ---------------------------------------------------------------------


def test_aud07_catches_an_edited_reconciliation_amount(session):
    wp = workpaper(session, OPENAI)
    record = {**wp.calculation_inputs_json["reconciliation"], "actual": "18000.00"}
    edit_inputs(wp, reconciliation=record)
    session.flush()
    assert caught(run_audit(session), "AUD-07", OPENAI, "records actual 18000.00")


def test_aud07_catches_a_diagnosis_that_the_data_does_not_support(session):
    wp = workpaper(session, META)
    record = {**wp.calculation_inputs_json["reconciliation"], "root_cause": None}
    edit_inputs(wp, reconciliation=record)
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-07", META, "Re-diagnosing the variance gives SOURCE_DATA_ERROR")


def test_aud07_catches_an_obligation_closed_over_a_source_data_error(session):
    ob = session.get(m.TrueUpObligation, META)
    ob.workflow_stage, ob.next_action = e.WorkflowStage.CLOSED, e.NextAction.NONE
    session.flush()
    assert caught(run_audit(session), "AUD-07", META, "should route to AWAITING_CONTROLLER")


def test_aud07_catches_a_ledger_accrual_that_differs_from_what_was_reconciled(session):
    lines = [
        {"account_code": "610100", "debit": "1300.00", "credit": "0.00", "description": "x"},
        {"account_code": "210100", "debit": "0.00", "credit": "1300.00", "description": "x"},
    ]
    session.execute(
        text("UPDATE company_gl_entries SET lines_json = :j WHERE gl_entry_id = :i"),
        {"j": json.dumps(lines), "i": "JE-OBL-MINTLIFY-2026-12-ACC"},
    )
    session.expire_all()
    assert caught(run_audit(session), "AUD-07", MINTLIFY, "not the 1400.00 that was reconciled")


# --- AUD-08 learning rules ---------------------------------------------------------------------


def rule_row(session):
    return session.scalars(
        select(m.TrueUpLearningRule).where(m.TrueUpLearningRule.status == e.LearningStatus.ACTIVE)
    ).one()


def test_aud08_catches_an_active_rule_nobody_approved(session):
    wp = workpaper(session, OPENAI)
    session.add(
        m.TrueUpLearningRule(
            learning_id="LRN-FORGED",
            obligation_id=OPENAI,
            workpaper_id=wp.workpaper_id,
            invoice_id=None,
            actual_amount=Decimal("18600.00"),
            accrual_amount=Decimal("14880.00"),
            variance_amount=Decimal("3720.00"),
            variance_percent=None,
            root_cause=e.RootCause.MISSED_ESCALATOR,
            root_cause_summary="forged",
            candidate_rule_json=CandidateRule.apply_contract_escalator().model_dump(mode="json"),
            replay_result_json=None,
            status=e.LearningStatus.ACTIVE,
            approved_by="AP-001",
            created_at=DEC_31,
            updated_at=DEC_31,
        )
    )
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-08", None, "no approval by the configured controller")
    assert caught(report, "AUD-08", None, "no passing replay")


def test_aud08_catches_a_rule_that_names_a_vendor(session):
    row = rule_row(session)
    rule = {**row.candidate_rule_json, "description": "Always step up OpenAI usage rates."}
    row.candidate_rule_json = rule
    session.flush()
    assert caught(run_audit(session), "AUD-08", None, "names a vendor")


def test_aud08_catches_a_contradicted_rule_that_is_still_active(session):
    row = rule_row(session)
    rule = json.loads(json.dumps(row.candidate_rule_json))
    rule["lifecycle"] = {"stage": "PROVISIONAL", "uses": 1, "contradictions": 1}
    row.candidate_rule_json = rule
    session.flush()
    assert caught(run_audit(session), "AUD-08", None, "must have been revoked")


def test_aud08_catches_a_rule_confirmed_too_early(session):
    row = rule_row(session)
    rule = json.loads(json.dumps(row.candidate_rule_json))
    rule["lifecycle"] = {"stage": "CONFIRMED", "uses": 1, "contradictions": 0}
    row.candidate_rule_json = rule
    session.flush()
    assert caught(run_audit(session), "AUD-08", None, "fewer than 3")


def test_aud08_catches_an_estimate_that_used_a_rule_that_was_already_revoked(session):
    row = rule_row(session)
    row.replay_result_json = {
        **row.replay_result_json,
        "revocation": {"by": "learning", "reason": "test", "at": "2026-12-15T00:00:00+00:00"},
    }
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-08", OPENAI, "was not an approved, active rule")
    assert any(f.check_id == "AUD-02" and f.obligation_id == OPENAI for f in report.findings)


def test_aud08_catches_a_step_up_with_no_rule_behind_it(session):
    edit_inputs(workpaper(session, OPENAI), rules_applied=[])
    session.flush()
    assert caught(run_audit(session), "AUD-08", OPENAI, "without any approved rule")


# --- AUD-09 completeness -----------------------------------------------------------------------


def test_aud09_catches_an_obligation_that_was_deleted(session):
    session.delete(session.get(m.TrueUpObligation, MINTLIFY))
    session.flush()
    report = run_audit(session)
    assert caught(report, "AUD-09", None, "CON-MINTLIFY")
    assert caught(report, "AUD-09", None, "OBL-MINTLIFY-2026-12 was opened by Detection")


def test_aud09_catches_a_failed_run_nobody_resolved(session):
    AgentRunLog(session).append(
        agent_name="estimation",
        action="estimate_accrual",
        status=e.AgentRunStatus.FAILED,
        decision_summary="boom",
        output_summary="boom",
        at=script.JANUARY,
        obligation_id=OPENAI,
    )
    session.flush()
    assert caught(run_audit(session), "AUD-09", OPENAI, "failed at estimate_accrual")


def test_aud09_warns_about_an_obligation_that_was_detected_and_never_started(session):
    ob = session.get(m.TrueUpObligation, NOTABILITY)
    ob.workflow_stage, ob.next_action = e.WorkflowStage.DETECTED, e.NextAction.SEARCH_AP
    session.flush()
    report = run_audit(session)
    assert any(
        f.check_id == "AUD-09"
        and f.severity == Severity.WARNING
        and "no agent has started it" in f.message
        for f in report.findings
    )


# --- the summary --------------------------------------------------------------------------------


def test_the_summary_is_a_template_with_no_model(session):
    report = run_audit(session)
    assert report.summary_source == "template"
    assert "5 obligations" in report.summary and "No critical findings" in report.summary


def test_the_summary_names_the_failing_controls(session):
    workpaper(session, ASUS).proposed_amount = Decimal("33000.00")
    session.flush()
    report = run_audit(session)
    assert "AUD-02 on OBL-ASUS-2026-12" in report.summary


def test_a_model_summary_is_used_when_it_adds_no_number(session):
    def narrator(facts):
        return f"The close held up across {facts['obligations_tested']} obligations."

    report = run_audit(session, narrator=narrator)
    assert report.summary_source == "llm" and report.summary_note is None


def test_a_model_summary_with_an_invented_number_is_refused(session):
    report = run_audit(session, narrator=lambda facts: "The close missed 99 controls.")
    assert report.summary_source == "template"
    assert "numbers not in the facts: 99" in report.summary_note


def test_a_failing_model_falls_back_to_the_template(session):
    def broken(facts):
        raise llm.LLMError("down")

    report = run_audit(session, narrator=broken)
    assert report.summary_source == "template" and "down" in report.summary_note


def test_the_narrator_only_sees_facts_and_no_answer_key(session):
    seen = {}

    def narrator(facts):
        seen.update(facts)
        return "Nothing to add."

    run_audit(session, narrator=narrator)
    assert set(seen) == {"period", "obligations_tested", "findings_by_severity", "findings"}


# --- boundaries ---------------------------------------------------------------------------------


def test_a_control_that_cannot_run_is_a_failure_not_a_pass(session, monkeypatch):
    def boom(world, case, rec):
        raise RuntimeError("bad record")

    monkeypatch.setattr(auditor_agent, "_OBLIGATION_CONTROLS", [("AUD-05", boom)])
    report = run_audit(session)
    assert caught(report, "AUD-05", ASUS, "could not be performed")
    assert not report.passed


def test_the_auditor_never_reads_the_answer_keys_or_names_a_vendor():
    source = inspect.getsource(auditor_agent)
    for forbidden in (
        "relevance_truth",
        "historical_truth",
        "RelevanceTruth",
        "simulator.files",
        "stand_in",
        "scoring",
        "VEN-",
        "Mintlify",
        "OpenAI",
        "Notability",
        "ASUS",
    ):
        assert forbidden not in source
    assert "seed_dir" in source and "read_text" in source


def test_the_auditor_writes_only_to_the_run_log():
    source = inspect.getsource(auditor_agent)
    for write in ("session.add(", "session.delete(", "session.merge(", ".commit(", "advance("):
        assert write not in source
