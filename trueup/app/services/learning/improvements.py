"""Generate improvements.md from the database.

Strictly one-way: rows in trueup_learning_rules produce this markdown. Nothing
ever parses it back. The agents read rules from the table; this file exists so a
human can see, in one page, what the system learned, from which outcomes, and on
what evidence it was allowed to change its own behaviour.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TrueupLearningRule, TrueupObligation
from app.services.agents.common import config

STATUS_ORDER = {"ACTIVE": 0, "REPLAY_PASSED": 1, "REPLAY_FAILED": 2,
                "ESCALATED_NO_RULE": 3, "REJECTED": 4, "REVOKED": 5, "OBSERVED": 6}


def generate(session: Session, path: str | Path) -> str:
    rows = sorted(
        session.scalars(select(TrueupLearningRule)),
        key=lambda r: (STATUS_ORDER.get(r.status, 9), r.learning_id),
    )
    people = config(session, "people")

    out: list[str] = ["# TrueUp Improvements", ""]
    active = [r for r in rows if r.status == "ACTIVE"]
    escalated = [r for r in rows if r.status == "ESCALATED_NO_RULE"]
    failed = [r for r in rows if r.status in ("REPLAY_FAILED", "REJECTED")]

    out += [
        f"_Generated from `trueup_learning_rules` on {dt.date.today().isoformat()}._",
        "",
        f"- **{len(active)}** active rule(s)",
        f"- **{len(failed)}** candidate(s) rejected or failed replay",
        f"- **{len(escalated)}** diagnosed outcome(s) escalated with no rule proposed",
        "",
        "Rules are read by the agents from the database, never from this file.",
        "",
    ]

    if active:
        out.append("## Active rules")
        out.append("")
        for r in active:
            out += _render_rule(session, r, people)

    if failed:
        out.append("## Candidates that did not survive replay")
        out.append("")
        for r in failed:
            rr = r.replay_result_json or {}
            key = (r.candidate_rule_json or {}).get("rule_key", "(no candidate)")
            out += [
                f"### {key} — {r.status}",
                "",
                f"- Root cause: `{r.root_cause}`",
                f"- Verdict: {rr.get('verdict_reason', 'n/a')}",
                f"- Regressions: {rr.get('regression_count', 'n/a')}",
                "",
                "  This candidate was blocked before any human was asked to approve it.",
                "",
            ]

    if escalated:
        out.append("## Diagnosed, but deliberately not automated")
        out.append("")
        for r in escalated:
            ob = session.get(TrueupObligation, r.obligation_id)
            out += [
                f"### {r.root_cause} — {ob.vendor_id if ob else '?'} {ob.period if ob else ''}",
                "",
                f"- Variance: {r.variance_amount} "
                f"({r.variance_percent if r.variance_percent is not None else 'n/a'}%)",
                f"- {r.root_cause_summary}",
                "",
            ]

    text = "\n".join(out).rstrip() + "\n"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return text


def _render_rule(session: Session, r: TrueupLearningRule, people: dict) -> list[str]:
    c = r.candidate_rule_json or {}
    rr = r.replay_result_json or {}
    scope = c.get("scope", {})
    action = c.get("action", {})
    approver = people.get(r.approved_by or "", {}).get("name", r.approved_by or "unknown")

    action_line = {
        "REQUIRE_EVIDENCE": f"Require evidence `{action.get('evidence_type')}` before asserting an amount",
        "REQUIRE_OUTREACH": f"Require outreach to {action.get('outreach_role')} before estimating",
        "REQUIRE_CONTROLLER": "Require Controller review",
        "PROHIBIT_ESTIMATOR": f"Prohibit estimator `{action.get('estimator')}`",
        "SELECT_ESTIMATOR": f"Select estimator `{action.get('estimator')}`",
    }.get(action.get("action_type"), action.get("action_type", "?"))

    counts = rr.get("counts", {})
    lines = [
        f"### {c.get('title', c.get('rule_key'))}",
        "",
        f"- **Rule key**: `{c.get('rule_key')}`",
        f"- **Status**: {r.status}",
        f"- **Root cause addressed**: `{r.root_cause}`",
        f"- **Trigger**: {', '.join(scope.get('conditions', [])) or 'n/a'}",
        f"- **Scope**: {', '.join(scope.get('purchase_types', [])) or 'all purchase types'}",
        f"- **Action**: {action_line}",
        f"- **Source outcomes**: {', '.join(c.get('source_learning_ids', [])) or 'n/a'}",
        f"- **Historical replay**: {rr.get('cases_replayed', '?')} case(s) — "
        f"baseline MAE {rr.get('baseline_mae', '?')}, candidate MAE {rr.get('candidate_mae', '?')}",
        f"- **In-scope cases**: {counts.get('positive', 0)} "
        f"(baseline MAE {rr.get('baseline_mae_positive','?')} -> "
        f"{rr.get('candidate_mae_positive','?')})",
        f"- **Out-of-scope cases left unchanged**: {counts.get('negative', 0)} "
        f"({'yes' if rr.get('negative_cases_unchanged') else 'NO - see regressions'})",
        f"- **Held-out cases**: {counts.get('held_out', 0)} "
        f"(baseline MAE {rr.get('baseline_mae_held_out','?')} -> "
        f"{rr.get('candidate_mae_held_out','?')}) — excluded from deriving this rule",
        f"- **Regressions**: {rr.get('regression_count', 0)}",
        f"- **Approved by**: {approver}",
        f"- **Effective date**: {r.updated_at:%Y-%m-%d}",
        "",
        f"> {c.get('rationale', '')}",
        "",
    ]
    return lines
