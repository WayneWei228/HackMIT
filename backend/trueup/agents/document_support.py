"""Which documents must still stand behind an estimate after a person removed files.

Each purchase type needs a few kinds of fact before its amount can be trusted. When a person takes
away the only document that carried one of them, the obligation has lost that support. The table
below is the whole rule; it names fact kinds, never vendors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents.selection_override import withdrawn_keys
from trueup.store import enums as e
from trueup.store import models as m

Route = Literal["outreach", "controller"]


@dataclass(frozen=True)
class Requirement:
    label: str
    keys: frozenset[str]
    status: e.EvidenceStatus
    route: Route


def _need(label: str, status: e.EvidenceStatus, route: Route, *keys: str) -> Requirement:
    return Requirement(label, frozenset(keys), status, route)


_S = e.EvidenceStatus

REQUIREMENTS: dict[e.PurchaseType, tuple[Requirement, ...]] = {
    e.PurchaseType.FIXED_RECURRING: (
        _need("monthly fee", _S.MISSING_RATE, "controller", "MONTHLY_FEE"),
    ),
    e.PurchaseType.USAGE_BASED: (
        _need("contract rate", _S.MISSING_RATE, "controller", "UNIT_RATE"),
        _need(
            "usage report",
            _S.MISSING_USAGE,
            "outreach",
            "USAGE_QUANTITY",
            "USAGE_COVERAGE_END",
        ),
    ),
    e.PurchaseType.RECEIPT_BASED: (
        _need("purchase order price", _S.MISSING_RATE, "controller", "UNIT_RATE", "ORDER_TOTAL"),
        _need(
            "goods receipt",
            _S.MISSING_SERVICE_CONFIRMATION,
            "outreach",
            "RECEIVED_QUANTITY",
        ),
    ),
    e.PurchaseType.MILESTONE_BASED: (
        _need(
            "campaign order budget",
            _S.MISSING_RATE,
            "controller",
            "BUDGET_CEILING",
            "ORDER_TOTAL",
        ),
        _need(
            "campaign delivery report",
            _S.MISSING_SERVICE_CONFIRMATION,
            "outreach",
            "DELIVERED_AMOUNT",
        ),
    ),
    e.PurchaseType.PREPAID: (
        _need(
            "amortization schedule",
            _S.MISSING_RATE,
            "controller",
            "PREPAID_SERVICE_MONTHS",
            "TERM_MONTHS",
        ),
        _need("prepaid invoice", _S.MISSING_RATE, "controller", "INVOICE_AMOUNT", "ORDER_TOTAL"),
    ),
}


def support_gaps(session: Session, obligation: m.TrueUpObligation) -> list[Requirement]:
    """Requirements whose supporting facts a person removed and no remaining document restates."""
    removed = withdrawn_keys(session, obligation.obligation_id)
    if not removed:
        return []
    standing = {
        (card.value_json or {}).get("key")
        for card in session.scalars(
            select(m.TrueUpEvidence).where(
                m.TrueUpEvidence.obligation_id == obligation.obligation_id,
                m.TrueUpEvidence.source_table == "document",
                m.TrueUpEvidence.status == e.EvidenceCardStatus.VERIFIED,
            )
        )
    }
    return [
        need
        for need in REQUIREMENTS.get(obligation.purchase_type, ())
        if need.keys & removed and not need.keys & standing
    ]
