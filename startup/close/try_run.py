"""Run the whole close, month by month, on a folder of PDFs. A thin CLI over `close.runner`.

    cd startup && ../.venv/bin/python -m close.try_run ../output/pdf/startup_minimal_data [2026-12 ...] [--fresh] [--improvements FILE]

Nothing is seeded: the vendors, the purchase orders and their lines are built by the Evidence worker from the
PURCHASE ORDER documents in the folders, exactly like every other table.

Folders decide when a document becomes known (<next> = the following month):
    <P>/*                      during the month              (<P>-01)
    <P>/replies/*              answers before the cutoff     (<next>-03)   a reply is named REPLY-<ticket_id>
    <P>/afterclose/*           arrives after the close       (<next>-12)
    <P>/afterclose/replies/*   vendor answers after close    (<next>-20)
Each month runs in four passes on a simulated clock:
    <next>-02  close pass 1   evidence, detection, invoice lookup, classification, estimation, outreach (asks)
    <next>-05  close pass 2   the same again with the replies, outreach (answers / expiries -> forced estimates), close out
    <next>-15  settle pass 1  evidence (after-close documents), settlement (true-ups, vendor questions)
    <next>-25  settle pass 2  evidence (vendor replies), outreach (answers), settlement (explanations)
Everything is written under close/_run/try/ (git-ignored):
    out/<P>/documents/<DOC>.json   what Evidence extracted from each document and the row it wrote
    out/<P>/cases/<LINE>.json      one dossier per case: obligation, invoice match, classification, estimate, settlement, tickets, decisions
    out/<P>/accruals.json  tickets.json  trueups.json  tables/
"""
import argparse
import shutil
from pathlib import Path

from . import runner
from .llm import bedrock_llm
from .workspace import CLOSE_DIR


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf_dir", type=Path)
    ap.add_argument("periods", nargs="*", help="months to run, e.g. 2026-12 (default: every month folder, in order)")
    ap.add_argument("--improvements", type=Path, help="a lessons file to install as state/improvements.md before the run")
    ap.add_argument("--fresh", action="store_true", help="wipe close/_run/try first (otherwise earlier months and unchanged documents are kept)")
    args = ap.parse_args()

    root = CLOSE_DIR / "_run" / "try"
    if args.fresh:
        runner.reset(root)
    if args.improvements:
        (root / "state").mkdir(parents=True, exist_ok=True)
        shutil.copy(args.improvements, root / "state" / "improvements.md")

    for period in args.periods or runner.periods(args.pdf_dir):
        runner.run_close(root, args.pdf_dir, period, bedrock_llm, out=print)
        runner.run_settlement(root, args.pdf_dir, period, bedrock_llm, out=print)
        accruals = runner.read_json(root / "out" / period / "accruals.json")
        total = sum(a["amount"] for a in accruals)
        print(f"\n  {period} accrued {total:,.2f} over {len(accruals)} case(s); files: {root / 'out' / period}/")


if __name__ == "__main__":
    main()
