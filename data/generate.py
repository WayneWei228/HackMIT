"""Generate the Northstar Analytics fixture set into data/northstar/.

Run from the repo root:  uv run --with reportlab python data/generate.py
(plain `python3 data/generate.py` also works; it just skips the PDFs.)
Output is deterministic: same code, same files.
"""
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gen import docs, ledger, records, truth, world as w  # noqa: E402

OUT = Path(__file__).parent / "northstar"


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ("contracts", "invoices/pdf", "evidence", "inbox/attachments", "ground_truth"):
        (OUT / sub).mkdir(parents=True)

    invoices = records.build_invoices()
    pos, change_orders = records.build_pos()
    answer_key = truth.build_truth(invoices)
    contracts = {v["vendor_id"]: docs.contract_text(v) for v in w.VENDORS}

    write_json(OUT / "company.json", w.COMPANY)
    write_json(OUT / "org_directory.json", {
        "employees": [dict(zip(("employee_id", "name", "title", "role", "cost_center", "legal_entity_id"), e),
                           email=e[1].lower().replace(" ", ".") + "@northstar.example") for e in w.EMPLOYEES],
        "vendor_contacts": [{"vendor_id": v["vendor_id"], "name": v["billing_contact"], "email": v["billing_email"],
                             "role": "VENDOR_BILLING"} for v in w.VENDORS]})
    write_json(OUT / "vendors.json", w.VENDORS)
    write_json(OUT / "purchase_orders.json", pos)
    write_json(OUT / "change_orders.json", change_orders)
    write_json(OUT / "policies.json", docs.POLICIES_JSON)
    (OUT / "close_policy_manual.md").write_text(docs.POLICY_MANUAL)
    for vid, text in contracts.items():
        (OUT / "contracts" / f"{w.VENDOR[vid]['contract_id']}.txt").write_text(text + "\n")
    write_json(OUT / "invoices" / "invoices.json", invoices)
    write_csv(OUT / "ap_queue.csv", ledger.build_ap_queue(invoices))
    write_csv(OUT / "gl_entries.csv", ledger.build_gl(invoices))
    write_csv(OUT / "evidence" / "usage_daily.csv", records.build_usage())
    write_csv(OUT / "evidence" / "seat_snapshots.csv", records.build_seats())
    write_csv(OUT / "evidence" / "timesheets.csv", records.build_timesheets())
    write_csv(OUT / "evidence" / "hr_hires.csv", records.build_hires())
    write_csv(OUT / "evidence" / "goods_receipts.csv", records.build_deliveries())
    write_json(OUT / "inbox" / "scripted_responses.json", truth.build_inbox(answer_key))
    (OUT / "inbox" / "attachments" / "DOC-PAGERLOOP-UPLIFT-NOTICE.txt").write_text(
        "PagerLoop Inc. - Renewal Pricing Notice\nDate: October 28, 2026\nTo: Northstar Analytics billing contact\n\n"
        "Under section 4.3 of our agreement (CTR-005), Fees will increase by 5.5% effective January 1, 2027.\n"
        "Current monthly fee: $6,400.00. New monthly fee: $6,752.00.\n")
    write_csv(OUT / "ground_truth" / "obligations_truth.csv", answer_key)
    write_json(OUT / "ground_truth" / "extra_exceptions.json", truth.EXTRA_EXCEPTIONS)

    pdfs = docs.render_pdfs(OUT, contracts, invoices)
    print(f"vendors={len(w.VENDORS)} invoices={len(invoices)} obligations={len(answer_key)} "
          f"pdfs={'yes' if pdfs else 'skipped (no reportlab)'} -> {OUT}")


if __name__ == "__main__":
    main()
