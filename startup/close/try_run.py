"""Run the workers built so far (Evidence, Detection, Invoice Lookup) month by month on a folder of PDFs.

    cd startup && ../.venv/bin/python -m close.try_run ../output/pdf/startup_minimal_data [2026-12 ...] [--skip-jev] [--fresh]

<pdf_dir>/<YYYY-MM>/ holds the documents of that month. Each monthly run reads ONLY its own folder; what earlier
months established (contracts, invoices) is already in the db, exactly as in a real close. With no period given,
every month folder is run in order. The clock of a run is the 5th of the following month.
Everything is written under close/_run/try/ (git-ignored).
"""
import argparse
import json
import re
import shutil
from pathlib import Path

from . import detection, evidence, invoice_lookup, store
from .jev import TypeSafeJev
from .llm import bedrock_llm
from .workspace import CLOSE_DIR, Workspace

VENDORS = [("V001", "Mintlify"), ("V002", "OpenAI"), ("V003", "ASUS"), ("V004", "Meta")]
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}
HEADERS = [
    {"po_number": "PO-001", "vendor_id": "V001", "order_type": "FO", **YEAR},
    {"po_number": "PO-002", "vendor_id": "V002", "order_type": "FO", **YEAR},
    {"po_number": "PO-003", "vendor_id": "V003", "order_type": "NB"},
    {"po_number": "CAMPAIGN-004", "vendor_id": "V004", "order_type": "NB", "validity_start": "2026-12-01", "validity_end": "2026-12-31"},
]
LINES = [
    {"po_line_id": "PO-001-001", "po_number": "PO-001", "item_category": "P", "contract_id": "CTR-001", "pricing_model": "FIXED",
     "billing_frequency": "MONTHLY", "unit_price": 1200, "line_description": "Team documentation platform subscription, billed monthly"},
    {"po_line_id": "PO-002-001", "po_number": "PO-002", "item_category": "B", "contract_id": "CTR-002", "pricing_model": "USAGE",
     "billing_frequency": "MONTHLY", "overall_limit": 300000, "line_description": "AI API usage, billed monthly on metered units"},
    {"po_line_id": "PO-003-001", "po_number": "PO-003", "item_category": "", "pricing_model": "UNIT", "billing_frequency": "NONE",
     "gr_required": True, "quantity_ordered": 25, "unit_price": 1600, "line_description": "Laptop packages for new hires"},
    {"po_line_id": "CAMPAIGN-004-001", "po_number": "CAMPAIGN-004", "item_category": "B", "pricing_model": "LIMIT",
     "billing_frequency": "NONE", "overall_limit": 30000, "line_description": "Product-launch advertising campaign, charged on delivery"},
]

class SkipJev:
    """Stands in when there is no TYPESAFE_API_KEY: agrees with the extractor and says so in every answer."""

    def ask(self, state, questions, *, tag):  # noqa: ARG002
        out = {q: {"type": "noul", "noul": 1.0, "skipped": True} for q in questions}
        out["changes_prior_terms"]["noul"] = 0.0
        out["doc_type"] = {"type": "choice", "choice": state["extracted"]["document_type"], "confidence": 1.0,
                           "probabilities": {}, "skipped": True}
        return out


def close_clock(period: str) -> str:
    y, m = map(int, period.split("-"))
    return f"{y + m // 12}-{m % 12 + 1:02d}-05T12:00:00Z"


def build_world(root: Path, pdf_dir: Path) -> None:
    (root / "documents").mkdir(parents=True, exist_ok=True)
    dump = lambda name, rows: (root / f"{name}.json").write_text(json.dumps(rows, indent=1))
    dump("vendors", [{"vendor_id": i, "vendor_name": n, "aliases": []} for i, n in VENDORS])
    dump("po_headers", [{"entity_id": "ORBIT-US", "status": "Open", "validity_start": None, "validity_end": None, **h} for h in HEADERS])
    dump("po_lines", [{"contract_id": None, "gr_required": False, "quantity_received": None, "quantity_billed": 0, **l} for l in LINES])
    files = sorted(p for p in pdf_dir.glob("*/*") if p.suffix.lower() in (".pdf", ".txt") and re.fullmatch(r"\d{4}-\d{2}", p.parent.name))
    dump("documents/index", [{"doc_id": p.stem, "file": str(p.resolve()), "period": p.parent.name} for p in files])


def show(title: str, rows: list[dict], cols: tuple[str, ...]) -> None:
    print(f"\n  {title} ({len(rows)})")
    for r in rows:
        print("    " + "  ".join(f"{c}={r.get(c)}" for c in cols))


def snapshot(ws, period: str, documents: list[dict], cases: list[dict], matched: list[dict]) -> None:
    """Freeze what each worker produced for this month under out/<period>/, so later months do not overwrite it."""
    out = ws.out_dir / period
    shutil.rmtree(out, ignore_errors=True)
    (out / "evidence" / "tables").mkdir(parents=True)
    (out / "detection").mkdir()
    (out / "evidence" / "documents_read_this_month.json").write_text(json.dumps(documents, indent=2))
    (out / "evidence" / "documents").mkdir()
    for d in documents:  # one file per PDF, for checking them one by one
        rows = store.load_table(ws, d["applied_to"]) if d["applied_to"] else []
        one = {"pdf": d["file"], "doc_id": d["doc_id"], "doc_type": d["doc_type"], "extracted": d["record"],
               "matched_vendor_id": d["vendor_id"], "matched_po_line_id": d["po_line_id"], "jev_checks": d["checks"],
               "quality": d["quality"], "reasons": d["reasons"], "written_to_table": d["applied_to"],
               "written_row": next((r for r in rows if r.get("source_doc") == d["doc_id"]), None)}
        (out / "evidence" / "documents" / f"{d['doc_id']}.json").write_text(json.dumps(one, indent=2))
    for table in sorted(ws.db_dir.glob("*.json")):
        if table.name != "documents.json":
            shutil.copy(table, out / "evidence" / "tables" / table.name)
    (out / "detection" / "cases.json").write_text(json.dumps(cases, indent=2))
    (out / "invoice_lookup").mkdir()
    (out / "invoice_lookup" / "cases.json").write_text(json.dumps(matched, indent=2))
    invoices = store.visible(store.load_table(ws, "invoices"), ws.as_of)
    for c in matched:  # one file per detected PO line: what lookup saw, and what it concluded
        same_line = [i for i in invoices if i.get("po_line_id") == c["po_line_id"]]
        one = {"case_id": c["case_id"], "po_line_id": c["po_line_id"], "vendor_id": c["vendor_id"],
               "recognition_basis": c["obligation"]["recognition_basis"],
               "input_invoices_for_this_line": [{k: i.get(k) for k in ("invoice_id", "service_period", "amount", "status")} for i in same_line],
               "output_invoice_match": c["invoice_match"], "flags": c["flags"],
               "decision": [d for d in c["decision_log"] if d["worker"] == "invoice_lookup"]}
        (out / "invoice_lookup" / f"{c['case_key']}.json").write_text(json.dumps(one, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf_dir", type=Path)
    ap.add_argument("periods", nargs="*", help="months to run, e.g. 2026-12 (default: every month folder, in order)")
    ap.add_argument("--skip-jev", action="store_true", help="no Jev key: accept the extractor's record unverified")
    ap.add_argument("--fresh", action="store_true", help="wipe close/_run/try first (otherwise earlier months and unchanged documents are kept)")
    args = ap.parse_args()

    root = CLOSE_DIR / "_run" / "try"
    if args.fresh:
        shutil.rmtree(root, ignore_errors=True)
    build_world(root / "world", args.pdf_dir)
    periods = args.periods or sorted(p.name for p in args.pdf_dir.iterdir() if re.fullmatch(r"\d{4}-\d{2}", p.name))
    ws = Workspace(world_dir=root / "world", db_dir=root / "db", state_dir=root / "state", out_dir=root / "out",
                   as_of=close_clock(periods[0])).ensure()
    jev = SkipJev() if args.skip_jev else TypeSafeJev(ws)

    for period in periods:
        ws = ws.at(close_clock(period))
        print(f"\n=== {period} close, as_of {ws.as_of} - reading {args.pdf_dir / period}/ ===")
        done = evidence.run(ws, bedrock_llm, jev, period)
        for d in done:
            facts = {k: v for k, v in d["record"].items() if v is not None and k != "document_type"}
            print(f"  {d['doc_id']:<22} {d['doc_type']:<18} {d['quality']:<12} -> {d['applied_to'] or '-':<14} "
                  f"vendor={d['vendor_id']} line={d['po_line_id']}")
            print(f"      {facts}")
            for reason in d["reasons"]:
                print(f"      ! {reason}")
        print(f"\n  --- Detection: PO lines owed for {period} (input: po_headers + po_lines only) ---")
        cases = detection.run(ws, period)
        for c in cases:
            o = c["obligation"]
            print(f"  {c['case_key']:<18} {o['recognition_basis']:<17} why: {'; '.join(o['reasons'])}")
        detected = json.loads(json.dumps(cases))  # Detection's output, before Invoice Lookup writes on the cases
        print(f"\n  --- Invoice Lookup for {period} (input: detected cases + invoices + po_lines) ---")
        matched = invoice_lookup.run(ws, jev, period)
        for c in matched:
            m = c["invoice_match"]
            where = f"on AP {m['on_ap']} / in queue {m['in_queue']}" if m["invoice_ids"] else "nothing on the AP or in the queue"
            print(f"  {c['case_key']:<18} {m['result']:<19} invoiced={m['invoiced_amount']:>10,.2f}  {where}")
        snapshot(ws, period, done, detected, matched)

    print(f"\n=== db after {periods[-1]} ===")
    show("contracts", store.load_table(ws, "contracts"),
         ("contract_id", "version", "status", "monthly_rate", "unit_rate", "effective_start", "effective_end", "source_doc"))
    show("invoices", store.load_table(ws, "invoices"), ("invoice_id", "po_line_id", "service_period", "amount", "status"))
    show("activity", store.load_table(ws, "activity"),
         ("activity_id", "po_line_id", "kind", "service_period", "coverage_start", "coverage_end", "quantity", "value"))
    show("goods_receipts", store.load_table(ws, "goods_receipts"), ("gr_id", "po_line_id", "received_date", "quantity"))
    print(f"\nPer-month output files: {root / 'out'}/<YYYY-MM>/{evidence,detection,invoice_lookup}/")


if __name__ == "__main__":
    main()
