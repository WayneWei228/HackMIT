"""Derivations: how TrueUp produces an evidence fact a learned rule demands.

Pure functions of the EstimationContext, for the same reason the estimator is
pure — replay must be able to model exactly what the Evidence Agent *would* have
produced under a candidate rule, without re-running the agent against a rewound
database.

A derivation either returns a value backed by source fields, or fails with a
reason. It never guesses.
"""
from __future__ import annotations

from decimal import Decimal

from app.money import rate


def derive_effective_rate(ctx) -> tuple[dict | None, str | None]:
    """The unit rate actually in force for the service period, escalator applied.

    Deterministic arithmetic on contract fields. If the clause is incomplete —
    a percentage with no effective date — the derivation fails, and the caller
    must escalate rather than pick an interpretation.
    """
    c = ctx.contract
    if c is None or c.base_rate is None:
        return None, "no contract rate on the effective version"
    base = rate(c.base_rate)
    if not c.escalator_percent:
        return {"rate": str(base), "escalator_applied": False,
                "basis": "no escalator clause on the effective version"}, None
    if not c.escalator_effective_date:
        return None, ("contract states an escalator percentage but no effective date; "
                      "the in-force rate cannot be determined from the record")
    if c.escalator_effective_date > ctx.service_start:
        return {"rate": str(base), "escalator_applied": False,
                "basis": f"escalator effective {c.escalator_effective_date}, after service start"}, None
    esc = rate(c.escalator_percent)
    eff = base * (Decimal(1) + esc / Decimal(100))
    return {"rate": str(eff), "escalator_applied": True, "base_rate": str(base),
            "escalator_percent": str(esc),
            "escalator_effective_date": c.escalator_effective_date.isoformat(),
            "basis": f"{base} x (1 + {esc}/100) = {eff}"}, None


DERIVATIONS = {"EFFECTIVE_RATE": derive_effective_rate}


def apply_required_derivations(ctx, active_rules):
    """Return a context clone carrying every evidence fact the given rules require
    and TrueUp can actually derive.

    This is what makes a REQUIRE_EVIDENCE rule change an *amount*: the rule does
    not name a number, it forces a fact onto the record, and the estimator then
    binds that fact instead of the naive one.
    """
    from dataclasses import replace

    from app.services.estimators.context import EvidenceFact
    from app.services.estimators.engine import rules_in_scope

    ev = dict(ctx.evidence)
    changed = False
    for ar in rules_in_scope(ctx, active_rules):
        a = ar.rule.action
        if a.action_type != "REQUIRE_EVIDENCE" or a.evidence_type in ev:
            continue
        deriver = DERIVATIONS.get(a.evidence_type)
        if deriver is None:
            continue
        value, failure = deriver(ctx)
        if value is None:
            continue   # stays missing; the estimator will refuse to assert an amount
        ev[a.evidence_type] = EvidenceFact(
            evidence_id=f"DERIVED:{a.evidence_type}:{ctx.obligation_id}",
            evidence_type=a.evidence_type, value=value, confidence=Decimal("1.00"),
            source_table="company_contracts",
            source_id=ctx.contract.contract_row_id if ctx.contract else "",
        )
        changed = True
    return replace(ctx, evidence=ev) if changed else ctx
