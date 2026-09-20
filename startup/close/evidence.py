"""Evidence worker: canonicalise raw evidence into db tables.

The LLM turns document text into a record, Jev verifies the record against the text,
and code alone decides what gets applied to the canonical tables.
"""
import hashlib
import subprocess
from datetime import date, timedelta
from pathlib import Path

from typesafe_sdk import Choice, Noul

from . import events, policy, safe_math, store
from .jev import JevUnavailable
from .workspace import period_bounds

# System feeds copied as-is (already structured). The MERGED tables also receive rows from documents;
# on the same key the feed row wins, because the ERP knows the posting status and the PDF does not.
COPIED = ("vendors", "po_headers", "po_lines", "card_transactions", "gl", "prior_accruals", "org_directory")
MERGED = {"activity": "activity_id", "goods_receipts": "gr_id", "invoices": "invoice_id"}

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
)
NUMERIC = ("amount", "quantity", "unit_rate", "monthly_rate")
ACTIVITY_KIND = {"USAGE_REPORT": "USAGE", "DELIVERY_REPORT": "DELIVERY", "TIMESHEET": "TIMESHEET"}
NEEDS_LINE = set(ACTIVITY_KIND) | {"GOODS_RECEIPT"}  # an invoice without a line is kept: Invoice Lookup matches it
MAX_TEXT = 60_000
FIELD_MEANINGS = {
    "amount": "money actually billed, used or delivered for the period; never a budget, cap, limit or unused remainder",
    "quantity": "units used, hours worked or items received",
    "unit_rate": "price per unit or hour in force from effective_start",
    "monthly_rate": "fixed monthly fee in force from effective_start; for an amendment, the new fee",
}


def doc_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True)
        return out.stdout
    return path.read_text()


def pull_feeds(ws) -> None:
    """Copy the structured system feeds visible at ws.as_of into the db. Later workers read only the db."""
    if store.company(ws):  # optional: entity id, materiality, de minimis threshold
        store.save_table(ws, "company", [store.company(ws)])
    for name in COPIED:
        if (ws.world_dir / f"{name}.json").exists():  # no feed, no table
            store.save_table(ws, name, store.world(ws, name))
    for name, key in MERGED.items():
        rows = store.load_table(ws, name)
        for row in store.world(ws, name):
            old = next((r for r in rows if r.get(key) == row[key]), {})
            store.upsert(rows, {**old, **row}, (key,))
        if rows:
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
            line["quantity_received"] = max(line.get("quantity_received") or 0, received[line["po_line_id"]])
    store.save_table(ws, "po_lines", lines)


def clean(raw: dict) -> dict:
    """Keep only the known keys; numbers become floats or None."""
    record = {k: raw.get(k) for k in RECORD_KEYS}
    for k in NUMERIC:
        v = record[k]
        if isinstance(v, str):
            try:
                v = safe_math.evaluate(v)
            except ValueError:
                v = None
        record[k] = round(float(v), 6) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    if record["document_type"] not in DOC_TYPES:
        record["document_type"] = "OTHER"
    return record


def questions() -> dict:
    return {
        "doc_type": Choice(
            instructions="What kind of business document is `document_text`?",
            criteria=DOC_TYPES,
        ),
        "vendor_consistent": Noul(
            instructions="Is `extracted.vendor_name` the vendor (seller or service provider) that `document_text` is from or about? "
            "Different spellings or legal suffixes of the same company count as the same vendor."
        ),
        "amounts_supported": Noul(
            instructions="Is every non-null number in `extracted` among amount, quantity, unit_rate and monthly_rate "
            "stated in `document_text` with the meaning given in `field_meanings`? Answer no if any of them is absent "
            "from the text, is a different figure, or is really another kind of figure such as a budget, cap, "
            "limit, earlier rate or unused remainder."
        ),
        "dates_supported": Noul(
            instructions="Is every non-null date or period in `extracted` (service_period, effective_start, effective_end, "
            "coverage_start, coverage_end, received_date, termination_effective) supported by `document_text`?"
        ),
        "recurring_obligation": Noul(
            instructions="Does `document_text` establish a payment obligation that repeats every month?"
        ),
        "changes_prior_terms": Noul(
            instructions="Does `document_text` change, replace or end the terms of an earlier agreement between the same parties?"
        ),
    }


def verify(ws, jev, doc_id: str, text: str, record: dict) -> tuple[dict, list[str]]:
    """One Jev call per document. Returns (answers, reasons the record cannot be trusted)."""
    state = {"document_text": text[:MAX_TEXT], "extracted": record, "field_meanings": FIELD_MEANINGS}
    try:
        answers = jev.ask(state, questions(), tag=f"evidence:{doc_id}")
    except JevUnavailable as exc:
        return {}, [f"JEV_UNAVAILABLE: {exc}"]
    reasons = []
    kind = answers["doc_type"]
    if kind["choice"] != record["document_type"]:
        reasons.append(f"TYPE_MISMATCH: extractor {record['document_type']}, Jev {kind['choice']} ({kind['confidence']:.2f})")
    elif policy.gate(kind["confidence"]) == "REVIEW":
        reasons.append(f"TYPE_UNCERTAIN: {kind['choice']} ({kind['confidence']:.2f})")
    for qid, label in (("vendor_consistent", "VENDOR"), ("amounts_supported", "AMOUNTS"), ("dates_supported", "DATES")):
        if answers[qid]["noul"] < policy.NOUL_YES:
            reasons.append(f"{label}_NOT_SUPPORTED ({answers[qid]['noul']:.2f})")
    changes = answers["changes_prior_terms"]["noul"]
    if record["document_type"] == "CONTRACT" and changes >= policy.NOUL_YES:
        reasons.append(f"CONTRACT_READS_AS_AMENDMENT ({changes:.2f})")
    return answers, reasons


def resolve_vendor(ws, name: str | None) -> dict | None:
    if not name:
        return None
    want = name.strip().lower()
    for v in store.load_table(ws, "vendors"):
        names = [v["vendor_name"], *v.get("aliases", [])]
        if any(want == n.lower() or want.startswith(n.lower()) or n.lower().startswith(want) for n in names):
            return v
    return None


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


def apply(ws, doc_id: str, record: dict, vendor: dict | None, line_id: str | None, available_at: str | None = None) -> str | None:
    """Write one verified record to its canonical table, stamped with when the document became available."""
    kind = record["document_type"]
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
    return None  # purchase orders arrive through the PO feed; the document is kept as evidence only


def missing_fields(record: dict) -> list[str]:
    need = {
        "CONTRACT": ("contract_id", "effective_start"), "AMENDMENT": ("contract_id", "effective_start"),
        "TERMINATION_NOTICE": ("termination_effective",), "GOODS_RECEIPT": ("quantity", "received_date"),
        "USAGE_REPORT": ("service_period", "quantity"), "DELIVERY_REPORT": ("service_period", "amount"),
        "TIMESHEET": ("service_period", "quantity"), "INVOICE": ("amount", "service_period"),
    }.get(record["document_type"], ())
    missing = [k for k in need if record[k] is None]
    if record["document_type"] in ("CONTRACT", "AMENDMENT") and record["monthly_rate"] is None and record["unit_rate"] is None:
        missing.append("rate")
    return missing


def run(ws, llm, jev, period: str) -> list[dict]:
    """Process this period's documents only (new or changed, visible at ws.as_of). Returns the rows it (re)wrote.

    Earlier months are never re-read: what they established is already in the db."""
    pull_feeds(ws)
    documents = store.load_table(ws, "documents")
    seen = {d["doc_id"]: d for d in documents}
    vendor_names = [v["vendor_name"] for v in store.load_table(ws, "vendors")]
    done = []
    for entry in sorted(store.world(ws, "documents/index"), key=lambda e: (e.get("available_at") or "", e["doc_id"])):
        if entry.get("period", period) != period:
            continue
        doc_id = entry["doc_id"]
        # a month-folder document cannot be known before its month: keeps a re-run of an earlier month clean
        available_at = entry.get("available_at") or (f"{entry['period']}-01" if entry.get("period") else None)
        text = doc_text(ws.world_dir / "documents" / entry["file"])
        digest = hashlib.sha256(text.encode()).hexdigest()
        old = seen.get(doc_id)
        if old and old["hash"] == digest and not any(r.startswith("JEV_UNAVAILABLE") for r in old["reasons"]):
            continue
        record = clean(llm("extract", {"DOCUMENT": text, "DOC_ID": doc_id, "KNOWN_VENDORS": vendor_names,
                                       "DOCUMENT_TYPES": list(DOC_TYPES)}))
        answers, reasons = verify(ws, jev, doc_id, text, record)
        vendor = resolve_vendor(ws, record["vendor_name"])
        line_id = resolve_line(ws, record, vendor)
        if record["document_type"] != "OTHER" and vendor is None:
            reasons.append("UNKNOWN_VENDOR")
        if record["document_type"] in NEEDS_LINE and line_id is None:
            reasons.append("UNRESOLVED_PO_LINE")
        reasons += [f"MISSING_{k.upper()}" for k in missing_fields(record)]
        quality = "NEEDS_REVIEW" if reasons else "OK"
        applied_to = apply(ws, doc_id, record, vendor, line_id, available_at) if quality == "OK" else None
        row = {
            "doc_id": doc_id, "file": entry["file"], "hash": digest, "period": entry.get("period"), "available_at": available_at,
            "doc_type": record["document_type"], "vendor_id": vendor and vendor["vendor_id"], "po_line_id": line_id,
            "record": record, "checks": answers, "quality": quality, "reasons": reasons, "applied_to": applied_to,
        }
        store.upsert(documents, row, ("doc_id",))
        done.append(row)
        events.log(ws, "evidence", f"{doc_id}: {record['document_type']} {quality}"
                   + (f" -> {applied_to}" if applied_to else "") + (f" [{'; '.join(reasons)}]" if reasons else ""), period)
    store.save_table(ws, "documents", documents)
    sync_received(ws, period)
    return done
