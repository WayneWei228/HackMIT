"""Try the workers built so far (Evidence, then Detection) on a folder of PDFs.

    cd startup && ../.venv/bin/python -m close.try_run <pdf_dir> [--skip-jev] [--fresh]

Folder layout decides when a document becomes visible: reference/ -> 2026-01-01, <YYYY-MM>/ -> the 28th of
that month, <YYYY-MM>/afterclose/ -> the 12th of the next month. Two passes run: the close (as_of 2027-01-05)
and the settlement (as_of 2027-01-25), so after-close documents only appear in the second one.
Everything is written under close/_run/try/ (git-ignored).
"""
import argparse
import json
import re
import shutil
from pathlib import Path

from . import detection, evidence, store
from .jev import TypeSafeJev
from .llm import bedrock_llm
from .workspace import CLOSE_DIR, Workspace

CLOSE_AS_OF, SETTLE_AS_OF = "2027-01-05T12:00:00Z", "2027-01-25T12:00:00Z"
VENDORS = [("V001", "Mintlify"), ("V002", "OpenAI"), ("V003", "ASUS"), ("V004", "Meta"), ("V005", "Twilio")]
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}
HEADERS = [
    {"po_number": "PO-001", "vendor_id": "V001", "order_type": "FO", **YEAR},
    {"po_number": "PO-002", "vendor_id": "V002", "order_type": "FO", **YEAR},
    {"po_number": "PO-003", "vendor_id": "V003", "order_type": "NB"},
    {"po_number": "CAMPAIGN-004", "vendor_id": "V004", "order_type": "NB"},
    {"po_number": "PO-005", "vendor_id": "V005", "order_type": "NB"},
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
    {"po_line_id": "PO-005-001", "po_number": "PO-005", "item_category": "", "pricing_model": "UNIT", "billing_frequency": "NONE",
     "gr_required": True, "quantity_ordered": 1, "unit_price": 5000, "line_description": "Monthly SMS usage charges billed per message sent"},
]
RECEIPTS = [{"gr_id": "GR-TWILIO-DEC", "po_line_id": "PO-005-001", "received_date": "2026-12-31", "quantity": 1, "available_at": "2026-12-31"}]
CARDS = [
    {"transaction_id": "RAMP-1", "program": "Ramp", "merchant": "Delta Air Lines", "transaction_date": "2026-12-04", "status": "CLEARED",
     "authorized_amount": 1840.00, "settled_amount": 1840.00, "settled_at": "2026-12-06", "erp_exported_at": "2026-12-15", "available_at": "2026-12-04"},
    {"transaction_id": "RAMP-2", "program": "Ramp", "merchant": "WeWork day passes", "transaction_date": "2026-12-12", "status": "CLEARED",
     "authorized_amount": 6610.25, "settled_amount": 6610.25, "settled_at": "2026-12-14", "erp_exported_at": None, "available_at": "2026-12-12"},
    {"transaction_id": "RAMP-3", "program": "Ramp", "merchant": "Figma", "transaction_date": "2026-12-30", "status": "PENDING",
     "authorized_amount": 1210.00, "settled_amount": None, "settled_at": None, "erp_exported_at": None, "available_at": "2026-12-30"},
    {"transaction_id": "RAMP-4", "program": "Ramp", "merchant": "Uber", "transaction_date": "2027-01-02", "status": "PENDING",
     "authorized_amount": 64.10, "settled_amount": None, "settled_at": None, "erp_exported_at": None, "available_at": "2027-01-02"},
]


class SkipJev:
    """Stands in when there is no TYPESAFE_API_KEY: agrees with the extractor and says so in every answer."""

    def ask(self, state, questions, *, tag):  # noqa: ARG002
        out = {q: {"type": "noul", "noul": 1.0, "skipped": True} for q in questions}
        out["changes_prior_terms"]["noul"] = 0.0
        out["doc_type"] = {"type": "choice", "choice": state["extracted"]["document_type"], "confidence": 1.0,
                           "probabilities": {}, "skipped": True}
        return out


def available_at(rel: Path) -> str:
    parts = rel.parts
    month = next((p for p in parts if re.fullmatch(r"\d{4}-\d{2}", p)), None)
    if month is None:
        return "2026-01-01"
    if "afterclose" in parts:
        y, m = map(int, month.split("-"))
        return f"{y + m // 12}-{m % 12 + 1:02d}-12"
    return f"{month}-28"


def build_world(root: Path, pdf_dir: Path) -> None:
    (root / "documents").mkdir(parents=True, exist_ok=True)
    dump = lambda name, rows: (root / f"{name}.json").write_text(json.dumps(rows, indent=1))
    dump("vendors", [{"vendor_id": i, "vendor_name": n, "aliases": []} for i, n in VENDORS])
    dump("company", {"entity_id": "ORBIT-US", "name": "Orbit Labs, Inc.", "materiality": 10000, "de_minimis": 2500})
    dump("po_headers", [{"entity_id": "ORBIT-US", "status": "Open", "validity_start": None, "validity_end": None, **h} for h in HEADERS])
    dump("po_lines", [{"contract_id": None, "gr_required": False, **l} for l in LINES])
    dump("goods_receipts", RECEIPTS)
    dump("card_transactions", CARDS)
    files = sorted(p for p in pdf_dir.rglob("*") if p.suffix.lower() in (".pdf", ".txt"))
    dump("documents/index", [{"doc_id": p.stem.removeprefix("ISSUE-"), "file": str(p.resolve()),
                              "available_at": available_at(p.relative_to(pdf_dir))} for p in files])


def show(title: str, rows: list[dict], cols: tuple[str, ...]) -> None:
    print(f"\n  {title} ({len(rows)})")
    for r in rows:
        print("    " + "  ".join(f"{c}={r.get(c)}" for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf_dir", type=Path)
    ap.add_argument("--skip-jev", action="store_true", help="no Jev key: accept the extractor's record unverified")
    ap.add_argument("--fresh", action="store_true", help="wipe close/_run/try first (otherwise unchanged documents are cached)")
    args = ap.parse_args()

    root = CLOSE_DIR / "_run" / "try"
    if args.fresh:
        shutil.rmtree(root, ignore_errors=True)
    build_world(root / "world", args.pdf_dir)
    ws = Workspace(world_dir=root / "world", db_dir=root / "db", state_dir=root / "state", out_dir=root / "out",
                   as_of=CLOSE_AS_OF).ensure()
    jev = SkipJev() if args.skip_jev else TypeSafeJev(ws)

    for label, as_of in (("CLOSE", CLOSE_AS_OF), ("SETTLEMENT", SETTLE_AS_OF)):
        ws = ws.at(as_of)
        print(f"\n=== {label} pass, as_of {as_of} ===")
        for d in evidence.run(ws, bedrock_llm, jev, "2026-12"):
            facts = {k: v for k, v in d["record"].items() if v is not None and k != "document_type"}
            print(f"  {d['doc_id']:<22} {d['doc_type']:<18} {d['quality']:<12} -> {d['applied_to'] or '-':<14} "
                  f"vendor={d['vendor_id']} line={d['po_line_id']}")
            print(f"      {facts}")
            for reason in d["reasons"]:
                print(f"      ! {reason}")
        show("contracts", store.load_table(ws, "contracts"),
             ("contract_id", "version", "status", "monthly_rate", "unit_rate", "effective_start", "effective_end", "source_doc"))
        show("activity", store.load_table(ws, "activity"),
             ("activity_id", "po_line_id", "kind", "service_period", "coverage_start", "coverage_end", "quantity", "value", "replaced_by"))
        show("goods_receipts", store.load_table(ws, "goods_receipts"), ("gr_id", "po_line_id", "received_date", "quantity"))
        show("invoices", store.load_table(ws, "invoices"), ("invoice_id", "po_line_id", "service_period", "amount", "status", "received_date"))
        show("terminations", store.load_table(ws, "terminations"), ("source_doc", "po_line_id", "effective_date"))
        if label == "CLOSE":
            print("\n  --- Detection: obligations for 2026-12 ---")
            for c in detection.run(ws, jev, "2026-12"):
                o = c["obligation"]
                extra = {k: o[k] for k in ("settled_unbooked", "pending", "already_booked") if k in o}
                print(f"  {c['case_key']:<18} {c['vendor_name']:<9} {o['recognition_basis']:<17} flags={c['flags']} evidence={c['evidence_refs']}")
                print(f"      why: {'; '.join(o['reasons'])} {extra or ''}")
    print(f"\nFull output: {root / 'db'}/*.json (documents.json has every record, Jev check and reason)")


if __name__ == "__main__":
    main()
