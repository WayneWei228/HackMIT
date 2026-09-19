"""Contract text, the close policy manual, and PDF rendering for contracts and invoices."""
from xml.sax.saxutils import escape

from . import world as w

# vendor -> (effective date, term, fee clause, extra clauses)
TERMS = {
    "V001": ("December 1, 2025", "24 months",
             "Customer shall pay a Platform Fee of $50,000.00 per month, invoiced monthly in arrears.",
             ["4.3 Annual Adjustment. On each anniversary of the Effective Date, all recurring Fees shall increase by five percent (5%) over the Fees in effect immediately prior. No further notice is required.",
              "4.4 The Order Form reflects Fees as of the Effective Date only."]),
    "V002": ("January 1, 2026", "36 months",
             "Customer commits to a Monthly Commitment of $36,000.00, which includes 300,000 compute hours (an effective rate of $0.12 per hour). The Monthly Commitment is payable regardless of usage.",
             ["4.3 Overage. Compute hours above 300,000 in a calendar month are billed at $0.15 per hour.",
              "4.4 Invoices issue by the 5th business day following month end, based on metered usage."]),
    "V003": ("March 1, 2026", "12 months, auto-renewing",
             "Customer shall pay $85.00 per agent seat per month for 120 seats, invoiced monthly in arrears.",
             ["4.3 Added Seats. Seats added mid-month by Change Order are billed at the same per-seat rate, prorated by calendar days from the effective date of the Change Order.",
              "4.4 Seat reductions take effect only at renewal."]),
    "V004": ("January 1, 2025", "36 months",
             "Customer shall pay a Subscription Fee of $18,000.00 per month, invoiced monthly in arrears.",
             ["Order Form footnote (1): Subscription Fee is subject to an uplift of four percent (4%) effective each January 1 following the first contract year."]),
    "V005": ("March 1, 2025", "12 months, auto-renewing",
             "Customer shall pay a Subscription Fee of $6,400.00 per month, invoiced monthly in arrears.",
             ["4.3 Renewal Pricing. Provider may increase Fees effective each January 1 by a percentage notified in writing to Customer's billing contact no later than sixty (60) days prior, not to exceed seven percent (7%). Absent notice, Fees are unchanged."]),
    "V006": ("October 1, 2026", "through February 28, 2027",
             "Services are provided on a time-and-materials basis at $185.00 per hour against Purchase Order PO-1042, not to exceed $120,000.00 without written amendment.",
             ["4.3 Consultant timesheets are submitted weekly and are billable only once approved by Customer's Program Manager or Head of PMO.",
              "4.4 Invoices issue by the 10th of the month following the services."]),
    "V007": ("February 10, 2024", "until terminated (engagement letter)",
             "Fees are based on hourly rates of the attorneys involved, which range from $420 to $1,150 per hour, and are billed periodically. No estimate, cap or retainer applies.",
             ["3. Invoices may reflect partner-level write-downs at the firm's discretion."]),
    "V008": ("January 1, 2024", "60 months",
             "Base Rent of $22,500.00 per month is due on the first day of each month and is invoiced in advance.",
             ["4.3 Base Rent is fixed for the Term."]),
    "V009": ("June 1, 2025", "24 months",
             "Customer shall pay $4,150.00 per month for the Payroll Platform, invoiced monthly.",
             ["4.3 Additional modules require a signed Order Form addendum."]),
    "V010": ("August 1, 2026", "12 months",
             "Customer shall pay an Annual Subscription Fee of $96,000.00, invoiced in full in advance on the Effective Date for the term August 1, 2026 through July 31, 2027.",
             ["4.3 Fees are non-refundable."]),
    "V011": ("April 15, 2025", "until terminated",
             "For each candidate hired, Customer shall pay a Placement Fee equal to twenty percent (20%) of the candidate's first-year base salary. The fee is earned on the candidate's start date and invoiced within 30 days.",
             ["4.3 No fee is due for any month without a placement start."]),
    "V012": ("n/a", "per Purchase Order",
             "Work is quoted per job and performed only against a Customer Purchase Order. The invoice amount equals the PO amount unless a revised quote is approved.",
             []),
    "V013": ("February 1, 2026", "24 months",
             "Customer commits to $8,000.00 per month, which includes 400,000 GB of egress (an effective rate of $0.02 per GB).",
             ["4.3 Overage. Egress above 400,000 GB in a calendar month is billed at $0.03 per GB.",
              "4.4 Invoices issue after month end based on metered usage."]),
    "V014": ("February 1, 2025", "36 months",
             "Customer shall pay $4,500.00 per month for janitorial and maintenance services.",
             ["4.3 Fees are invoiced quarterly in arrears, in February, May, August and November, each invoice covering the preceding three calendar months."]),
    "V015": ("December 15, 2026", "12 months",
             "Customer shall pay $9,300.00 per month, invoiced monthly in advance on the 15th for the service month running from the 15th to the 14th.",
             ["4.3 The first service month begins December 15, 2026."]),
    "V016": ("July 1, 2023", "month to month",
             "Charges comprise fixed line rental plus metered voice and data usage, and vary monthly. Invoices issue on the last day of each month.",
             []),
    "V017": ("September 1, 2025", "24 months",
             "Licence Fee of $6,900.00 per month (billed in USD), invoiced monthly in arrears to Northstar Analytics UK Ltd.",
             ["4.3 The Licensee is Northstar Analytics UK Ltd. Invoices addressed to any other entity are invalid."]),
}


def contract_text(v):
    eff, term, fee, extras = TERMS[v["vendor_id"]]
    entity = next(e["name"] for e in w.COMPANY["entities"] if e["entity_id"] == v["legal_entity_id"])
    body = [
        f"{'ENGAGEMENT LETTER' if v['vendor_id'] == 'V007' else 'MASTER SERVICES AGREEMENT'}",
        f"Contract ID: {v['contract_id']}",
        f"Between {v['name']} (\"Provider\") and {entity} (\"Customer\").",
        f"Effective Date: {eff}. Term: {term}.",
        "",
        "1. Services. Provider will supply the services described in the Order Form to Customer's "
        f"{next(c['name'] for c in w.COMPANY['cost_centers'] if c['id'] == v['cost_center'])} team.",
        "2. Acceptance. Services are deemed received when made available to or performed for Customer.",
        "3. Confidentiality. Each party will protect the other's confidential information.",
        "4. Fees.",
        f"4.1 {fee}",
        f"4.2 Payment terms: {v['payment_terms']}. Invoices are sent to ap@northstar.example.",
        *extras,
        "5. Taxes. Fees exclude applicable taxes.",
        "6. Termination. Either party may terminate for material breach on 30 days' notice.",
        "7. Governing law. State of Delaware." if v["legal_entity_id"] == "NS-US" else "7. Governing law. England and Wales.",
        "",
        f"Provider billing contact: {v['billing_contact']} <{v['billing_email']}>",
        f"Customer business owner: {next(e[1] for e in w.EMPLOYEES if e[0] == v['operational_owner'])}",
        f"Purchase Order: {v['po_id'] or 'none'}",
    ]
    return "\n".join(body)


POLICY_MANUAL = """# Northstar Analytics - Vendor Accrual and Close Policy (v1.0)

Owner: Controller (Dana Whitfield). Applies to all vendor spend for NS-US and NS-UK.

## 1. When to accrue
1.1 Accrue an expense when a service was received in the period and no valid invoice was received by the close cutoff (5th calendar day after month end).
1.2 Do not accrue when the service was not received, or when the cost was already invoiced in advance and sits in Prepaid Expenses (1300).
1.3 An invoice received by the cutoff for the period's service is booked at its actual amount, not estimated.
1.4 An invoice covering more than one period is allocated by calendar days of the stated service period.

## 2. Allowed estimation methods
| Method | Required evidence |
|---|---|
| FIXED_CONTRACT_FEE | Active contract with a stated fee; service period |
| USAGE_X_RATE | Usage, seat, hours or hire record for the period; valid contract rate |
| PRORATED_FEE | Contract fee; service start and end dates |
| PO_BASED | Approved PO; goods or service receipt |
| HISTORICAL_RUN_RATE | At least 3 prior invoices. Only when the estimate is under $10,000 and the last 3 invoices vary by under 10% |
No other method may be used. An owner's verbal estimate is not a method; it is evidence for a Controller decision.

## 3. Evidence of service received
At least one of: usage or seat record, approved timesheet, HR start record, goods receipt, or written confirmation from the operational owner. An unanswered request is not evidence.

## 4. Approval thresholds (per obligation)
| Amount | Requirement |
|---|---|
| Under $10,000, confidence at least 0.85 | May be prepared without individual review; batch review |
| $10,000 to $24,999.99 | Reviewer (Accounting Manager) approval |
| $25,000 and over | Controller approval |
Any amount with low confidence, conflicting evidence, or no allowed method: escalate; do not post.

## 5. Posting controls
5.1 Entries must balance and may only post to an OPEN period.
5.2 One active accrual per vendor obligation per period. Duplicate invoices (same vendor, PO, amount and service period) are held, not posted.
5.3 Vendor, entity, cost center, account, period and obligation ID are mandatory. The entity on the invoice must match the contracting entity.
5.4 Accruals auto-reverse on the first day of the next period. Costs still unbilled at the next close are re-accrued.

## 6. True-ups
A difference between accrual and invoice above the greater of $500 or 2% requires a documented root cause. An unaccrued prior-period invoice of $25,000 or more goes to the Controller.

## 7. Outreach
Ask the person or system most likely to know: operational owner (was it received), requester or PO owner (did scope or rate change), AP (is it already in the queue), vendor billing contact (where is the invoice, what is the price), Controller (which treatment). Allow 48 hours, then try the next-best source or escalate before the cutoff.

## 8. Changes to this policy
New or changed rules must be replay-tested against prior periods and approved by the Controller before activation. No rule may lower a threshold in section 4 or remove a control in section 5 without Controller approval.
"""

POLICIES_JSON = {
    "policy_version": "1.0",
    "close_cutoff_day": 5,
    "allowed_methods": {
        "FIXED_CONTRACT_FEE": ["contract", "service_period"],
        "USAGE_X_RATE": ["usage_record", "contract_rate"],
        "PRORATED_FEE": ["contract", "service_dates"],
        "PO_BASED": ["purchase_order", "service_receipt"],
        "HISTORICAL_RUN_RATE": ["prior_invoices_min_3"],
    },
    "historical_run_rate_limits": {"max_amount": 10000.0, "max_variation_pct": 10.0},
    "approval_thresholds": {"auto_max": 9999.99, "reviewer_max": 24999.99, "min_auto_confidence": 0.85},
    "true_up_tolerance": {"abs": 500.0, "pct": 2.0},
    "prior_period_controller_threshold": 25000.0,
    "outreach_wait_hours": 48,
    "learned_policies": [],
}


def render_pdfs(out_dir, contracts, invoices):
    """Render contracts and invoices to PDF. Returns False when reportlab is unavailable."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return False
    st = getSampleStyleSheet()
    for vid, text in contracts.items():
        doc = SimpleDocTemplate(str(out_dir / "contracts" / f"{w.VENDOR[vid]['contract_id']}.pdf"), pagesize=LETTER)
        lines = text.split("\n")
        flow = [Paragraph(lines[0], st["Title"])]
        flow += [Paragraph(escape(l), st["BodyText"]) if l else Spacer(1, 10) for l in lines[1:]]
        doc.build(flow)
    for inv in invoices:
        doc = SimpleDocTemplate(str(out_dir / "invoices" / "pdf" / f"{inv['invoice_id']}.pdf"), pagesize=LETTER)
        head = [Paragraph(inv["vendor_name"], st["Title"]),
                Paragraph("CREDIT MEMO" if inv["amount"] < 0 else "INVOICE", st["Heading2"]),
                Paragraph(f"Invoice number: {inv['invoice_number']}<br/>Invoice date: {inv['invoice_date']}<br/>"
                          f"Bill to: {inv['bill_to']}<br/>PO: {inv['po_id'] or '-'}<br/>"
                          f"Service period: {inv['service_period_start']} to {inv['service_period_end']}<br/>"
                          f"Terms: {inv['payment_terms']}", st["BodyText"]), Spacer(1, 14)]
        data = [["Description", "Qty", "Unit price", "Amount"]]
        data += [[Paragraph(l["description"], st["BodyText"]), f"{l['quantity']:,}", f"${l['unit_price']:,.2f}",
                  f"${l['amount']:,.2f}"] for l in inv["line_items"]]
        data.append(["", "", "Total due (USD)", f"${inv['amount']:,.2f}"])
        tbl = Table(data, colWidths=[280, 60, 80, 90])
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
                                 ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                 ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                                 ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold")]))
        doc.build(head + [tbl] + ([Spacer(1, 12), Paragraph(inv["notes"], st["Italic"])] if inv["notes"] else []))
    return True
