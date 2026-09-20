"""Draft, post and reverse entries for the demo cases: python scripts/run_journal_entries.py."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.estimation_agent import estimate  # noqa: E402
from trueup.agents.journal_entry_service import (  # noqa: E402
    JournalEntryError,
    draft_entry,
    post_due_reversals,
    post_simulated,
)
from trueup.agents.policy_agent import enforce  # noqa: E402
from trueup.close_orchestrator import walk_to  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.store import models as m  # noqa: E402
from trueup.store.workflow import IllegalTransitionError  # noqa: E402

PERIOD = "2026-12"
NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
# Vendor -> amount drafted at close, or None when no entry may be drafted. ASUS waits for the
# Controller, Notability is blocked, and OpenAI has only partial usage at close.
EXPECTED = {
    "VEN-MINTLIFY": "1400.00",
    "VEN-OPENAI": None,
    "VEN-ASUS": None,
    "VEN-META": "24700.00",
    "VEN-NOTABILITY": None,
}


def gl_rows(session, obligation_id):
    return session.scalars(
        select(m.CompanyGLEntry)
        .where(m.CompanyGLEntry.obligation_id == obligation_id)
        .order_by(m.CompanyGLEntry.posting_date, m.CompanyGLEntry.gl_entry_id)
    ).all()


def main() -> None:
    sim = Simulator.initialize()
    sim.advance_to("2026-12-31T23:00:00Z")
    hits = 0
    drafted = []
    with sim.session() as session:
        for vendor_id, expected in EXPECTED.items():
            ob = walk_to(session, vendor_id, PERIOD, now=NOW)
            classify(session, ob.obligation_id, now=NOW)
            estimate(session, ob.obligation_id, now=NOW)
            if (ob.workflow_stage.value, ob.next_action.value) == ("ESTIMATING", "VERIFY_POLICY"):
                enforce(session, ob.obligation_id, now=NOW)
            try:
                result = draft_entry(session, ob.obligation_id, now=NOW)
            except (JournalEntryError, IllegalTransitionError) as exc:
                hit = expected is None
                hits += hit
                print(f"{vendor_id:15} no entry drafted: {exc}  [{'hit' if hit else 'MISS'}]")
                continue
            post_simulated(session, ob.obligation_id, now=NOW)
            accrual = result.entries[0]
            amount = accrual["lines"][0]["debit"]
            hit = amount == expected
            hits += hit
            drafted.append(ob)
            print(
                f"{vendor_id:15} drafted {amount:>10} approved by {result.approved_by}, "
                f"{len(result.entries)} entries  [{'hit' if hit else f'MISS, expected {expected}'}]"
            )

        print(f"\nLedger rows at close ({NOW:%Y-%m-%d}):")
        for ob in drafted:
            for row in gl_rows(session, ob.obligation_id):
                print(f"  {row.gl_entry_id} {row.entry_type.value} {row.status.value}")
        print(f"reversals due at close: {len(post_due_reversals(session, now=NOW).posted)}")

        sim.advance_to("2027-01-02T00:00:00Z")
        after = post_due_reversals(session, now=sim.now())
        print(f"\nClock advanced to {sim.now():%Y-%m-%d}: {len(after.posted)} reversals posted")
        for ob in drafted:
            for row in gl_rows(session, ob.obligation_id):
                print(f"  {row.gl_entry_id} {row.entry_type.value} {row.status.value}")
                for line in row.lines_json:
                    print(
                        f"      {line['account_code']}  debit {line['debit']:>10}  "
                        f"credit {line['credit']:>10}"
                    )
        print(f"second run posts {len(post_due_reversals(session, now=sim.now()).posted)} more")
    print(f"\n{hits}/{len(EXPECTED)} expected outcomes matched")


if __name__ == "__main__":
    main()
