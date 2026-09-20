"""Policy Enforcer — deterministic routing. No LLM reaches this code.

Every check returns a hard verdict, and the strongest verdict wins:
BLOCK > REQUIRE_CONTROLLER > REQUIRE_OUTREACH > PERMIT. The summary lists every
check with its outcome, so a reviewer sees not just the decision but the full
control surface that produced it.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyGlEntry, TrueupObligation, TrueupWorkpaper
from app.money import ZERO, money
from app.repositories.runs import log_run
from app.services.agents.common import advance, config, evidence_for
from app.services.estimators.engine import METHODS
from app.services.simulator.clock import close_cutoff

AGENT = "PolicyEnforcer"

SEVERITY = {"PERMIT": 0, "REQUIRE_OUTREACH": 1, "REQUIRE_CONTROLLER": 2, "BLOCK": 3}


def run(session: Session, workpaper_id: str, as_of: dt.datetime | None = None) -> TrueupWorkpaper:
    wp = session.get(TrueupWorkpaper, workpaper_id)
    ob = session.get(TrueupObligation, wp.obligation_id)
    as_of = as_of or close_cutoff(ob.period)

    checks: list[tuple[str, str, str]] = []   # (name, verdict, detail)
    inputs = wp.calculation_inputs_json or {}
    thresholds = config(session, "approval_thresholds")
    policy = config(session, "policy_rules")
    allowed = set(config(session, "allowed_gl_accounts").get("accounts", []))
    amount = money(wp.proposed_amount)

    # 1. period open
    periods = config(session, "accounting_periods")
    if periods.get(ob.period, {}).get("status") != "OPEN":
        checks.append(("period_open", "BLOCK", f"period {ob.period} is not open for posting"))
    else:
        checks.append(("period_open", "PERMIT", f"period {ob.period} is open"))

    # 2. no matching AP invoice
    if ob.invoice_status == "FOUND":
        checks.append(("no_ap_invoice", "BLOCK",
                       f"AP already holds {ob.matched_invoice_id}; accruing would double-count"))
    elif ob.invoice_status == "AMBIGUOUS":
        checks.append(("no_ap_invoice", "REQUIRE_CONTROLLER", "AP match is ambiguous"))
    else:
        checks.append(("no_ap_invoice", "PERMIT", "no invoice in AP for this service period"))

    # 3. no duplicate accrual
    existing = session.scalars(
        select(CompanyGlEntry).where(
            CompanyGlEntry.obligation_id == ob.obligation_id,
            CompanyGlEntry.entry_type == "ACCRUAL",
            CompanyGlEntry.status == "POSTED_SIMULATED",
        )
    ).first()
    if existing is not None and wp.status != "POSTED":
        checks.append(("no_duplicate_accrual", "BLOCK",
                       f"accrual {existing.gl_entry_id} already posted for this obligation"))
    else:
        checks.append(("no_duplicate_accrual", "PERMIT", "no prior accrual for this obligation"))

    # 4. required evidence present
    if not inputs.get("supported", True):
        missing = inputs.get("missing_evidence") or []
        verdict = "REQUIRE_OUTREACH" if missing else "REQUIRE_CONTROLLER"
        checks.append(("evidence_sufficient", verdict,
                       inputs.get("unsupported_reason") or "estimate is not supported by evidence"))
    elif ob.evidence_status == "CONFLICTING":
        checks.append(("evidence_sufficient", "REQUIRE_CONTROLLER",
                       "contradictory evidence on the record"))
    else:
        checks.append(("evidence_sufficient", "PERMIT", f"evidence is {ob.evidence_status}"))

    # 5. allowed estimator
    if wp.estimation_method not in METHODS:
        checks.append(("allowed_estimator", "BLOCK",
                       f"estimator {wp.estimation_method} is not an approved method"))
    else:
        checks.append(("allowed_estimator", "PERMIT", f"{wp.estimation_method} is approved"))

    # 6. balanced entry
    ok, detail = _balanced(wp.journal_entry_json)
    if not ok and policy.get("block_unbalanced_entries", True):
        checks.append(("entry_balanced", "BLOCK", detail))
    else:
        checks.append(("entry_balanced", "PERMIT", detail))

    # 7. allowed GL accounts
    bad = [l["account"] for l in (wp.journal_entry_json or {}).get("lines", [])
           if l["account"] not in allowed]
    if bad:
        checks.append(("allowed_gl_accounts", "BLOCK", f"account(s) not permitted: {bad}"))
    else:
        checks.append(("allowed_gl_accounts", "PERMIT", "all accounts are on the approved list"))

    # 8. materiality / de minimis
    de_minimis = money(thresholds.get("de_minimis", "0"))
    if amount != ZERO and abs(amount) < de_minimis:
        checks.append(("materiality", "BLOCK",
                       f"{amount} is below the de minimis threshold of {de_minimis}; "
                       f"no accrual is recorded"))
    else:
        checks.append(("materiality", "PERMIT", f"{amount} is at or above de minimis {de_minimis}"))

    # 9. approval threshold
    ctrl = money(thresholds.get("controller_review", "0"))
    if abs(amount) >= ctrl:
        checks.append(("approval_required", "REQUIRE_CONTROLLER",
                       f"{amount} is at or above the Controller review threshold of {ctrl}"))
    else:
        checks.append(("approval_required", "PERMIT", f"{amount} is below {ctrl}"))

    # 10. fallback estimates are never posted unreviewed
    if inputs.get("is_fallback"):
        checks.append(("fallback_review", "REQUIRE_CONTROLLER",
                       "amount comes from HISTORICAL_RUN_RATE, not from evidence of this period"))
    else:
        checks.append(("fallback_review", "PERMIT", "amount is evidence-based"))

    # 11. active learned rules complied with
    forced = wp.policy_summary or ""
    rule_effects = inputs.get("active_rules_applied") or []
    if "REQUIRE_CONTROLLER" in forced:
        checks.append(("learned_rules", "REQUIRE_CONTROLLER", "an active rule requires Controller review"))
    elif "REQUIRE_OUTREACH" in forced:
        checks.append(("learned_rules", "REQUIRE_OUTREACH", "an active rule requires outreach first"))
    elif rule_effects:
        checks.append(("learned_rules", "PERMIT", f"{len(rule_effects)} active rule effect(s) applied"))
    else:
        checks.append(("learned_rules", "PERMIT", "no active rule applies"))

    decision = max(checks, key=lambda c: SEVERITY[c[1]])[1]
    summary = " | ".join(f"{n}={v}: {d}" for n, v, d in checks)

    wp.policy_decision = decision
    wp.policy_summary = summary
    wp.status = {
        "PERMIT": "APPROVED" if abs(amount) < ctrl else "PENDING_CONTROLLER",
        "REQUIRE_OUTREACH": "DRAFT",
        "REQUIRE_CONTROLLER": "PENDING_CONTROLLER",
        "BLOCK": "BLOCKED",
    }[decision]
    wp.updated_at = as_of
    session.flush()

    next_action, agent, accrual_status = {
        "PERMIT": ("POST_ENTRY", "JournalEntryService", "APPROVED"),
        "REQUIRE_OUTREACH": ("REQUEST_MISSING_FACT", "OutreachAgent", "PROPOSED"),
        "REQUIRE_CONTROLLER": ("CONTROLLER_REVIEW", "ControllerService", "PROPOSED"),
        "BLOCK": ("CLOSE_BLOCKED", None, "BLOCKED" if ob.invoice_status != "FOUND" else "NO_ACCRUAL"),
    }[decision]

    advance(session, ob, stage=f"POLICY_{decision}", next_action=next_action, agent=agent,
            accrual_status=accrual_status, at=as_of)

    log_run(session, agent_name=AGENT, action="enforce_policy",
            status="OK" if decision == "PERMIT" else ("BLOCKED" if decision == "BLOCK" else "ESCALATED"),
            obligation_id=ob.obligation_id, workpaper_id=wp.workpaper_id,
            facts_used=[f"{n}={v}" for n, v, _ in checks],
            decision_summary=f"{decision} ({len([c for c in checks if c[1]!='PERMIT'])} of "
                             f"{len(checks)} checks not clean)",
            uncertainties=[d for _, v, d in checks if v != "PERMIT"],
            output_summary=f"workpaper {wp.workpaper_id} -> {wp.status}; next={next_action}",
            input_record_ids=[e.evidence_id for e in evidence_for(session, ob.obligation_id)],
            output_record_ids=[wp.workpaper_id], at=as_of)
    return wp


def _balanced(je: dict | None) -> tuple[bool, str]:
    lines = (je or {}).get("lines") or []
    if not lines:
        return False, "journal entry has no lines"
    debits = sum(money(l.get("debit", 0)) for l in lines)
    credits = sum(money(l.get("credit", 0)) for l in lines)
    if debits != credits:
        return False, f"unbalanced: debits {debits} != credits {credits}"
    return True, f"balanced: debits {debits} = credits {credits}"
