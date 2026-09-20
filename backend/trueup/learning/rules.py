"""Typed playbook rules that change how Estimation behaves once a Controller has approved them.

A rule is a pydantic `CandidateRule` stored in `trueup_learning_rules.candidate_rule_json`.
Only rows whose status is ACTIVE are ever consulted; candidates, rejected and revoked rows are
inert. A rule is a predicate over FEATURES (purchase type, contract terms), never over a vendor:
the model forbids unknown fields, rejects any vendor id in its text, and `load_active_rules`
also rejects any vendor name found in a stored rule.

Public interface for the Learning agent and its replay harness:
- `CandidateRule.apply_contract_escalator(provenance)` builds the one supported rule kind.
- `features_for(obligation, contract)` and `matches(rule, features)` decide applicability.
- `load_active_rules(session)` returns `(learning_id, rule)` for every ACTIVE row.
- `trueup.agents.estimation_agent.usage_rate(...)` is the pure rate function that takes `rules`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m

_VENDOR_ID = re.compile(r"\bVEN-", re.IGNORECASE)


class BiasGuardError(ValueError):
    """A rule names a vendor, which a playbook rule may never do."""


class RuleKind(StrEnum):
    APPLY_CONTRACT_ESCALATOR = "APPLY_CONTRACT_ESCALATOR"


class RulePredicate(BaseModel):
    """When a rule applies: purchase types, plus an escalator that is in effect by period end."""

    model_config = ConfigDict(extra="forbid")

    purchase_types: list[e.PurchaseType] = Field(min_length=1)
    requires_escalator_by_period_end: bool = True


class RuleLifecycle(BaseModel):
    """How much live evidence backs an approved rule: provisional until confirmed 3 times."""

    model_config = ConfigDict(extra="forbid")

    stage: Literal["PROVISIONAL", "CONFIRMED"] = "PROVISIONAL"
    uses: int = 0
    contradictions: int = 0


class CandidateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RuleKind
    predicate: RulePredicate
    description: str
    provenance: list[str] = Field(default_factory=list)
    lifecycle: RuleLifecycle | None = None

    def signature(self) -> tuple[str, tuple[str, ...], bool]:
        """Two rules with the same signature are the same rule, whoever proposed them."""
        predicate = self.predicate
        types = tuple(sorted(t.value for t in predicate.purchase_types))
        return (self.kind.value, types, predicate.requires_escalator_by_period_end)

    @model_validator(mode="after")
    def _no_vendor_ids(self) -> CandidateRule:
        if _VENDOR_ID.search(self.model_dump_json()):
            raise BiasGuardError("a rule must not reference a vendor id")
        return self

    @classmethod
    def apply_contract_escalator(cls, provenance: Iterable[str] = ()) -> CandidateRule:
        return cls(
            kind=RuleKind.APPLY_CONTRACT_ESCALATOR,
            predicate=RulePredicate(purchase_types=[e.PurchaseType.USAGE_BASED]),
            description=(
                "Honor a usage contract's escalator step-up in the unit rate once its "
                "effective date has passed."
            ),
            provenance=list(provenance),
        )


class RuleFeatures(BaseModel):
    """The facts about one obligation that a predicate may look at. No vendor fields."""

    purchase_type: e.PurchaseType
    escalator_percent: Decimal | None
    escalator_effective_date: date | None
    period_end: date


def features_for(obligation: m.TrueUpObligation, contract: m.CompanyContract) -> RuleFeatures:
    return RuleFeatures(
        purchase_type=obligation.purchase_type,
        escalator_percent=contract.escalator_percent,
        escalator_effective_date=contract.escalator_effective_date,
        period_end=obligation.service_end_date,
    )


def matches(rule: CandidateRule, features: RuleFeatures) -> bool:
    predicate = rule.predicate
    if features.purchase_type not in predicate.purchase_types:
        return False
    if predicate.requires_escalator_by_period_end:
        effective = features.escalator_effective_date
        if features.escalator_percent is None or effective is None:
            return False
        return effective <= features.period_end
    return True


def reject_vendor_references(rule: CandidateRule, vendors: Iterable[tuple[str, str]]) -> None:
    """Raise `BiasGuardError` if the rule's text contains any known vendor id or name."""
    text = rule.model_dump_json().lower()
    for vendor_id, vendor_name in vendors:
        for term in (vendor_id, vendor_name):
            if term and re.search(rf"\b{re.escape(term.lower())}\b", text):
                raise BiasGuardError(f"a rule must not reference the vendor {term!r}")


def load_active_rules(session: Session) -> list[tuple[str, CandidateRule]]:
    """Every ACTIVE rule as `(learning_id, rule)`, oldest first. Other statuses are ignored."""
    rows = session.scalars(
        select(m.TrueUpLearningRule)
        .where(m.TrueUpLearningRule.status == e.LearningStatus.ACTIVE)
        .order_by(m.TrueUpLearningRule.created_at, m.TrueUpLearningRule.learning_id)
    ).all()
    rows = [r for r in rows if r.candidate_rule_json is not None]
    if not rows:
        return []
    vendors = [(v.vendor_id, v.vendor_name) for v in session.scalars(select(m.CompanyVendor)).all()]
    loaded = []
    for row in rows:
        rule = CandidateRule.model_validate(row.candidate_rule_json)
        reject_vendor_references(rule, vendors)
        loaded.append((row.learning_id, rule))
    return loaded
