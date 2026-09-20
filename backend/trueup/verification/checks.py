"""The handoff checks: deterministic Python that reads the tables and answers pass or fail.

A check never calls a model, never reads a hidden answer key and never writes. It re-derives what
it can from source records (the policy rules, the estimate, the journal entry totals) and compares
that with what the previous agent recorded.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trueup.agents import estimation_agent, policy_agent
from trueup.agents.controller_workspace import controller_id
from trueup.ingest.manifest import FileEntry, FileUniverse
from trueup.ingest.readers import UnsupportedFile, read_text
from trueup.learning.rules import CandidateRule
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.integrity import UnbalancedEntryError, assert_balanced
from trueup.store.types import coerce_money
from trueup.verification.models import ActionProposal, CheckResult, Verdict
from trueup.verification.states import State, label

TOLERANCE = Decimal("0.01")
MIN_EVIDENCE_CONFIDENCE = Decimal("0.60")

# Who may move an obligation out of each state. Anyone else is refused.
STATE_OWNERS: dict[State, frozenset[str]] = {
    (e.WorkflowStage.DETECTED, e.NextAction.SEARCH_AP): frozenset({"detection"}),
    (e.WorkflowStage.SEARCHING_AP, e.NextAction.SEARCH_AP): frozenset({"invoice_lookup"}),
    (e.WorkflowStage.GATHERING_EVIDENCE, e.NextAction.GATHER_EVIDENCE): frozenset({"orchestrator"}),
    (e.WorkflowStage.CLASSIFYING, e.NextAction.CLASSIFY): frozenset({"classification"}),
    (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE): frozenset({"estimation"}),
    (e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY): frozenset({"policy"}),
    (e.WorkflowStage.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH): frozenset({"outreach"}),
    (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW): frozenset(
        {"controller_workspace"}
    ),
    (e.WorkflowStage.BLOCKED, e.NextAction.CONTROLLER_REVIEW): frozenset({"controller_workspace"}),
    (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY): frozenset(
        {"journal_entry_service"}
    ),
    (e.WorkflowStage.AWAITING_ACTUAL_INVOICE, e.NextAction.WAIT_FOR_INVOICE): frozenset(
        {"reconciliation"}
    ),
    (e.WorkflowStage.RECONCILING, e.NextAction.MATCH_AND_TRUE_UP): frozenset({"reconciliation"}),
    (e.WorkflowStage.RECONCILING, e.NextAction.EVALUATE_LEARNING): frozenset({"learning"}),
}

# The evidence a purchase type must rest on, once documents have been gathered.
REQUIRED_EVIDENCE: dict[e.PurchaseType, frozenset[e.EvidenceCardType]] = {
    e.PurchaseType.FIXED_RECURRING: frozenset({e.EvidenceCardType.CONTRACT_TERM}),
    e.PurchaseType.USAGE_BASED: frozenset(
        {e.EvidenceCardType.CONTRACT_TERM, e.EvidenceCardType.SERVICE_USAGE}
    ),
    e.PurchaseType.RECEIPT_BASED: frozenset(
        {e.EvidenceCardType.PO_DETAIL, e.EvidenceCardType.SERVICE_RECEIPT}
    ),
    e.PurchaseType.MILESTONE_BASED: frozenset(
        {e.EvidenceCardType.PO_DETAIL, e.EvidenceCardType.SERVICE_RECEIPT}
    ),
    e.PurchaseType.PREPAID: frozenset({e.EvidenceCardType.CONTRACT_TERM}),
}

_APPROVING = (e.ControllerDecision.APPROVE, e.ControllerDecision.APPROVE_WITH_ADJUSTMENT)
_LEDGERED = (e.GLEntryStatus.POSTED, e.GLEntryStatus.REVERSED)
_ACTIVE_ACCRUAL = (
    e.AccrualStatus.DRAFTED,
    e.AccrualStatus.PENDING_APPROVAL,
    e.AccrualStatus.APPROVED,
    e.AccrualStatus.POSTED_SIMULATED,
)


class Environment:
    """What a gate may read besides the tables: the file manifest and the files themselves."""

    def __init__(
        self,
        seed_dir: Path | str,
        universe_loader: Callable[[], FileUniverse | None] | None = None,
    ):
        self.seed_dir = Path(seed_dir)
        self._loader = universe_loader
        self._universe: FileUniverse | None = None
        self._loaded = False
        self._texts: dict[str, str | None] = {}

    @property
    def universe(self) -> FileUniverse | None:
        if not self._loaded:
            self._loaded = True
            try:
                self._universe = self._loader() if self._loader else None
            except (OSError, ValueError):
                self._universe = None
        return self._universe

    def file(self, file_id: str) -> FileEntry | None:
        universe = self.universe
        if universe is None:
            return None
        return next((f for f in universe.files if f.file_id == file_id), None)

    def text(self, entry: FileEntry) -> str | None:
        if entry.file_id not in self._texts:
            try:
                self._texts[entry.file_id] = read_text(self.seed_dir / entry.path)
            except (UnsupportedFile, OSError, ValueError):
                self._texts[entry.file_id] = None
        return self._texts[entry.file_id]


@dataclass
class Handoff:
    """One proposed move along a workflow edge, with everything a check may look at."""

    session: Session
    ob: m.TrueUpObligation
    frm: State
    to: State
    actor: str | None
    at: datetime
    env: Environment
    graph: Mapping[State, frozenset[State]]
    facts: Mapping[str, Any] = field(default_factory=dict)
    proposal: ActionProposal | None = None
    proposal_error: str | None = None

    @cached_property
    def wp(self) -> m.TrueUpWorkpaper | None:
        if not self.ob.current_workpaper_id:
            return None
        return self.session.get(m.TrueUpWorkpaper, self.ob.current_workpaper_id)

    @cached_property
    def cards(self) -> list[m.TrueUpEvidence]:
        return list(
            self.session.scalars(
                select(m.TrueUpEvidence)
                .where(m.TrueUpEvidence.obligation_id == self.ob.obligation_id)
                .order_by(m.TrueUpEvidence.evidence_id)
            )
        )

    @cached_property
    def config(self) -> dict[str, Any]:
        return {
            row.config_key: row.config_value_json
            for row in self.session.scalars(select(m.CompanyConfig))
        }

    @cached_property
    def controller(self) -> str | None:
        try:
            return controller_id(self.session)
        except Exception:  # noqa: BLE001 - a missing controller is itself a failed check
            return None

    @cached_property
    def inputs(self) -> dict[str, Any]:
        return dict((self.wp.calculation_inputs_json or {}) if self.wp else {})


Check = Callable[[Handoff], CheckResult]


def _pass(check_id: str, name: str, detail: str, *, expected: str | None = None) -> CheckResult:
    return CheckResult(
        check_id=check_id, name=name, passed=True, expected=expected, actual=expected, detail=detail
    )


def _skip(check_id: str, name: str, detail: str) -> CheckResult:
    return CheckResult(check_id=check_id, name=name, passed=True, skipped=True, detail=detail)


def _fail(
    check_id: str,
    name: str,
    detail: str,
    on_fail: Verdict = Verdict.BLOCK,
    *,
    expected: str | None = None,
    actual: str | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        name=name,
        passed=False,
        on_fail=on_fail,
        expected=expected,
        actual=actual,
        detail=detail,
    )


def _floats(value: Any, path: str = "") -> list[str]:
    if isinstance(value, float):
        return [path or "value"]
    if isinstance(value, Mapping):
        return [f for k, v in value.items() for f in _floats(v, f"{path}.{k}".lstrip("."))]
    if isinstance(value, list | tuple):
        return [f for i, v in enumerate(value) for f in _floats(v, f"{path}[{i}]")]
    return []


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).lower()).strip()


def _amount(h: Handoff) -> Decimal | None:
    return coerce_money(h.wp.proposed_amount) if h.wp is not None else None


# ---- VER-01, VER-02: the structure of the handoff -----------------------------------------------


def ver_01(h: Handoff) -> CheckResult:
    name = "Legal edge, authorised actor"
    if h.to not in h.graph.get(h.frm, frozenset()):
        return _fail(
            "VER-01",
            name,
            f"{label(h.frm)} to {label(h.to)} is not an edge of the workflow.",
            expected="an edge of the workflow graph",
            actual=f"{label(h.frm)} -> {label(h.to)}",
        )
    owners = STATE_OWNERS.get(h.frm, frozenset())
    if h.actor not in owners:
        return _fail(
            "VER-01",
            name,
            f"{h.actor or 'No actor'} may not move an obligation out of {label(h.frm)}.",
            expected=" or ".join(sorted(owners)) or "no actor",
            actual=str(h.actor),
        )
    return _pass("VER-01", name, f"{h.actor} owns {label(h.frm)} and the edge is legal.")


def ver_02(h: Handoff) -> CheckResult:
    name = "Proposal is well formed and money is exact"
    if h.proposal is None:
        return _fail(
            "VER-02",
            name,
            f"The action proposal is not valid: {h.proposal_error}.",
            actual="invalid",
        )
    found: list[str] = []
    if h.wp is not None:
        found += _floats(h.wp.calculation_inputs_json, "calculation_inputs")
        found += _floats(h.wp.journal_entry_json, "journal_entry")
        if not h.wp.currency:
            return _fail("VER-02", name, "The workpaper has no currency.", expected="a currency")
    if found:
        return _fail(
            "VER-02",
            name,
            f"Money is stored as a float at {found[0]}; amounts must be Decimal strings.",
            expected="Decimal strings",
            actual=", ".join(found[:3]),
        )
    return _pass("VER-02", name, "The proposal validates and every amount is an exact Decimal.")


# ---- VER-03, VER-04, VER-05, VER-06: the evidence -----------------------------------------------


def _recorded_evidence_ids(h: Handoff) -> list[str]:
    runs = h.session.scalars(
        select(m.TrueUpAgentRun).where(
            m.TrueUpAgentRun.obligation_id == h.ob.obligation_id,
            m.TrueUpAgentRun.agent_name == "evidence",
            m.TrueUpAgentRun.action == "extract_facts",
        )
    )
    return [i for run in runs for i in (run.output_record_ids_json or [])]


def ver_03(h: Handoff) -> CheckResult:
    name = "Evidence ids resolve to cards of this obligation"
    recorded = _recorded_evidence_ids(h)
    have = {c.evidence_id for c in h.cards}
    missing = [i for i in recorded if i not in have]
    if missing:
        return _fail(
            "VER-03",
            name,
            f"Evidence card {missing[0]} was recorded for this obligation but no longer exists.",
            expected=f"{len(recorded)} recorded cards",
            actual=f"{len(recorded) - len(missing)} found",
        )
    return _pass("VER-03", name, f"All {len(recorded)} recorded evidence cards exist.")


def ver_04(h: Handoff) -> CheckResult:
    name = "Quoted spans appear verbatim in their source files"
    documents = [
        c
        for c in h.cards
        if c.source_table == "document" and c.status != e.EvidenceCardStatus.SUPERSEDED
    ]
    if not documents:
        return _skip("VER-04", name, "No document evidence was gathered for this obligation.")
    if h.env.universe is None:
        return _skip(
            "VER-04", name, "The file manifest is not available, so quotes were not re-read."
        )
    for card in documents:
        entry = h.env.file(card.source_id)
        if entry is None:
            return _fail(
                "VER-04",
                name,
                f"Card {card.evidence_id} cites file {card.source_id}, not in the universe.",
            )
        if entry.vendor_id != h.ob.vendor_id:
            return _fail(
                "VER-04",
                name,
                f"Card {card.evidence_id} cites a file that belongs to another vendor.",
                expected=h.ob.vendor_id,
                actual=entry.vendor_id,
            )
        text = h.env.text(entry)
        if text is None:
            return _fail(
                "VER-04",
                name,
                f"The source file {entry.name} for {card.evidence_id} cannot be read.",
            )
        quote = _normalize(card.source_excerpt or "")
        if not quote or quote not in _normalize(text):
            return _fail(
                "VER-04",
                name,
                f"The quote on card {card.evidence_id} does not appear verbatim in {entry.name}.",
                expected="a verbatim quote",
                actual=(card.source_excerpt or "")[:80],
            )
    return _pass("VER-04", name, f"All {len(documents)} quotes were found verbatim in their files.")


_SOURCE_KIND: dict[type, tuple[e.EvidenceCardType, ...]] = {
    m.CompanyContract: (e.EvidenceCardType.CONTRACT_TERM,),
    m.CompanyPurchaseOrder: (e.EvidenceCardType.PO_DETAIL,),
    m.CompanyServiceEvidence: (
        e.EvidenceCardType.SERVICE_USAGE,
        e.EvidenceCardType.SERVICE_RECEIPT,
    ),
}


def _kinds_cited(h: Handoff) -> set[e.EvidenceCardType]:
    kinds: set[e.EvidenceCardType] = set()
    for source_id in h.inputs.get("sources") or []:
        for model, covers in _SOURCE_KIND.items():
            if h.session.get(model, source_id) is not None:
                kinds.update(covers)
        card = h.session.get(m.TrueUpEvidence, source_id)
        if card is not None:
            kinds.add(card.evidence_type)
    return kinds


def ver_05(h: Handoff) -> CheckResult:
    name = "Evidence the purchase type depends on is present"
    required = REQUIRED_EVIDENCE.get(h.ob.purchase_type)
    if required is None:
        return _skip("VER-05", name, "This purchase type has no required evidence list.")
    carded = {c.evidence_type for c in h.cards if c.status != e.EvidenceCardStatus.SUPERSEDED}
    cited = _kinds_cited(h)
    missing = sorted(t.value for t in required - carded - cited)
    if missing:
        return _fail(
            "VER-05",
            name,
            f"No {missing[0]} evidence card or cited source record supports this "
            f"{h.ob.purchase_type.value} obligation.",
            Verdict.OUTREACH,
            expected=", ".join(sorted(t.value for t in required)),
            actual=", ".join(sorted(t.value for t in carded | cited)) or "none",
        )
    return _pass(
        "VER-05",
        name,
        "Every evidence type this purchase type needs is backed by a card or a source record.",
    )


def ver_06(h: Handoff) -> CheckResult:
    name = "Evidence is neither conflicting nor low confidence"
    live = [c for c in h.cards if c.status != e.EvidenceCardStatus.SUPERSEDED]
    conflicts = [c for c in live if c.status == e.EvidenceCardStatus.CONFLICTING]
    if conflicts:
        return _fail(
            "VER-06",
            name,
            f"Evidence card {conflicts[0].evidence_id} conflicts with another source.",
            Verdict.REVIEW,
            expected="no conflicting evidence",
            actual=f"{len(conflicts)} conflicting",
        )
    weak = [
        c
        for c in live
        if c.status == e.EvidenceCardStatus.VERIFIED and c.confidence < MIN_EVIDENCE_CONFIDENCE
    ]
    if weak:
        return _fail(
            "VER-06",
            name,
            f"Evidence card {weak[0].evidence_id} has confidence {weak[0].confidence}.",
            Verdict.REVIEW,
            expected=f"at least {MIN_EVIDENCE_CONFIDENCE}",
            actual=str(weak[0].confidence),
        )
    return _pass("VER-06", name, "No evidence card conflicts or falls below the confidence floor.")


# ---- VER-07, VER-08, VER-09: the estimate and the entry -----------------------------------------


def _source_exists(session: Session, source_id: str) -> bool:
    for model in (
        m.CompanyContract,
        m.CompanyPurchaseOrder,
        m.CompanyServiceEvidence,
        m.CompanyAPInvoice,
        m.CompanyGLEntry,
        m.CompanyNonPOSpend,
        m.TrueUpEvidence,
    ):
        if session.get(model, source_id) is not None:
            return True
    return False


def ver_07(h: Handoff) -> CheckResult:
    name = "Estimation method is allowed and its sources exist"
    wp = h.wp
    if wp is None:
        return _fail("VER-07", name, "There is no workpaper to verify.", expected="a workpaper")
    allowed = estimation_agent.METHOD_BY_TYPE.get(h.ob.purchase_type)
    if allowed is None or wp.estimation_method != allowed:
        return _fail(
            "VER-07",
            name,
            f"{wp.estimation_method.value} is not the allowed method for a "
            f"{h.ob.purchase_type.value} obligation.",
            Verdict.REVIEW,
            expected=str(allowed.value if allowed else "none"),
            actual=wp.estimation_method.value,
        )
    sources = list(h.inputs.get("sources") or [])
    if not sources:
        return _fail("VER-07", name, "The workpaper cites no source record for its amount.")
    for source_id in sources:
        if not _source_exists(h.session, source_id):
            return _fail(
                "VER-07",
                name,
                f"The workpaper cites {source_id}, which is not in any source table.",
            )
    return _pass(
        "VER-07", name, f"{wp.estimation_method.value} is allowed; {len(sources)} sources exist."
    )


def ver_08(h: Handoff) -> CheckResult:
    name = "The amount is reproduced by the deterministic estimator"
    wp = h.wp
    if wp is None:
        return _fail("VER-08", name, "There is no workpaper to recompute.", expected="a workpaper")
    if h.inputs.get("controller_adjustment"):
        return _skip(
            "VER-08", name, "The Controller adjusted this amount; the adjustment is verified."
        )
    try:
        fresh = estimation_agent.compute(h.session, h.ob).estimate.amount
    except estimation_agent.Insufficient as exc:
        return _fail("VER-08", name, f"The estimate cannot be reproduced: {exc}.")
    recorded = coerce_money(wp.proposed_amount)
    if abs(fresh - recorded) > TOLERANCE:
        return _fail(
            "VER-08",
            name,
            f"Recomputing gives {fresh}, not the recorded {recorded}.",
            expected=str(fresh),
            actual=str(recorded),
        )
    return _pass(
        "VER-08", name, f"Recomputing from the sources gives {fresh}.", expected=str(recorded)
    )


def _entry_lines(wp: m.TrueUpWorkpaper) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The accrual lines and the drafted entries (empty until the entry is drafted)."""
    payload = wp.journal_entry_json
    if isinstance(payload, Mapping):
        entries = list(payload.get("entries") or [])
        accrual = next((x for x in entries if x.get("entry_type") == "ACCRUAL"), None)
        return list((accrual or {}).get("lines") or []), entries
    return list(payload or []), []


def ver_09(h: Handoff) -> CheckResult:
    name = "Journal entry balances and uses chart accounts"
    wp = h.wp
    if wp is None:
        return _fail(
            "VER-09", name, "There is no workpaper carrying an entry.", expected="a workpaper"
        )
    lines, entries = _entry_lines(wp)
    chart = {a["account_code"] for a in h.config.get("allowed_gl_accounts") or []}
    try:
        for entry_lines in [lines, *[list(x.get("lines") or []) for x in entries]]:
            assert_balanced(entry_lines)
        total = assert_balanced(lines)
    except (UnbalancedEntryError, TypeError, ValueError) as exc:
        return _fail(
            "VER-09",
            name,
            f"The journal entry is not valid: {exc}.",
            expected="balanced exact lines",
        )
    amount = coerce_money(wp.proposed_amount)
    if total != amount:
        return _fail(
            "VER-09",
            name,
            f"The entry total {total} does not equal the workpaper amount {amount}.",
            expected=str(amount),
            actual=str(total),
        )
    unknown = sorted({ln["account_code"] for ln in lines if ln.get("account_code") not in chart})
    if chart and unknown:
        return _fail("VER-09", name, f"Account {unknown[0]} is not in the chart of accounts.")
    if entries:
        reversal = next((x for x in entries if x.get("entry_type") == "ACCRUAL_REVERSAL"), None)
        prepaid = wp.estimation_method == e.EstimationMethod.PREPAID_AMORTIZATION
        if prepaid and reversal is not None:
            return _fail("VER-09", name, "A prepaid amortization must not be reversed.")
        if not prepaid and reversal is None:
            return _fail("VER-09", name, "The accrual has no reversing entry.")
    return _pass(
        "VER-09", name, f"The entry balances at {total} on chart accounts.", expected=str(amount)
    )


# ---- VER-10, VER-11, VER-12, VER-13: policy, period, duplicates, approval ----------------------

_EDGE_DECISION = {
    (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY): e.PolicyDecision.PERMIT,
    (
        e.WorkflowStage.AWAITING_OUTREACH,
        e.NextAction.SEND_OUTREACH,
    ): e.PolicyDecision.REQUIRE_OUTREACH,
    (
        e.WorkflowStage.AWAITING_CONTROLLER,
        e.NextAction.CONTROLLER_REVIEW,
    ): e.PolicyDecision.REQUIRE_CONTROLLER,
    (e.WorkflowStage.BLOCKED, e.NextAction.CONTROLLER_REVIEW): e.PolicyDecision.BLOCK,
}
_DECISION_VERDICT = {
    e.PolicyDecision.BLOCK: Verdict.BLOCK,
    e.PolicyDecision.REQUIRE_OUTREACH: Verdict.OUTREACH,
    e.PolicyDecision.REQUIRE_CONTROLLER: Verdict.REVIEW,
    e.PolicyDecision.PERMIT: Verdict.REVIEW,
}


def ver_10(h: Handoff) -> CheckResult:
    name = "Policy rules re-run and agree with the recorded decision"
    wp = h.wp
    if wp is None:
        return _fail("VER-10", name, "There is no workpaper for policy to have checked.")
    decision, rules = policy_agent.evaluate(h.session, h.ob, wp)
    hits = [r.rule_id for r in rules if r.status == "HIT"]
    recorded = wp.policy_decision
    if h.frm == (e.WorkflowStage.ESTIMATING, e.NextAction.VERIFY_POLICY):
        implied = _EDGE_DECISION.get(h.to)
        if implied == decision == recorded:
            return _pass(
                "VER-10",
                name,
                f"Re-running {len(rules)} policy rules gives {decision.value}, as recorded.",
                expected=decision.value,
            )
        return _fail(
            "VER-10",
            name,
            f"Re-running the policy rules gives {decision.value} ({', '.join(hits) or 'no hits'}), "
            f"but the record says {recorded.value} and the edge implies "
            f"{implied.value if implied else 'none'}.",
            _DECISION_VERDICT[decision],
            expected=decision.value,
            actual=f"{recorded.value} / edge {implied.value if implied else 'none'}",
        )
    approvable = (e.PolicyDecision.PERMIT, e.PolicyDecision.REQUIRE_CONTROLLER)
    if decision in approvable and recorded in approvable:
        return _pass(
            "VER-10",
            name,
            f"Re-running the policy rules gives {decision.value}; the accrual may be approved.",
            expected="PERMIT or REQUIRE_CONTROLLER",
        )
    return _fail(
        "VER-10",
        name,
        f"Re-running the policy rules gives {decision.value} ({', '.join(hits) or 'no hits'}) and "
        f"the record says {recorded.value}, so the accrual cannot be approved.",
        _DECISION_VERDICT[decision],
        expected="PERMIT or REQUIRE_CONTROLLER",
        actual=f"{decision.value} / recorded {recorded.value}",
    )


def ver_11(h: Handoff) -> CheckResult:
    name = "Accounting period is open"
    info = (h.config.get("accounting_periods") or {}).get(h.ob.period)
    if info is None:
        return _fail("VER-11", name, f"Period {h.ob.period} is not defined.", expected="OPEN")
    if info.get("status") != "OPEN":
        return _fail(
            "VER-11",
            name,
            f"Period {h.ob.period} is {info.get('status')}, not OPEN.",
            expected="OPEN",
            actual=str(info.get("status")),
        )
    return _pass("VER-11", name, f"Period {h.ob.period} is open.", expected="OPEN")


def ver_12(h: Handoff) -> CheckResult:
    name = "No duplicate accrual"
    ob = h.ob
    if ob.accrual_status in (e.AccrualStatus.POSTED_SIMULATED, e.AccrualStatus.TRUE_UP_COMPLETE):
        return _fail(
            "VER-12",
            name,
            f"{ob.obligation_id} is already {ob.accrual_status.value}; it cannot be accrued again.",
        )
    if (
        h.wp is not None
        and isinstance(h.wp.journal_entry_json, Mapping)
        and h.to
        == (
            e.WorkflowStage.READY_TO_DRAFT,
            e.NextAction.DRAFT_ENTRY,
        )
    ):
        return _fail("VER-12", name, "The workpaper already carries drafted entries.")
    others = h.session.scalars(
        select(m.TrueUpObligation).where(
            m.TrueUpObligation.vendor_id == ob.vendor_id,
            m.TrueUpObligation.period == ob.period,
            m.TrueUpObligation.obligation_id != ob.obligation_id,
            m.TrueUpObligation.accrual_status.in_(_ACTIVE_ACCRUAL),
        )
    ).all()
    if others:
        return _fail(
            "VER-12",
            name,
            f"{others[0].obligation_id} already has an active accrual for this vendor and period.",
        )
    posted = h.session.scalars(
        select(m.CompanyGLEntry).where(
            m.CompanyGLEntry.obligation_id == ob.obligation_id,
            m.CompanyGLEntry.entry_type == e.GLEntryType.ACCRUAL,
            m.CompanyGLEntry.status.in_(_LEDGERED),
        )
    ).first()
    if posted is not None:
        return _fail("VER-12", name, f"{posted.gl_entry_id} is already posted for this obligation.")
    return _pass("VER-12", name, "No other accrual is active for this vendor and period.")


_DECISION_FOR_TARGET = {
    (e.WorkflowStage.READY_TO_DRAFT, e.NextAction.DRAFT_ENTRY): _APPROVING,
    (e.WorkflowStage.CLOSED_NO_ACCRUAL, e.NextAction.NONE): (e.ControllerDecision.REJECT,),
    (e.WorkflowStage.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH): (
        e.ControllerDecision.REQUEST_MORE_EVIDENCE,
    ),
    (e.WorkflowStage.GATHERING_EVIDENCE, e.NextAction.GATHER_EVIDENCE): (
        e.ControllerDecision.REQUEST_MORE_EVIDENCE,
    ),
    (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE): (
        e.ControllerDecision.REQUEST_MORE_EVIDENCE,
    ),
}


def ver_13(h: Handoff) -> CheckResult:
    name = "The configured Controller made this decision"
    decision = h.facts.get("controller_decision")
    decided_by = h.facts.get("decided_by")
    if not decision or not decided_by:
        return _fail("VER-13", name, "No Controller decision accompanies this handoff.")
    if h.controller is None or decided_by != h.controller:
        return _fail(
            "VER-13",
            name,
            f"{decided_by} is not the configured Controller.",
            expected=str(h.controller),
            actual=str(decided_by),
        )
    allowed = _DECISION_FOR_TARGET.get(h.to)
    try:
        chosen = e.ControllerDecision(decision)
    except ValueError:
        return _fail("VER-13", name, f"{decision} is not a Controller decision.")
    if allowed is not None and chosen not in allowed:
        return _fail(
            "VER-13",
            name,
            f"{chosen.value} does not lead to {label(h.to)}.",
            expected=" or ".join(d.value for d in allowed),
            actual=chosen.value,
        )
    if chosen in _APPROVING and h.wp is not None and h.wp.policy_decision == e.PolicyDecision.BLOCK:
        return _fail("VER-13", name, "A policy BLOCK can never be approved.")
    if chosen == e.ControllerDecision.APPROVE_WITH_ADJUSTMENT:
        adjusted = h.facts.get("adjusted_amount")
        try:
            ok = adjusted is not None and coerce_money(adjusted) > 0
        except (TypeError, ValueError):
            ok = False
        if not ok:
            return _fail(
                "VER-13", name, "The adjusted amount is missing or not a positive Decimal."
            )
    return _pass(
        "VER-13", name, f"{decided_by} decided {chosen.value}.", expected=str(h.controller)
    )


def ver_23(h: Handoff) -> CheckResult:
    name = "The approval needed to draft or post is on record"
    wp = h.wp
    if wp is None:
        return _fail("VER-23", name, "There is no workpaper to approve.")
    if wp.status not in (e.WorkpaperStatus.APPROVED, e.WorkpaperStatus.POSTED_SIMULATED):
        return _fail(
            "VER-23",
            name,
            f"The workpaper is {wp.status.value}, not APPROVED.",
            expected="APPROVED",
            actual=wp.status.value,
        )
    if wp.policy_decision == e.PolicyDecision.PERMIT and wp.controller_decision is None:
        return _pass(
            "VER-23", name, "Policy permitted the accrual; no Controller approval was needed."
        )
    if (
        wp.policy_decision != e.PolicyDecision.REQUIRE_CONTROLLER
        and wp.policy_decision != e.PolicyDecision.PERMIT
    ):
        return _fail("VER-23", name, f"The policy decision is {wp.policy_decision.value}.")
    if wp.controller_decision not in _APPROVING:
        return _fail(
            "VER-23", name, "The accrual needs a Controller approval and none is recorded."
        )
    card = h.session.scalars(
        select(m.TrueUpEvidence).where(
            m.TrueUpEvidence.obligation_id == h.ob.obligation_id,
            m.TrueUpEvidence.evidence_type == e.EvidenceCardType.CONTROLLER_DECISION,
        )
    ).first()
    who = (card.value_json or {}).get("decided_by") if card is not None else None
    if card is None or who != h.controller:
        return _fail(
            "VER-23",
            name,
            "The approval is not backed by a decision card from the configured Controller.",
            expected=str(h.controller),
            actual=str(who),
        )
    return _pass("VER-23", name, f"{who} approved the accrual and the decision card is on record.")


# ---- VER-14, VER-17: invoice cutoff and classification ------------------------------------------

_INVOICE_ROUTE = {
    e.InvoiceStatus.INVOICE_FOUND: (e.WorkflowStage.CLOSED_NO_ACCRUAL, e.NextAction.NONE),
    e.InvoiceStatus.MISSING: (e.WorkflowStage.GATHERING_EVIDENCE, e.NextAction.GATHER_EVIDENCE),
    e.InvoiceStatus.AMBIGUOUS: (
        e.WorkflowStage.AWAITING_CONTROLLER,
        e.NextAction.CONTROLLER_REVIEW,
    ),
}


def ver_14(h: Handoff) -> CheckResult:
    name = "The invoice search result matches the route taken"
    ob = h.ob
    expected = _INVOICE_ROUTE.get(ob.invoice_status)
    if expected != h.to:
        return _fail(
            "VER-14",
            name,
            f"The search recorded {ob.invoice_status.value}, which does not lead to {label(h.to)}.",
            expected=label(expected) if expected else "a recorded search result",
            actual=label(h.to),
        )
    if ob.invoice_status == e.InvoiceStatus.INVOICE_FOUND:
        invoice = (
            h.session.get(m.CompanyAPInvoice, ob.matched_invoice_id)
            if ob.matched_invoice_id
            else None
        )
        if invoice is None or invoice.vendor_id != ob.vendor_id:
            return _fail(
                "VER-14",
                name,
                "No accrual is needed only if a real invoice of this vendor is matched.",
            )
    return _pass("VER-14", name, f"{ob.invoice_status.value} leads to {label(h.to)}.")


def ver_17(h: Handoff) -> CheckResult:
    name = "The classification has an allowed estimator"
    if h.ob.purchase_type not in estimation_agent.METHOD_BY_TYPE:
        return _fail(
            "VER-17",
            name,
            f"{h.ob.purchase_type.value} has no allowed estimation method.",
            Verdict.REVIEW,
            expected="a supported purchase type",
            actual=h.ob.purchase_type.value,
        )
    return _pass(
        "VER-17", name, f"{h.ob.purchase_type.value} maps to an allowed estimation method."
    )


# ---- VER-15: learned rules ----------------------------------------------------------------------


def _rule_problem(
    session: Session, row: m.TrueUpLearningRule, controller: str | None
) -> str | None:
    if row.approved_by is None or row.approved_by != controller:
        return f"{row.learning_id} is ACTIVE but was not approved by the configured Controller."
    replay = row.replay_result_json or {}
    if not replay.get("passed") or not all((replay.get("criteria") or {}).values()):
        return f"{row.learning_id} is ACTIVE but has no passing replay on record."
    try:
        rule = CandidateRule.model_validate(row.candidate_rule_json)
    except Exception as exc:  # noqa: BLE001 - any invalid stored rule fails the control
        return f"{row.learning_id} is not a valid rule: {exc}"
    del rule
    return None


def ver_15(h: Handoff) -> CheckResult:
    name = "Every active and applied rule was replayed and Controller approved"
    rows = h.session.scalars(
        select(m.TrueUpLearningRule).where(m.TrueUpLearningRule.status == e.LearningStatus.ACTIVE)
    ).all()
    for row in rows:
        problem = _rule_problem(h.session, row, h.controller)
        if problem:
            return _fail(
                "VER-15",
                name,
                problem,
                expected="approved by the Controller after a passing replay",
            )
    applied = [r.get("learning_id") for r in (h.inputs.get("rules_applied") or [])]
    active = {r.learning_id for r in rows}
    stray = [i for i in applied if i not in active]
    if stray:
        return _fail(
            "VER-15", name, f"The estimate applied {stray[0]}, which is not an ACTIVE rule."
        )
    return _pass(
        "VER-15",
        name,
        f"{len(rows)} active rules are approved and replayed; {len(applied)} applied.",
    )


# ---- VER-20, VER-21, VER-22: after the close ----------------------------------------------------


def ver_20(h: Handoff) -> CheckResult:
    name = "A posted accrual and a matched invoice exist"
    ob = h.ob
    if ob.accrual_status != e.AccrualStatus.POSTED_SIMULATED:
        return _fail(
            "VER-20",
            name,
            f"The accrual is {ob.accrual_status.value}; nothing was posted to reconcile.",
            expected=e.AccrualStatus.POSTED_SIMULATED.value,
            actual=ob.accrual_status.value,
        )
    posted = h.session.scalars(
        select(m.CompanyGLEntry).where(
            m.CompanyGLEntry.obligation_id == ob.obligation_id,
            m.CompanyGLEntry.entry_type == e.GLEntryType.ACCRUAL,
            m.CompanyGLEntry.status.in_(_LEDGERED),
        )
    ).first()
    if posted is None:
        return _fail("VER-20", name, "The ledger holds no posted accrual for this obligation.")
    ids = h.inputs.get("matched_invoice_ids") or (
        [ob.matched_invoice_id] if ob.matched_invoice_id else []
    )
    invoices = [h.session.get(m.CompanyAPInvoice, i) for i in ids]
    if not ids or any(i is None or i.vendor_id != ob.vendor_id for i in invoices):
        return _fail("VER-20", name, "The matched invoice is missing or belongs to another vendor.")
    return _pass("VER-20", name, f"{posted.gl_entry_id} is posted and {len(ids)} invoice(s) match.")


def ver_21(h: Handoff) -> CheckResult:
    name = "Variance and route agree with the recorded reconciliation"
    wp = h.wp
    record = h.inputs.get("reconciliation")
    if wp is None or not record:
        return _fail("VER-21", name, "No reconciliation record was written before the handoff.")
    invoices = [h.session.get(m.CompanyAPInvoice, i) for i in record.get("invoice_ids") or []]
    if not invoices or any(i is None for i in invoices):
        return _fail("VER-21", name, "The reconciliation cites an invoice that does not exist.")
    accrued = coerce_money(wp.proposed_amount)
    actual = sum((coerce_money(i.amount) for i in invoices if i is not None), Decimal("0"))
    variance = actual - accrued
    try:
        recorded = coerce_money(record.get("variance"))
    except (TypeError, ValueError):
        return _fail("VER-21", name, "The recorded variance is not an exact Decimal.")
    if abs(recorded - variance) > TOLERANCE:
        return _fail(
            "VER-21",
            name,
            f"The recorded variance {recorded} is not invoiced {actual} less accrued {accrued}.",
            expected=str(variance),
            actual=str(recorded),
        )
    matched = abs(variance) <= TOLERANCE
    closes = h.to == (e.WorkflowStage.CLOSED, e.NextAction.NONE)
    if matched != closes:
        return _fail(
            "VER-21",
            name,
            f"A variance of {variance} {'must' if matched else 'must not'} close the obligation.",
            expected="CLOSED" if matched else "LEARN or CONTROLLER",
            actual=label(h.to),
        )
    return _pass("VER-21", name, f"Variance {variance} agrees with the invoice and the route.")


def ver_22(h: Handoff) -> CheckResult:
    name = "A learning record exists for the graded obligation"
    row = h.session.scalars(
        select(m.TrueUpLearningRule).where(m.TrueUpLearningRule.obligation_id == h.ob.obligation_id)
    ).first()
    if row is None:
        return _fail("VER-22", name, "No learning record was written for this true-up.")
    record = h.inputs.get("reconciliation") or {}
    if (
        record.get("variance") is not None
        and abs(coerce_money(row.variance_amount) - coerce_money(record["variance"])) > TOLERANCE
    ):
        return _fail(
            "VER-22", name, "The learning record's variance differs from the reconciliation."
        )
    return _pass("VER-22", name, f"{row.learning_id} records {row.root_cause.value}.")


# ---- VER-24: approving a rule -------------------------------------------------------------------


def ver_24(h: Handoff) -> CheckResult:
    name = "The rule passed replay and only the Controller approves it"
    learning_id = h.facts.get("learning_id")
    row = h.session.get(m.TrueUpLearningRule, learning_id) if learning_id else None
    if row is None:
        return _fail("VER-24", name, "The rule to approve does not exist.")
    if h.facts.get("decided_by") != h.controller:
        return _fail("VER-24", name, "Only the configured Controller may approve a rule.")
    if row.status != e.LearningStatus.REPLAY_PASSED:
        return _fail("VER-24", name, f"{row.learning_id} is {row.status.value}, not REPLAY_PASSED.")
    replay = row.replay_result_json or {}
    if not replay.get("passed") or not all((replay.get("criteria") or {}).values()):
        return _fail("VER-24", name, f"{row.learning_id} has no passing replay on record.")
    try:
        CandidateRule.model_validate(row.candidate_rule_json)
    except Exception as exc:  # noqa: BLE001
        return _fail("VER-24", name, f"{row.learning_id} is not a valid feature-based rule: {exc}")
    return _pass("VER-24", name, f"{row.learning_id} passed replay and the Controller decides.")


REGISTRY: dict[str, Check] = {
    "VER-01": ver_01,
    "VER-02": ver_02,
    "VER-03": ver_03,
    "VER-04": ver_04,
    "VER-05": ver_05,
    "VER-06": ver_06,
    "VER-07": ver_07,
    "VER-08": ver_08,
    "VER-09": ver_09,
    "VER-10": ver_10,
    "VER-11": ver_11,
    "VER-12": ver_12,
    "VER-13": ver_13,
    "VER-14": ver_14,
    "VER-15": ver_15,
    "VER-17": ver_17,
    "VER-20": ver_20,
    "VER-21": ver_21,
    "VER-22": ver_22,
    "VER-23": ver_23,
    "VER-24": ver_24,
}
