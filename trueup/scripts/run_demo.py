#!/usr/bin/env python3
"""End-to-end demonstration.

Runs the same twelve months of Orbit Labs twice, in two independent databases:

  BASELINE    - the original estimator, no learned rules, ever.
  CALIBRATED  - identical code, but the eleven historical closes are replayed,
                graded by the invoices that followed, diagnosed, and the
                surviving candidate rules are activated before the live close.

Then it compares the two on the live period. The numbers are computed from the
runs; nothing is asserted.

Works with no GEMINI_API_KEY - the deterministic stub stands in for the model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import HISTORICAL_PERIODS, LIVE_PERIOD, OUT_DIR, PROJECT_ROOT
from app.db.session import init_db, session_scope, use_database
from app.services import metrics
from app.services.learning.improvements import generate
from app.services.llm import get_llm
from app.services.orchestrator import run_close
from app.services.simulator.backtest import close_and_grade, grade_period, run_calibration
from app.services.simulator.seed import seed_all

# Stand-in inbox. In production these are real replies from real people; here they
# let the demo show an outreach request being answered and the answer becoming
# attributable evidence. Reasons with no entry go unanswered on purpose - silence
# must escalate, never resolve.
FIXTURE_REPLIES = {
    "MISSING_USAGE": (
        "Hi - checked the Vanta console just now. 550 monitored assets were active "
        "for the December service period. - Taylor"
    ),
}


def banner(t):
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def build(db_path: Path):
    use_database(f"sqlite:///{db_path}")
    init_db(drop=True)
    with session_scope() as s:
        return seed_all(s)


def run_mode(db_path: Path, *, calibrate: bool, label: str):
    banner(f"{label}  (db: {db_path.name})")
    stats = build(db_path)
    print(f"seeded: {stats['vendors']} vendors, {stats['contract_versions']} contract versions, "
          f"{stats['ap_invoices']} AP invoices, {stats['non_po_spend']} non-PO transactions, "
          f"{stats['pdf_documents']} source PDFs")

    if calibrate:
        print(f"\n-- historical calibration over {len(HISTORICAL_PERIODS)} prior closes --")
        with session_scope() as s:
            cal = run_calibration(s, HISTORICAL_PERIODS)
        for p in cal["per_period"]:
            print(f"   {p['period']}: {p['obligations']:>2} obligations, {p['posted']:>2} posted "
                  f"({p['posted_amount']:>12}), {p['no_accrual']} no-accrual, "
                  f"{p['graded_cases']} graded")
        print(f"\n   outcomes examined     : {cal['candidates_considered']}")
        print(f"   rules ACTIVATED       : {len(cal['rules_activated'])} "
              f"{cal['rules_activated'] or ''}")
        print(f"   rules rejected        : {len(cal['rules_rejected'])} "
              f"{cal['rules_rejected'] or ''}")
        print(f"   escalated, no rule    : {len(cal['escalated_without_rule'])} "
              f"(diagnosed, deliberately not automated)")
        with session_scope() as s:
            from sqlalchemy import select
            from app.models import TrueupLearningRule
            for r in s.scalars(select(TrueupLearningRule).where(
                    TrueupLearningRule.status == "ACTIVE")):
                rr = r.replay_result_json or {}
                print(f"      -> {(r.candidate_rule_json or {}).get('rule_key')}: "
                      f"replay {rr.get('cases_replayed')} cases, MAE "
                      f"{rr.get('baseline_mae')} -> {rr.get('candidate_mae')}, "
                      f"{rr.get('regression_count')} regressions")
    else:
        print(f"\n-- historical closes, NO learning (frozen baseline) --")
        with session_scope() as s:
            for p in HISTORICAL_PERIODS:
                close_and_grade(s, p)

    print(f"\n-- live close {LIVE_PERIOD} --")
    with session_scope() as s:
        live = run_close(s, LIVE_PERIOD, fixture_replies=FIXTURE_REPLIES)
        grade_period(s, LIVE_PERIOD)
    print("   " + json.dumps(live["accrual_status"]) +
          f"  posted={live['posted']} amount={live['posted_amount']}")

    with session_scope() as s:
        m_live = metrics.compute(s, [LIVE_PERIOD], label=f"{label} / live")
        m_all = metrics.compute(s, None, label=f"{label} / all periods")
    return m_live, m_all


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"LLM client: {get_llm().name}"
          + ("  (no GEMINI_API_KEY set - deterministic stub in use)"
             if get_llm().name == "stub" else ""))

    base_live, base_all = run_mode(PROJECT_ROOT / "trueup_baseline.db",
                                   calibrate=False, label="FROZEN BASELINE")
    cal_live, cal_all = run_mode(PROJECT_ROOT / "trueup_calibrated.db",
                                 calibrate=True, label="CALIBRATED AGENT")

    banner("LIVE PERIOD COMPARISON  (2026-12)")
    cmp_live = metrics.compare(base_live, cal_live)
    for k, v in cmp_live.items():
        if isinstance(v, dict) and "delta" in v:
            mark = "" if v["improved"] is None else ("  <-- improved" if v["improved"] else "  <-- WORSE")
            print(f"  {k:36} {v['baseline']:>12} -> {v['calibrated']:>12}"
                  f"  (delta {v['delta']:>10}){mark}")
        else:
            print(f"  {k:36} {v}")

    banner("ALL PERIODS COMPARISON  (2026-01 .. 2026-12)")
    for k, v in metrics.compare(base_all, cal_all).items():
        if isinstance(v, dict) and "delta" in v:
            mark = "" if v["improved"] is None else ("  <-- improved" if v["improved"] else "  <-- WORSE")
            print(f"  {k:36} {v['baseline']:>12} -> {v['calibrated']:>12}"
                  f"  (delta {v['delta']:>10}){mark}")
        else:
            print(f"  {k:36} {v}")

    use_database(f"sqlite:///{PROJECT_ROOT / 'trueup_calibrated.db'}")
    with session_scope() as s:
        generate(s, OUT_DIR / "improvements.md")
    (OUT_DIR / "metrics.json").write_text(json.dumps({
        "baseline_live": base_live, "calibrated_live": cal_live,
        "baseline_all": base_all, "calibrated_all": cal_all,
        "comparison_live": cmp_live,
    }, indent=2))
    print(f"\nwrote {OUT_DIR / 'improvements.md'}")
    print(f"wrote {OUT_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
