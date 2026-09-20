"""The estimator: a pure function from (context, active rules) to an amount.

Nothing here touches the database, the clock, or an LLM. That is deliberate —
it is what makes `replay` possible: rebuild a historical context, run it with and
without a candidate rule, and diff the results.

All arithmetic is Decimal. Every result carries the formula, the bound inputs and
the evidence ids that justified them, because a number without a workpaper is not
an accrual.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.money import ZERO, money, rate
from app.schemas.rules import ActiveRule

# The six estimators from the spec. A rule may select or prohibit among these;
# it may never invent a seventh.
METHODS = (
    "FIXED_CONTRACT_RATE",
    "USAGE_TIMES_RATE",
    "RECEIVED_QUANTITY_TIMES_PRICE",
    "MILESTONE_ACCEPTED_AMOUNT",
    "HISTORICAL_RUN_RATE",
    "NON_PO_BALANCE_SUM",
)

DEFAULT_METHOD_BY_TYPE = {
    "FIXED_RECURRING": "FIXED_CONTRACT_RATE",
    "USAGE_BASED": "USAGE_TIMES_RATE",
    "RECEIPT_BASED": "RECEIVED_QUANTITY_TIMES_PRICE",
    "MILESTONE_BASED": "MILESTONE_ACCEPTED_AMOUNT",
    "NON_PO_CARD_SPEND": "NON_PO_BALANCE_SUM",
    "NON_PO_DIRECT_SPEND": "NON_PO_BALANCE_SUM",
    # Sentinel used by the Estimation Agent to request the policy-approved
    # fallback explicitly, rather than having the fallback fire implicitly.
    "__FALLBACK__": "HISTORICAL_RUN_RATE",
}


@dataclass
class EstimateResult:
    method: str
    amount: Decimal
    currency: str
    expression: str
    inputs: dict
    evidence_ids: list[str] = field(default_factory=list)
    supported: bool = True
    unsupported_reason: str | None = None
    missing_evidence: list[str] = field(default_factory=list)
    # Evidence demanded by an ACTIVE rule and absent. Distinct from
    # `missing_evidence`, which also covers ordinary gaps like "no meter yet":
    # an ordinary gap is what the policy-approved fallback exists for, whereas a
    # rule-demanded gap must never be papered over by a fallback.
    rule_required_missing: list[str] = field(default_factory=list)
    rule_effects: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    routing_override: str | None = None       # REQUIRE_OUTREACH | REQUIRE_CONTROLLER
    outreach_role: str | None = None
    is_fallback: bool = False


# ---------------------------------------------------------------------------
# Rule application
# ---------------------------------------------------------------------------

def rules_in_scope(ctx, active_rules: list[ActiveRule]) -> list[ActiveRule]:
    out = []
    for ar in active_rules:
        sc = ar.rule.scope
        if sc.purchase_types and ctx.purchase_type not in sc.purchase_types:
            continue
        # All listed conditions must hold (AND), so a rule narrows rather than fires broadly.
        if not all(ctx.condition_holds(c) for c in sc.conditions):
            continue
        out.append(ar)
    return out


# ---------------------------------------------------------------------------
# Rate resolution — where the escalator lesson actually lands
# ---------------------------------------------------------------------------

def _resolve_unit_rate(ctx, result: EstimateResult) -> Decimal | None:
    """Bind the unit rate.

    Baseline behaviour: take `base_rate` off the effective contract version. That
    is the naive read, and it is wrong whenever an escalator has taken effect
    mid-term — the failure this system is built to notice.

    When an EFFECTIVE_RATE evidence card is on the record, the estimator binds
    that instead. A learned REQUIRE_EVIDENCE[EFFECTIVE_RATE] rule is what causes
    the Evidence Agent to produce that card, so the rule changes the bound input
    without ever naming an amount itself.
    """
    ev = ctx.evidence.get("EFFECTIVE_RATE")
    if ev is not None:
        r = rate(ev.value.get("rate"))
        result.evidence_ids.append(ev.evidence_id)
        result.inputs["rate_source"] = "EFFECTIVE_RATE evidence (escalator-resolved)"
        result.inputs["escalator_applied"] = ev.value.get("escalator_applied", False)
        return r
    if ctx.contract and ctx.contract.base_rate is not None:
        result.inputs["rate_source"] = "contract.base_rate (no escalator check)"
        return rate(ctx.contract.base_rate)
    return None


# ---------------------------------------------------------------------------
# The six methods
# ---------------------------------------------------------------------------

def _fixed_contract_rate(ctx, res: EstimateResult) -> EstimateResult:
    r = _resolve_unit_rate(ctx, res)
    if r is None:
        return _unsupported(res, "No contract rate available for a fixed recurring obligation",
                            missing=["CONTRACT_RATE"])
    res.amount = money(r)
    res.inputs |= {"monthly_rate": str(r), "billing_frequency":
                   ctx.contract.billing_frequency if ctx.contract else None}
    res.expression = f"monthly_rate({r}) = {res.amount}"
    if ctx.contract:
        res.evidence_ids.append(ctx.contract.contract_row_id)
    return res


def _usage_times_rate(ctx, res: EstimateResult) -> EstimateResult:
    if ctx.usage_quantity is None:
        return _unsupported(res, "No measured usage for the service period",
                            missing=["USAGE_QUANTITY"])
    r = _resolve_unit_rate(ctx, res)
    if r is None:
        return _unsupported(res, "No contract rate for a usage-based obligation",
                            missing=["CONTRACT_RATE"])
    qty = rate(ctx.usage_quantity)
    res.amount = money(qty * r)
    res.inputs |= {"usage_quantity": str(qty), "unit_rate": str(r), "unit": ctx.usage_unit}
    res.expression = f"usage_quantity({qty}) * unit_rate({r}) = {res.amount}"
    return res


def _received_qty_times_price(ctx, res: EstimateResult) -> EstimateResult:
    if not ctx.po:
        return _unsupported(res, "Receipt-based accrual requires a purchase order",
                            missing=["PURCHASE_ORDER"])
    total = ZERO
    detail = []
    for ln in ctx.po.lines:
        unbilled = rate(ln.quantity_received) - rate(ln.quantity_billed)
        if unbilled <= 0:
            continue
        line_amt = money(unbilled * rate(ln.unit_price))
        total += line_amt
        detail.append({
            "po_line_id": ln.po_line_id,
            "received": str(ln.quantity_received),
            "billed": str(ln.quantity_billed),
            "unbilled": str(unbilled),
            "unit_price": str(ln.unit_price),
            "amount": str(line_amt),
        })
    if not detail:
        res.amount = ZERO
        res.expression = "no received-but-unbilled quantity = 0.00"
        res.inputs |= {"lines": []}
        return res
    res.amount = money(total)
    res.inputs |= {"lines": detail}
    res.expression = " + ".join(
        f"({d['unbilled']} x {d['unit_price']})" for d in detail
    ) + f" = {res.amount}"
    return res


def _milestone_accepted(ctx, res: EstimateResult) -> EstimateResult:
    if ctx.milestone_accepted_amount is None:
        return _unsupported(res, "No accepted/delivered amount for the milestone period",
                            missing=["ACCEPTED_AMOUNT"])
    res.amount = money(ctx.milestone_accepted_amount)
    res.inputs |= {"accepted_amount": str(res.amount)}
    res.expression = f"accepted_delivered_value({res.amount}) = {res.amount}"
    return res


def _historical_run_rate(ctx, res: EstimateResult) -> EstimateResult:
    """Policy-approved low-risk fallback. Always flagged as a fallback on the
    workpaper so a reviewer can see the number was not evidenced."""
    hist = [money(h) for h in ctx.historical_amounts if h is not None]
    if not hist:
        return _unsupported(res, "No history available for a run-rate fallback",
                            missing=["HISTORICAL_AMOUNTS"])
    window = hist[-3:]
    avg = money(sum(window) / Decimal(len(window)))
    res.amount = avg
    res.is_fallback = True
    res.inputs |= {"window": [str(h) for h in window], "n": len(window)}
    res.expression = f"avg({', '.join(str(h) for h in window)}) = {avg}"
    res.uncertainties.append(
        "HISTORICAL_RUN_RATE is a fallback, not evidence of this period's service."
    )
    return res


def _non_po_balance_sum(ctx, res: EstimateResult) -> EstimateResult:
    """Eligible pending + settled, less refunds, less anything already carrying an
    AP link. The AP-linked exclusion is the duplicate-accrual guard."""
    included, excluded = [], []
    total = ZERO
    for ln in ctx.non_po_lines:
        if ln.has_ap_link:
            excluded.append({"id": ln.non_po_spend_id, "reason": "AP invoice already exists"})
            continue
        if ln.transaction_status == "VOIDED":
            excluded.append({"id": ln.non_po_spend_id, "reason": "voided"})
            continue
        if ln.transaction_status == "DISPUTED":
            excluded.append({"id": ln.non_po_spend_id, "reason": "disputed - routed to Controller"})
            continue
        total += money(ln.amount)
        included.append({
            "id": ln.non_po_spend_id,
            "merchant": ln.merchant_name,
            "status": ln.transaction_status,
            "amount": str(money(ln.amount)),
        })
    res.amount = money(total)
    res.inputs |= {"included": included, "excluded": excluded,
                   "included_count": len(included), "excluded_count": len(excluded)}
    res.expression = (
        f"sum(pending+settled-refunds over {len(included)} eligible txns, "
        f"{len(excluded)} excluded) = {res.amount}"
    )
    if ctx.non_po_disputed_count:
        res.uncertainties.append(
            f"{ctx.non_po_disputed_count} disputed transaction(s) excluded pending Controller review"
        )
    return res


_DISPATCH = {
    "FIXED_CONTRACT_RATE": _fixed_contract_rate,
    "USAGE_TIMES_RATE": _usage_times_rate,
    "RECEIVED_QUANTITY_TIMES_PRICE": _received_qty_times_price,
    "MILESTONE_ACCEPTED_AMOUNT": _milestone_accepted,
    "HISTORICAL_RUN_RATE": _historical_run_rate,
    "NON_PO_BALANCE_SUM": _non_po_balance_sum,
}


def _unsupported(res: EstimateResult, reason: str, missing: list[str] | None = None) -> EstimateResult:
    res.supported = False
    res.unsupported_reason = reason
    res.amount = ZERO
    res.expression = "UNSUPPORTED - no amount may be asserted"
    res.missing_evidence.extend(missing or [])
    return res


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def estimate(ctx, active_rules: list[ActiveRule] | None = None) -> EstimateResult:
    """Pure. Same context + same rules => same result, always."""
    active_rules = active_rules or []
    res = EstimateResult(
        method="", amount=ZERO, currency=ctx.currency, expression="", inputs={}
    )

    method = DEFAULT_METHOD_BY_TYPE.get(ctx.purchase_type)
    fired = rules_in_scope(ctx, active_rules)

    prohibited: set[str] = set()
    for ar in fired:
        a = ar.rule.action
        tag = f"[{ar.learning_id}] {ar.rule.rule_key}"

        if a.action_type == "REQUIRE_EVIDENCE":
            if a.evidence_type not in ctx.evidence:
                res.missing_evidence.append(a.evidence_type)
                res.rule_required_missing.append(a.evidence_type)
                res.rule_effects.append(
                    f"{tag}: requires evidence {a.evidence_type} - NOT PRESENT"
                )
            else:
                res.rule_effects.append(f"{tag}: required evidence {a.evidence_type} present")

        elif a.action_type == "PROHIBIT_ESTIMATOR":
            prohibited.add(a.estimator)
            res.rule_effects.append(f"{tag}: prohibits estimator {a.estimator}")

        elif a.action_type == "SELECT_ESTIMATOR":
            method = a.estimator
            res.rule_effects.append(f"{tag}: selects estimator {a.estimator}")

        elif a.action_type == "REQUIRE_OUTREACH":
            res.routing_override = "REQUIRE_OUTREACH"
            res.outreach_role = a.outreach_role
            res.rule_effects.append(f"{tag}: requires outreach to {a.outreach_role}")

        elif a.action_type == "REQUIRE_CONTROLLER":
            # Controller review outranks an outreach hop.
            res.routing_override = "REQUIRE_CONTROLLER"
            res.rule_effects.append(f"{tag}: requires Controller review")

    if method is None:
        return _unsupported(res, f"No estimator defined for purchase_type={ctx.purchase_type}")

    if method in prohibited:
        alt = "HISTORICAL_RUN_RATE" if method != "HISTORICAL_RUN_RATE" else None
        if alt is None or alt in prohibited:
            return _unsupported(res, f"Estimator {method} prohibited by an active rule and no alternative permitted")
        res.rule_effects.append(f"falling back {method} -> {alt} (prohibited)")
        method = alt

    res.method = method
    res = _DISPATCH[method](ctx, res)

    # A rule that demanded evidence which is absent must never resolve to a
    # confident number, whatever the estimator produced.
    if res.missing_evidence and res.supported:
        res.supported = False
        res.unsupported_reason = (
            "Active rule requires evidence that is not on the record: "
            + ", ".join(sorted(set(res.missing_evidence)))
        )
        res.uncertainties.append(res.unsupported_reason)

    return res
