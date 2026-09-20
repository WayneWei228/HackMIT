"""Shared result type for the deterministic estimators. Every dollar comes from here."""

from __future__ import annotations

from pydantic import BaseModel, Field

from trueup.schemas import Evidence


class Estimate(BaseModel):
    model: str
    amount_cents: int | None  # None means the estimator lacks data and needs outreach
    inputs: dict = Field(default_factory=dict)
    reasoning: str
    evidence: list[Evidence] = Field(default_factory=list)
    missing: str | None = None  # what is needed when amount_cents is None
    flags: list[str] = Field(default_factory=list)  # e.g. po_contract_mismatch
