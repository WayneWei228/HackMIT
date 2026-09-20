"""The typed action proposal and the verifier's answer.

An agent's output at a handoff is described as an `ActionProposal`. A deterministic gate checks it
against encoded company controls and answers with a `VerificationResult`. Nothing here proves an
AI's reading of a document is correct; it proves the action satisfies the controls.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from trueup.store.types import coerce_money

POLICY_VERSION = "1.0"


class ActionType(StrEnum):
    DETECT_OBLIGATION = "DETECT_OBLIGATION"
    LOOKUP_INVOICE = "LOOKUP_INVOICE"
    SELECT_FILES = "SELECT_FILES"
    EXTRACT_FACTS = "EXTRACT_FACTS"
    CLASSIFY_OBLIGATION = "CLASSIFY_OBLIGATION"
    PROPOSE_ESTIMATE = "PROPOSE_ESTIMATE"
    ROUTE_BY_POLICY = "ROUTE_BY_POLICY"
    SEND_OUTREACH = "SEND_OUTREACH"
    PROCESS_REPLY = "PROCESS_REPLY"
    CONTROLLER_DECISION = "CONTROLLER_DECISION"
    PROPOSE_ENTRY = "PROPOSE_ENTRY"
    POST_ACCRUAL = "POST_ACCRUAL"
    RECORD_TRUE_UP = "RECORD_TRUE_UP"
    PROPOSE_RULE = "PROPOSE_RULE"
    APPROVE_RULE = "APPROVE_RULE"
    REVIEW_FINDING = "REVIEW_FINDING"


class Verdict(StrEnum):
    PERMIT = "PERMIT"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    OUTREACH = "OUTREACH"


# How strict each verdict is. The strictest failing check decides, as in the Policy agent.
STRICTNESS = {Verdict.PERMIT: 0, Verdict.REVIEW: 1, Verdict.OUTREACH: 2, Verdict.BLOCK: 3}


def _no_float(value: Any) -> Any:
    if value is None:
        return None
    try:
        return coerce_money(value)
    except TypeError as exc:
        raise ValueError(str(exc)) from exc


class ActionProposal(BaseModel):
    """What an agent wants to do at a handoff. Amounts come from the workpaper, never a model."""

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    actor: str
    obligation_id: str
    period: str
    amount: Decimal | None = None
    currency: str = "USD"
    calculation_method: str | None = None
    accounts: dict[str, str] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    policy_version: str = POLICY_VERSION
    stage_from: str
    stage_to: str

    @field_validator("amount", "confidence", mode="before")
    @classmethod
    def _exact(cls, value: Any) -> Any:
        return _no_float(value)

    @field_serializer("amount", "confidence")
    def _as_string(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    name: str
    passed: bool
    skipped: bool = False
    on_fail: Verdict = Verdict.BLOCK
    expected: str | None = None
    actual: str | None = None
    detail: str


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    checks: list[CheckResult]
    policy_version: str = POLICY_VERSION
    timestamp: datetime
    actor: str | None

    @property
    def applied(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.skipped]

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.applied if c.passed)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def summary(self) -> str:
        applied = self.applied
        text = f"{self.passed_count}/{len(applied)} checks passed"
        skipped = len(self.checks) - len(applied)
        return text + (f", {skipped} not applicable" if skipped else "")


def strictest(results: list[CheckResult]) -> Verdict:
    """The verdict a set of check results calls for: PERMIT when every applied check passed."""
    verdict = Verdict.PERMIT
    for check in results:
        if not check.passed and STRICTNESS[check.on_fail] > STRICTNESS[verdict]:
            verdict = check.on_fail
    return verdict
