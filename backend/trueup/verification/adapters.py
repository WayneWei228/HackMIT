"""Turn what an agent just wrote into the typed action proposal the verifier checks.

The adapters read the tables; they never rewrite an agent's output. The amount always comes from
the workpaper, so no model can put a number into a proposal.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.store import enums as e
from trueup.store import models as m
from trueup.verification import states as st
from trueup.verification.models import POLICY_VERSION, ActionProposal, ActionType
from trueup.verification.states import State, label

_ACTION_BY_STATE: dict[State, ActionType] = {
    st.INITIAL: ActionType.DETECT_OBLIGATION,
    st.SEARCH: ActionType.LOOKUP_INVOICE,
    st.GATHER: ActionType.EXTRACT_FACTS,
    st.CLASSIFY: ActionType.CLASSIFY_OBLIGATION,
    st.ESTIMATE: ActionType.PROPOSE_ESTIMATE,
    st.POLICY: ActionType.ROUTE_BY_POLICY,
    st.FALLBACK: ActionType.PROPOSE_INCOMPLETE_ESTIMATE,
    st.OUTREACH: ActionType.PROCESS_REPLY,
    st.CONTROLLER: ActionType.CONTROLLER_DECISION,
    st.BLOCKED: ActionType.CONTROLLER_DECISION,
    st.DRAFT: ActionType.PROPOSE_ENTRY,
    st.WAIT: ActionType.RECORD_TRUE_UP,
    st.RECONCILE: ActionType.RECORD_TRUE_UP,
    st.LEARN: ActionType.PROPOSE_RULE,
}


# An edge whose meaning differs from the state it leaves: no reply, not a reply.
_ACTION_BY_EDGE: dict[tuple[State, State | None], ActionType] = {
    (st.OUTREACH, st.FALLBACK): ActionType.EXPIRE_OUTREACH,
}


def action_for(frm: State, to: State | None = None) -> ActionType:
    return _ACTION_BY_EDGE.get((frm, to)) or _ACTION_BY_STATE[frm]


def build_proposal(
    session: Session,
    ob: m.TrueUpObligation,
    frm: State,
    to: State,
    actor: str | None,
    *,
    action: ActionType | None = None,
) -> tuple[ActionProposal | None, str | None]:
    """The proposal for a handoff, or None and the reason it cannot be built."""
    wp = (
        session.get(m.TrueUpWorkpaper, ob.current_workpaper_id) if ob.current_workpaper_id else None
    )
    cards = list(
        session.scalars(
            select(m.TrueUpEvidence)
            .where(m.TrueUpEvidence.obligation_id == ob.obligation_id)
            .order_by(m.TrueUpEvidence.evidence_id)
        )
    )
    live = [c for c in cards if c.status != e.EvidenceCardStatus.SUPERSEDED]
    confidence: Decimal | None = min((c.confidence for c in live), default=None)
    try:
        proposal = ActionProposal(
            action_type=action or action_for(frm, to),
            actor=actor or "unknown",
            obligation_id=ob.obligation_id,
            period=ob.period,
            amount=wp.proposed_amount if wp is not None else None,
            currency=(wp.currency if wp is not None and wp.currency else "USD"),
            calculation_method=wp.estimation_method.value if wp is not None else None,
            accounts=(
                {"debit": wp.expense_account, "credit": wp.accrual_liability_account}
                if wp is not None
                else None
            ),
            evidence_ids=[c.evidence_id for c in live],
            confidence=confidence,
            policy_version=POLICY_VERSION,
            stage_from=label(frm),
            stage_to=label(to),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        return None, str(exc).splitlines()[0]
    return proposal, None
