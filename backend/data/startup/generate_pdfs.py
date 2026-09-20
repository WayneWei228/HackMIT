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
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INPUT = Path(__file__).with_name("classification_input.json")
OUTPUT = Path(__file__).with_name("pdf")

NAVY = colors.HexColor("#13233F")
BLUE = colors.HexColor("#276EF1")
SLATE = colors.HexColor("#526176")
PALE = colors.HexColor("#F3F6FA")
LINE = colors.HexColor("#D8E0EA")
GREEN = colors.HexColor("#16794A")


styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="DocTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=NAVY,
        spaceAfter=8,
    )
)
styles.add(
    ParagraphStyle(
        name="DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=SLATE,
        spaceAfter=16,
    )
)
styles.add(
    ParagraphStyle(
        name="Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=NAVY,
        spaceBefore=9,
        spaceAfter=6,
    )
)
styles.add(
    ParagraphStyle(
        name="BodySmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#263548"),
    )
)
styles.add(
    ParagraphStyle(
        name="Label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=SLATE,
        spaceAfter=2,
    )
)
styles.add(
    ParagraphStyle(
        name="Value",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=NAVY,
    )
)
styles.add(
    ParagraphStyle(
        name="Amount",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        alignment=TA_RIGHT,
        textColor=NAVY,
    )
)
styles.add(
    ParagraphStyle(
        name="CenterSmall",
        parent=styles["BodySmall"],
        alignment=TA_CENTER,
    )
)
styles.add(
    ParagraphStyle(
        name="TableHeader",
        parent=styles["Label"],
        textColor=colors.white,
    )
)


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


def info_grid(
    items: list[tuple[str, str]], widths=(1.55 * inch, 2.2 * inch, 1.55 * inch, 2.2 * inch)
):
    cells = []
    for label, value in items:
        safe_label = escape(str(label).upper())
        safe_value = escape(str(value)).replace("\n", "<br/>")
        cells.append(
            Paragraph(
                f'<font name="Helvetica-Bold" size="8" color="#526176">{safe_label}</font>'
                f'<br/><font name="Helvetica" size="9" color="#13233F">{safe_value}</font>',
                styles["Value"],
            )
        )
    if len(cells) % 2:
        cells.append("")
    rows = [cells[i : i + 2] for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[sum(widths[:2]), sum(widths[2:])], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
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
        [
            "1. Services",
            f"{vendor} will provide the service described in this order form to Orbit Labs, Inc.",
        ],
        ["2. Commercial terms", fee_text],
        [
            "3. Service records",
            "Vendor usage or active-service records will support each billing period.",
        ],
        [
            "4. Invoice timing",
            "Invoices are issued after the applicable monthly service period and are due Net 30.",
        ],
        [
            "5. Changes",
            "Pricing or scope changes require a written amendment signed by both parties.",
        ],
    ]
    story = [
        info_grid(
            [
                ("Agreement ID", doc["document_id"]),
                ("Effective date", "January 1, 2026"),
                ("Customer", "Orbit Labs, Inc."),
                ("Vendor", vendor),
            ]
        ),
        Spacer(1, 12),
        p("COMMERCIAL SUMMARY", "Section"),
        p(fee_text),
        Spacer(1, 8),
        p("TERMS", "Section"),
        standard_table(terms, [1.45 * inch, 5.35 * inch]),
        Spacer(1, 20),
        standard_table(
            [
                ["Accepted for Orbit Labs, Inc.", f"Accepted for {vendor}"],
                [
                    "Jordan Lee, VP Finance\nSigned: December 15, 2025",
                    "Authorized Representative\nSigned: December 15, 2025",
                ],
            ],
            [3.4 * inch, 3.4 * inch],
        ),
    ]
    document(
        path, "SERVICE ORDER FORM", f"{doc['document_id']}  |  Orbit Labs, Inc. and {vendor}", story
    )


def make_invoice(vendor: str, doc: dict, path: Path):
    invoice_date = date.fromisoformat(doc["invoice_date"])
    due = invoice_date + timedelta(days=30)
    quantity = doc.get("quantity", 1)
    unit = doc.get("unit", "monthly service")
    rate = doc.get("unit_rate", doc["amount"])
    story = [
        info_grid(
            [
                ("Invoice number", doc["document_id"]),
                ("Invoice date", invoice_date.isoformat()),
                ("Service period", doc["service_period"]),
                ("Due date", due.isoformat()),
                ("Bill to", "Orbit Labs, Inc.\n85 Main Street\nCambridge, MA 02142"),
                ("Remit to", f"{vendor}\n{VENDOR_DETAILS[vendor]['address']}"),
            ]
        ),
        Spacer(1, 14),
        standard_table(
            [
                ["Description", "Quantity", "Unit", "Rate", "Amount"],
                [doc["description"], f"{quantity:,}", unit, money(rate), money(doc["amount"])],
            ],
            [2.75 * inch, 0.8 * inch, 1.2 * inch, 0.9 * inch, 1.15 * inch],
            right_cols=(1, 3, 4),
        ),
        Spacer(1, 14),
        Table(
            [
                [p("SUBTOTAL", "Label"), p(money(doc["amount"]), "Amount")],
                [p("TAX", "Label"), p("$0.00", "Amount")],
                [p("TOTAL DUE", "Label"), p(money(doc["amount"]), "Amount")],
            ],
            colWidths=[4.85 * inch, 1.95 * inch],
            style=TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LINEABOVE", (0, 2), (-1, 2), 1.2, NAVY),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        ),
        Spacer(1, 18),
        p(
            f"Questions: {VENDOR_DETAILS[vendor]['email']}. Please reference {doc['document_id']} with payment."
        ),
    ]
    document(path, "INVOICE", f"{vendor}  |  {doc['document_id']}", story)


def make_usage_report(vendor: str, doc: dict, path: Path):
    projected = doc["quantity"] * 0.02
    story = [
        info_grid(
            [
                ("Report ID", doc["document_id"]),
                ("Reporting period", doc["service_period"]),
                ("Customer", "Orbit Labs, Inc."),
                ("Status", "Final through December 31"),
            ]
        ),
        Spacer(1, 14),
        p("USAGE SUMMARY", "Section"),
        standard_table(
            [
                ["Service", "Measured quantity", "Contract rate", "Expected charge"],
                [
                    doc["description"],
                    f"{doc['quantity']:,} {doc['unit']}s",
                    "$0.02 per unit",
                    money(projected),
                ],
            ],
            [2.55 * inch, 1.55 * inch, 1.35 * inch, 1.35 * inch],
            right_cols=(1, 2, 3),
        ),
        Spacer(1, 15),
        p("CERTIFICATION", "Section"),
        p(
            "Usage reflects accepted API requests recorded from December 1 through December 31, 2026. The amount shown is an estimate under the contracted rate and is not an invoice."
        ),
        Spacer(1, 18),
        info_grid(
            [
                ("Prepared by", "Automated Usage Operations"),
                ("Generated at", "2027-01-01 02:00 UTC"),
            ]
        ),
    ]
    document(path, "MONTHLY USAGE REPORT", f"{vendor}  |  {doc['document_id']}", story)


def make_purchase_order(vendor: str, doc: dict, path: Path):
    per_unit = doc["fixed_order_total"] / doc["ordered_quantity"]
    story = [
        info_grid(
            [
                ("Purchase order", doc["document_id"]),
                ("Issue date", doc["issue_date"]),
                ("Vendor", vendor),
                ("Expected delivery", doc["expected_delivery_date"]),
                ("Ship to", "Orbit Labs, Inc.\n85 Main Street\nCambridge, MA 02142"),
                ("Buyer", "Morgan Chen, IT Procurement"),
            ]
        ),
        Spacer(1, 14),
        standard_table(
            [
                ["Description", "Quantity", "Unit price", "Order total"],
                [
                    doc["description"],
                    f"{doc['ordered_quantity']}",
                    money(per_unit),
                    money(doc["fixed_order_total"]),
                ],
            ],
            [3.55 * inch, 0.8 * inch, 1.15 * inch, 1.3 * inch],
            right_cols=(1, 2, 3),
        ),
        Spacer(1, 14),
        p("DELIVERY AND INVOICING", "Section"),
        p(
            "Orbit Labs records only units received and accepted. Vendor must reference this PO on the invoice. Partial shipments may be invoiced only for accepted units."
        ),
        Spacer(1, 18),
        info_grid(
            [
                ("Approved by", "Jordan Lee, VP Finance"),
                ("Approval date", "December 10, 2026"),
            ]
        ),
    ]
    document(path, "PURCHASE ORDER", f"Orbit Labs, Inc.  |  {doc['document_id']}", story)


def make_goods_receipt(vendor: str, doc: dict, path: Path):
    per_unit = 40000 / 25
    accepted_value = doc["received_quantity"] * per_unit
    story = [
        info_grid(
            [
                ("Receipt ID", doc["document_id"]),
                ("Receipt date", doc["receipt_date"]),
                ("Vendor", vendor),
                ("Purchase order", "PO-003"),
                ("Receiving location", "Orbit Labs - Cambridge HQ"),
                ("Inspection status", "20 units accepted"),
            ]
        ),
        Spacer(1, 14),
        standard_table(
            [
                ["Description", "Ordered", "Received", "Open", "Accepted value"],
                [
                    doc["description"],
                    f"{doc['ordered_quantity']}",
                    f"{doc['received_quantity']}",
                    f"{doc['ordered_quantity'] - doc['received_quantity']}",
                    money(accepted_value),
                ],
            ],
            [2.75 * inch, 0.85 * inch, 0.85 * inch, 0.75 * inch, 1.6 * inch],
            right_cols=(1, 2, 3, 4),
        ),
        Spacer(1, 14),
        p("RECEIVING NOTE", "Section"),
        p(
            "Twenty laptop packages were physically received, inspected, and accepted. Five packages remain open on the purchase order and were not received by December 31, 2026."
        ),
        Spacer(1, 18),
        info_grid(
            [
                ("Received by", "Taylor Brooks, IT Operations"),
                ("Recorded at", "2026-12-28 15:42 EST"),
            ]
        ),
    ]
    document(path, "GOODS RECEIPT", f"Orbit Labs, Inc.  |  {doc['document_id']}", story)


def make_campaign_order(vendor: str, doc: dict, path: Path):
    story = [
        info_grid(
            [
                ("Campaign order", doc["document_id"]),
                ("Vendor", vendor),
                ("Campaign start", doc["start_date"]),
                ("Campaign end", doc["end_date"]),
                ("Customer", "Orbit Labs, Inc."),
                ("Maximum budget", money(doc["maximum_budget"])),
            ]
        ),
        Spacer(1, 14),
        p("CAMPAIGN", "Section"),
        p(doc["description"]),
        Spacer(1, 8),
        p("PRICING", "Section"),
        p(doc["pricing_text"]),
        Spacer(1, 8),
        p(
            "The maximum budget is a spending limit and does not represent a guaranteed charge. Final billing will reflect delivered advertising shown in the campaign delivery report."
        ),
        Spacer(1, 18),
        info_grid(
            [
                ("Approved by", "Avery Patel, VP Marketing"),
                ("Approval date", "November 28, 2026"),
            ]
        ),
    ]
    document(
        path, "CAMPAIGN ORDER", f"Orbit Labs, Inc. and {vendor}  |  {doc['document_id']}", story
    )


def make_delivery_report(vendor: str, doc: dict, path: Path):
    story = [
        info_grid(
            [
                ("Report ID", doc["document_id"]),
                ("Campaign order", "CAMPAIGN-004"),
                ("Reporting period", doc["service_period"]),
                ("Status", "Final"),
            ]
        ),
        Spacer(1, 14),
        p("DELIVERY SUMMARY", "Section"),
        standard_table(
            [
                ["Campaign", "Budget", "Delivered advertising", "Unused budget"],
                [
                    doc["description"],
                    "$30,000.00",
                    money(doc["delivered_amount"]),
                    money(30000 - doc["delivered_amount"]),
                ],
            ],
            [2.9 * inch, 1.25 * inch, 1.4 * inch, 1.25 * inch],
            right_cols=(1, 2, 3),
        ),
        Spacer(1, 14),
        p("CERTIFICATION", "Section"),
        p(
            "Delivered advertising includes activity through December 31, 2026. The unused campaign budget was not delivered and is not billable."
        ),
        Spacer(1, 18),
        info_grid(
            [
                ("Prepared by", "Campaign Billing Operations"),
                ("Generated at", "2027-01-02 09:30 EST"),
            ]
        ),
    ]
    document(path, "CAMPAIGN DELIVERY REPORT", f"{vendor}  |  {doc['document_id']}", story)


def main() -> None:
    data = json.loads(INPUT.read_text())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generated = []
    for case in data["cases"]:
        vendor = case["vendor_name"]
        for source in case["documents"]:
            path = OUTPUT / safe_name(source["document_id"])
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
    if len(generated) != 14:
        raise RuntimeError(f"Expected 14 PDFs, generated {len(generated)}")
    print(f"generated={len(generated)} output={OUTPUT}")


if __name__ == "__main__":
    main()
