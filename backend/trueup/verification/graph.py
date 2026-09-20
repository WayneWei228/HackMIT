"""Model-check the workflow graph and its gates.

The graph is a finite table, so its safety properties can be checked exhaustively instead of
sampled. The check walks every reachable (state, facts) pair, where the facts are what the gates
establish or require along the way (a policy decision was recorded, the Controller approved, an
entry was drafted). An edge is only taken when its gate's requirements hold, exactly as at
runtime. A property fails with the shortest path that breaks it.

This proves properties of the workflow and its gates. It does not prove that a model's reading of
a document is right; the gates check that every action still satisfies the encoded controls.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from trueup.store import enums as e
from trueup.store.workflow import allowed_transitions
from trueup.verification import states as st
from trueup.verification.gates import (
    DRAFTED,
    EDGE_GATES,
    ESTIMATED,
    POLICY_BLOCKED,
    POLICY_EVALUATED,
    RULE_ACTIVE,
    Edge,
    HandoffGate,
    edges_of,
)
from trueup.verification.states import State, label

Graph = Mapping[State, frozenset[State]]

# States from which an accrual can be drafted, posted, reconciled or closed.
POSTING = frozenset({st.DRAFT, st.WAIT, st.RECONCILE, st.LEARN, st.CLOSED})
# States where the accrual itself is drafted or waiting to be posted.
DRAFTING = frozenset({st.DRAFT, st.WAIT})
_BLOCKED_PENDING = "blocked_pending"
_POLICY_BLOCK = "policy_block_open"

_L = e.LearningStatus
# (from, to) -> (who may do it, what must already hold)
RULE_TRANSITIONS: dict[tuple[e.LearningStatus, e.LearningStatus], tuple[str, tuple[str, ...]]] = {
    (_L.TRUE_UP_RECORDED, _L.RULE_CANDIDATE): ("learning", ()),
    (_L.DIAGNOSED, _L.RULE_CANDIDATE): ("learning", ()),
    (_L.RULE_CANDIDATE, _L.REPLAY_PASSED): ("learning", ("replay",)),
    (_L.REPLAY_PASSED, _L.ACTIVE): ("controller", ("replay_passed",)),
    (_L.REPLAY_PASSED, _L.REJECTED): ("controller", ()),
    (_L.RULE_CANDIDATE, _L.REJECTED): ("controller", ()),
    (_L.ACTIVE, _L.REVOKED): ("controller", ()),
}


@dataclass(frozen=True)
class PropertyResult:
    key: str
    title: str
    holds: bool
    scope: str
    counterexample: list[str] | None = None
    detail: str = ""


@dataclass
class GraphReport:
    properties: list[PropertyResult] = field(default_factory=list)
    states: int = 0
    edges: int = 0
    product_states: int = 0
    paths: int = 0

    @property
    def holds(self) -> bool:
        return all(p.holds for p in self.properties)

    def get(self, key: str) -> PropertyResult:
        return next(p for p in self.properties if p.key == key)


def verify_workflow_graph(
    graph: Graph | None = None,
    gates: Mapping[Edge, HandoffGate] | None = None,
    rule_transitions: Mapping[
        tuple[e.LearningStatus, e.LearningStatus], tuple[str, tuple[str, ...]]
    ]
    | None = None,
) -> GraphReport:
    graph = graph if graph is not None else allowed_transitions()
    gates = gates if gates is not None else EDGE_GATES
    rules = rule_transitions if rule_transitions is not None else RULE_TRANSITIONS
    states = set(graph) | {t for targets in graph.values() for t in targets}
    edges = edges_of(graph)

    explored = _explore(graph, gates)
    report = GraphReport(
        states=len(states),
        edges=len(edges),
        product_states=len(explored.seen),
        paths=_count_paths(graph),
    )
    report.properties = [
        _completeness(edges, gates),
        _policy_before_posting(explored),
        _blocked_needs_controller(explored),
        _policy_block_stays_blocked(explored),
        _closed_needs_accrual(explored),
        _drafted_once(explored),
        _no_dead_ends(graph, states, explored),
        _rule_activation(gates, rules, graph),
    ]
    return report


# ---- exploration --------------------------------------------------------------------------------


@dataclass
class _Explored:
    seen: set[tuple[State, frozenset[str]]]
    parent: dict[tuple[State, frozenset[str]], tuple[State, frozenset[str]] | None]
    violations: dict[str, tuple[State, frozenset[str]]]
    edge_violations: dict[str, tuple[tuple[State, frozenset[str]], State]]

    def path_to(self, node: tuple[State, frozenset[str]], extra: State | None = None) -> list[str]:
        steps: list[State] = []
        cursor: tuple[State, frozenset[str]] | None = node
        while cursor is not None:
            steps.append(cursor[0])
            cursor = self.parent[cursor]
        steps.reverse()
        if extra is not None:
            steps.append(extra)
        return [label(s) for s in steps]


def _explore(graph: Graph, gates: Mapping[Edge, HandoffGate]) -> _Explored:
    start = (st.INITIAL, frozenset[str]())
    seen = {start}
    parent: dict[tuple[State, frozenset[str]], tuple[State, frozenset[str]] | None] = {start: None}
    violations: dict[str, tuple[State, frozenset[str]]] = {}
    edge_violations: dict[str, tuple[tuple[State, frozenset[str]], State]] = {}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        state, facts = node
        _check_state(state, facts, node, violations)
        for target in sorted(graph.get(state, frozenset()), key=str):
            gate = gates.get((state, target))
            if gate is not None and not (gate.requires <= facts and not (gate.forbids & facts)):
                continue
            if target == st.DRAFT and DRAFTED in facts:
                edge_violations.setdefault("drafted_twice", (node, target))
            following = _next_facts(facts, state, target, gate)
            child = (target, following)
            if child not in seen:
                seen.add(child)
                parent[child] = node
                queue.append(child)
    return _Explored(seen, parent, violations, edge_violations)


def _next_facts(
    facts: frozenset[str], frm: State, to: State, gate: HandoffGate | None
) -> frozenset[str]:
    out = set(facts)
    if gate is not None:
        out -= gate.clears
        out |= gate.establishes
    if to == st.BLOCKED:
        out.add(_BLOCKED_PENDING)
    if gate is not None and gate.by_controller:
        out.discard(_BLOCKED_PENDING)
    if frm == st.POLICY:
        out.discard(_POLICY_BLOCK)
        if to == st.BLOCKED:
            out.add(_POLICY_BLOCK)
    return frozenset(out)


def _check_state(
    state: State,
    facts: frozenset[str],
    node: tuple[State, frozenset[str]],
    violations: dict[str, tuple[State, frozenset[str]]],
) -> None:
    if state in (st.DRAFT, st.WAIT) and (
        ESTIMATED not in facts or POLICY_EVALUATED not in facts or POLICY_BLOCKED in facts
    ):
        violations.setdefault("policy_before_posting", node)
    if state in POSTING and _BLOCKED_PENDING in facts:
        violations.setdefault("blocked_needs_controller", node)
    if state in DRAFTING and _POLICY_BLOCK in facts:
        violations.setdefault("policy_block_stays_blocked", node)
    if state == st.CLOSED and DRAFTED not in facts:
        violations.setdefault("closed_needs_accrual", node)


def _count_paths(graph: Graph) -> int:
    """Simple paths from the first state to a terminal state."""
    total = 0

    def walk(state: State, visited: frozenset[State]) -> None:
        nonlocal total
        if state in st.TERMINAL:
            total += 1
            return
        for target in graph.get(state, frozenset()):
            if target not in visited:
                walk(target, visited | {target})

    walk(st.INITIAL, frozenset({st.INITIAL}))
    return total


# ---- the properties -----------------------------------------------------------------------------


def _completeness(edges: list[Edge], gates: Mapping[Edge, HandoffGate]) -> PropertyResult:
    missing = [edge for edge in edges if edge not in gates]
    scope = f"{len(edges) - len(missing)} of {len(edges)} edges have a gate"
    return PropertyResult(
        "completeness",
        "Every edge of the workflow has a registered gate",
        not missing,
        scope,
        counterexample=[f"{label(a)} -> {label(b)}" for a, b in missing] or None,
        detail="An edge without a gate would let an agent move an obligation unverified.",
    )


def _policy_before_posting(x: _Explored) -> PropertyResult:
    return _result(
        x,
        "policy_before_posting",
        "No path reaches drafting or the invoice wait without a policy decision and approval",
        f"holds over {len(x.seen)} reachable (state, facts) pairs",
    )


def _blocked_needs_controller(x: _Explored) -> PropertyResult:
    return _result(
        x,
        "blocked_needs_controller",
        "No path leaves BLOCKED toward a posted or closed accrual without a Controller decision",
        f"holds over {len(x.seen)} reachable (state, facts) pairs",
    )


def _policy_block_stays_blocked(x: _Explored) -> PropertyResult:
    return _result(
        x,
        "policy_block_stays_blocked",
        "After a policy BLOCK, no path posts except by re-verifying via the loop back to GATHER",
        f"holds over {len(x.seen)} reachable (state, facts) pairs",
    )


def _closed_needs_accrual(x: _Explored) -> PropertyResult:
    return _result(
        x,
        "closed_needs_accrual",
        "No path closes an accrual that was never drafted",
        f"holds over {len(x.seen)} reachable (state, facts) pairs",
    )


def _result(x: _Explored, key: str, title: str, scope: str) -> PropertyResult:
    node = x.violations.get(key)
    if node is None:
        return PropertyResult(key, title, True, scope)
    return PropertyResult(
        key,
        title,
        False,
        "violated",
        counterexample=x.path_to(node),
        detail=f"Reachable with facts {sorted(node[1])}.",
    )


def _drafted_once(x: _Explored) -> PropertyResult:
    title = "An accrual is drafted at most once on any path"
    found = x.edge_violations.get("drafted_twice")
    if found is None:
        return PropertyResult(
            "drafted_once", title, True, f"holds over {len(x.seen)} reachable (state, facts) pairs"
        )
    node, target = found
    return PropertyResult(
        "drafted_once",
        title,
        False,
        "violated",
        counterexample=x.path_to(node, extra=target),
        detail="A second draft after posting would double count the accrual.",
    )


def _no_dead_ends(graph: Graph, states: set[State], x: _Explored) -> PropertyResult:
    title = "Every state is reachable, and every state can reach a terminal state"
    reachable = {state for state, _ in x.seen}
    unreachable = sorted(states - reachable, key=str)
    reverse: dict[State, set[State]] = {s: set() for s in states}
    for frm, targets in graph.items():
        for to in targets:
            reverse[to].add(frm)
    can_finish: set[State] = set(st.TERMINAL & states)
    queue = deque(can_finish)
    while queue:
        for prev in reverse[queue.popleft()]:
            if prev not in can_finish:
                can_finish.add(prev)
                queue.append(prev)
    stuck = sorted(states - can_finish, key=str)
    problems = [f"unreachable: {label(s)}" for s in unreachable] + [
        f"cannot finish: {label(s)}" for s in stuck
    ]
    return PropertyResult(
        "no_dead_ends",
        title,
        not problems,
        f"holds over {len(states)} states",
        counterexample=problems or None,
    )


def _rule_activation(
    gates: Mapping[Edge, HandoffGate],
    rules: Mapping[tuple[e.LearningStatus, e.LearningStatus], tuple[str, tuple[str, ...]]],
    graph: Graph,
) -> PropertyResult:
    title = "A learned rule can only become ACTIVE through Controller approval after replay"
    problems: list[str] = []
    for edge, gate in gates.items():
        if RULE_ACTIVE in gate.establishes:
            problems.append(f"workflow edge {label(edge[0])} -> {label(edge[1])} activates a rule")
    for (frm, to), (actor, requires) in rules.items():
        if to == e.LearningStatus.ACTIVE and (
            actor != "controller" or "replay_passed" not in requires
        ):
            problems.append(f"{frm.value} -> ACTIVE by {actor} without replay_passed")
    into_active = [t for t in rules if t[1] == e.LearningStatus.ACTIVE]
    if not into_active:
        problems.append("no transition into ACTIVE is declared")
    learn_edges = [edge for edge in edges_of(graph) if edge[0] == st.LEARN]
    return PropertyResult(
        "rule_activation",
        title,
        not problems,
        f"holds over {len(rules)} rule transitions and {len(learn_edges)} LEARN edges",
        counterexample=problems or None,
    )


def render(report: GraphReport) -> list[str]:
    lines = []
    for prop in report.properties:
        verdict = "PROVED" if prop.holds else "FAILED"
        lines.append(f"{verdict}  {prop.title}")
        lines.append(f"        {prop.scope}")
        if prop.counterexample:
            lines.append("        counterexample: " + " -> ".join(prop.counterexample))
    return lines
