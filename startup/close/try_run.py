"""Run the whole close, month by month, on a folder of PDFs.

    cd startup && ../.venv/bin/python -m close.try_run ../output/pdf/startup_minimal_data [2026-12 ...] [--fresh] [--improvements FILE]

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
import json
import re
import shutil
from pathlib import Path

from . import case as cases_mod
from . import classifier, detection, estimation, evidence, improvements, invoice_lookup, outreach, settlement, store, tickets
from .llm import bedrock_llm
from .workspace import CLOSE_DIR, Workspace

VENDORS = [("V001", "Mintlify"), ("V002", "OpenAI"), ("V003", "ASUS"), ("V004", "Meta")]
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}
HEADERS = [  # SYNTHETIC: stands in for the e-procurement PO database, which the PDFs cannot provide
    {"po_number": "PO-001", "vendor_name": "Mintlify", "vendor_id": "V001", "order_type": "FO", "requester": "sam.lee", "cost_center_owner": "priya.shah", **YEAR},
    {"po_number": "PO-002", "vendor_name": "OpenAI", "vendor_id": "V002", "order_type": "FO", "requester": "dana.kim", "cost_center_owner": "raj.patel", **YEAR},
    {"po_number": "PO-003", "vendor_name": "ASUS", "vendor_id": "V003", "order_type": "NB", "requester": "alex.chen", "cost_center_owner": "priya.shah"},
    {"po_number": "CAMPAIGN-004", "vendor_name": "Meta", "vendor_id": "V004", "order_type": "NB", "requester": "maria.gomez", "cost_center_owner": "tom.baker",
     "validity_start": "2026-12-01", "validity_end": "2026-12-31"},
]
LINES = [
    {"po_line_id": "PO-001-001", "po_number": "PO-001", "item_category": "P", "contract_id": "CTR-001", "unit_price": 1200, "line_description": "Team documentation platform subscription, billed monthly"},
    {"po_line_id": "PO-002-001", "po_number": "PO-002", "item_category": "B", "contract_id": "CTR-002", "overall_limit": 300000, "line_description": "AI API usage, billed monthly on metered units"},
    {"po_line_id": "PO-003-001", "po_number": "PO-003", "item_category": "",
     "gr_required": True, "quantity_ordered": 25, "unit_price": 1600, "line_description": "Laptop packages for new hires"},
    {"po_line_id": "CAMPAIGN-004-001", "po_number": "CAMPAIGN-004", "item_category": "B", "overall_limit": 30000, "line_description": "Product-launch advertising campaign, charged on delivery"},
]


def next_month(period: str) -> str:
    y, m = map(int, period.split("-"))
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def available_at(period: str, rel: Path) -> str:
    parts, nxt = rel.parts[:-1], next_month(period)
    if "afterclose" in parts:
        return f"{nxt}-20" if "replies" in parts else f"{nxt}-12"
    return f"{nxt}-03" if "replies" in parts else f"{period}-01"


def build_world(root: Path, pdf_dir: Path) -> None:
    (root / "documents").mkdir(parents=True, exist_ok=True)
    dump = lambda name, rows: (root / f"{name}.json").write_text(json.dumps(rows, indent=1))
    dump("vendors", [{"vendor_id": i, "vendor_name": n, "aliases": []} for i, n in VENDORS])
    dump("po_headers", [{"entity_id": "ORBIT-US", "status": "Open", "validity_start": None, "validity_end": None, **h} for h in HEADERS])
    dump("po_lines", [{"contract_id": None, "gr_required": False, "quantity_received": None, "quantity_billed": 0, **l} for l in LINES])
    index = []
    for month in sorted(p for p in pdf_dir.iterdir() if re.fullmatch(r"\d{4}-\d{2}", p.name)):
        for f in sorted(p for p in month.rglob("*") if p.suffix.lower() in (".pdf", ".txt")):
            index.append({"doc_id": f.stem, "file": str(f.resolve()), "period": month.name, "available_at": available_at(month.name, f.relative_to(month))})
    dump("documents/index", index)


def close_out(ws, period: str) -> list[dict]:
    """The cutoff: every estimate becomes the month's accrual and the case is closed. Invoiced cases close with nothing to accrue."""
    everything = cases_mod.load_cases(ws)
    accruals = []
    for c in (c for c in everything if c["period"] == period):
        if c["status"] == "ESTIMATED":
            cases_mod.transition(ws, c, "JOURNALED", "runner", "cutoff: estimate booked as the accrual")
            cases_mod.transition(ws, c, "CLOSED", "runner", "period closed")
            e = c["estimate"]
            accruals.append({"case_key": c["case_key"], "vendor": c["vendor_id"], "category": e["category"], "amount": e["amount"], "calculation": e["calculation"],
                             "estimator": e["estimator"], "complete": e["complete"], "flags": c["flags"]})
        elif c["status"] == "INVOICED":
            cases_mod.transition(ws, c, "CLOSED", "runner", "period closed, invoice on hand")
    cases_mod.save_cases(ws, everything)
    return accruals


def snapshot(ws, period: str, documents: list[dict], accruals: list[dict] | None = None) -> None:
    out = ws.out_dir / period
    for sub in ("documents", "cases", "tables"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for d in documents:
        rows = store.load_table(ws, d["applied_to"]) if d["applied_to"] else []
        key = {"invoices": "invoice_id", "activity": "activity_id", "goods_receipts": "gr_id"}.get(d["applied_to"], "source_doc")
        one = {"file": d["file"], "doc_id": d["doc_id"], "known_from": d.get("available_at"), "doc_type": d["doc_type"], "extracted": d["record"],
               "matched_vendor_id": d["vendor_id"], "matched_po_line_id": d["po_line_id"], "quality": d["quality"], "reasons": d["reasons"],
               "written_to_table": d["applied_to"], "written_row": next((r for r in rows if r.get(key) == d["doc_id"] or r.get("source_doc") == d["doc_id"]), None)}
        (out / "documents" / f"{d['doc_id']}.json").write_text(json.dumps(one, indent=2))
    all_tickets = tickets.load(ws)
    for c in cases_mod.cases_for(ws, period):
        dossier = {k: c[k] for k in ("case_id", "status", "vendor_id", "po_line_id", "flags", "obligation", "invoice_match", "classification", "estimate", "settlement")}
        dossier["tickets"] = [t for t in all_tickets if t["case_id"] == c["case_id"]]
        dossier["decision_log"] = c["decision_log"]
        (out / "cases" / f"{c['case_key'].replace('/', '-')}.json").write_text(json.dumps(dossier, indent=2))
    for table in sorted(ws.db_dir.glob("*.json")):
        shutil.copy(table, out / "tables" / table.name)
    (out / "tickets.json").write_text(json.dumps([t for t in all_tickets if t["period"] == period], indent=2))
    if accruals is not None:
        (out / "accruals.json").write_text(json.dumps(accruals, indent=2))
    settled = [{"case_key": c["case_key"], **c["settlement"]} for c in cases_mod.cases_for(ws, period) if c.get("settlement")]
    (out / "trueups.json").write_text(json.dumps(settled, indent=2))


def show_documents(documents: list[dict]) -> None:
    for d in documents:
        print(f"    {d['doc_id']:<52} {d['doc_type']:<16} {d['quality']:<12} -> {d['applied_to'] or '-'}" + (f"   ! {'; '.join(d['reasons'])}" if d["reasons"] else ""))


def show_cases(ws, period: str) -> None:
    for c in cases_mod.cases_for(ws, period):
        e, s = c.get("estimate"), c.get("settlement")
        amount = f"{e['amount']:>10,.2f} = {e['calculation']}  [{e['estimator']}]" if e and e["amount"] is not None else ("       n/a" if e else "         -")
        tail = f"   actual {s['actual']:,.2f}, true-up {s['true_up']:+,.2f}, {s['cause']}" + ("" if s["explained"] else " (asked the vendor)") if s else ""
        print(f"    {c['case_key']:<18} {c['status']:<17} {amount}{tail}  {c['flags'] or ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf_dir", type=Path)
    ap.add_argument("periods", nargs="*", help="months to run, e.g. 2026-12 (default: every month folder, in order)")
    ap.add_argument("--improvements", type=Path, help="a lessons file to install as state/improvements.md before the run")
    ap.add_argument("--fresh", action="store_true", help="wipe close/_run/try first (otherwise earlier months and unchanged documents are kept)")
    args = ap.parse_args()

    root = CLOSE_DIR / "_run" / "try"
    if args.fresh:
        shutil.rmtree(root, ignore_errors=True)
    build_world(root / "world", args.pdf_dir)
    if args.improvements:
        (root / "state").mkdir(parents=True, exist_ok=True)
        shutil.copy(args.improvements, root / "state" / "improvements.md")
    periods = args.periods or sorted(p.name for p in args.pdf_dir.iterdir() if re.fullmatch(r"\d{4}-\d{2}", p.name))
    ws = Workspace(world_dir=root / "world", db_dir=root / "db", state_dir=root / "state", out_dir=root / "out", as_of=f"{periods[0]}-01T00:00:00Z").ensure()

    for period in periods:
        nxt, accruals = next_month(period), None
        shutil.rmtree(ws.out_dir / period, ignore_errors=True)
        active = [l["id"] for l in improvements.load(ws) if l["status"] == "ACTIVE"]
        print(f"\n================ {period}   (active lessons: {active or 'none'}) ================")
        for label, day, cutoff in (("close pass 1", "02", False), ("close pass 2 - cutoff", "05", True)):
            ws = ws.at(f"{nxt}-{day}T12:00:00Z")
            print(f"\n  -- {label}, clock {ws.as_of}")
            documents = evidence.run(ws, bedrock_llm, period)
            show_documents(documents)
            detection.run(ws, period)
            invoice_lookup.run(ws, period)
            classifier.run(ws, bedrock_llm, period)
            estimation.run(ws, bedrock_llm, period)
            for t in outreach.run(ws, bedrock_llm, period, deadline=f"{nxt}-05T00:00:00Z"):
                print(f"    ticket {t['ticket_id']:<52} {t['state']:<9} to {t['to']} ({t['asked_of']})")
            if cutoff:
                accruals = close_out(ws, period)
            show_cases(ws, period)
            snapshot(ws, period, documents, accruals)
        for label, day in (("settle pass 1", "15"), ("settle pass 2", "25")):
            ws = ws.at(f"{nxt}-{day}T12:00:00Z")
            documents = evidence.run(ws, bedrock_llm, period)
            outreach.run(ws, bedrock_llm, period, deadline=f"{nxt}-05T00:00:00Z")      # vendor replies -> ANSWERED
            settled = settlement.run(ws, period)
            changed = outreach.run(ws, bedrock_llm, period, deadline=f"{nxt}-05T00:00:00Z")  # word the vendor questions settlement just opened
            changed = [t for t in tickets.load(ws) if t["period"] == period and t["asked_of"] == "VENDOR"]
            if documents or settled:
                print(f"\n  -- {label}, clock {ws.as_of}")
                show_documents(documents)
                for t in (t for t in changed if t["asked_of"] == "VENDOR"):
                    print(f"    ticket {t['ticket_id']:<52} {t['state']:<9} to {t['to']} ({t['asked_of']})")
                show_cases(ws, period)
            snapshot(ws, period, documents)
        total = sum(a["amount"] for a in accruals or [])
        print(f"\n  {period} accrued {total:,.2f} over {len(accruals or [])} case(s); files: {ws.out_dir / period}/")


if __name__ == "__main__":
    main()
