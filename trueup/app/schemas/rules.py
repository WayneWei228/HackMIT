"""Typed learning rules.

A learned rule is not prose and not code. It is a small typed record whose scope
is a list of enumerated predicates and whose action is one of five allowed verbs.
That is what makes it inspectable by a Controller and replayable by a machine.

The forbidden-action list from the spec is enforced here, deterministically, so a
malformed or over-reaching candidate cannot reach replay, let alone activation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerated scope predicates. A rule can only ever ask about these; it cannot
# carry an arbitrary expression.
# ---------------------------------------------------------------------------
ConditionCode = Literal[
    "ALWAYS",
    "CONTRACT_HAS_ESCALATOR",
    "CONTRACT_ESCALATOR_EFFECTIVE_ON_OR_BEFORE_SERVICE_START",
    "NO_INVOICE_FOUND",
    "USAGE_EVIDENCE_PRESENT",
    "USAGE_EVIDENCE_MISSING",
    "PARTIAL_RECEIPT",
    "MULTI_PERIOD_SERVICE_WINDOW",
    "NON_PO_HAS_PENDING_TRANSACTIONS",
]

PurchaseType = Literal[
    "FIXED_RECURRING",
    "USAGE_BASED",
    "RECEIPT_BASED",
    "MILESTONE_BASED",
    "NON_PO_CARD_SPEND",
    "NON_PO_DIRECT_SPEND",
    "UNKNOWN",
]

# The six estimators from the spec. A rule may select among these; it may never
# introduce a new one.
EstimatorMethod = Literal[
    "FIXED_CONTRACT_RATE",
    "USAGE_TIMES_RATE",
    "RECEIVED_QUANTITY_TIMES_PRICE",
    "MILESTONE_ACCEPTED_AMOUNT",
    "HISTORICAL_RUN_RATE",
    "NON_PO_BALANCE_SUM",
]

ActionType = Literal[
    "REQUIRE_EVIDENCE",
    "PROHIBIT_ESTIMATOR",
    "SELECT_ESTIMATOR",
    "REQUIRE_OUTREACH",
    "REQUIRE_CONTROLLER",
]

OutreachRole = Literal[
    "AP_OWNER",
    "SERVICE_OWNER",
    "PO_OWNER",
    "PROCUREMENT_OWNER",
    "CARDHOLDER",
    "VENDOR_BILLING_CONTACT",
    "CONTROLLER",
]


class RuleViolation(ValueError):
    """A candidate rule attempted something the spec forbids."""


class RuleScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purchase_types: list[PurchaseType] = Field(default_factory=list)
    conditions: list[ConditionCode] = Field(default_factory=lambda: ["ALWAYS"])

    # Present so that a vendor-specific shortcut is *representable and rejected*
    # rather than quietly slipping through as an unmodelled concept.
    vendor_ids: list[str] = Field(default_factory=list)

    @field_validator("vendor_ids")
    @classmethod
    def _no_vendor_shortcuts(cls, v: list[str]) -> list[str]:
        if v:
            raise RuleViolation(
                "FORBIDDEN: vendor-name-specific shortcut. A rule must generalise "
                "by condition, not name specific vendors."
            )
        return v


class RuleAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: ActionType
    evidence_type: str | None = None
    estimator: EstimatorMethod | None = None
    outreach_role: OutreachRole | None = None
    reason: str = ""

    def model_post_init(self, _ctx) -> None:
        if self.action_type == "REQUIRE_EVIDENCE" and not self.evidence_type:
            raise RuleViolation("REQUIRE_EVIDENCE needs an evidence_type")
        if self.action_type in ("PROHIBIT_ESTIMATOR", "SELECT_ESTIMATOR") and not self.estimator:
            raise RuleViolation(f"{self.action_type} needs an estimator")
        if self.action_type == "REQUIRE_OUTREACH" and not self.outreach_role:
            raise RuleViolation("REQUIRE_OUTREACH needs an outreach_role")


# Keys that, if present anywhere in a candidate payload, mean the proposer tried
# to do something structurally forbidden.
FORBIDDEN_KEYS = {
    "amount", "fixed_amount", "dollar_amount", "override_amount", "set_amount",
    "approval_threshold", "materiality_threshold", "lower_threshold",
    "skip_approval", "auto_post", "post_without_approval",
    "accounting_policy", "period_policy", "close_calendar",
    "override_block", "ignore_block", "bypass_policy",
}


class CandidateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """What the Learning Agent is allowed to propose."""

    rule_key: str
    title: str
    rationale: str
    scope: RuleScope
    action: RuleAction
    source_learning_ids: list[str] = Field(default_factory=list)
    root_cause: str = "UNKNOWN"

    def validate_allowed(self) -> None:
        """Deterministic guard against every forbidden action in the spec.

        Called before replay and again before activation — an LLM proposed the
        text, so it is never trusted to have respected the boundaries itself.
        """
        blob = self.model_dump()
        found = _scan_forbidden(blob)
        if found:
            raise RuleViolation(
                f"FORBIDDEN: candidate rule contains disallowed key(s) {sorted(found)}. "
                "Rules may not set amounts, weaken approvals, auto-post, change "
                "accounting policy, or override a blocking control."
            )
        if self.scope.vendor_ids:
            raise RuleViolation("FORBIDDEN: vendor-specific shortcut")
        if not self.scope.conditions:
            raise RuleViolation("A rule must state at least one scope condition")
        # A rule with scope ALWAYS and no purchase-type narrowing would apply to
        # the entire company; require it to bind to something.
        if self.scope.conditions == ["ALWAYS"] and not self.scope.purchase_types:
            raise RuleViolation(
                "FORBIDDEN: unbounded rule (ALWAYS with no purchase_type scope)"
            )


def _scan_forbidden(obj: object) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS and v not in (None, "", [], {}):
                found.add(k)
            found |= _scan_forbidden(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _scan_forbidden(v)
    return found


def parse_candidate(payload: dict) -> "CandidateRule":
    """Validate a raw candidate payload.

    The scan runs on the RAW dict first. Pydantic would otherwise reject or drop
    an unknown key before the guard could report *which* prohibition was
    attempted, and "unknown field" is a far less useful audit message than
    "tried to set a dollar amount".
    """
    found = _scan_forbidden(payload)
    if found:
        raise RuleViolation(
            f"FORBIDDEN: candidate rule contains disallowed key(s) {sorted(found)}. "
            "Rules may not set amounts, weaken approvals, auto-post, change "
            "accounting policy, or override a blocking control."
        )
    cand = CandidateRule.model_validate(payload)
    cand.validate_allowed()
    return cand


class ActiveRule(BaseModel):
    """An ACTIVE rule as the estimator sees it: the candidate plus its provenance."""

    learning_id: str
    rule: CandidateRule
    approved_by: str
