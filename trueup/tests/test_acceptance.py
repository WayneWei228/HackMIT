"""The eighteen acceptance criteria from the specification, in order.

Each test is named for the criterion it covers so a reviewer can map the suite to
the spec without reading the bodies.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import session_scope
from app.models import (
    CompanyApInvoice,
    CompanyGlEntry,
    CompanyNonPoSpend,
    TrueupEvidence,
    TrueupLearningRule,
    TrueupObligation,
    TrueupWorkpaper,
)
from app.money import money
from app.repositories.rules import active_rules
from app.services import controller, journal
from app.services.agents import auditor, detection, learning, reconciliation
from app.services.learning.improvements import generate
from app.services.orchestrator import run_close
from app.services.simulator.backtest import close_and_grade, run_calibration
from app.services.simulator.clock import close_cutoff

LIVE = "2026-12"


def _ob(session, vendor_id, period=LIVE):
    return session.scalars(
        select(TrueupObligation).where(
            TrueupObligation.vendor_id == vendor_id, TrueupObligation.period == period
        )
    ).first()


# --- 1 ----------------------------------------------------------------------
def test_01_close_creates_obligations_for_po_contract_and_non_po(session):
    obs = detection.run(session, LIVE)
    kinds = {o.purchase_type for o in obs}
    assert {"FIXED_RECURRING", "USAGE_BASED", "RECEIPT_BASED", "MILESTONE_BASED"} <= kinds
    assert any(o.non_po_group_key for o in obs), "no non-PO spend obligation was opened"
    assert all(o.contract_id or o.po_id or o.non_po_group_key for o in obs)


# --- 2 ----------------------------------------------------------------------
def test_02_existing_ap_invoice_prevents_duplicate_accrual(session):
    run_close(session, LIVE)
    # Twilio invoices before the cutoff, so its obligation must close NO_ACCRUAL.
    twilio = _ob(session, "V007")
    assert twilio.invoice_status == "FOUND"
    assert twilio.accrual_status == "NO_ACCRUAL"
    assert twilio.matched_invoice_id is not None
    posted = session.scalars(
        select(CompanyGlEntry).where(CompanyGlEntry.obligation_id == twilio.obligation_id)
    ).all()
    assert posted == [], "an accrual was posted despite AP already holding the invoice"


# --- 3 ----------------------------------------------------------------------
def test_03_fixed_recurring_uses_effective_contract_version(session):
    run_close(session, LIVE)
    ob = _ob(session, "V001")
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    assert wp.estimation_method == "FIXED_CONTRACT_RATE"
    assert money(wp.proposed_amount) == money("1200.00")   # matches CTR-001 / INV-MINTLIFY-DEC
    ev = session.scalars(
        select(TrueupEvidence).where(
            TrueupEvidence.obligation_id == ob.obligation_id,
            TrueupEvidence.evidence_type == "CONTRACT_VERSION",
        )
    ).first()
    assert ev is not None and "overlap" in ev.fact.lower()


def test_03b_contract_version_selected_by_date_not_by_active_status(session):
    """Snowflake has two ACTIVE versions; a June close must pick v1, not the latest."""
    from app.repositories.contracts import effective_version

    v = effective_version(session, "CTR-005", dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    assert v.contract_version == 1
    v2 = effective_version(session, "CTR-005", dt.date(2026, 8, 1), dt.date(2026, 8, 31))
    assert v2.contract_version == 2


# --- 4 ----------------------------------------------------------------------
def test_04_usage_accrual_is_quantity_times_rate(session):
    run_close(session, LIVE)
    ob = _ob(session, "V002")
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    assert wp.estimation_method == "USAGE_TIMES_RATE"
    # 930,000 API units x $0.02 - the figure the December usage report states.
    assert money(wp.proposed_amount) == money("18600.00")
    assert "930000" in wp.calculation_expression


# --- 5 ----------------------------------------------------------------------
def test_05_receipt_accrual_uses_received_minus_billed(session):
    run_close(session, LIVE)
    ob = _ob(session, "V003")
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    assert wp.estimation_method == "RECEIVED_QUANTITY_TIMES_PRICE"
    # 20 of 25 accepted x $1,600 - the five open units must NOT be accrued.
    assert money(wp.proposed_amount) == money("32000.00")


def test_05b_milestone_accrues_delivered_not_budget(session):
    run_close(session, LIVE)
    wp = session.get(TrueupWorkpaper, _ob(session, "V004").current_workpaper_id)
    assert money(wp.proposed_amount) == money("24700.00")   # not the $30,000 budget


# --- 6 ----------------------------------------------------------------------
def test_06_non_po_accrual_excludes_voided_disputed_and_ap_linked(session):
    run_close(session, LIVE)
    obs = [o for o in session.scalars(select(TrueupObligation).where(
        TrueupObligation.period == LIVE)) if o.non_po_group_key]
    assert obs
    included, excluded_reasons = set(), set()
    for o in obs:
        wp = session.get(TrueupWorkpaper, o.current_workpaper_id)
        inputs = wp.calculation_inputs_json
        included |= {i["id"] for i in inputs.get("included", [])}
        excluded_reasons |= {e["reason"] for e in inputs.get("excluded", [])}

    rows = {r.non_po_spend_id: r for r in session.scalars(
        select(CompanyNonPoSpend).where(CompanyNonPoSpend.month == LIVE))}
    for tid, r in rows.items():
        if r.transaction_status == "VOIDED":
            assert tid not in included, "a voided charge was accrued"
        if r.transaction_status == "DISPUTED":
            assert tid not in included, "a disputed charge was auto-accrued"
        if r.ap_invoice_id:
            assert tid not in included, "a charge already in AP was accrued again"
    # The refund reduces rather than inflates the accrual.
    refunds = [r for r in rows.values() if r.transaction_status == "REFUND"]
    assert refunds and money(refunds[0].amount) < 0


# --- 7 ----------------------------------------------------------------------
def test_07_classification_disagreement_is_recorded_as_contradiction(session):
    """When the model disagrees with the structured fields, the deterministic
    answer stands AND the disagreement is written to the record."""
    from app.services.agents import classification
    from app.services.llm import get_llm, set_llm

    class Contrarian:
        name = "contrarian"

        def classify_purchase_type(self, description, context):
            return {"purchase_type": "MILESTONE_BASED", "confidence": 0.95,
                    "reason": "stub deliberately disagrees"}

        def __getattr__(self, item):
            from app.services.llm.stub import StubLLM
            return getattr(StubLLM(), item)

    detection.run(session, LIVE)
    ob = _ob(session, "V002")
    original = get_llm()
    try:
        set_llm(Contrarian())
        classification.run(session, ob.obligation_id)
    finally:
        set_llm(original)

    ob = _ob(session, "V002")
    assert ob.purchase_type == "USAGE_BASED", "the LLM overrode the deterministic classifier"
    conflict = session.scalars(select(TrueupEvidence).where(
        TrueupEvidence.obligation_id == ob.obligation_id,
        TrueupEvidence.evidence_type == "CLASSIFICATION_CONFLICT")).first()
    assert conflict is not None
    assert "MILESTONE_BASED" in conflict.fact


# --- 8 ----------------------------------------------------------------------
def test_08_every_workpaper_carries_formula_inputs_evidence_and_entry(session):
    run_close(session, LIVE)
    wps = session.scalars(select(TrueupWorkpaper).where(TrueupWorkpaper.period == LIVE)).all()
    assert wps
    for wp in wps:
        assert wp.calculation_expression, f"{wp.workpaper_id} has no formula"
        assert wp.calculation_inputs_json, f"{wp.workpaper_id} has no inputs"
        assert wp.calculation_inputs_json.get("evidence_ids"), f"{wp.workpaper_id} cites no evidence"
        lines = wp.journal_entry_json["lines"]
        assert len(lines) == 2
        assert sum(money(l["debit"]) for l in lines) == sum(money(l["credit"]) for l in lines)


# --- 9 ----------------------------------------------------------------------
def test_09_policy_blocks_unbalanced_unsupported_and_duplicate_postings(session):
    run_close(session, LIVE)
    ob = _ob(session, "V001")
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)

    # unbalanced
    bad = dict(wp.journal_entry_json)
    bad["lines"] = [dict(bad["lines"][0]), dict(bad["lines"][1])]
    bad["lines"][0]["debit"] = "999999.00"
    wp.journal_entry_json = bad
    session.flush()
    with pytest.raises(journal.PostingRefused, match="balance"):
        journal.post(session, wp.workpaper_id)

    # duplicate: restore a balanced entry; the accrual is already posted
    good = dict(bad)
    good["lines"] = [dict(l) for l in bad["lines"]]
    good["lines"][0]["debit"] = str(money(wp.proposed_amount))
    wp.journal_entry_json = good
    session.flush()
    with pytest.raises(journal.PostingRefused, match="already posted"):
        journal.post(session, wp.workpaper_id)


def test_09b_policy_blocks_posting_into_a_closed_period(session):
    from app.models import CompanyConfig

    run_close(session, LIVE)
    cfg = session.get(CompanyConfig, "accounting_periods")
    periods = dict(cfg.config_value_json)
    periods[LIVE] = {**periods[LIVE], "status": "CLOSED"}
    cfg.config_value_json = periods
    session.flush()

    ob = _ob(session, "V002")
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    wp.status = "APPROVED"
    session.flush()
    with pytest.raises(journal.PostingRefused, match="closed"):
        journal.post(session, wp.workpaper_id)


def test_09c_unsupported_estimate_is_never_posted(session):
    """No usage, no rate, no amount. The system must refuse rather than guess."""
    from app.models import CompanyServiceEvidence
    from app.services.agents import classification, estimation, evidence, invoice_lookup
    from app.services.policy import enforcer

    for r in session.scalars(select(CompanyServiceEvidence).where(
            CompanyServiceEvidence.vendor_id == "V009")):
        session.delete(r)
    for r in session.scalars(select(CompanyApInvoice).where(
            CompanyApInvoice.vendor_id == "V009")):
        session.delete(r)
    session.flush()

    detection.run(session, LIVE)
    ob = _ob(session, "V009")
    for step in (invoice_lookup, evidence, classification):
        step.run(session, ob.obligation_id)
    wp = estimation.run(session, ob.obligation_id)
    assert wp.calculation_inputs_json["supported"] is False
    enforcer.run(session, wp.workpaper_id)
    assert wp.policy_decision in ("REQUIRE_OUTREACH", "REQUIRE_CONTROLLER", "BLOCK")
    assert wp.status != "POSTED"


# --- 10 ---------------------------------------------------------------------
def test_10_controller_approval_enables_posting(session):
    from app.services.agents import classification, estimation, evidence, invoice_lookup
    from app.services.policy import enforcer

    detection.run(session, LIVE)
    ob = _ob(session, "V003")      # $32,000, above the Controller threshold
    for step in (invoice_lookup, evidence, classification):
        step.run(session, ob.obligation_id)
    wp = estimation.run(session, ob.obligation_id)
    enforcer.run(session, wp.workpaper_id)

    assert wp.policy_decision == "REQUIRE_CONTROLLER"
    with pytest.raises(journal.PostingRefused, match="Controller"):
        journal.post(session, wp.workpaper_id)

    controller.decide(session, ob.obligation_id, "APPROVE", notes="Receipt verified")
    entry = journal.post(session, wp.workpaper_id)
    assert entry.status == "POSTED_SIMULATED"
    assert session.get(TrueupWorkpaper, wp.workpaper_id).status == "POSTED"


def test_10b_controller_adjustment_rebalances_the_entry(session):
    run_close(session, LIVE)
    ob = _ob(session, "V001")
    wp = controller.decide(session, ob.obligation_id, "APPROVE_WITH_ADJUSTMENT",
                           adjusted_amount="1500.00", notes="Mid-month upgrade")
    assert money(wp.proposed_amount) == money("1500.00")
    lines = wp.journal_entry_json["lines"]
    assert sum(money(l["debit"]) for l in lines) == sum(money(l["credit"]) for l in lines)
    assert money(lines[0]["debit"]) == money("1500.00")


# --- 11 ---------------------------------------------------------------------
def test_11_later_invoice_triggers_true_up_with_correct_variance(session):
    run_close(session, LIVE)
    ob = _ob(session, "V005")                      # Snowflake: escalator in force
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    accrued = money(wp.proposed_amount)

    inv = session.scalars(select(CompanyApInvoice).where(
        CompanyApInvoice.vendor_id == "V005",
        CompanyApInvoice.service_start_date == ob.service_start_date)).first()
    assert inv.received_at > close_cutoff(LIVE), "the invoice was not actually late"

    lrs = reconciliation.run(session, inv.invoice_id)
    assert len(lrs) == 1
    lr = lrs[0]
    assert money(lr.actual_amount) == money(inv.amount)
    assert money(lr.variance_amount) == money(money(inv.amount) - accrued)
    assert lr.root_cause == "MISSED_ESCALATOR"

    trueup = session.scalars(select(CompanyGlEntry).where(
        CompanyGlEntry.obligation_id == ob.obligation_id,
        CompanyGlEntry.entry_type == "TRUE_UP")).first()
    assert trueup is not None
    d = sum(money(l["debit"]) for l in trueup.lines_json)
    c = sum(money(l["credit"]) for l in trueup.lines_json)
    assert d == c and d == abs(money(lr.variance_amount))


def test_11b_unexplainable_variance_is_labelled_unknown(session):
    """The AWS reserved-capacity surprise: metered usage reconciles exactly, so
    nothing on the record explains the difference. It must not be relabelled."""
    close_and_grade(session, "2026-08")
    lr = session.scalars(select(TrueupLearningRule).where(
        TrueupLearningRule.root_cause == "UNKNOWN")).all()
    aws = [x for x in lr if session.get(TrueupObligation, x.obligation_id).vendor_id == "V009"]
    assert aws, "the unexplainable case was explained away"
    assert money(aws[0].variance_amount) == money("12400.00")


# --- 12 ---------------------------------------------------------------------
def test_12_learning_agent_proposes_a_restricted_typed_rule(session):
    for p in ("2026-07", "2026-08", "2026-09"):
        close_and_grade(session, p)
    esc = [lr for lr in session.scalars(select(TrueupLearningRule))
           if lr.root_cause == "MISSED_ESCALATOR"]
    assert len(esc) >= 2
    lr = learning.run(session, esc[0].learning_id)
    assert lr.candidate_rule_json is not None

    from app.schemas.rules import CandidateRule

    cand = CandidateRule.model_validate(lr.candidate_rule_json)
    cand.validate_allowed()
    assert cand.action.action_type in (
        "REQUIRE_EVIDENCE", "PROHIBIT_ESTIMATOR", "SELECT_ESTIMATOR",
        "REQUIRE_OUTREACH", "REQUIRE_CONTROLLER")
    assert not cand.scope.vendor_ids, "the rule named specific vendors"


def test_12b_forbidden_rule_shapes_are_rejected(session):
    """Every prohibition in the spec, enforced deterministically."""
    from app.schemas.rules import (
        CandidateRule, RuleAction, RuleScope, RuleViolation, parse_candidate,
    )

    def make(**over):
        base = dict(rule_key="k", title="t", rationale="r",
                    scope=RuleScope(purchase_types=["USAGE_BASED"], conditions=["ALWAYS"]),
                    action=RuleAction(action_type="REQUIRE_CONTROLLER"))
        base.update(over)
        return CandidateRule(**base)

    for key, value, label in [
        ("amount", "500.00", "sets a dollar amount"),
        ("approval_threshold", "999999", "weakens an approval threshold"),
        ("auto_post", True, "auto-posts"),
        ("override_block", True, "overrides a blocking control"),
        ("accounting_policy", "CASH", "changes accounting policy"),
    ]:
        d = make().model_dump()
        d["action"][key] = value
        with pytest.raises(RuleViolation, match="FORBIDDEN"):
            parse_candidate(d)

    # vendor-specific shortcut
    with pytest.raises(Exception):
        RuleScope(vendor_ids=["V005"])

    # unbounded scope
    with pytest.raises(RuleViolation, match="unbounded"):
        CandidateRule(rule_key="k", title="t", rationale="r",
                      scope=RuleScope(conditions=["ALWAYS"]),
                      action=RuleAction(action_type="REQUIRE_CONTROLLER")).validate_allowed()


# --- 13 ---------------------------------------------------------------------
def test_13_replay_blocks_a_rule_that_causes_a_regression(session):
    """An over-broad rule that fires on vendors with no escalator would change
    cases it has no business touching. Replay must refuse it."""
    from app.schemas.rules import CandidateRule, RuleAction, RuleScope
    from app.services.learning.replay import replay

    for p in ("2026-09", "2026-10", "2026-11"):
        close_and_grade(session, p)

    over_broad = CandidateRule(
        rule_key="prohibit_usage_estimator_everywhere",
        title="Never use the usage estimator",
        rationale="Deliberately over-broad candidate used to prove replay rejects regressions.",
        scope=RuleScope(purchase_types=["USAGE_BASED"], conditions=["ALWAYS"]),
        action=RuleAction(action_type="PROHIBIT_ESTIMATOR", estimator="USAGE_TIMES_RATE"),
    )
    result = replay(session, over_broad, "TEST")
    assert result["verdict"] == "FAIL"
    assert result["regression_count"] > 0

    lr = session.scalars(select(TrueupLearningRule)).first()
    lr.candidate_rule_json = over_broad.model_dump()
    lr.replay_result_json = result
    lr.status = "REPLAY_FAILED"
    session.flush()
    with pytest.raises(ValueError, match="REPLAY_PASSED"):
        controller.decide_rule(session, lr.learning_id, "APPROVE_RULE")


def test_13b_a_rule_that_never_fires_is_rejected(session):
    from app.schemas.rules import CandidateRule, RuleAction, RuleScope
    from app.services.learning.replay import replay

    close_and_grade(session, "2026-09")
    inert = CandidateRule(
        rule_key="inert", title="Never fires", rationale="No case satisfies this scope.",
        scope=RuleScope(purchase_types=["MILESTONE_BASED"], conditions=["USAGE_EVIDENCE_PRESENT"]),
        action=RuleAction(action_type="REQUIRE_CONTROLLER"),
    )
    result = replay(session, inert, "TEST")
    assert result["verdict"] == "FAIL"
    assert "never fired" in result["verdict_reason"]


# --- 14 ---------------------------------------------------------------------
def test_14_controller_approval_activates_a_passing_rule(session):
    cal = run_calibration(session, ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11"])
    assert cal["rules_activated"], "no rule reached activation"
    rules = active_rules(session)
    assert len(rules) >= 1
    assert all(r.approved_by for r in rules)
    row = session.get(TrueupLearningRule, rules[0].learning_id)
    assert row.status == "ACTIVE"
    assert row.replay_result_json["verdict"] == "PASS"
    assert row.replay_result_json["regression_count"] == 0


# --- 15 ---------------------------------------------------------------------
def test_15_held_out_case_behaves_differently_because_of_the_active_rule(session):
    """Confluent (V008) is excluded from rule derivation entirely. If the learned
    rule is real rather than memorised, it must still fix V008."""
    from app.services.simulator.profile import HELD_OUT_VENDORS

    assert "V008" in HELD_OUT_VENDORS

    run_close(session, LIVE)
    before = money(session.get(
        TrueupWorkpaper, _ob(session, "V008").current_workpaper_id).proposed_amount)

    cal = run_calibration(session, ["2026-10", "2026-11"])
    assert cal["rules_activated"]

    # No rule may cite a held-out case as its source.
    for lid in cal["rules_activated"]:
        row = session.get(TrueupLearningRule, lid)
        for src in row.candidate_rule_json["source_learning_ids"]:
            src_ob = session.get(TrueupObligation,
                                 session.get(TrueupLearningRule, src).obligation_id)
            assert src_ob.vendor_id not in HELD_OUT_VENDORS, "a rule was derived from held-out data"

    # Re-estimate V008's live period under the now-active rule.
    from app.services.agents import estimation, evidence

    ob = _ob(session, "V008")
    evidence.run(session, ob.obligation_id)
    wp = estimation.run(session, ob.obligation_id)
    after = money(wp.proposed_amount)

    inv = session.scalars(select(CompanyApInvoice).where(
        CompanyApInvoice.vendor_id == "V008",
        CompanyApInvoice.service_start_date == ob.service_start_date)).first()
    actual = money(inv.amount)

    assert after != before, "the active rule changed nothing for the held-out vendor"
    assert abs(after - actual) < abs(before - actual), "the rule did not improve the held-out case"
    assert after == actual


# --- 16 ---------------------------------------------------------------------
def test_16_auditor_re_performs_and_reports(session):
    run_close(session, LIVE)
    report = auditor.run_period(session, LIVE)
    assert report["audited"] == report["passed"] + report["exceptions"]
    assert report["exceptions"] == 0, [
        c for r in report["reports"] for c in r["checks"] if c["result"] == "EXCEPTION"]

    # And it detects a tampered figure rather than rubber-stamping it.
    ob = _ob(session, "V002")
    wp = session.get(TrueupWorkpaper, ob.current_workpaper_id)
    wp.proposed_amount = money("1.00")
    session.flush()
    one = auditor.run(session, ob.obligation_id)
    assert one["verdict"] == "EXCEPTION"
    assert any(c["check"] == "arithmetic" and c["result"] == "EXCEPTION" for c in one["checks"])


# --- 17 ---------------------------------------------------------------------
def test_17_improvements_md_is_generated_from_rule_records(session, tmp_path):
    run_calibration(session, ["2026-09", "2026-10", "2026-11"])
    path = tmp_path / "improvements.md"
    text = generate(session, path)
    assert path.exists()
    assert "# TrueUp Improvements" in text
    for r in session.scalars(select(TrueupLearningRule).where(
            TrueupLearningRule.status == "ACTIVE")):
        assert r.candidate_rule_json["rule_key"] in text
        assert "Historical replay" in text
        assert "Regressions" in text


# --- 18 ---------------------------------------------------------------------
def test_18_whole_simulation_runs_without_an_llm_api_key(session, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.services.llm import get_llm

    assert get_llm().name == "stub"
    summary = run_close(session, LIVE)
    assert summary["posted"] > 0
    assert summary["obligations"] > 0
