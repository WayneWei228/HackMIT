"""One gate per workflow edge: which checks run, and what the edge means for the model check.

The table is the single place that says what verifies each handoff. `verify_workflow_graph()`
reads the same table, so the proofs and the runtime cannot drift apart. An edge without a gate
is a defect: the model check reports it and the runtime refuses to move along it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from trueup.store.workflow import allowed_transitions
from trueup.verification import states as st
from trueup.verification.checks import REGISTRY, Handoff
from trueup.verification.models import (
    ActionType,
    CheckResult,
    Verdict,
    VerificationResult,
    strictest,
)
from trueup.verification.states import State

Edge = tuple[State, State]

# What the model check tracks along a path, about the current workpaper.
ESTIMATED = "estimated"
POLICY_EVALUATED = "policy_evaluated"
POLICY_BLOCKED = "policy_blocked"
CONTROLLER_APPROVED = "controller_approved"
DRAFTED = "drafted"
RULE_ACTIVE = "rule_active"


@dataclass(frozen=True)
class HandoffGate:
    edge: Edge
    checks: tuple[str, ...]
    requires: frozenset[str] = frozenset()
    forbids: frozenset[str] = frozenset()
    establishes: frozenset[str] = frozenset()
    clears: frozenset[str] = frozenset()
    by_controller: bool = False


_FRESH = frozenset({POLICY_EVALUATED, POLICY_BLOCKED, CONTROLLER_APPROVED})
_STALE = _FRESH | {ESTIMATED}
_BASE = ("VER-01", "VER-02")
_EVIDENCE = ("VER-03", "VER-04")
_TO_DRAFT = ("VER-06", "VER-09", "VER-11", "VER-12", "VER-15")


def _gate(frm: State, to: State, *checks: str, **spec: object) -> HandoffGate:
    return HandoffGate(edge=(frm, to), checks=(*_BASE, *checks), **spec)  # type: ignore[arg-type]


def _f(*names: str) -> frozenset[str]:
    return frozenset(names)


def _table() -> dict[Edge, HandoffGate]:
    g = _gate
    gates = [
        g(st.INITIAL, st.SEARCH, "VER-11"),
        g(st.SEARCH, st.NO_ACCRUAL, "VER-14"),
        g(st.SEARCH, st.GATHER, "VER-14", clears=_STALE),
        g(st.SEARCH, st.OUTREACH),
        g(st.SEARCH, st.CONTROLLER, "VER-14"),
        g(st.GATHER, st.CLASSIFY, *_EVIDENCE, "VER-28", clears=_STALE),
        g(st.GATHER, st.OUTREACH),
        g(st.GATHER, st.CONTROLLER),
        g(st.CLASSIFY, st.ESTIMATE, "VER-17", clears=_STALE),
        g(st.CLASSIFY, st.OUTREACH),
        g(st.CLASSIFY, st.CONTROLLER),
        g(
            st.ESTIMATE,
            st.POLICY,
            *_EVIDENCE,
            "VER-05",
            "VER-06",
            "VER-07",
            "VER-08",
            "VER-33",
            "VER-09",
            "VER-15",
            clears=_FRESH,
            establishes=_f(ESTIMATED),
        ),
        g(st.ESTIMATE, st.OUTREACH),
        g(st.ESTIMATE, st.CONTROLLER),
        g(
            st.POLICY,
            st.DRAFT,
            "VER-10",
            *_TO_DRAFT,
            requires=_f(ESTIMATED),
            forbids=_f(DRAFTED),
            establishes=_f(POLICY_EVALUATED),
        ),
        g(
            st.POLICY,
            st.OUTREACH,
            "VER-10",
            requires=_f(ESTIMATED),
            establishes=_f(POLICY_EVALUATED),
        ),
        g(
            st.POLICY,
            st.CONTROLLER,
            "VER-10",
            requires=_f(ESTIMATED),
            establishes=_f(POLICY_EVALUATED),
        ),
        g(st.POLICY, st.BLOCKED, "VER-10", requires=_f(ESTIMATED), establishes=_f(POLICY_BLOCKED)),
        g(
            st.FALLBACK,
            st.POLICY,
            *_EVIDENCE,
            "VER-05",
            "VER-06",
            "VER-07",
            "VER-30",
            "VER-31",
            "VER-32",
            "VER-09",
            "VER-15",
            clears=_FRESH,
            establishes=_f(ESTIMATED),
        ),
        g(st.FALLBACK, st.CONTROLLER),
        g(st.OUTREACH, st.SEARCH, "VER-03", clears=_STALE),
        g(st.OUTREACH, st.GATHER, "VER-03", clears=_STALE),
        g(st.OUTREACH, st.ESTIMATE, "VER-03", clears=_STALE),
        g(st.OUTREACH, st.POLICY, "VER-03", "VER-07", requires=_f(ESTIMATED), clears=_FRESH),
        # No reply by the company's deadline: estimate from the incomplete data, never past policy.
        g(st.OUTREACH, st.FALLBACK, "VER-29", clears=_STALE),
        g(st.OUTREACH, st.CONTROLLER),
        # A vendor's answer to a dispute returns a posted accrual to the wait for the corrected
        # invoice. It is only reachable with an accrual already drafted and cleared by policy.
        g(
            st.OUTREACH,
            st.WAIT,
            "VER-26",
            "VER-27",
            requires=_f(DRAFTED, ESTIMATED, POLICY_EVALUATED),
            forbids=_f(POLICY_BLOCKED),
        ),
        g(
            st.CONTROLLER,
            st.DRAFT,
            "VER-13",
            "VER-10",
            *_TO_DRAFT[1:],
            requires=_f(POLICY_EVALUATED),
            forbids=_f(POLICY_BLOCKED, DRAFTED),
            establishes=_f(CONTROLLER_APPROVED),
            by_controller=True,
        ),
        g(st.CONTROLLER, st.OUTREACH, "VER-13", "VER-25", by_controller=True),
        g(st.CONTROLLER, st.NO_ACCRUAL, "VER-13", by_controller=True),
        g(st.CONTROLLER, st.LEARN, "VER-13", "VER-20", by_controller=True, requires=_f(DRAFTED)),
        g(st.BLOCKED, st.GATHER, "VER-13", by_controller=True, clears=_STALE),
        g(st.BLOCKED, st.ESTIMATE, "VER-13", by_controller=True, clears=_STALE),
        g(st.BLOCKED, st.NO_ACCRUAL, "VER-13", by_controller=True),
        g(
            st.DRAFT,
            st.WAIT,
            "VER-09",
            "VER-11",
            "VER-12",
            "VER-23",
            requires=_f(POLICY_EVALUATED),
            forbids=_f(POLICY_BLOCKED),
            establishes=_f(DRAFTED),
        ),
        g(st.DRAFT, st.BLOCKED, establishes=_f(POLICY_BLOCKED)),
        g(st.WAIT, st.RECONCILE, "VER-20", requires=_f(DRAFTED)),
        g(st.RECONCILE, st.LEARN, "VER-21", requires=_f(DRAFTED)),
        g(st.RECONCILE, st.CLOSED, "VER-21", requires=_f(DRAFTED)),
        g(st.RECONCILE, st.CONTROLLER, "VER-21", requires=_f(DRAFTED)),
        g(st.LEARN, st.CLOSED, "VER-22", "VER-15"),
    ]
    return {gate.edge: gate for gate in gates}


EDGE_GATES: Mapping[Edge, HandoffGate] = _table()

# Actions that are not workflow edges but still carry a typed proposal and a verdict.
ACTION_CHECKS: Mapping[ActionType, tuple[str, ...]] = {
    ActionType.POST_ACCRUAL: ("VER-09", "VER-11", "VER-12", "VER-23"),
    ActionType.APPROVE_RULE: ("VER-24",),
}


def edges_of(graph: Mapping[State, frozenset[State]] | None = None) -> list[Edge]:
    graph = graph if graph is not None else allowed_transitions()
    return [(frm, to) for frm, targets in graph.items() for to in sorted(targets, key=str)]


def gate_for(edge: Edge, gates: Mapping[Edge, HandoffGate] | None = None) -> HandoffGate | None:
    return (gates if gates is not None else EDGE_GATES).get(edge)


def run_checks(handoff: Handoff, check_ids: Iterable[str]) -> list[CheckResult]:
    """Run each check. A check that cannot run fails closed instead of letting the move through."""
    results = []
    for check_id in check_ids:
        try:
            results.append(REGISTRY[check_id](handoff))
        except Exception as exc:
            results.append(
                CheckResult(
                    check_id=check_id,
                    name="The check could not run",
                    passed=False,
                    on_fail=Verdict.BLOCK,
                    detail=f"{check_id} raised {type(exc).__name__}: {exc}",
                )
            )
    return results


def verify_edge(
    handoff: Handoff, gates: Mapping[Edge, HandoffGate] | None = None
) -> VerificationResult:
    """Run the gate for `handoff`'s edge. An edge with no gate is blocked."""
    gate = gate_for((handoff.frm, handoff.to), gates)
    if gate is None:
        results = [
            CheckResult(
                check_id="VER-00",
                name="Every edge has a gate",
                passed=False,
                on_fail=Verdict.BLOCK,
                detail=(
                    f"No gate is registered for {st.label(handoff.frm)} to {st.label(handoff.to)}."
                ),
            )
        ]
    else:
        results = run_checks(handoff, gate.checks)
    return VerificationResult(
        verdict=strictest(results),
        checks=results,
        timestamp=_aware(handoff.at),
        actor=handoff.actor,
    )


def verify_action(handoff: Handoff, action: ActionType) -> VerificationResult:
    results = run_checks(handoff, ACTION_CHECKS[action])
    return VerificationResult(
        verdict=strictest(results),
        checks=results,
        timestamp=_aware(handoff.at),
        actor=handoff.actor,
    )


def _aware(stamp: datetime) -> datetime:
    from datetime import UTC

    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
