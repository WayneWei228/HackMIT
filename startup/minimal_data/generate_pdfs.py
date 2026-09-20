"""Generate synthetic finance PDFs from classification_input.json."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
INPUT = Path(__file__).with_name("classification_input.json")
OUTPUT = ROOT / "output" / "pdf" / "startup_minimal_data"

NAVY = colors.HexColor("#13233F")
BLUE = colors.HexColor("#276EF1")
SLATE = colors.HexColor("#526176")
PALE = colors.HexColor("#F3F6FA")
LINE = colors.HexColor("#D8E0EA")
GREEN = colors.HexColor("#16794A")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="DocTitle",
    parent=styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=21,
    leading=25,
    textColor=NAVY,
    spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="DocSubtitle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    leading=13,
    textColor=SLATE,
    spaceAfter=16,
))
styles.add(ParagraphStyle(
    name="Section",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=NAVY,
    spaceBefore=9,
    spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="BodySmall",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#263548"),
))
styles.add(ParagraphStyle(
    name="Label",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8,
    leading=11,
    textColor=SLATE,
    spaceAfter=2,
))
styles.add(ParagraphStyle(
    name="Value",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    leading=12,
    textColor=NAVY,
))
styles.add(ParagraphStyle(
    name="Amount",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=17,
    leading=20,
    alignment=TA_RIGHT,
    textColor=NAVY,
))
styles.add(ParagraphStyle(
    name="CenterSmall",
    parent=styles["BodySmall"],
    alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="TableHeader",
    parent=styles["Label"],
    textColor=colors.white,
))


VENDOR_DETAILS = {
    "Mintlify": {
        "address": "548 Market Street, San Francisco, CA 94104",
        "email": "billing@mintlify.example",
    },
    "OpenAI": {
        "address": "1455 Third Street, San Francisco, CA 94158",
        "email": "accounts@openai.example",
    },
    "ASUS": {
        "address": "48720 Kato Road, Fremont, CA 94538",
        "email": "commercial@asus.example",
    },
    "Meta": {
        "address": "1 Hacker Way, Menlo Park, CA 94025",
        "email": "ads-billing@meta.example",
    },
}


def money(value: float | int | None) -> str:
    return "" if value is None else f"${value:,.2f}"


def safe_name(document_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", document_id) + ".pdf"


def p(text: object, style: str = "BodySmall") -> Paragraph:
    return Paragraph(str(text), styles[style])


def footer(canvas, doc):
    canvas.saveState()
    width, _ = letter
    canvas.setStrokeColor(LINE)
    canvas.line(doc.leftMargin, 34, width - doc.rightMargin, 34)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE)
    canvas.drawString(doc.leftMargin, 22, "Synthetic demo document for TrueUp Close")
    canvas.drawRightString(width - doc.rightMargin, 22, f"Page {doc.page}")
    canvas.restoreState()


def document(path: Path, title: str, subtitle: str, story: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.52 * inch,
        bottomMargin=0.56 * inch,
        title=title,
        author="Orbit Labs, Inc.",
        subject="Synthetic finance fixture",
    )
    heading = [p(title, "DocTitle"), p(subtitle, "DocSubtitle")]
    doc.build(heading + story, onFirstPage=footer, onLaterPages=footer)


def info_grid(items: list[tuple[str, str]], widths=(1.55 * inch, 2.2 * inch, 1.55 * inch, 2.2 * inch)):
    cells = []
    for label, value in items:
        safe_label = escape(str(label).upper())
        safe_value = escape(str(value)).replace("\n", "<br/>")
        cells.append(Paragraph(
            f'<font name="Helvetica-Bold" size="8" color="#526176">{safe_label}</font>'
            f'<br/><font name="Helvetica" size="9" color="#13233F">{safe_value}</font>',
            styles["Value"],
        ))
    if len(cells) % 2:
        cells.append("")
    rows = [cells[i:i + 2] for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[sum(widths[:2]), sum(widths[2:])], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def standard_table(data, col_widths, right_cols=()):
    formatted = [[p(cell, "TableHeader") for cell in data[0]]]
    for row in data[1:]:
        formatted.append([p(cell) for cell in row])
    table = Table(formatted, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    rules = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    for col in right_cols:
        rules.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
    table.setStyle(TableStyle(rules))
    return table


def make_contract(vendor: str, doc: dict, path: Path):
    fee_text = doc["text"]
    terms = [
        ["Section", "Details"],
        ["1. Services", f"{vendor} will provide the service described in this order form to Orbit Labs, Inc."],
        ["2. Commercial terms", fee_text],
        ["3. Service records", "Vendor usage or active-service records will support each billing period."],
        ["4. Invoice timing", "Invoices are issued after the applicable monthly service period and are due Net 30."],
        ["5. Changes", "Pricing or scope changes require a written amendment signed by both parties."],
    ]
    story = [
        info_grid([
            ("Agreement ID", doc["document_id"]),
            ("Effective date", "January 1, 2026"),
            ("Customer", "Orbit Labs, Inc."),
            ("Vendor", vendor),
        ]),
        Spacer(1, 12),
        p("COMMERCIAL SUMMARY", "Section"),
        p(fee_text),
        Spacer(1, 8),
        p("TERMS", "Section"),
        standard_table(terms, [1.45 * inch, 5.35 * inch]),
        Spacer(1, 20),
        standard_table([
            ["Accepted for Orbit Labs, Inc.", f"Accepted for {vendor}"],
            ["Jordan Lee, VP Finance\nSigned: December 15, 2025", "Authorized Representative\nSigned: December 15, 2025"],
        ], [3.4 * inch, 3.4 * inch]),
    ]
    document(path, "SERVICE ORDER FORM", f"{doc['document_id']}  |  Orbit Labs, Inc. and {vendor}", story)


def make_invoice(vendor: str, doc: dict, path: Path):
    invoice_date = date.fromisoformat(doc["invoice_date"])
    due = invoice_date + timedelta(days=30)
    quantity = doc.get("quantity", 1)
    unit = doc.get("unit", "monthly service")
    rate = doc.get("unit_rate", doc["amount"])
    story = [
        info_grid([
            ("Invoice number", doc["document_id"]),
            ("Invoice date", invoice_date.isoformat()),
            ("Service period", doc["service_period"]),
            ("Due date", due.isoformat()),
            ("Bill to", "Orbit Labs, Inc.\n85 Main Street\nCambridge, MA 02142"),
            ("Remit to", f"{vendor}\n{VENDOR_DETAILS[vendor]['address']}"),
        ]),
        Spacer(1, 14),
        standard_table([
            ["Description", "Quantity", "Unit", "Rate", "Amount"],
            [doc["description"], f"{quantity:,}", unit, money(rate), money(doc["amount"])],
        ], [2.75 * inch, 0.8 * inch, 1.2 * inch, 0.9 * inch, 1.15 * inch], right_cols=(1, 3, 4)),
        Spacer(1, 14),
        Table([
            [p("SUBTOTAL", "Label"), p(money(doc["amount"]), "Amount")],
            [p("TAX", "Label"), p("$0.00", "Amount")],
            [p("TOTAL DUE", "Label"), p(money(doc["amount"]), "Amount")],
        ], colWidths=[4.85 * inch, 1.95 * inch], style=TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEABOVE", (0, 2), (-1, 2), 1.2, NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])),
        Spacer(1, 18),
        p(f"Questions: {VENDOR_DETAILS[vendor]['email']}. Please reference {doc['document_id']} with payment."),
    ]
    document(path, "INVOICE", f"{vendor}  |  {doc['document_id']}", story)


def human_date(value: str) -> str:
    return date.fromisoformat(value).strftime("%B %d, %Y")


def make_usage_report(vendor: str, doc: dict, path: Path):
    unit_rate = doc.get("unit_rate", 0.02)
    amount = doc.get("amount", doc["quantity"] * unit_rate)
    status = doc.get("status", "FINAL")
    is_partial = status == "PARTIAL"
    coverage_start = doc.get("coverage_start")
    coverage_end = doc.get("coverage_end")
    coverage_label = (
        f"{human_date(coverage_start)} to {human_date(coverage_end)}"
        if coverage_start and coverage_end
        else doc["service_period"]
    )
    generated_on = doc.get("generated_on")
    replaces = doc.get("replaces")

    if is_partial:
        status_label = f"PARTIAL - covers {coverage_label} only"
        certification = (
            f"This report is NOT AN INVOICE. It reflects usage recorded from {human_date(coverage_start)} "
            f"through {human_date(coverage_end)} only. Usage after {human_date(coverage_end)} is not "
            "included and will be reported in the final usage report for this period."
        )
    else:
        status_label = f"FINAL for {coverage_label}"
        certification = (
            f"This is the FINAL usage report for {coverage_label}. It reflects all accepted API requests "
            f"recorded during this period. The amount shown is calculated under the contracted rate and "
            "is not an invoice."
        )
        if replaces:
            certification += f" This report replaces report {replaces}, which covered a partial period."

    story = [
        info_grid([
            ("Report ID", doc["document_id"]),
            ("Reporting period", coverage_label),
            ("Customer", "Orbit Labs, Inc."),
            ("Status", status_label),
        ]),
        Spacer(1, 14),
        p("USAGE SUMMARY", "Section"),
        standard_table([
            ["Service", "Measured quantity", "Contract rate", "Expected charge"],
            [doc["description"], f"{doc['quantity']:,} {doc['unit']}s", money(unit_rate) + " per unit", money(amount)],
        ], [2.55 * inch, 1.55 * inch, 1.35 * inch, 1.35 * inch], right_cols=(1, 2, 3)),
        Spacer(1, 15),
        p("CERTIFICATION", "Section"),
        p(certification),
        Spacer(1, 18),
        info_grid([
            ("Prepared by", "Automated Usage Operations"),
            ("Generated at", human_date(generated_on) if generated_on else "2027-01-01"),
        ]),
    ]
    document(path, "MONTHLY USAGE REPORT", f"{vendor}  |  {doc['document_id']}", story)


ORDER_TYPE_LABEL = {"FO": "FO - framework order", "NB": "NB - standard order"}
ITEM_CATEGORY_LABEL = {"P": "P - service", "B": "B - limit", "E": "E - limit", "": "standard"}


def order_header_fields(doc: dict, vendor: str, id_label: str) -> list[tuple[str, str]]:
    """The labelled fields procurement puts on the order itself. Empty values are dropped."""
    fields = [
        (id_label, doc["document_id"]),
        ("Vendor", vendor),
        ("Order type", ORDER_TYPE_LABEL.get(doc.get("order_type", ""), doc.get("order_type") or "")),
        ("Issue date", doc.get("issue_date", "")),
        ("Validity start", doc.get("validity_start", "")),
        ("Validity end", doc.get("validity_end", "")),
        ("Requester", doc.get("requester", "")),
        ("Cost center owner", doc.get("cost_center_owner", "")),
        ("Linked contract", doc.get("contract_id", "")),
        ("Expected delivery", doc.get("expected_delivery_date", "")),
        ("Customer", "Orbit Labs, Inc.\n85 Main Street\nCambridge, MA 02142"),
        ("Buyer", doc.get("buyer", "Morgan Chen, Procurement")),
    ]
    return [(label, value) for label, value in fields if value]


def order_line_table(doc: dict):
    rows = [["Line", "Item category", "Description", "Qty ordered", "Unit price", "Overall limit", "GR required"]]
    for line in doc["lines"]:
        rows.append([
            line["po_line_id"],
            ITEM_CATEGORY_LABEL.get(line.get("item_category", ""), line.get("item_category") or "standard"),
            line["description"],
            "" if line.get("quantity_ordered") is None else f"{line['quantity_ordered']:,}",
            money(line.get("unit_price")),
            money(line.get("overall_limit")),
            "yes" if line.get("gr_required") else "no",
        ])
    return standard_table(
        rows,
        [1.45 * inch, 0.90 * inch, 1.55 * inch, 0.62 * inch, 0.78 * inch, 0.83 * inch, 0.75 * inch],
        right_cols=(3, 4, 5),
    )


def make_order(vendor: str, doc: dict, path: Path, *, title: str, id_label: str, extra: list | None = None):
    """One renderer for every buyer-issued order: it prints exactly the fields the close needs."""
    notes = []
    for line in doc["lines"]:
        if line.get("unit_basis"):
            notes.append(f"{line['po_line_id']}: unit price {money(line['unit_price'])} {line['unit_basis']}.")
        if line.get("overall_limit") is not None:
            notes.append(f"{line['po_line_id']}: overall limit {money(line['overall_limit'])} is a spending cap for the line, "
                         "not a guaranteed charge.")
    story = [
        info_grid(order_header_fields(doc, vendor, id_label)),
        Spacer(1, 14),
        p("ORDER LINES", "Section"),
        order_line_table(doc),
        Spacer(1, 10),
    ]
    for note in notes:
        story.append(p(note))
    story += (extra or [])
    story += [
        Spacer(1, 12),
        p("DELIVERY AND INVOICING", "Section"),
        p("Orbit Labs records only what is received, used or delivered. Vendor must reference this order and the line on "
          "every invoice. A line marked GR required is recognised on goods receipt only."),
        Spacer(1, 18),
        info_grid([
            ("Approved by", doc.get("approved_by", "Jordan Lee, VP Finance")),
            ("Approval date", doc.get("approval_date", "")),
        ]),
    ]
    document(path, title, f"Orbit Labs, Inc.  |  {doc['document_id']}", story)


def make_purchase_order(vendor: str, doc: dict, path: Path):
    make_order(vendor, doc, path, title="PURCHASE ORDER", id_label="Purchase order")


def make_goods_receipt(vendor: str, doc: dict, path: Path):
    per_unit = 40000 / 25
    accepted_value = doc["received_quantity"] * per_unit
    story = [
        info_grid([
            ("Receipt ID", doc["document_id"]),
            ("Receipt date", doc["receipt_date"]),
            ("Vendor", vendor),
            ("Purchase order", "PO-003"),
            ("Receiving location", "Orbit Labs - Cambridge HQ"),
            ("Inspection status", "20 units accepted"),
        ]),
        Spacer(1, 14),
        standard_table([
            ["Description", "Ordered", "Received", "Open", "Accepted value"],
            [doc["description"], f"{doc['ordered_quantity']}", f"{doc['received_quantity']}", f"{doc['ordered_quantity'] - doc['received_quantity']}", money(accepted_value)],
        ], [2.75 * inch, 0.85 * inch, 0.85 * inch, 0.75 * inch, 1.6 * inch], right_cols=(1, 2, 3, 4)),
        Spacer(1, 14),
        p("RECEIVING NOTE", "Section"),
        p("Twenty laptop packages were physically received, inspected, and accepted. Five packages remain open on the purchase order and were not received by December 31, 2026."),
        Spacer(1, 18),
        info_grid([
            ("Received by", "Taylor Brooks, IT Operations"),
            ("Recorded at", "2026-12-28 15:42 EST"),
        ]),
    ]
    document(path, "GOODS RECEIPT", f"Orbit Labs, Inc.  |  {doc['document_id']}", story)


def make_campaign_order(vendor: str, doc: dict, path: Path):
    """A campaign order is a purchase order with a campaign window: same fields, same line table."""
    extra = [
        Spacer(1, 8),
        p("PRICING", "Section"),
        p(doc["pricing_text"]),
        p("The overall limit is a spending limit and does not represent a guaranteed charge. Final billing will reflect "
          "delivered advertising shown in the campaign delivery report."),
    ]
    make_order(vendor, doc, path, title="CAMPAIGN ORDER", id_label="Campaign order", extra=extra)


def make_delivery_report(vendor: str, doc: dict, path: Path):
    story = [
        info_grid([
            ("Report ID", doc["document_id"]),
            ("Campaign order", "CAMPAIGN-004"),
            ("Reporting period", doc["service_period"]),
            ("Status", "Final"),
        ]),
        Spacer(1, 14),
        p("DELIVERY SUMMARY", "Section"),
        standard_table([
            ["Campaign", "Budget", "Delivered advertising", "Unused budget"],
            [doc["description"], "$30,000.00", money(doc["delivered_amount"]), money(30000 - doc["delivered_amount"])],
        ], [2.9 * inch, 1.25 * inch, 1.4 * inch, 1.25 * inch], right_cols=(1, 2, 3)),
        Spacer(1, 14),
        p("CERTIFICATION", "Section"),
        p("Delivered advertising includes activity through December 31, 2026. The unused campaign budget was not delivered and is not billable."),
        Spacer(1, 18),
        info_grid([
            ("Prepared by", "Campaign Billing Operations"),
            ("Generated at", "2027-01-02 09:30 EST"),
        ]),
    ]
    document(path, "CAMPAIGN DELIVERY REPORT", f"{vendor}  |  {doc['document_id']}", story)


def month_of(case: dict, source: dict) -> str:
    """The folder a document belongs to. An explicit "folder" field (e.g. "2026-12/afterclose")
    overrides the default month-of-service_period placement, for documents that arrive after
    close or replies to an after-close question. Contracts go in the first month the case is
    billed."""
    if source.get("folder"):
        return source["folder"]
    if source["document_type"] == "CONTRACT":
        return min(d["service_period"] for d in case["documents"] if d.get("service_period"))
    if source.get("service_period"):
        return source["service_period"]
    return re.search(r"\d{4}-\d{2}", json.dumps(source)).group(0)


def main() -> None:
    data = json.loads(INPUT.read_text())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generated = []
    for case in data["cases"]:
        vendor = case["vendor_name"]
        for source in case["documents"]:
            path = OUTPUT / month_of(case, source) / safe_name(source["document_id"])
            kind = source["document_type"]
            if kind == "CONTRACT":
                make_contract(vendor, source, path)
            elif kind == "INVOICE":
                make_invoice(vendor, source, path)
            elif kind == "USAGE_REPORT":
                make_usage_report(vendor, source, path)
            elif kind == "PURCHASE_ORDER":
                make_purchase_order(vendor, source, path)
            elif kind == "GOODS_RECEIPT":
                make_goods_receipt(vendor, source, path)
            elif kind == "CAMPAIGN_ORDER":
                make_campaign_order(vendor, source, path)
            elif kind == "DELIVERY_REPORT":
                make_delivery_report(vendor, source, path)
            else:
                raise ValueError(f"Unsupported document type: {kind}")
            generated.append(path)
    if len(generated) != 17:
        raise RuntimeError(f"Expected 17 PDFs, generated {len(generated)}")
    print(f"generated={len(generated)} output={OUTPUT}")


if __name__ == "__main__":
    main()
