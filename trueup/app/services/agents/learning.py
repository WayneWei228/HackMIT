"""Learning Agent — proposes a controlled behavioural change.

The discipline here matters more than the cleverness. The agent may only propose
a rule when:

  - the same root cause has been observed on more than one independent case
    (one variance is an anecdote),
  - the root cause has a known typed remedy,
  - the resulting rule passes every forbidden-action check, and
  - replay shows it improves history without regressions.

When a variance has no known remedy — the UNKNOWN case — the agent says so and
escalates. Proposing a rule for something it does not understand would be the
single most dangerous thing this system could do.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TrueupLearningRule, TrueupObligation
from app.money import jsonable, money
from app.repositories.runs import log_run
from app.schemas.rules import CandidateRule, RuleAction, RuleScope, RuleViolation
from app.services.learning.replay import replay
from app.services.llm import get_llm
from app.services.simulator.profile import HELD_OUT_VENDORS

AGENT = "LearningAgent"

MIN_SUPPORTING_CASES = 2


# ---------------------------------------------------------------------------
# The typed remedies TrueUp knows about. A root cause absent from this table is
# escalated, never improvised.
# ---------------------------------------------------------------------------

def _escalator_rule(cases) -> CandidateRule:
    return CandidateRule(
        rule_key="verify_escalator_effective_rate",
        title="Verify the in-force rate when a contract escalator has taken effect",
        rationale=(
            "Across these closes the accrual used the contract base rate while an escalator "
            "clause was already in force, so every affected period was under-accrued by exactly "
            "the escalator percentage. The escalated rate was recorded on the contract the whole "
            "time; nothing was unknowable. Requiring the in-force rate as evidence forces the "
            "escalator to be resolved before an amount is asserted — and where it cannot be "
            "resolved from the record, the item escalates instead of being estimated."
        ),
        scope=RuleScope(
            purchase_types=["USAGE_BASED", "FIXED_RECURRING"],
            conditions=["CONTRACT_ESCALATOR_EFFECTIVE_ON_OR_BEFORE_SERVICE_START"],
        ),
        action=RuleAction(
            action_type="REQUIRE_EVIDENCE",
            evidence_type="EFFECTIVE_RATE",
            reason="The rate actually in force must be on the record before an amount is asserted.",
        ),
        source_learning_ids=[c.learning_id for c in cases],
        root_cause="MISSED_ESCALATOR",
    )


def _missing_usage_rule(cases) -> CandidateRule:
    return CandidateRule(
        rule_key="chase_missing_usage_before_estimating",
        title="Ask the service owner for usage before falling back to a run rate",
        rationale=(
            "These closes fell back to a historical run rate because the usage meter had not "
            "landed by cutoff, and the run rate proved materially wrong. The usage existed; it "
            "simply had not been fetched. Requiring outreach to the service owner converts a "
            "guess into either a fact or an explicit escalation."
        ),
        scope=RuleScope(
            purchase_types=["USAGE_BASED"],
            conditions=["USAGE_EVIDENCE_MISSING", "NO_INVOICE_FOUND"],
        ),
        action=RuleAction(
            action_type="REQUIRE_OUTREACH",
            outreach_role="SERVICE_OWNER",
            reason="Usage is knowable; a run-rate fallback should not substitute for asking.",
        ),
        source_learning_ids=[c.learning_id for c in cases],
        root_cause="USAGE_VARIANCE",
    )


REMEDIES = {
    "MISSED_ESCALATOR": _escalator_rule,
    "USAGE_VARIANCE": _missing_usage_rule,
}

# Root causes that are real, diagnosable, and deliberately NOT automatable:
# they need a human or a process change, not an estimator rule.
NO_RULE_EXPLANATION = {
    "TIMING_DIFFERENCE": (
        "Transactions posted after the cutoff cannot be seen at close by definition. "
        "This is a calendar fact, not an estimation defect; no estimator rule can fix it "
        "without inventing amounts."
    ),
    "SCOPE_CHANGE": (
        "Delivered scope differed from accepted scope. This needs a receiving-process fix, "
        "not a change to how the accrual is calculated."
    ),
    "MULTI_PERIOD_INVOICE": (
        "Allocation across periods already runs deterministically; the variance reflects the "
        "allocation basis, which is an accounting-policy question for the Controller."
    ),
    "DUPLICATE_NON_PO_ACCRUAL": (
        "Duplicate detection is a hard control, not a learned heuristic. Weakening or widening "
        "it through a learned rule is exactly what a rule must never do."
    ),
    "SOURCE_DATA_ERROR": (
        "Upstream data was wrong. The fix belongs in the source system."
    ),
    "UNKNOWN": (
        "No recorded fact explains this variance. TrueUp will not propose a rule for a pattern "
        "it cannot characterise - that would be fitting a control to a coincidence. Escalated "
        "to the Controller for human diagnosis."
    ),
}


def run(session: Session, learning_id: str, at: dt.datetime | None = None) -> TrueupLearningRule:
    lr = session.get(TrueupLearningRule, learning_id)
    at = at or dt.datetime.now()

    # A held-out case may never father a rule. Its whole purpose is to sit
    # outside the derivation so that improving on it means something.
    home = session.get(TrueupObligation, lr.obligation_id)
    if home is not None and home.vendor_id in HELD_OUT_VENDORS:
        lr.status = "OBSERVED"
        lr.updated_at = at
        session.flush()
        log_run(session, agent_name=AGENT, action="propose_rule", status="OK",
                obligation_id=lr.obligation_id, workpaper_id=lr.workpaper_id,
                facts_used=[f"vendor={home.vendor_id}", "held_out=true"],
                decision_summary=f"{home.vendor_id} is a held-out vendor; no rule may be "
                                 f"derived from it",
                output_summary="reserved for out-of-sample evaluation",
                output_record_ids=[learning_id], at=at)
        return lr

    cohort = _cohort(session, lr)
    facts = [f"root_cause={lr.root_cause}", f"variance={money(lr.variance_amount)}",
             f"cohort_size={len(cohort)}",
             f"cohort={[c.learning_id for c in cohort]}"]

    # An exact hit is a confirmation, not a failure. Treating every graded
    # outcome as something to escalate would bury the real misses in noise.
    if money(lr.variance_amount) == money(0):
        lr.status = "OBSERVED"
        lr.updated_at = at
        session.flush()
        log_run(session, agent_name=AGENT, action="propose_rule", status="OK",
                obligation_id=lr.obligation_id, workpaper_id=lr.workpaper_id, facts_used=facts,
                decision_summary="Accrual matched the invoice exactly; nothing to learn",
                output_summary="recorded as a confirmation of current behaviour",
                output_record_ids=[learning_id], at=at)
        return lr

    remedy = REMEDIES.get(lr.root_cause)

    if remedy is None:
        lr.status = "ESCALATED_NO_RULE"
        lr.root_cause_summary += (
            f" | No rule proposed: {NO_RULE_EXPLANATION.get(lr.root_cause, 'no known remedy.')}"
        )
        lr.updated_at = at
        session.flush()
        log_run(session, agent_name=AGENT, action="propose_rule", status="ESCALATED",
                obligation_id=lr.obligation_id, workpaper_id=lr.workpaper_id, facts_used=facts,
                decision_summary=f"{lr.root_cause} has no typed remedy; no rule proposed",
                uncertainties=[NO_RULE_EXPLANATION.get(lr.root_cause, "unknown pattern")],
                output_summary="escalated to Controller for human diagnosis",
                output_record_ids=[learning_id], at=at)
        return lr

    if len(cohort) < MIN_SUPPORTING_CASES:
        lr.status = "OBSERVED"
        lr.updated_at = at
        session.flush()
        log_run(session, agent_name=AGENT, action="propose_rule", status="OK",
                obligation_id=lr.obligation_id, workpaper_id=lr.workpaper_id, facts_used=facts,
                decision_summary=f"Only {len(cohort)} case(s) of {lr.root_cause}; "
                                 f"{MIN_SUPPORTING_CASES} required before proposing a rule",
                uncertainties=["single observation may not be a pattern"],
                output_summary="held as OBSERVED pending corroboration",
                output_record_ids=[learning_id], at=at)
        return lr

    candidate = remedy(cohort)
    # The LLM may reword the title and rationale; it cannot touch scope or action.
    worded = get_llm().propose_rule({
        "default_title": candidate.title, "default_rationale": candidate.rationale,
        "root_cause": lr.root_cause, "cases": len(cohort),
    })
    if worded.get("title"):
        candidate.title = str(worded["title"])[:200]
    if worded.get("rationale"):
        candidate.rationale = str(worded["rationale"])[:2000]

    try:
        candidate.validate_allowed()
    except RuleViolation as exc:
        lr.status = "REJECTED"
        lr.root_cause_summary += f" | Candidate rejected by the rule guard: {exc}"
        lr.updated_at = at
        session.flush()
        log_run(session, agent_name=AGENT, action="propose_rule", status="BLOCKED",
                obligation_id=lr.obligation_id, facts_used=facts,
                decision_summary=f"Candidate violated the rule constraints: {exc}",
                output_summary="rejected before replay", output_record_ids=[learning_id], at=at)
        return lr

    result = replay(session, candidate, learning_id)

    lr.candidate_rule_json = jsonable(candidate.model_dump())
    lr.replay_result_json = jsonable(result)
    lr.status = "REPLAY_PASSED" if result["verdict"] == "PASS" else "REPLAY_FAILED"
    lr.updated_at = at
    session.flush()

    log_run(session, agent_name=AGENT, action="propose_rule",
            status="OK" if result["verdict"] == "PASS" else "ESCALATED",
            obligation_id=lr.obligation_id, workpaper_id=lr.workpaper_id,
            facts_used=facts + [f"replay_cases={result['cases_replayed']}",
                                f"baseline_mae={result['baseline_mae']}",
                                f"candidate_mae={result['candidate_mae']}",
                                f"regressions={result['regression_count']}"],
            decision_summary=f"Candidate '{candidate.rule_key}' replay {result['verdict']}: "
                             f"{result['verdict_reason']}",
            uncertainties=([r["why"] for r in result["regressions"]]
                           if result["regressions"] else []),
            output_summary=f"status {lr.status}; awaiting Controller approval"
                           if result["verdict"] == "PASS" else "candidate will not be offered",
            output_record_ids=[learning_id], at=at)
    return lr


def _cohort(session: Session, lr: TrueupLearningRule) -> list[TrueupLearningRule]:
    """Independent cases sharing this root cause.

    Held-out vendors are excluded: a rule must never be derived from the data
    reserved to test whether it generalises.
    """
    rows = session.scalars(
        select(TrueupLearningRule).where(TrueupLearningRule.root_cause == lr.root_cause)
    )
    out = []
    for r in rows:
        ob = session.get(TrueupObligation, r.obligation_id)
        if ob is None or ob.vendor_id in HELD_OUT_VENDORS:
            continue
        if r.status in ("REJECTED", "REVOKED"):
            continue
        out.append(r)
    return sorted(out, key=lambda r: r.learning_id)


def run_all_observed(session: Session, at: dt.datetime | None = None) -> list[TrueupLearningRule]:
    """Sweep every ungraded outcome. Deduplicates by rule_key so one pattern
    produces one candidate rather than one per case."""
    observed = list(session.scalars(
        select(TrueupLearningRule).where(TrueupLearningRule.status == "OBSERVED")
    ))
    seen_keys: set[str] = set()
    out = []
    for lr in sorted(observed, key=lambda r: (r.root_cause, r.learning_id)):
        ob = session.get(TrueupObligation, lr.obligation_id)
        if ob is not None and ob.vendor_id in HELD_OUT_VENDORS:
            continue
        if lr.root_cause in REMEDIES:
            key = REMEDIES[lr.root_cause]([lr]).rule_key
            if key in seen_keys:
                continue
            seen_keys.add(key)
        out.append(run(session, lr.learning_id, at))
    return out
