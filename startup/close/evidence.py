"""Evidence worker: canonicalise raw evidence into db tables.

EVERY table starts from a document. The LLM turns document text into a record; code checks it (resolvable PO line,
required fields) and alone decides what gets applied to the canonical tables. A PURCHASE ORDER document builds the
`po_headers` and `po_lines` rows every later worker reads, and a vendor is created the first time a document names
one - nothing is seeded. No Jev here: Jev is used by the Classification worker only.
"""
import hashlib
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

from . import events, safe_math, store
from .workspace import period_bounds

# Optional structured system feeds, when a world directory happens to carry them. Without them the close runs
# entirely on the documents. COPIED tables are taken as-is; on the same key a MERGED feed row wins over the
# document row, because the ERP knows the posting status and the PDF does not.
COPIED = ("card_transactions", "gl", "prior_accruals", "org_directory")
MERGED = {"vendors": "vendor_id", "po_headers": "po_number", "po_lines": "po_line_id",
          "activity": "activity_id", "goods_receipts": "gr_id", "invoices": "invoice_id"}

DOC_TYPES = {
    "CONTRACT": "An original agreement, order form or master service agreement that sets prices or rates.",
    "AMENDMENT": "A change order, renewal or amendment that changes the price, rate or term of an earlier agreement.",
    "TERMINATION_NOTICE": "A notice that ends or cancels a service or agreement from a stated date.",
    "USAGE_REPORT": "A report of metered consumption (units, tokens, API calls, seats) for a period. Not a bill.",
    "DELIVERY_REPORT": "A report of value or spend actually delivered for a period, such as advertising delivered. Not a bill.",
    "TIMESHEET": "Approved hours worked by a contractor or consultant for a period.",
    "GOODS_RECEIPT": "A record that physical goods were received, with a quantity and a date.",
    "INVOICE": "A vendor bill requesting payment.",
    "PURCHASE_ORDER": "A buyer-issued order for goods or services.",
    "OTHER": "None of the above.",
}
RECORD_KEYS = (
    "document_type", "vendor_name", "contract_id", "po_number", "po_line_id", "service_period",
    "amount", "quantity", "unit_rate", "monthly_rate", "effective_start", "effective_end",
    "coverage_start", "coverage_end", "received_date", "termination_effective", "replaces",
    "invoice_number", "invoice_date",
    # a buyer-issued order: the header fields procurement prints on it
    "order_type", "validity_start", "validity_end", "requester", "cost_center_owner",
)
NUMERIC = ("amount", "quantity", "unit_rate", "monthly_rate")
# one order line, as the document prints it. The extractor may return a `lines` array or a single flat line.
LINE_KEYS = ("po_line_id", "item_category", "contract_id", "gr_required",
             "quantity_ordered", "unit_price", "overall_limit", "line_description")
LINE_NUMERIC = ("quantity_ordered", "unit_price", "overall_limit")
ITEM_CATEGORIES = ("P", "B", "E")
ORDER_TYPES = ("FO", "NB")
ACTIVITY_KIND = {"USAGE_REPORT": "USAGE", "DELIVERY_REPORT": "DELIVERY", "TIMESHEET": "TIMESHEET"}
NEEDS_LINE = set(ACTIVITY_KIND) | {"GOODS_RECEIPT"}  # an invoice without a line is kept: Invoice Lookup matches it
# Documents are applied in dependency order, so an invoice in the same folder as its purchase order resolves its line.
APPLY_ORDER = ("PURCHASE_ORDER", "CONTRACT", "AMENDMENT", "TERMINATION_NOTICE", "GOODS_RECEIPT",
               "USAGE_REPORT", "DELIVERY_REPORT", "TIMESHEET", "INVOICE", "OTHER")

def doc_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True)
        return out.stdout
    return path.read_text()


def pull_feeds(ws) -> None:
    """Copy whatever structured system feeds the world happens to carry, visible at ws.as_of, into the db.

    Optional to the last file: with no feeds in the world directory this reads nothing and writes nothing,
    and every table is built from the documents instead."""
    if store.company(ws):  # optional: entity id, materiality, de minimis threshold
        store.save_table(ws, "company", [store.company(ws)])
    for name in COPIED:
        if (ws.world_dir / f"{name}.json").exists():  # no feed, no table
            store.save_table(ws, name, store.world(ws, name))
    for name, key in MERGED.items():
        if not (ws.world_dir / f"{name}.json").exists():
            continue  # no feed: the document rows stand untouched
        feed = store.world(ws, name)
        if not feed:
            continue
        rows = store.load_table(ws, name)
        for row in feed:
            old = next((r for r in rows if r.get(key) == row[key]), {})
            store.upsert(rows, {**old, **row}, (key,))
        store.save_table(ws, name, rows)


def sync_received(ws, period: str) -> None:
    """Keep po_lines.quantity_received in step with the goods received by the end of the period, as the warehouse log would."""
    end = period_bounds(period)[1]
    received: dict[str, float] = {}
    for g in store.visible(store.load_table(ws, "goods_receipts"), ws.as_of):
        if (g.get("received_date") or "") > end:
            continue  # arrived after the period being closed
        received[g["po_line_id"]] = received.get(g["po_line_id"], 0) + (g.get("quantity") or 0)
    lines = store.load_table(ws, "po_lines")
    for line in lines:
        if line["po_line_id"] in received:
            line["quantity_received"] = received[line["po_line_id"]]
        elif "quantity_received" in line:
            line["quantity_received"] = None  # nothing has arrived that this clock and this period can see
    store.save_table(ws, "po_lines", lines)


def number(value) -> float | None:
    if isinstance(value, str):
        try:
            value = safe_math.evaluate(value)
        except ValueError:
            return None
    return round(float(value), 6) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def flag(value) -> bool | None:
    """A yes/no the document printed, however the extractor spelled it."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "y", "required", "1"):
            return True
        if text in ("false", "no", "n", "not required", "0"):
            return False
    return None


def one_of(value, allowed: tuple[str, ...]) -> str | None:
    """The code the document printed, taken from a label such as "FO - framework order" or "P - service"."""
    if not isinstance(value, str):
        return None
    head = re.split(r"[^A-Za-z]", value.strip(), maxsplit=1)[0].upper()
    return head if head in allowed else None


def clean_line(raw: dict) -> dict:
    """One order line: known keys only, numbers as floats, the item category as its bare code."""
    line = {k: raw.get(k) for k in LINE_KEYS}
    for k in LINE_NUMERIC:
        line[k] = number(line[k])
    line["item_category"] = one_of(line["item_category"], ITEM_CATEGORIES) or ""
    line["gr_required"] = bool(flag(line["gr_required"]))
    for k in ("po_line_id", "contract_id", "line_description"):
        line[k] = line[k].strip() if isinstance(line[k], str) and line[k].strip() else None
    return line


def clean(raw: dict) -> dict:
    """Keep only the known keys; numbers become floats or None; order lines become a list."""
    record = {k: raw.get(k) for k in RECORD_KEYS}
    for k in NUMERIC:
        record[k] = number(record[k])
    record["order_type"] = one_of(record["order_type"], ORDER_TYPES)
    if record["document_type"] not in DOC_TYPES:
        record["document_type"] = "OTHER"
    lines = []
    if record["document_type"] == "PURCHASE_ORDER":  # only an order has order lines
        given = raw.get("lines")
        lines = [clean_line(l) for l in given if isinstance(l, dict)] if isinstance(given, list) else []
        if not lines and any(raw.get(k) is not None for k in LINE_KEYS if k != "contract_id"):
            lines = [clean_line(raw)]  # the extractor returned a single flat line instead of an array
    record["lines"] = lines
    return record


def vendor_id_for(name: str) -> str:
    """A deterministic id from the name, so the same vendor gets the same id in every run: "V-MINTLIFY"."""
    slug = re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")
    return f"V-{slug}" if slug else "V-UNKNOWN"


def resolve_vendor(ws, name: str | None, doc_id: str | None = None, available_at: str | None = None) -> dict | None:
    """The vendor this name means, created on first sight. A document is never rejected for naming a new vendor."""
    if not name or not name.strip():
        return None
    want = name.strip().lower()
    vendors = store.load_table(ws, "vendors")
    for v in vendors:
        names = [v["vendor_name"], *v.get("aliases", [])]
        if any(want == n.lower() or want.startswith(n.lower()) or n.lower().startswith(want) for n in names):
            return v
    row = {"vendor_id": vendor_id_for(name.strip()), "vendor_name": name.strip(), "aliases": [],
           "source_doc": doc_id, "available_at": available_at}
    store.upsert(vendors, row, ("vendor_id",))
    store.save_table(ws, "vendors", vendors)
    return row


def resolve_line(ws, record: dict, vendor: dict | None) -> str | None:
    """Exact keys only, in order of strength; ambiguity returns None."""
    lines = store.load_table(ws, "po_lines")
    if any(l["po_line_id"] == record["po_line_id"] for l in lines):
        return record["po_line_id"]
    headers = {h["po_number"]: h for h in store.load_table(ws, "po_headers")}
    tries = (
        [l for l in lines if record["po_number"] and l["po_number"] == record["po_number"]],
        [l for l in lines if record["contract_id"] and l.get("contract_id") == record["contract_id"]],
        [l for l in lines if vendor and headers.get(l["po_number"], {}).get("vendor_id") == vendor["vendor_id"]],
    )
    for hits in tries:
        if len(hits) == 1:
            return hits[0]["po_line_id"]
    return None


def _day_before(iso: str) -> str:
    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()


def apply_contract(ws, doc_id: str, record: dict, vendor: dict | None, available_at: str | None) -> str:
    """Insert the version, then renumber the contract's versions by effective_start: latest is Active."""
    rows = store.load_table(ws, "contracts")
    known = {r["contract_id"] for r in rows}
    contract_id = record["contract_id"]
    if contract_id not in known and record["replaces"] in known:  # extractor put the amendment's own id here
        contract_id = record["replaces"]
    row = {
        "contract_id": contract_id, "source_doc": doc_id, "available_at": available_at,
        "vendor_id": vendor and vendor["vendor_id"], "vendor_name": record["vendor_name"],
        "monthly_rate": record["monthly_rate"], "unit_rate": record["unit_rate"],
        "effective_start": record["effective_start"], "effective_end": record["effective_end"],
    }
    store.upsert(rows, row, ("contract_id", "source_doc"))
    versions = sorted((r for r in rows if r["contract_id"] == row["contract_id"]), key=lambda r: r["effective_start"] or "")
    for n, r in enumerate(versions, start=1):
        r["version"] = n
        last = n == len(versions)
        r["status"] = "Active" if last else "Superseded"
        if not last:
            nxt = versions[n]["effective_start"]
            if nxt and (r["effective_end"] is None or r["effective_end"] >= nxt):
                r["effective_end"] = _day_before(nxt)
            for k in ("monthly_rate", "unit_rate"):  # an amendment that is silent on a rate inherits it
                if versions[n][k] is None:
                    versions[n][k] = r[k]
    store.save_table(ws, "contracts", rows)
    return "contracts"


def apply_purchase_order(ws, doc_id: str, record: dict, vendor: dict | None, available_at: str | None) -> str:
    """Build the purchase tables from the order itself: one `po_headers` row and its `po_lines` rows.

    Re-ingesting a changed order document replaces the rows it wrote; `quantity_received` is re-derived from the
    goods receipts by `sync_received` afterwards, and `quantity_billed` only ever comes from the ERP feed."""
    po_number = record["po_number"] or record["po_line_id"] or doc_id
    headers = store.load_table(ws, "po_headers")
    old = next((h for h in headers if h.get("po_number") == po_number), {})
    store.upsert(headers, {
        **old,
        "po_number": po_number, "vendor_id": vendor and vendor["vendor_id"],
        "vendor_name": (vendor and vendor["vendor_name"]) or record["vendor_name"], "entity_id": None,
        "order_type": record["order_type"], "validity_start": record["validity_start"], "validity_end": record["validity_end"],
        "requester": record["requester"], "cost_center_owner": record["cost_center_owner"],
        "status": "Open", "source_doc": doc_id, "available_at": available_at,
    }, ("po_number",))
    store.save_table(ws, "po_headers", headers)

    rows = [l for l in store.load_table(ws, "po_lines") if l.get("source_doc") != doc_id]  # this order's old rows go
    for n, line in enumerate(record["lines"] or [{}], start=1):
        old_line = next((l for l in rows if l.get("po_line_id") == line.get("po_line_id")), {})
        store.upsert(rows, {
            **old_line,
            "po_line_id": line.get("po_line_id") or f"{po_number}-{n:03d}", "po_number": po_number,
            "item_category": line.get("item_category") or "", "contract_id": line.get("contract_id") or record["contract_id"],
            "gr_required": bool(line.get("gr_required")), "quantity_ordered": line.get("quantity_ordered"),
            "unit_price": line.get("unit_price"), "overall_limit": line.get("overall_limit"),
            "quantity_received": old_line.get("quantity_received"), "quantity_billed": old_line.get("quantity_billed") or 0,
            "line_description": line.get("line_description"), "source_doc": doc_id, "available_at": available_at,
        }, ("po_line_id",))
    store.save_table(ws, "po_lines", rows)
    return "po_headers"


def apply(ws, doc_id: str, record: dict, vendor: dict | None, line_id: str | None, available_at: str | None = None) -> str | None:
    """Write one verified record to its canonical table, stamped with when the document became available."""
    kind = record["document_type"]
    if kind == "PURCHASE_ORDER":
        return apply_purchase_order(ws, doc_id, record, vendor, available_at)
    if kind in ("CONTRACT", "AMENDMENT"):
        return apply_contract(ws, doc_id, record, vendor, available_at)
    if kind == "TERMINATION_NOTICE":
        rows = store.load_table(ws, "terminations")
        store.upsert(rows, {
            "source_doc": doc_id, "available_at": available_at, "vendor_id": vendor and vendor["vendor_id"], "contract_id": record["contract_id"],
            "po_number": record["po_number"], "po_line_id": line_id, "effective_date": record["termination_effective"],
        }, ("source_doc",))
        store.save_table(ws, "terminations", rows)
        return "terminations"
    if kind in ACTIVITY_KIND:
        rows = store.load_table(ws, "activity")
        store.upsert(rows, {
            "activity_id": doc_id, "po_line_id": line_id, "kind": ACTIVITY_KIND[kind],
            "service_period": record["service_period"], "coverage_start": record["coverage_start"],
            "coverage_end": record["coverage_end"], "quantity": record["quantity"],
            "value": None if record["amount"] is None else round(record["amount"], 2),
            "replaces": record["replaces"], "replaced_by": None, "source_doc": doc_id, "available_at": available_at,
        }, ("activity_id",))
        for r in rows:
            if record["replaces"] and r["activity_id"] == record["replaces"]:
                r["replaced_by"] = doc_id
        store.save_table(ws, "activity", rows)
        return "activity"
    if kind == "GOODS_RECEIPT":
        rows = store.load_table(ws, "goods_receipts")
        store.upsert(rows, {"gr_id": doc_id, "po_line_id": line_id, "received_date": record["received_date"],
                            "quantity": record["quantity"], "source_doc": doc_id, "available_at": available_at}, ("gr_id",))
        store.save_table(ws, "goods_receipts", rows)
        return "goods_receipts"
    if kind == "INVOICE":
        rows = store.load_table(ws, "invoices")
        old = next((r for r in rows if r["invoice_id"] == doc_id), {})
        store.upsert(rows, {
            "invoice_id": doc_id, "vendor_id": vendor and vendor["vendor_id"], "entity_id": None,
            "po_number": record["po_number"], "po_line_id": line_id, "invoice_number": record["invoice_number"] or doc_id,
            "service_period": record["service_period"], "amount": None if record["amount"] is None else round(record["amount"], 2),
            "quantity": record["quantity"], "unit_rate": record["unit_rate"], "currency": "USD",
            "status": "QUEUE", "received_date": record["invoice_date"], "posted_at": None,  # received by AP; only the ERP feed says POSTED
            "source_doc": doc_id, "available_at": available_at, **old,
        }, ("invoice_id",))
        store.save_table(ws, "invoices", rows)
        return "invoices"
    return None  # OTHER: the document is kept as evidence only


def missing_fields(record: dict) -> list[str]:
    need = {
        "CONTRACT": ("contract_id", "effective_start"), "AMENDMENT": ("contract_id", "effective_start"),
        "TERMINATION_NOTICE": ("termination_effective",), "GOODS_RECEIPT": ("quantity", "received_date"),
        "USAGE_REPORT": ("service_period", "quantity"), "DELIVERY_REPORT": ("service_period", "amount"),
        "TIMESHEET": ("service_period", "quantity"), "INVOICE": ("amount", "service_period"),
        "PURCHASE_ORDER": ("po_number",),
    }.get(record["document_type"], ())
    missing = [k for k in need if record[k] is None]
    if record["document_type"] in ("CONTRACT", "AMENDMENT") and record["monthly_rate"] is None and record["unit_rate"] is None:
        missing.append("rate")
    if record["document_type"] == "PURCHASE_ORDER" and not record["lines"]:
        missing.append("lines")
    return missing


def extract_new(ws, llm, period: str) -> list[dict]:
    """Read every new or changed document of the period, one model call each. No table is touched yet."""
    seen = {d["doc_id"]: d for d in store.load_table(ws, "documents")}
    vendor_names = [v["vendor_name"] for v in store.load_table(ws, "vendors")]
    pending = []
    for entry in sorted(store.world(ws, "documents/index"), key=lambda e: (e.get("available_at") or "", e["doc_id"])):
        if entry.get("period", period) != period:
            continue
        doc_id = entry["doc_id"]
        text = doc_text(ws.world_dir / "documents" / entry["file"])
        digest = hashlib.sha256(text.encode()).hexdigest()
        old = seen.get(doc_id)
        if old and old["hash"] == digest:
            continue
        record = clean(llm("extract", {"DOCUMENT": text, "DOC_ID": doc_id, "KNOWN_VENDORS": vendor_names,
                                       "DOCUMENT_TYPES": list(DOC_TYPES)}))
        # a month-folder document cannot be known before its month: keeps a re-run of an earlier month clean
        available_at = entry.get("available_at") or (f"{entry['period']}-01" if entry.get("period") else None)
        pending.append({"doc_id": doc_id, "entry": entry, "record": record, "hash": digest, "available_at": available_at})
    return pending


def apply_order_key(item: dict) -> tuple:
    kind = item["record"]["document_type"]
    rank = APPLY_ORDER.index(kind) if kind in APPLY_ORDER else len(APPLY_ORDER)
    return rank, item["available_at"] or "", item["doc_id"]


def run(ws, llm, period: str) -> list[dict]:
    """Process this period's documents only (new or changed, visible at ws.as_of). Returns the rows it (re)wrote.

    Everything the month's folder holds is read first, then applied in dependency order (purchase orders, then
    agreements, then the evidence of what happened, then invoices), so an invoice filed beside its purchase order
    still resolves its line. Earlier months are never re-read: what they established is already in the db."""
    pull_feeds(ws)
    documents = store.load_table(ws, "documents")
    done = []
    for item in sorted(extract_new(ws, llm, period), key=apply_order_key):
        doc_id, entry, record, available_at = item["doc_id"], item["entry"], item["record"], item["available_at"]
        vendor = resolve_vendor(ws, record["vendor_name"], doc_id, available_at)  # created on first sight
        line_id = resolve_line(ws, record, vendor)
        reasons = []
        if record["document_type"] in NEEDS_LINE and line_id is None:
            reasons.append("UNRESOLVED_PO_LINE")
        reasons += [f"MISSING_{k.upper()}" for k in missing_fields(record)]
        quality = "NEEDS_REVIEW" if reasons else "OK"
        applied_to = apply(ws, doc_id, record, vendor, line_id, available_at) if quality == "OK" else None
        if applied_to == "po_headers" and line_id is None:
            line_id = resolve_line(ws, record, vendor)  # the order's own lines exist now: link the document to one
        row = {
            "doc_id": doc_id, "file": entry["file"], "hash": item["hash"], "period": entry.get("period"), "available_at": available_at,
            "doc_type": record["document_type"], "vendor_id": vendor and vendor["vendor_id"], "po_line_id": line_id,
            "record": record, "quality": quality, "reasons": reasons, "applied_to": applied_to,
        }
        store.upsert(documents, row, ("doc_id",))
        done.append(row)
        events.log(ws, "evidence", f"{doc_id}: {record['document_type']} {quality}"
                   + (f" -> {applied_to}" if applied_to else "") + (f" [{'; '.join(reasons)}]" if reasons else ""), period)
    store.save_table(ws, "documents", documents)
    sync_received(ws, period)
    return done
