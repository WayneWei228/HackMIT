"""Start a test or a chain script from a taught state.

The real way a rule becomes ACTIVE is the Learning agent's loop: grade a past accrual against its
invoice, diagnose the miss, propose a rule, replay it over history, and wait for the Controller.
`activate_escalator_rule` skips all of that and exists only so unit tests and chain scripts can
begin with the escalator rule already learned. Its parent rows are marked `test_fixture` and
belong to a closed history period, so no live agent ever picks them up. The rule is recorded as
approved by the configured Controller after a passing replay, exactly as the real loop leaves it,
so the verifier sees a rule that meets the controls it enforces.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.learning.rules import CandidateRule
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import assert_balanced

FIXTURE_AGENT = "test_fixture"
LEARNING_ID = "LRN-FIXTURE-ESCALATOR"
HISTORY_PERIOD = "2026-11"


def activate_escalator_rule(session: Session, *, now: datetime) -> str:
    """Insert one ACTIVE APPLY_CONTRACT_ESCALATOR rule and the history rows it hangs off.

    Returns the learning id. Calling it twice returns the same id without inserting again.
    """
    if session.get(m.TrueUpLearningRule, LEARNING_ID) is not None:
        return LEARNING_ID
    contract = session.scalars(
        select(m.CompanyContract)
        .where(m.CompanyContract.escalator_percent.is_not(None))
        .order_by(m.CompanyContract.contract_row_id)
    ).first()
    if contract is None:
        raise LookupError("no contract with an escalator to hang the fixture rule on")
    vendor_id = contract.vendor_id
    obligation_id = f"OBL-FIXTURE-{vendor_id}-{HISTORY_PERIOD}"
    workpaper_id = f"WP-{obligation_id}-01"
    accrued, actual = Decimal("11840.00"), Decimal("14800.00")
    lines = [
        {
            "account_code": "610200",
            "debit": str(accrued),
            "credit": "0.00",
            "description": "fixture accrual",
        },
        {
            "account_code": "210100",
            "debit": "0.00",
            "credit": str(accrued),
            "description": "fixture accrual",
        },
    ]
    assert_balanced(lines)
    session.add(
        m.TrueUpObligation(
            obligation_id=obligation_id,
            vendor_id=vendor_id,
            period=HISTORY_PERIOD,
            contract_id=contract.contract_id,
            po_id=None,
            non_po_group_key=None,
            service_start_date=date(2026, 11, 1),
            service_end_date=date(2026, 11, 30),
            purchase_type=e.PurchaseType.USAGE_BASED,
            invoice_status=e.InvoiceStatus.MATCHED_AFTER_CLOSE,
            evidence_status=e.EvidenceStatus.SUFFICIENT,
            workflow_stage=e.WorkflowStage.CLOSED,
            next_action=e.NextAction.NONE,
            assigned_agent=FIXTURE_AGENT,
            accrual_status=e.AccrualStatus.TRUE_UP_COMPLETE,
            risk_level="LOW",
            current_workpaper_id=workpaper_id,
            matched_invoice_id=None,
            opened_at=now,
            updated_at=now,
            resolved_at=now,
        )
    )
    session.flush()
    session.add(
        m.TrueUpWorkpaper(
            workpaper_id=workpaper_id,
            obligation_id=obligation_id,
            period=HISTORY_PERIOD,
            estimation_method=e.EstimationMethod.USAGE_TIMES_RATE,
            proposed_amount=accrued,
            currency="USD",
            calculation_expression="740000 x 0.016 per API_CALL",
            calculation_inputs_json={"fixture": True, "step_up_applied": False},
            expense_account="610200",
            accrual_liability_account="210100",
            cost_center="UNASSIGNED",
            status=e.WorkpaperStatus.POSTED_SIMULATED,
            policy_decision=e.PolicyDecision.PERMIT,
            policy_summary="Fixture history row.",
            controller_decision=None,
            controller_notes=None,
            journal_entry_json=lines,
            created_by_agent=FIXTURE_AGENT,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    rule = CandidateRule.apply_contract_escalator([LEARNING_ID])
    ownership = session.get(m.CompanyConfig, "ownership_map")
    controller = (ownership.config_value_json or {}).get("controller") if ownership else None
    session.add(
        m.TrueUpLearningRule(
            learning_id=LEARNING_ID,
            obligation_id=obligation_id,
            workpaper_id=workpaper_id,
            invoice_id=None,
            actual_amount=actual,
            accrual_amount=accrued,
            variance_amount=actual - accrued,
            variance_percent=Decimal("25.00"),
            root_cause=e.RootCause.MISSED_ESCALATOR,
            root_cause_summary="Fixture: the baseline ignored the contract escalator step-up.",
            candidate_rule_json=rule.model_dump(mode="json"),
            replay_result_json={
                "fixture": True,
                "passed": True,
                "criteria": {
                    "supporting_misses_improve": True,
                    "no_correct_estimate_flips": True,
                    "total_error_falls": True,
                },
            },
            status=e.LearningStatus.ACTIVE,
            approved_by=controller or FIXTURE_AGENT,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    return LEARNING_ID
