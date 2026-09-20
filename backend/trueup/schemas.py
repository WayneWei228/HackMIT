"""Pydantic models shared across agents.

The ProposedJE validators are the product's core guarantee: no journal entry
exists without evidence, and every entry balances exactly (integer cents).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CloseStatus = Literal["done", "waiting", "blocked", "needs_review"]
AmountType = Literal["fixed", "dynamic"]
Cadence = Literal["recurring", "one_time"]


class Evidence(BaseModel):
    source_table: str
    row_id: int | str
    note: str | None = None


class JELine(BaseModel):
    account: str
    debit_cents: int = Field(default=0, ge=0)
    credit_cents: int = Field(default=0, ge=0)


class ProposedJE(BaseModel):
    lines: list[JELine]
    evidence: list[Evidence]
    rule: str
    reason: str
    status: Literal["auto_approved", "needs_review", "approved", "rejected"]

    @field_validator("evidence")
    @classmethod
    def evidence_must_be_non_empty(cls, value: list[Evidence]) -> list[Evidence]:
        if not value:
            raise ValueError("a proposed JE must cite at least one evidence row")
        return value

    @field_validator("lines")
    @classmethod
    def lines_must_be_non_empty(cls, value: list[JELine]) -> list[JELine]:
        if not value:
            raise ValueError("a proposed JE must have at least one line")
        return value

    @model_validator(mode="after")
    def lines_must_balance(self) -> ProposedJE:
        debits = sum(line.debit_cents for line in self.lines)
        credits = sum(line.credit_cents for line in self.lines)
        if debits != credits:
            raise ValueError(f"JE does not balance: debits {debits} != credits {credits} cents")
        return self


class Classification(BaseModel):
    """What kind of purchase a PO line is."""

    amount_type: AmountType
    cadence: Cadence

    @property
    def kind(self) -> str:
        return f"{self.amount_type}_{self.cadence}"


class ClassificationResult(BaseModel):
    """Rules answer, Jev answer, and the reconciled final answer for one PO line."""

    po_line_id: str
    rules: Classification
    jev: Classification | None = None
    jev_confidence: float | None = None
    final: Classification
    agreed: bool
    needs_human: bool
    contradictions: list[str] = Field(default_factory=list)
    suggested: Classification | None = None  # what we think the row should say


class Obligation(BaseModel):
    """One expected vendor obligation for a period, produced by detection."""

    period: str
    source: Literal["po", "card"]
    obligation_key: str
    vendor_id: str | None = None
    po_number: str | None = None
    po_line_id: str | None = None
    amount_cents: int | None = None  # set for card spend, which is accrued directly
    evidence: list[Evidence]
