"""A scripted decision maker in place of the human Controller, for the demo script and tests.

The orchestrator never approves anything itself. This class is the caller-supplied decision maker:
it approves the vendors it is told to and leaves everything else in the queue.
"""

from __future__ import annotations

from collections.abc import Iterable

from trueup.agents.controller_workspace import ReviewPacket
from trueup.close_orchestrator import ControllerAction, RuleCandidate, RuleDecision
from trueup.store import enums as e


class ScriptedController:
    def __init__(
        self,
        person_id: str,
        *,
        approve_vendors: Iterable[str] = (),
        approve_rules: bool = True,
    ):
        self.person_id = person_id
        self.approve_vendors = frozenset(approve_vendors)
        self.approve_rules = approve_rules
        self.seen: list[str] = []

    def review(self, packet: ReviewPacket) -> ControllerAction | None:
        self.seen.append(packet.obligation.obligation_id)
        vendor_id = packet.obligation.vendor_id
        if vendor_id in self.approve_vendors and e.ControllerDecision.APPROVE in (
            packet.allowed_decisions
        ):
            return ControllerAction(
                decision=e.ControllerDecision.APPROVE,
                notes="Reviewed the workpaper and the evidence; approved as estimated.",
            )
        return None

    def review_rule(self, candidate: RuleCandidate) -> RuleDecision | None:
        if not self.approve_rules:
            return None
        return RuleDecision(approve=True, notes="Replay passed and the rule names no vendor.")
