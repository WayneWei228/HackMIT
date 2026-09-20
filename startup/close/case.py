"""The CloseCase: its shape, its legal moves, and the log of why it moved."""

from __future__ import annotations

from typing import Any

from close import events, store
from close.workspace import Workspace

STATUSES = [
    "DETECTED",
    "ENRICHED",
    "INVOICED",
    "ESTIMATE_REQUIRED",
    "OUTREACH_PENDING",
    "FORCED_ESTIMATE",
    "ESTIMATED",
    "NO_ACCRUAL",
    "REVIEW",
    "JOURNALED",
    "CLOSED",
    "SETTLED",
    "LEARNED",
]

TRANSITIONS: dict[str, list[str]] = {
    "DETECTED": ["ENRICHED"],
    "ENRICHED": ["INVOICED", "ESTIMATE_REQUIRED", "NO_ACCRUAL", "REVIEW"],
    "ESTIMATE_REQUIRED": ["ESTIMATED", "OUTREACH_PENDING", "REVIEW"],
    "OUTREACH_PENDING": ["ESTIMATE_REQUIRED", "FORCED_ESTIMATE"],
    "FORCED_ESTIMATE": ["ESTIMATED"],
    "ESTIMATED": ["JOURNALED", "REVIEW"],
    "REVIEW": ["ESTIMATE_REQUIRED", "JOURNALED", "NO_ACCRUAL"],
    "INVOICED": ["CLOSED"],
    "NO_ACCRUAL": ["CLOSED"],
    "JOURNALED": ["CLOSED"],
    "CLOSED": ["SETTLED"],
    "SETTLED": ["LEARNED"],
    "LEARNED": [],
}


class IllegalTransition(Exception):
    """A worker tried to move a case somewhere the state machine does not allow."""


def new_case(
    ws: Workspace,
    period: str,
    kind: str,
    case_key: str,
    vendor_id: str | None,
    vendor_name: str | None,
    entity_id: str,
    obligation: dict | None,
    po_line_id: str | None = None,
) -> dict:
    return {
        "case_id": f"{period}/{case_key}",
        "case_key": case_key,
        "period": period,
        "as_of": ws.as_of,
        "kind": kind,
        "entity_id": entity_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "po_line_id": po_line_id,
        "status": "DETECTED",
        "obligation": obligation,
        "invoice_match": None,
        "classification": None,
        "estimate": None,
        "outreach": None,
        "journal": None,
        "settlement": None,
        "flags": [],
        "evidence_refs": [],
        "decision_log": [],
    }


def log_decision(
    ws: Workspace,
    case: dict,
    worker: str,
    kind: str,
    question: str,
    answer: Any,
    confidence: float | None = None,
    action: str = "",
) -> dict:
    entry = {
        "at": ws.as_of,
        "worker": worker,
        "kind": kind,
        "question": question,
        "answer": answer,
        "confidence": confidence,
        "action": action,
    }
    case.setdefault("decision_log", []).append(entry)
    return entry


def transition(ws: Workspace, case: dict, new_status: str, worker: str, why: str) -> dict:
    old = case.get("status")
    if new_status not in STATUSES:
        raise IllegalTransition(f"unknown status {new_status!r}")
    if new_status not in TRANSITIONS.get(old, []):
        raise IllegalTransition(f"{case.get('case_id')}: {old} -> {new_status} is not allowed")
    case["status"] = new_status
    log_decision(ws, case, worker, "RULE", why, new_status, action=f"{old} -> {new_status}")
    events.log(ws, worker, f"{case.get('case_id')} {old} -> {new_status}: {why}", case.get("period"))
    return case


def add_flag(case: dict, flag: str) -> dict:
    flags = case.setdefault("flags", [])
    if flag not in flags:
        flags.append(flag)
    return case


def load_cases(ws: Workspace) -> list[dict]:
    return store.load_state(ws, "cases", [])


def save_cases(ws: Workspace, cases: list[dict]) -> list[dict]:
    return store.save_state(ws, "cases", cases)


def cases_for(ws: Workspace, period: str) -> list[dict]:
    return [c for c in load_cases(ws) if c.get("period") == period]


def find_case(cases: list[dict], case_id: str) -> dict | None:
    for c in cases:
        if c.get("case_id") == case_id:
            return c
    return None
