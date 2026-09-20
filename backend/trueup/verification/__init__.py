"""Encoded controls verified deterministically at every agent handoff.

We do not prove an AI's reading of a document is correct. We verify that every consequential
action satisfies the company's encoded controls, and we model-check the workflow graph itself.
"""

from trueup.verification.gatekeeper import HandoffRefusedError, Verified, Verifier
from trueup.verification.gates import EDGE_GATES, HandoffGate
from trueup.verification.graph import GraphReport, verify_workflow_graph
from trueup.verification.models import (
    ActionProposal,
    ActionType,
    CheckResult,
    Verdict,
    VerificationResult,
)

__all__ = [
    "EDGE_GATES",
    "ActionProposal",
    "ActionType",
    "CheckResult",
    "GraphReport",
    "HandoffGate",
    "HandoffRefusedError",
    "Verdict",
    "Verified",
    "VerificationResult",
    "Verifier",
    "verify_workflow_graph",
]
