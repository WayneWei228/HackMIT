"""Evidence Agent — builds source-backed evidence cards.

Two jobs:

1. Gather the facts that justify an amount, each pinned to a source table, a
   source id and (where the source is a document) a quoted excerpt. The LLM reads
   contract prose into structured JSON here; deterministic code decides what to
   do with it.

2. Satisfy whatever ACTIVE learned rules demand. This is the mechanism by which
   learning actually changes behaviour: a REQUIRE_EVIDENCE rule causes this agent
   to run a *derivation* it would otherwise skip — and if the derivation cannot
   be completed from source data, the fact is recorded as MISSING rather than
   guessed, which forces an escalation downstream.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import TrueupObligation
from app.money import money, rate
from app.repositories.contracts import all_versions, effective_version
from app.repositories.rules import active_rules
from app.repositories.runs import log_run
from app.services.agents.common import add_evidence, advance, evidence_for, vendor_name
from app.services.estimators.builder import build_context
from app.services.estimators.engine import rules_in_scope
from app.services.llm import get_llm
from app.services.pdf.extract import find_excerpt
from app.services.simulator.clock import close_cutoff

AGENT = "EvidenceAgent"


def run(session: Session, obligation_id: str, as_of: dt.datetime | None = None) -> TrueupObligation:
    ob = session.get(TrueupObligation, obligation_id)
    as_of = as_of or close_cutoff(ob.period)
    facts_used: list[str] = []
    uncertainties: list[str] = []
    created: list[str] = []

    created += _contract_evidence(session, ob, as_of, facts_used, uncertainties)
    created += _po_evidence(session, ob, as_of, facts_used)
    created += _service_evidence(session, ob, as_of, facts_used, uncertainties)
    created += _non_po_evidence(session, ob, as_of, facts_used)
    session.flush()

    # --- satisfy active learned rules ---------------------------------------
    created += _satisfy_required_evidence(session, ob, as_of, facts_used, uncertainties)
    session.flush()

    conflicts = _detect_contradictions(session, ob, as_of)
    created += conflicts

    status, next_action, agent = _assess(session, ob, conflicts, uncertainties)
    advance(session, ob, stage="EVIDENCE_GATHERED", next_action=next_action, agent=agent,
            evidence_status=status,
            risk_level="HIGH" if conflicts else ob.risk_level, at=as_of)

    log_run(session, agent_name=AGENT, action="gather_evidence",
            status="ESCALATED" if conflicts else "OK",
            obligation_id=ob.obligation_id, facts_used=facts_used,
            decision_summary=f"Evidence assessed as {status}",
            uncertainties=uncertainties,
            output_summary=f"{len(created)} evidence card(s); next={next_action} -> {agent}",
            output_record_ids=created, at=as_of)
    return ob


# ---------------------------------------------------------------------------

def _contract_evidence(session, ob, as_of, facts_used, uncertainties) -> list[str]:
    if not ob.contract_id:
        return []
    out = []
    versions = all_versions(session, ob.contract_id)
    c = effective_version(session, ob.contract_id, ob.service_start_date, ob.service_end_date)
    if c is None:
        uncertainties.append(f"No contract version of {ob.contract_id} covers {ob.period}")
        return []

    facts_used.append(
        f"selected {c.contract_row_id} of {len(versions)} version(s) by effective-date overlap "
        f"with {ob.service_start_date}..{ob.service_end_date}"
    )
    out.append(add_evidence(
        session, obligation_id=ob.obligation_id, evidence_type="CONTRACT_VERSION",
        source_table="company_contracts", source_id=c.contract_row_id,
        fact=(f"Version {c.contract_version} of {c.contract_id} is effective "
              f"{c.effective_start_date}..{c.effective_end_date}, which overlaps the service "
              f"period. Selected by date overlap, not by ACTIVE status."),
        value={"contract_row_id": c.contract_row_id, "version": c.contract_version,
               "billing_model": c.billing_model,
               "versions_considered": [v.contract_row_id for v in versions]},
        agent=AGENT, at=as_of,
    ).evidence_id)

    if c.base_rate is not None:
        out.append(add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type="CONTRACT_RATE",
            source_table="company_contracts", source_id=c.contract_row_id,
            fact=f"Contracted base rate is {c.base_rate} per {c.rate_unit}, billed {c.billing_frequency}.",
            value={"base_rate": str(rate(c.base_rate)), "rate_unit": c.rate_unit,
                   "billing_frequency": c.billing_frequency},
            agent=AGENT,
            excerpt=find_excerpt(c.contract_text, "per month", "per unit", "Contracted rate",
                                 "COMMERCIAL SUMMARY"),
            at=as_of,
        ).evidence_id)

    # The escalator clause is recorded as a FACT whether or not anything acts on
    # it. The baseline estimator ignores it — that is the failure the backtest is
    # designed to expose, and it has to be visible on the record afterwards.
    if c.escalator_percent:
        in_force = bool(c.escalator_effective_date and c.escalator_effective_date <= ob.service_start_date)
        out.append(add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type="CONTRACT_ESCALATOR",
            source_table="company_contracts", source_id=c.contract_row_id,
            fact=(f"Contract carries a {c.escalator_percent}% escalator effective "
                  f"{c.escalator_effective_date}. As of service start {ob.service_start_date} "
                  f"this escalator is {'IN FORCE' if in_force else 'not yet in force'}."),
            value={"escalator_percent": str(rate(c.escalator_percent)),
                   "escalator_effective_date": c.escalator_effective_date.isoformat()
                   if c.escalator_effective_date else None,
                   "in_force": in_force},
            agent=AGENT,
            excerpt=find_excerpt(c.contract_text, "increase", "escalat", "adjustment"),
            at=as_of,
        ).evidence_id)
        if in_force:
            uncertainties.append(
                f"Escalator of {c.escalator_percent}% has been in force since "
                f"{c.escalator_effective_date}; base_rate alone may understate the billed rate."
            )

    # LLM reads the clause text; deterministic code keeps custody of the numbers.
    terms = get_llm().extract_contract_terms(c.contract_text, vendor_name(session, ob.vendor_id))
    if terms:
        out.append(add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type="CONTRACT_TERMS_EXTRACTED",
            source_table="company_contracts", source_id=c.contract_row_id,
            fact="Commercial terms extracted from contract text: "
                 + "; ".join(terms.get("clauses", [])[:3] or ["(no clause text matched)"]),
            value=terms, agent=AGENT, confidence=float(terms.get("confidence", 0.7) or 0.7),
            excerpt=find_excerpt(c.contract_text, "Commercial terms", "COMMERCIAL SUMMARY"),
            at=as_of,
        ).evidence_id)
    return out


def _po_evidence(session, ob, as_of, facts_used) -> list[str]:
    if not ob.po_id:
        return []
    from app.models import CompanyPurchaseOrder

    po = session.get(CompanyPurchaseOrder, ob.po_id)
    if po is None:
        return []
    facts_used.append(f"read purchase order {po.po_id} with {len(po.line_items_json or [])} line(s)")
    return [add_evidence(
        session, obligation_id=ob.obligation_id, evidence_type="PURCHASE_ORDER",
        source_table="company_purchase_orders", source_id=po.po_id,
        fact=(f"PO {po.po_number} ({po.status}, {po.order_type}) approved for "
              f"{money(po.approved_total)} against {po.gl_account}. {po.description}"),
        value={"po_id": po.po_id, "approved_total": str(money(po.approved_total)),
               "lines": po.line_items_json, "gl_account": po.gl_account,
               "cost_center": po.cost_center},
        agent=AGENT, at=as_of,
    ).evidence_id]


def _service_evidence(session, ob, as_of, facts_used, uncertainties) -> list[str]:
    from app.repositories.asof import visible_service_evidence

    rows = visible_service_evidence(session, as_of, vendor_id=ob.vendor_id)
    rows = [
        r for r in rows
        if r.service_end_date >= ob.service_start_date and r.service_start_date <= ob.service_end_date
        and (ob.po_id is None or r.po_id in (None, ob.po_id))
    ]
    facts_used.append(f"{len(rows)} service-evidence record(s) visible as of cutoff")
    out = []
    for r in rows:
        if r.evidence_type == "USAGE_METER":
            etype, fact = "USAGE_QUANTITY", (
                f"Metered usage of {r.quantity} {r.unit} for {r.service_start_date}.."
                f"{r.service_end_date}, recorded by {r.source_system}, status {r.confirmation_status}."
            )
            value = {"quantity": str(rate(r.quantity or 0)), "unit": r.unit,
                     "source_system": r.source_system}
        elif r.evidence_type == "GOODS_RECEIPT":
            etype, fact = "RECEIPT_QUANTITY", (
                f"Goods receipt {r.service_evidence_id}: {r.quantity} {r.unit} received and "
                f"accepted on {r.service_end_date}, accepted value {money(r.accepted_amount or 0)}, "
                f"confirmed by {r.confirmed_by_person_id}."
            )
            value = {"quantity": str(rate(r.quantity or 0)),
                     "accepted_amount": str(money(r.accepted_amount or 0))}
        elif r.evidence_type == "DELIVERY_REPORT":
            etype, fact = "ACCEPTED_AMOUNT", (
                f"Delivery report {r.service_evidence_id}: {money(r.accepted_amount or 0)} of "
                f"service actually delivered through {r.service_end_date}. Undelivered budget is "
                f"not billable and must not be accrued."
            )
            value = {"accepted_amount": str(money(r.accepted_amount or 0))}
        else:
            continue
        out.append(add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type=etype,
            source_table="company_service_evidence", source_id=r.service_evidence_id,
            fact=fact, value=value, agent=AGENT, at=as_of,
        ).evidence_id)

    if ob.purchase_type == "USAGE_BASED" and not any(r.evidence_type == "USAGE_METER" for r in rows):
        uncertainties.append("No usage meter has landed for this period")
    return out


def _non_po_evidence(session, ob, as_of, facts_used) -> list[str]:
    if not ob.non_po_group_key:
        return []
    from app.repositories.asof import disputed_non_po_spend, eligible_non_po_spend

    rows = [
        r for r in eligible_non_po_spend(session, as_of, ob.period)
        if f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}" == ob.non_po_group_key
    ]
    disputed = [
        r for r in disputed_non_po_spend(session, as_of, ob.period)
        if f"{ob.period}|{r.spend_source}|{r.cost_center}|{r.gl_account}" == ob.non_po_group_key
    ]
    facts_used.append(f"{len(rows)} eligible + {len(disputed)} disputed non-PO transaction(s)")
    out = [add_evidence(
        session, obligation_id=ob.obligation_id, evidence_type="NON_PO_TRANSACTIONS",
        source_table="company_non_po_spend", source_id=ob.non_po_group_key,
        fact=(f"{len(rows)} eligible transaction(s) totalling "
              f"{money(sum(money(r.amount) for r in rows))}: pending and settled charges in "
              f"{ob.period} with no AP invoice and no prior accrual."),
        value={"transactions": [
            {"id": r.non_po_spend_id, "merchant": r.merchant_name,
             "status": r.transaction_status, "amount": str(money(r.amount))} for r in rows]},
        agent=AGENT, at=as_of,
    ).evidence_id]
    if disputed:
        out.append(add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type="NON_PO_DISPUTED",
            source_table="company_non_po_spend", source_id=ob.non_po_group_key,
            fact=(f"{len(disputed)} disputed transaction(s) excluded from the automatic accrual "
                  f"population and referred to the Controller."),
            value={"transactions": [r.non_po_spend_id for r in disputed]},
            agent=AGENT, confidence=0.6, at=as_of,
        ).evidence_id)
    return out


# ---------------------------------------------------------------------------
# Derivations demanded by ACTIVE learned rules
# ---------------------------------------------------------------------------

from app.services.estimators.derivations import DERIVATIONS  # shared with replay





def _satisfy_required_evidence(session, ob, as_of, facts_used, uncertainties) -> list[str]:
    rules = active_rules(session)
    if not rules:
        return []
    ctx = build_context(session, ob, as_of)
    fired = rules_in_scope(ctx, rules)
    out = []
    for ar in fired:
        a = ar.rule.action
        if a.action_type != "REQUIRE_EVIDENCE":
            continue
        etype = a.evidence_type
        if etype in ctx.evidence:
            continue
        deriver = DERIVATIONS.get(etype)
        if deriver is None:
            uncertainties.append(f"Active rule {ar.rule.rule_key} requires {etype}, "
                                 f"which TrueUp has no derivation for")
            continue
        value, failure = deriver(ctx)
        if value is None:
            uncertainties.append(f"Could not derive {etype}: {failure}")
            out.append(add_evidence(
                session, obligation_id=ob.obligation_id, evidence_type=f"{etype}_MISSING",
                source_table="company_contracts",
                source_id=ctx.contract.contract_row_id if ctx.contract else "",
                fact=(f"Active rule {ar.rule.rule_key} requires {etype}, but it cannot be derived "
                      f"from the record: {failure}. No amount may be asserted."),
                value={"required_by_rule": ar.rule.rule_key, "learning_id": ar.learning_id,
                       "failure": failure},
                agent=AGENT, confidence=0.0, at=as_of,
            ).evidence_id)
            continue
        facts_used.append(f"derived {etype} required by active rule {ar.rule.rule_key}")
        out.append(add_evidence(
            session, obligation_id=ob.obligation_id, evidence_type=etype,
            source_table="company_contracts",
            source_id=ctx.contract.contract_row_id if ctx.contract else "",
            fact=(f"In-force rate for {ob.period} is {value['rate']} "
                  f"({value.get('basis')}). Derived because active rule "
                  f"{ar.rule.rule_key} [{ar.learning_id}] requires {etype}."),
            value=value | {"required_by_rule": ar.rule.rule_key, "learning_id": ar.learning_id},
            agent=AGENT, at=as_of,
        ).evidence_id)
    return out


def _detect_contradictions(session, ob, as_of) -> list[str]:
    """Contract says one thing, PO says another. Record it; do not resolve it
    silently."""
    out = []
    ev = {e.evidence_type: e for e in evidence_for(session, ob.obligation_id)}
    contract_rate = ev.get("CONTRACT_RATE")
    po = ev.get("PURCHASE_ORDER")
    if contract_rate and po:
        lines = (po.value_json or {}).get("lines") or []
        c_rate = rate((contract_rate.value_json or {}).get("base_rate", 0))
        for l in lines:
            p_rate = rate(l.get("unit_price", 0))
            if c_rate and p_rate and abs(p_rate - c_rate) / c_rate > Decimal("0.05"):
                out.append(add_evidence(
                    session, obligation_id=ob.obligation_id, evidence_type="CONTRACT_PO_CONFLICT",
                    source_table="company_purchase_orders", source_id=po.source_id,
                    fact=(f"Contract rate {c_rate} conflicts with PO line {l.get('po_line_id')} "
                          f"unit price {p_rate}. TrueUp will not choose between them."),
                    value={"contract_rate": str(c_rate), "po_unit_price": str(p_rate),
                           "po_line_id": l.get("po_line_id")},
                    agent=AGENT, confidence=0.5, at=as_of,
                ).evidence_id)
                break
    return out


def _assess(session, ob, conflicts, uncertainties):
    if conflicts:
        return "CONFLICTING", "RESOLVE_CONFLICT", "ControllerService"
    ev_types = {e.evidence_type for e in evidence_for(session, ob.obligation_id)}
    if any(t.endswith("_MISSING") for t in ev_types):
        return "MISSING", "REQUEST_MISSING_FACT", "OutreachAgent"
    required = {
        "USAGE_BASED": {"USAGE_QUANTITY", "CONTRACT_RATE"},
        "FIXED_RECURRING": {"CONTRACT_RATE"},
        "RECEIPT_BASED": {"RECEIPT_QUANTITY", "PURCHASE_ORDER"},
        "MILESTONE_BASED": {"ACCEPTED_AMOUNT"},
        "NON_PO_CARD_SPEND": {"NON_PO_TRANSACTIONS"},
        "NON_PO_DIRECT_SPEND": {"NON_PO_TRANSACTIONS"},
    }.get(ob.purchase_type, set())
    if required - ev_types:
        return "MISSING", "CLASSIFY", "ClassificationAgent"
    return "SUFFICIENT", "CLASSIFY", "ClassificationAgent"
