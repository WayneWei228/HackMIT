"""Thresholds: how much confidence buys how much autonomy."""

from __future__ import annotations

ACT = 0.90
CAUTION = 0.50
NOUL_YES = 0.80
NOUL_NO = 0.20


def gate(confidence: float | None, amount: float | None = None, materiality: float | None = None) -> str:
    """ACT / VERIFY / REVIEW. A material amount promotes VERIFY to REVIEW."""
    if confidence is None:
        return "REVIEW"
    if confidence >= ACT:
        decision = "ACT"
    elif confidence >= CAUTION:
        decision = "VERIFY"
    else:
        decision = "REVIEW"
    if decision == "VERIFY" and amount is not None and materiality is not None and amount >= materiality:
        return "REVIEW"
    return decision
