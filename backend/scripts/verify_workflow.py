"""Model-check the workflow graph and its gates: python scripts/verify_workflow.py.

The graph is a finite table, so its safety properties are checked exhaustively, not sampled. This
proves properties of the workflow and its gates. It does not prove a model reads a document right.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.store.workflow import allowed_transitions  # noqa: E402
from trueup.verification import HandoffGate, verify_workflow_graph  # noqa: E402
from trueup.verification import states as st  # noqa: E402
from trueup.verification.gates import EDGE_GATES  # noqa: E402
from trueup.verification.graph import GraphReport, render  # noqa: E402


def show(title: str, report: GraphReport) -> None:
    print(title)
    print(
        f"  {report.edges} edges, {report.states} states, {report.product_states} reachable "
        f"(state, facts) pairs, {report.paths} simple paths to a terminal state"
    )
    for line in render(report):
        print(f"  {line}")
    print()


def broken_graph():
    graph = {state: set(targets) for state, targets in allowed_transitions().items()}
    graph[st.BLOCKED].add(st.DRAFT)
    return {state: frozenset(targets) for state, targets in graph.items()}


def main() -> None:
    real = verify_workflow_graph()
    show("THE REAL WORKFLOW", real)

    unguarded = dict(EDGE_GATES)
    unguarded[(st.BLOCKED, st.DRAFT)] = HandoffGate(
        edge=(st.BLOCKED, st.DRAFT), checks=("VER-01", "VER-02")
    )
    planted = verify_workflow_graph(graph=broken_graph(), gates=unguarded)
    show("PLANTED DEFECT: an extra edge BLOCKED -> READY_TO_DRAFT with no guard", planted)

    gate = EDGE_GATES[(st.CONTROLLER, st.LEARN)]
    weakened = dict(EDGE_GATES)
    weakened[gate.edge] = HandoffGate(**{**gate.__dict__, "requires": frozenset()})
    hole = verify_workflow_graph(gates=weakened)
    show("PLANTED DEFECT: CONTROLLER -> LEARN no longer requires a drafted accrual", hole)

    missing = verify_workflow_graph(graph=broken_graph())
    print("EXPECTED")
    checks = [
        ("every property is proved on the real workflow", real.holds),
        ("the real workflow has 37 edges and every one has a gate", real.get("completeness").holds),
        (
            "an unguarded BLOCKED -> DRAFT edge breaks policy-before-posting",
            not planted.get("policy_before_posting").holds,
        ),
        (
            "the same edge lets a blocked accrual post without the Controller",
            not planted.get("blocked_needs_controller").holds,
        ),
        (
            "an edge with no registered gate is reported as incomplete",
            not missing.get("completeness").holds,
        ),
        (
            "dropping the drafted-accrual guard lets an accrual close undrafted",
            not hole.get("closed_needs_accrual").holds,
        ),
        (
            "each failure names the shortest path that breaks it",
            all(
                p.counterexample and p.counterexample[0] == "DETECTED/SEARCH_AP"
                for p in (planted.get("policy_before_posting"), hole.get("closed_needs_accrual"))
            ),
        ),
    ]
    for text, ok in checks:
        print(f"  {text:74} [{'hit' if ok else 'MISS'}]")
    print(f"\n{sum(ok for _, ok in checks)}/{len(checks)} expected outcomes matched")


if __name__ == "__main__":
    main()
