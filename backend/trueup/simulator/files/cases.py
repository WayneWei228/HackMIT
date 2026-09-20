"""Per-vendor file universes. Every figure, date and name is read from the world view."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from trueup.simulator.files import previews
from trueup.simulator.files.common import (
    CLOSE,
    DAY_ONE,
    Ctx,
    Spec,
    addr,
    ap_history_spec,
    at,
    gl_export_spec,
    invoice_spec,
    latest_invoice,
    mail_spec,
    make_spec,
    memo_doc,
    slack_spec,
    vendor_master_spec,
)
from trueup.simulator.files.doc import Doc, KeyValues, Mail, Para, Sheet, Table
from trueup.simulator.files.text import (
    after_fees,
    before_fees,
    boilerplate,
    long_date,
    split_units,
    usd,
    usd2,
)
from trueup.simulator.scenario_models import APInvoiceRecord, ServiceEvidenceRecord

MEMO_DATE = at(12, 3)


def _po_doc(ctx: Ctx, po, extra_note: str) -> tuple[Doc, list[tuple[str, str]]]:
    line = po.line_items_json[0]
    qty = line.quantity_ordered or Decimal(1)
    rows = [
        ("PO number", po.po_number),
        ("Vendor", ctx.legal),
        ("Buyer", ctx.cast.customer),
        ("Order date", long_date(po.service_start_date or DAY_ONE.date())),
        ("Status", po.status),
        ("Approved total", usd2(po.approved_total)),
    ]
    doc = Doc(
        "Purchase Order",
        ctx.name,
        (
            KeyValues(tuple(rows)),
            Table(
                ("Line", "Description", "Qty", "Unit price", "Amount"),
                (
                    (
                        line.po_line_id,
                        line.line_description,
                        f"{qty:,.0f}",
                        usd2(line.unit_price),
                        usd2(qty * line.unit_price),
                    ),
                ),
            ),
            Para(extra_note),
        ),
    )
    return doc, rows


def _usage_summary_spec(
    ctx: Ctx, filename: str, title: str, rows, reason: str, role: str = "NOISE"
) -> Spec:
    doc = Doc(title, f"{ctx.name} product usage", (KeyValues(tuple(rows)),))
    return make_spec(
        "usage",
        "PDF",
        filename,
        title,
        f"{ctx.name} product usage",
        doc,
        previews.record(title, "USAGE REPORT", list(rows)),
        role,
        reason,
    )


def mintlify(ctx: Ctx) -> list[Spec]:
    vid = ctx.vendor.vendor_id
    contracts = ctx.view.contracts(vid)
    old, new = contracts[0], contracts[-1]
    po = ctx.view.pos(vid)[0]
    prior = latest_invoice(ctx)
    signed = new.effective_start_date - timedelta(days=13)
    term_end = new.effective_end_date or old.effective_end_date
    clause_42 = (
        f"Commencing {long_date(new.effective_start_date)}, the monthly subscription fee for the "
        f"Standard Workspace plan shall increase from {usd(old.base_rate)} to {usd(new.base_rate)} "
        "per month for the remainder of the term."
    )
    bp = boilerplate(ctx.legal, ctx.cast.customer)
    agreement = Doc(
        ctx.name,
        "Master Subscription Agreement",
        (
            KeyValues(
                (
                    ("Customer", ctx.cast.customer),
                    ("Vendor", ctx.legal),
                    ("Plan", "Standard Workspace"),
                    ("Initial term starts", long_date(old.effective_start_date)),
                    ("Term ends", long_date(term_end) if term_end else "auto-renews"),
                )
            ),
            *before_fees(bp),
            *_fees_section(
                f"4.1 During the initial term the monthly subscription fee for the Standard "
                f"Workspace plan is {usd(old.base_rate)} per month, invoiced monthly in arrears.",
                f"4.2 {clause_42}",
            ),
            *after_fees(bp),
            *_amendment(signed, new.effective_start_date, old.base_rate, new.base_rate),
        ),
    )
    memo = memo_doc(
        "Close Memo",
        (
            ("To", ctx.cast.person("CONTROLLER-001")["name"] + ", Controller"),
            ("From", "Finance Operations"),
            ("Date", long_date(MEMO_DATE.date())),
            ("Subject", "November close: Mintlify subscription accrual"),
        ),
        [
            f"November was accrued and invoiced at {usd(prior.amount)}, the rate in force through "
            f"{long_date(old.effective_end_date)}.",
            f"The amended agreement signed on {long_date(signed)} raises the monthly fee to "
            f"{usd(new.base_rate)} effective {long_date(new.effective_start_date)}.",
            "Action for the December close: accrue at the amended agreement rate, not the rate on "
            "the purchase order.",
        ],
    )
    po_doc, _ = _po_doc(
        ctx, po, "Order form as issued. Rate changes are handled by contract amendment."
    )
    invoice = invoice_spec(
        ctx,
        prior,
        "HARD_NEGATIVE",
        "The previous month's invoice at the old fee looks current but covers a closed period.",
    )
    person, mail_addr = ctx.contact
    riley = ctx.cast.owner(vid)
    thread = (
        Mail(
            addr(riley),
            addr((person, mail_addr)),
            at(12, 8, 10),
            "Mintlify SSO and custom domain",
            f"Hi {person.split()[0]},\n\nWe want to put the docs site on our own domain and turn on "
            "SSO for the editors. Which DNS records do you need from us?\n\nThanks,\n"
            + riley["name"].split()[0],
        ),
        Mail(
            addr((person, mail_addr)),
            addr(riley),
            at(12, 9, 14),
            "Re: Mintlify SSO and custom domain",
            "Add the CNAME from the dashboard, then paste the SAML metadata under Settings. "
            "Propagation usually takes under an hour.\n\nAlex",
        ),
        Mail(
            addr(riley),
            addr((person, mail_addr)),
            at(12, 10, 9, 30),
            "Re: Mintlify SSO and custom domain",
            "That worked, SSO is live. We stay on the current plan, so nothing else changes on our side.\n\nRiley",
        ),
    )
    return [
        make_spec(
            "agreement",
            "PDF",
            "mintlify_master_subscription_agreement.pdf",
            ctx.name,
            "Master Subscription Agreement",
            agreement,
            previews.clause(
                ctx.name, "Master Subscription Agreement", "4. Fees and Payment", "4.2", clause_42
            ),
            "SUPPORTS_AMOUNT",
            "The amended fee clause sets the effective monthly price for the accrued month.",
            at(11, 18),
        ),
        ap_history_spec(
            ctx,
            "SUPPORTS_DISCREPANCY",
            "Payment history shows the old fee still being billed, which exposes the price change.",
        ),
        make_spec(
            "prior",
            "DOCX",
            "november_close_memo_mintlify.docx",
            "Close Memo",
            "November close: Mintlify subscription accrual",
            memo,
            previews.memo(
                "December 2026",
                "Close Memo",
                {
                    "To": "Controller",
                    "From": "Finance Operations",
                    "Date": "Dec 3, 2026",
                    "Subject": "Mintlify subscription accrual",
                },
                memo.blocks[1].text + " " + memo.blocks[2].text,  # type: ignore[union-attr]
            ),
            "SUPPORTS_DISCREPANCY",
            "The prior close records the old accrual and flags the amendment for this month.",
            MEMO_DATE,
        ),
        vendor_master_spec(ctx),
        gl_export_spec(
            ctx,
            "Ledger rows are mostly other vendors, and the Mintlify rows show only past periods.",
        ),
        invoice,
        make_spec(
            "po",
            "PDF",
            "po_mintlify_2026.pdf",
            "Order Form",
            ctx.name,
            po_doc,
            previews.skeleton(
                "Order Form",
                ctx.name,
                [
                    ("Customer", "Northstar Analytics"),
                    ("Order date", long_date(po.service_start_date or DAY_ONE.date())),
                    ("Unit price", usd2(po.line_items_json[0].unit_price)),
                ],
            ),
            "HARD_NEGATIVE",
            "The purchase order still carries the pre-amendment price and was never updated.",
        ),
        mail_spec(
            ctx,
            "email",
            "re_mintlify_sso_and_custom_domain.eml",
            "Re: Mintlify SSO and custom domain",
            thread,
            "HARD_NEGATIVE",
            "Mentions the vendor and the current plan but states no price or effective date.",
            thread[-1].sent,
        ),
        slack_spec(
            ctx,
            "#eng-docs",
            [
                ("riley", 12, 6, 11, "docs site preview deploys are taking forever again"),
                (
                    "sam",
                    12,
                    6,
                    11,
                    "the docs site build is fine locally, could be the Mintlify preview queue",
                ),
                ("riley", 12, 7, 15, "can we add the new API reference pages before the release?"),
                ("taylor", 12, 7, 16, "yes, I will open the PR tonight"),
            ],
            "HARD_NEGATIVE",
            "Talks about the docs site and Mintlify but contains no pricing or contract facts.",
        ),
        _usage_summary_spec(
            ctx,
            "mintlify_workspace_usage_nov.pdf",
            "Usage Report",
            [
                ("Workspace", "Standard Workspace"),
                ("Period", "November 2026"),
                ("Page views", "48,210"),
                ("Active editors", "14"),
                ("Preview deploys", "212"),
            ],
            "Product analytics with no billing or fee information.",
        ),
    ]


def _fees_section(*clauses: str):
    from trueup.simulator.files.doc import Heading

    return (
        Heading("4. Fees and Payment"),
        *[Para(c) for c in clauses],
        Para("4.3 Fees are due net 30 from the invoice date. Late amounts accrue no interest."),
    )


def _amendment(signed: date, effective: date, old, new):
    from trueup.simulator.files.doc import Heading

    return (
        Heading("Amendment No. 1"),
        Para(
            f"Signed on {long_date(signed)}. The parties agree that from {long_date(effective)} the "
            f"monthly fee is {usd(new)} per month, replacing {usd(old)} per month."
        ),
    )


def _partial_usage(ctx: Ctx) -> tuple[ServiceEvidenceRecord, date, int]:
    december = [
        e
        for e in ctx.view.evidence(ctx.vendor.vendor_id)
        if e.service_start_date >= date(2026, 12, 1)
    ]
    if not december:
        raise ValueError("OpenAI has no December usage evidence before the close")
    evidence = december[-1]
    through = evidence.service_end_date
    if through >= date(2026, 12, 31):
        through = date(2026, 12, 19)
    return evidence, through, int(evidence.quantity or 0)


def _openai_messages(ctx: Ctx, through: date) -> tuple[Mail, ...]:
    ap, service = ctx.cast.person("AP-001"), ctx.cast.owner(ctx.vendor.vendor_id)
    first = service["name"].split()[0]
    return (
        Mail(
            addr(ap),
            addr(service),
            at(12, 29, 10),
            "OpenAI December usage export is incomplete",
            f"Hi {first},\n\nThe usage export in the finance folder only covers December 1 to "
            f"December {through.day}. Could you send the total API units for the full month? "
            f"We need it to finish the close.\n\nThanks,\n{ap['name'].split()[0]}",
        ),
        Mail(
            addr(ap),
            addr(service),
            at(12, 31, 8, 30),
            "Re: OpenAI December usage export is incomplete",
            f"Hi {first}, following up on the December usage total. The close cannot be finalized "
            "without it.\n\n" + ap["name"].split()[0],
        ),
    )


def openai(ctx: Ctx) -> list[Spec]:
    vid = ctx.vendor.vendor_id
    contract = ctx.view.contracts(vid)[-1]
    base = contract.base_rate or Decimal(0)
    pct = contract.escalator_percent
    eff = contract.escalator_effective_date
    rate = base * (1 + pct / 100) if pct else base
    evidence, through, partial_units = _partial_usage(ctx)
    invoices = ctx.view.invoices(vid)

    bp = boilerplate(ctx.legal, ctx.cast.customer)
    step = (
        f"5.2 Effective {long_date(eff)}, the usage rate increases by {pct.normalize():f} percent "
        f"from {usd(base)} to {usd(rate)} per unit."
        if pct and eff
        else "5.2 The usage rate is fixed for the term."
    )
    agreement = Doc(
        ctx.name,
        "API Services Agreement",
        (
            KeyValues(
                (
                    ("Customer", ctx.cast.customer),
                    ("Vendor", ctx.legal),
                    ("Billing model", "Usage based, monthly in arrears"),
                    ("Unit", "API unit"),
                    ("Term starts", long_date(contract.effective_start_date)),
                )
            ),
            *before_fees(bp),
            *_fees_section(f"4.1 Customer pays {usd(base)} per API unit consumed.", step),
            *after_fees(bp),
        ),
    )

    segments, day = [], date(2026, 12, 1)
    while day <= through:
        end = min(day + timedelta(days=6), through)
        segments.append((day, end))
        day = end + timedelta(days=1)
    parts = split_units(partial_units, len(segments))
    rows = tuple(
        (f"{a:%b} {a.day} - {b:%b} {b.day}", f"{u:,}")
        for (a, b), u in zip(segments, parts, strict=True)
    )
    usage = Doc(
        "Usage Report",
        f"{ctx.name} API, December 2026",
        (
            KeyValues(
                (
                    ("Export status", f"PARTIAL - data through December {through.day}"),
                    ("Units to date", f"{partial_units:,}"),
                    ("Not yet exported", f"December {through.day + 1} - December 31"),
                )
            ),
            Table(("Window", "Units"), rows),
        ),
    )

    accruals = {
        e.period: sum((ln.debit for ln in e.lines_json), Decimal(0))
        for e in ctx.view.gl_entries()
        if e.vendor_id == vid and e.entry_type == "ACCRUAL"
    }
    table_rows = []
    for inv in invoices:
        month = inv.service_end_date.strftime("%Y-%m") if inv.service_end_date else ""
        if month in accruals and month >= "2026-10":
            table_rows.append(
                (month, usd2(accruals[month]), usd2(inv.amount), usd2(inv.amount - accruals[month]))
            )
    if not table_rows:
        raise ValueError("OpenAI has no accrual history before the close")
    memo = memo_doc(
        "Close Memo",
        (
            ("To", ctx.cast.person("CONTROLLER-001")["name"] + ", Controller"),
            ("From", "Finance Operations"),
            ("Date", long_date(MEMO_DATE.date())),
            ("Subject", "November close: OpenAI accrual versus invoice"),
        ),
        [
            f"Accruals were booked at the base rate of {usd(base)} per unit. Invoices were billed at "
            f"{usd(rate)} per unit after the rate step-up effective {long_date(eff) if eff else 'earlier'}.",
            "The accrual came in under the invoice each month. Verify the effective rate before "
            "accruing usage.",
        ],
        Table(("Period", "Accrued", "Invoiced", "Variance"), tuple(table_rows)),
    )

    thread = _openai_messages(ctx, through)
    ap_spec = ap_history_spec(
        ctx,
        "HARD_NEGATIVE",
        "Past invoices tempt a run-rate estimate, which policy allows only as an approved fallback.",
    )
    old_invoice = invoice_spec(
        ctx,
        invoices[0],
        "HARD_NEGATIVE",
        "An early invoice for a closed period, with different units and a different rate.",
    )
    riley = ctx.cast.owner(vid)
    news = (
        Mail(
            "OpenAI Newsletter <news@openai.example>",
            addr(riley),
            at(12, 15, 12),
            "Product news and pricing update",
            "New models are now available in the API. List pricing for the latest model starts at "
            "$2.50 per 1M input tokens and $10.00 per 1M output tokens.\n\nManage preferences in your dashboard.",
        ),
    )
    return [
        make_spec(
            "agreement",
            "PDF",
            "openai_api_services_agreement.pdf",
            ctx.name,
            "API Services Agreement",
            agreement,
            previews.clause(
                ctx.name, "API Services Agreement", "4. Fees and Payment", "5.2", step[4:]
            ),
            "SUPPORTS_AMOUNT",
            "States the unit rate and the step-up that sets the effective price.",
            at(9, 1),
        ),
        make_spec(
            "usage",
            "PDF",
            "usage_report_dec_2026.pdf",
            "Usage Report",
            "API, December 2026",
            usage,
            previews.table(
                "Usage Report", "PARTIAL EXPORT", ["WINDOW", "UNITS"], [list(r) for r in rows]
            ),
            "SUPPORTS_AMOUNT",
            "The only usage evidence for the month, and it is incomplete.",
            evidence.created_at,
        ),
        make_spec(
            "prior",
            "DOCX",
            "november_close_memo_openai.docx",
            "Close Memo",
            "November close: OpenAI accrual versus invoice",
            memo,
            previews.memo(
                "November 2026",
                "Close Memo",
                {
                    "To": "Controller",
                    "From": "Finance Operations",
                    "Date": "Dec 3, 2026",
                    "Subject": "OpenAI accrual versus invoice",
                },
                memo.blocks[1].text,  # type: ignore[union-attr]
            ),
            "SUPPORTS_DISCREPANCY",
            "Records the earlier accrual miss caused by using the stale rate.",
            MEMO_DATE,
        ),
        mail_spec(
            ctx,
            "email",
            "openai_december_usage_export_thread.eml",
            thread[0].subject,
            thread,
            "SUPPORTS_DISCREPANCY",
            "Shows the December usage is incomplete and that the total was requested but not received.",
            thread[-1].sent,
        ),
        vendor_master_spec(ctx),
        gl_export_spec(ctx, "Ledger rows are mostly other vendors and show only past accruals."),
        old_invoice,
        slack_spec(
            ctx,
            "#ai-platform",
            [
                ("sam", 12, 10, 10, "rotating the API keys for staging this afternoon"),
                ("riley", 12, 10, 11, "eval run finished, latency looks good on the new prompt"),
                ("taylor", 12, 11, 9, "can someone bump the rate limit on the sandbox project?"),
            ],
            "NOISE",
            "Engineering chatter about keys and evals with no accounting facts.",
        ),
        mail_spec(
            ctx,
            "email",
            "openai_product_news_dec.eml",
            "Product news and pricing update",
            news,
            "NOISE",
            "Marketing newsletter with public list prices that do not apply to the contract.",
            news[0].sent,
        ),
        ap_spec,
    ]


def _receipt_evidence(ctx: Ctx) -> ServiceEvidenceRecord:
    receipts = [
        e for e in ctx.view.evidence(ctx.vendor.vendor_id) if e.evidence_type == "GOODS_RECEIPT"
    ]
    if not receipts:
        raise ValueError("ASUS has no goods receipt before the close")
    return receipts[-1]


def asus(ctx: Ctx) -> list[Spec]:
    vid = ctx.vendor.vendor_id
    po = ctx.view.pos(vid)[0]
    line = po.line_items_json[0]
    ordered = line.quantity_ordered or Decimal(0)
    receipt = _receipt_evidence(ctx)
    received = receipt.quantity or Decimal(0)
    accepted = receipt.accepted_amount or received * line.unit_price
    cap = ctx.view.config("capitalization_policy")
    life = line.useful_life_months or cap["useful_life_months"]

    po_doc, po_rows = _po_doc(
        ctx, po, "Deliver to HQ receiving. Partial shipments are accepted and billed as received."
    )
    goods = Doc(
        "Goods Receipt",
        ctx.name,
        (
            KeyValues(
                (
                    ("Receipt", receipt.service_evidence_id),
                    ("PO number", po.po_number),
                    ("Vendor", ctx.legal),
                    ("Received on", long_date(receipt.service_end_date)),
                    ("Location", "HQ receiving"),
                )
            ),
            Table(
                ("Line", "Description", "Ordered", "Received", "Backordered"),
                (
                    (
                        line.po_line_id,
                        line.line_description,
                        f"{ordered:,.0f}",
                        f"{received:,.0f}",
                        f"{ordered - received:,.0f}",
                    ),
                ),
            ),
            Para(
                f"Accepted value of goods received: {usd2(accepted)}. Remaining units are on backorder."
            ),
        ),
    )
    policy = memo_doc(
        "Capitalization Policy",
        (
            ("To", "Finance and Procurement"),
            ("From", ctx.cast.person("CONTROLLER-001")["name"] + ", Controller"),
            ("Date", "January 15, 2026"),
            ("Subject", "Fixed asset capitalization policy"),
        ),
        [
            f"Equipment purchases are capitalized when a single order of like items costs {usd(Decimal(cap['threshold_usd']))} "
            "or more and the items have a useful life beyond one year.",
            f"Capitalized equipment is depreciated straight-line over {life} months, starting when "
            "the asset is placed in service. Only units actually received are recorded as assets.",
        ],
    )
    old_invoice = Doc(
        "Invoice A-2025-1188",
        ctx.legal,
        (
            KeyValues((("Invoice date", "June 12, 2025"), ("Bill to", ctx.cast.customer))),
            Table(
                ("Description", "Qty", "Unit price", "Amount"),
                (("Laptops, prior year order", "10", "$1,450.00", "$14,500.00"),),
            ),
            Para("Total due: $14,500.00"),
        ),
    )
    ops = ctx.cast.person("OPS-001")
    desks = (
        Mail(
            addr(ops),
            "Deskworks Sales <sales@deskworks.example>",
            at(12, 4, 9),
            "Standing desk quote",
            "Could you quote 8 sit-stand desks for the new floor plan?\n\nTaylor",
        ),
        Mail(
            "Deskworks Sales <sales@deskworks.example>",
            addr(ops),
            at(12, 5, 13),
            "Re: Standing desk quote",
            "Quote attached: 8 desks at $620 each, delivered and assembled.\n\nDeskworks",
        ),
    )
    slip = Doc(
        "Packing Slip PS-88214",
        "Deskworks Supply",
        (
            KeyValues((("PO reference", "PO-2026-0412"), ("Delivered", "December 9, 2026"))),
            Table(("Item", "Qty"), (("Monitor arm, dual", "12"),)),
        ),
    )
    register = Sheet(
        "Asset register",
        ("Tag", "Asset", "Cost", "In service"),
        (
            ("FA-1001", "Rack server", Decimal("18400.00"), "2025-02-01"),
            ("FA-1002", "Conference room display", Decimal("3200.00"), "2025-05-15"),
            ("FA-1003", "Network switch", Decimal("2750.00"), "2025-08-01"),
        ),
    )
    return [
        make_spec(
            "po",
            "PDF",
            "po_asus_laptops.pdf",
            "Purchase Order",
            ctx.name,
            po_doc,
            previews.skeleton(
                "Purchase Order", ctx.name, po_rows[:4], ("Approved total", usd2(po.approved_total))
            ),
            "SUPPORTS_AMOUNT",
            "Sets the ordered quantity and the agreed unit price.",
            DAY_ONE,
        ),
        make_spec(
            "receipt",
            "PDF",
            f"goods_receipt_{receipt.service_evidence_id.lower()}.pdf",
            "Goods Receipt",
            ctx.name,
            goods,
            previews.skeleton(
                "Goods Receipt",
                ctx.name,
                [
                    ("PO number", po.po_number),
                    ("Ordered", f"{ordered:,.0f}"),
                    ("Received", f"{received:,.0f}"),
                ],
            ),
            "SUPPORTS_AMOUNT",
            "Shows how many units were actually received by year end.",
            receipt.created_at,
        ),
        make_spec(
            "policy",
            "DOCX",
            "capitalization_policy_memo.docx",
            "Capitalization Policy",
            "Fixed asset capitalization policy",
            policy,
            previews.memo(
                "Capitalization Policy",
                "Policy memo",
                {
                    "To": "Finance and Procurement",
                    "Date": "Jan 15, 2026",
                    "Subject": "Fixed asset capitalization policy",
                },
                policy.blocks[1].text,  # type: ignore[union-attr]
            ),
            "SUPPORTS_DISCREPANCY",
            "Explains that only received units are capitalized and how they depreciate.",
            at(1, 15),
        ),
        vendor_master_spec(ctx),
        gl_export_spec(
            ctx, "Ledger rows belong mostly to other vendors and contain no ASUS receipt."
        ),
        mail_spec(
            ctx,
            "email",
            "standing_desk_quote_thread.eml",
            "Standing desk quote",
            desks,
            "NOISE",
            "A quote thread about desks from a different supplier.",
            desks[-1].sent,
        ),
        slack_spec(
            ctx,
            "#eng-onboarding",
            [
                ("riley", 12, 12, 10, "new engineers start in January, are their laptops sorted?"),
                ("taylor", 12, 12, 11, "the laptops are late again, I will chase procurement"),
                ("sam", 12, 13, 9, "we also need monitor arms for the new desks"),
            ],
            "HARD_NEGATIVE",
            "Mentions laptops and delays but gives no quantities, prices or dates.",
        ),
        make_spec(
            "packing",
            "PDF",
            "packing_slip_ps_88214.pdf",
            "Packing Slip",
            "Deskworks Supply",
            slip,
            previews.skeleton(
                "Packing Slip",
                "Deskworks Supply",
                [("PO reference", "PO-2026-0412"), ("Delivered", "12/09/2026")],
            ),
            "HARD_NEGATIVE",
            "A delivery record for a different order from a different supplier.",
        ),
        make_spec(
            "register",
            "XLSX",
            "fixed_asset_register.xlsx",
            "Fixed Asset Register",
            "Asset listing",
            register,
            previews.table(
                "Fixed Asset Register",
                "Asset listing",
                ["TAG", "ASSET", "COST"],
                [[r[0], r[1], usd2(r[2])] for r in register.rows],
            ),
            "NOISE",
            "Existing assets only; the new laptops are not on the register yet.",
        ),
        make_spec(
            "invoice",
            "PDF",
            "invoice_a_2025_1188.pdf",
            "Invoice A-2025-1188",
            ctx.legal,
            old_invoice,
            previews.skeleton(
                "Invoice A-2025-1188",
                ctx.legal,
                [("Invoice date", "06/12/2025")],
                ("Total", "$14,500.00"),
            ),
            "HARD_NEGATIVE",
            "A prior-year invoice for an earlier order at a different price.",
            at(6, 12, year=2025),
        ),
    ]


def _delivery_evidence(ctx: Ctx) -> ServiceEvidenceRecord:
    reports = [e for e in ctx.view.evidence(ctx.vendor.vendor_id) if e.accepted_amount is not None]
    if not reports:
        raise ValueError("Meta has no delivery evidence before the close")
    return reports[-1]


def meta(ctx: Ctx) -> list[Spec]:
    vid = ctx.vendor.vendor_id
    po = ctx.view.pos(vid)[0]
    budget = po.approved_total
    report = _delivery_evidence(ctx)
    delivered = report.accepted_amount or Decimal(0)
    shares = (Decimal("0.45"), Decimal("0.35"))
    first = (delivered * shares[0]).quantize(Decimal("0.01"))
    second = (delivered * shares[1]).quantize(Decimal("0.01"))
    sets = (
        ("Launch video", first),
        ("Carousel", second),
        ("Retargeting", delivered - first - second),
    )

    order = Doc(
        "Campaign Order",
        ctx.name,
        (
            KeyValues(
                (
                    ("Order number", po.po_number),
                    ("Advertiser", ctx.cast.customer),
                    ("Campaign", "Product launch campaign"),
                    (
                        "Flight",
                        f"{long_date(po.service_start_date or DAY_ONE.date())} to {long_date(po.service_end_date or CLOSE.date())}",
                    ),
                    ("Not-to-exceed budget", usd2(budget)),
                )
            ),
            Para(
                "Charges are based on ad spend actually delivered and cannot exceed the stated budget."
            ),
        ),
    )
    delivery = Doc(
        "Delivery Report",
        f"{ctx.name} product launch campaign",
        (
            KeyValues(
                (
                    ("Campaign", "Product launch campaign"),
                    ("Reporting date", long_date(report.service_end_date)),
                    ("Budget", usd2(budget)),
                    ("Delivered to date", usd2(delivered)),
                )
            ),
            Table(("Ad set", "Delivered"), tuple((name, usd2(v)) for name, v in sets)),
        ),
    )
    memo = memo_doc(
        "Campaign Close Memo",
        (
            ("To", ctx.cast.person("CONTROLLER-001")["name"] + ", Controller"),
            ("From", "Finance Operations"),
            ("Date", "October 6, 2026"),
            ("Subject", "Q3 campaign close: accrue delivered spend"),
        ),
        [
            "For the Q3 campaign the order allowed $15,000 but only $13,120 of ads were delivered. "
            "We accrued the delivered $13,120 and the final invoice matched it.",
            "Rule of thumb: accrue delivered spend, never the order budget.",
        ],
    )
    brief = Doc(
        "Creative Brief",
        "Product launch campaign",
        (
            KeyValues(
                (
                    ("Audience", "Engineering leads at mid-size companies"),
                    ("Goal", "1.2M impressions"),
                    ("Channels", "Feed and stories"),
                )
            ),
            Para("Tone: direct and technical. Provide three creative variants per ad set."),
        ),
    )
    old_invoice = Doc(
        "Invoice M-Q3-2044",
        ctx.legal,
        (
            KeyValues((("Invoice date", "October 9, 2026"), ("Bill to", ctx.cast.customer))),
            Table(
                ("Description", "Amount"),
                (("Q3 awareness campaign, delivered media", "$13,120.00"),),
            ),
            Para("Total due: $13,120.00"),
        ),
    )
    agency = ("Jo Park", "jo@creative-agency.example")
    mkt = ctx.cast.owner(vid, "po_owner_id")
    specs_mail = (
        Mail(
            addr(agency),
            addr(mkt),
            at(12, 2, 10),
            "Launch creative specs",
            "Attached are the final specs: 1080x1350 for feed, 1080x1920 for stories. Please confirm the safe zones.\n\nJo",
        ),
    )
    performance = Sheet(
        "Campaign performance",
        ("Ad set", "Impressions", "Clicks"),
        (("Launch video", 412000, 5210), ("Carousel", 298000, 3880), ("Retargeting", 176000, 4105)),
    )
    return [
        make_spec(
            "order",
            "PDF",
            "campaign_order_meta.pdf",
            "Campaign Order",
            ctx.name,
            order,
            previews.skeleton(
                "Campaign Order",
                ctx.name,
                [("Order", po.po_number), ("Campaign", "Product launch")],
                ("Budget", usd2(budget)),
            ),
            "SUPPORTS_AMOUNT",
            "Sets the budget ceiling and says charges follow delivered spend.",
            DAY_ONE,
        ),
        make_spec(
            "delivery",
            "PDF",
            "delivery_report_meta_dec.pdf",
            "Delivery Report",
            ctx.name,
            delivery,
            previews.table(
                "Delivery Report",
                "Delivered to date",
                ["AD SET", "DELIVERED"],
                [[n, usd2(v)] for n, v in sets],
            ),
            "SUPPORTS_AMOUNT",
            "Shows how much advertising was actually delivered.",
            report.created_at,
        ),
        make_spec(
            "prior",
            "DOCX",
            "prior_campaign_close_meta.docx",
            "Campaign Close Memo",
            "Q3 campaign close: accrue delivered spend",
            memo,
            previews.memo(
                "Q3 campaign",
                "Close Memo",
                {"To": "Controller", "Date": "Oct 6, 2026", "Subject": "Accrue delivered spend"},
                memo.blocks[1].text,  # type: ignore[union-attr]
            ),
            "SUPPORTS_DISCREPANCY",
            "Precedent: the prior campaign was accrued on delivery, not budget.",
            at(10, 6),
        ),
        vendor_master_spec(ctx),
        gl_export_spec(
            ctx, "Ledger rows are mostly other vendors and contain no Meta campaign accrual."
        ),
        make_spec(
            "brief",
            "DOCX",
            "creative_brief_launch.docx",
            "Creative Brief",
            "Product launch campaign",
            brief,
            previews.memo(
                "Creative Brief",
                "Product launch campaign",
                {"Audience": "Engineering leads", "Goal": "1.2M impressions"},
                "Tone: direct and technical.",
            ),
            "NOISE",
            "Creative direction with no spend or delivery figures.",
            at(11, 20),
        ),
        slack_spec(
            ctx,
            "#marketing-launch",
            [
                ("taylor", 12, 3, 10, "launch video is approved, agency is loading it today"),
                ("riley", 12, 3, 11, "can we get the landing page ready before the ads go live?"),
                ("sam", 12, 4, 9, "landing page is up on staging"),
            ],
            "NOISE",
            "Launch logistics chatter with no amounts.",
        ),
        make_spec(
            "invoice",
            "PDF",
            "invoice_m_q3_2044.pdf",
            "Invoice M-Q3-2044",
            ctx.legal,
            old_invoice,
            previews.skeleton(
                "Invoice M-Q3-2044",
                ctx.legal,
                [("Invoice date", "10/09/2026")],
                ("Total", "$13,120.00"),
            ),
            "HARD_NEGATIVE",
            "An invoice for the previous campaign at a different amount.",
            at(10, 9),
        ),
        mail_spec(
            ctx,
            "email",
            "launch_creative_specs.eml",
            "Launch creative specs",
            specs_mail,
            "NOISE",
            "Creative file specifications from the agency with no financial content.",
            specs_mail[0].sent,
        ),
        make_spec(
            "report",
            "XLSX",
            "campaign_performance_export.xlsx",
            "Campaign Performance",
            "Impressions and clicks",
            performance,
            previews.table(
                "Campaign Performance",
                "Impressions and clicks",
                ["AD SET", "IMPRESSIONS", "CLICKS"],
                [[r[0], f"{r[1]:,}", f"{r[2]:,}"] for r in performance.rows],
            ),
            "NOISE",
            "Engagement metrics only; no dollars are reported.",
            at(12, 18),
        ),
    ]


def notability(ctx: Ctx) -> list[Spec]:
    vid = ctx.vendor.vendor_id
    contract = ctx.view.contracts(vid)[-1]
    invoice = latest_invoice(ctx)
    start, end = contract.effective_start_date, contract.effective_end_date
    months = ((end.year - start.year) * 12 + end.month - start.month + 1) if end else 12
    paid_on = invoice.invoice_date + timedelta(days=3)
    entries = [e for e in ctx.view.gl_entries() if e.vendor_id == vid]
    gl_rows = tuple(
        (
            e.posting_date.isoformat(),
            e.gl_entry_id,
            f"{e.entry_type}: {e.description} ({ln.account_code} {'Dr' if ln.debit else 'Cr'})",
            ln.debit or ln.credit,
        )
        for e in entries
        for ln in e.lines_json
    )
    detail = Sheet("GL detail", ("Date", "JE", "Description", "Amount"), gl_rows)
    bp = boilerplate(ctx.legal, ctx.cast.customer)
    agreement = Doc(
        ctx.name,
        "Team Subscription Agreement",
        (
            KeyValues(
                (
                    ("Customer", ctx.cast.customer),
                    ("Vendor", ctx.legal),
                    ("Service start", long_date(start)),
                    ("Service end", long_date(end) if end else "12 months after start"),
                    ("Term", f"{months} months"),
                )
            ),
            *before_fees(bp),
            *_fees_section(
                f"4.1 The team subscription fee is {usd(invoice.amount)} for the {months}-month term, "
                "invoiced annually in advance.",
                "4.2 The subscription covers the service dates stated above and renews annually unless cancelled.",
            ),
            *after_fees(bp),
        ),
    )
    payment = (
        Mail(
            "Accounts Payable <ap@northstar.example>",
            addr(ctx.contact),
            datetime.combine(paid_on, datetime.min.time(), tzinfo=DAY_ONE.tzinfo).replace(hour=15),
            f"Payment confirmation for invoice {invoice.invoice_number}",
            f"We paid {usd2(invoice.amount)} on {long_date(paid_on)} against invoice {invoice.invoice_number} "
            "by ACH. Remittance advice is attached to the payment record.",
        ),
    )
    pilot = Doc(
        "Invoice NP-2025-031",
        ctx.legal,
        (
            KeyValues((("Invoice date", "November 3, 2025"), ("Bill to", ctx.cast.customer))),
            Table(("Description", "Amount"), (("One-month team pilot", "$960.00"),)),
            Para("Total due: $960.00"),
        ),
    )
    lee = ctx.contact
    news = (
        Mail(
            addr(lee),
            addr(ctx.cast.owner(vid)),
            at(12, 14, 11),
            "Notability Teams product update",
            "New this month: shared notebooks and admin controls. Team plans start at $9.99 per user per month.\n\nThe Notability team",
        ),
    )
    return [
        invoice_spec(
            ctx,
            invoice,
            "SUPPORTS_AMOUNT",
            "The invoice sets the prepaid amount and service period.",
        ),
        make_spec(
            "agreement",
            "PDF",
            "notability_team_subscription_agreement.pdf",
            ctx.name,
            "Team Subscription Agreement",
            agreement,
            previews.clause(
                ctx.name,
                "Team Subscription Agreement",
                "4. Fees and Payment",
                "4.1",
                f"The team subscription fee is {usd(invoice.amount)} for the {months}-month term.",
            ),
            "SUPPORTS_AMOUNT",
            "Provides the twelve service months over which the cost is spread.",
            at(11, 20),
        ),
        make_spec(
            "gl",
            "XLSX",
            "gl_detail_notability.xlsx",
            "GL Detail",
            "Notability entries",
            detail,
            previews.table(
                "GL Detail",
                "Notability entries",
                ["DATE", "JE", "AMOUNT"],
                [[r[0], r[1], usd2(r[3])] for r in gl_rows],
            ),
            "SUPPORTS_DISCREPANCY",
            "Shows the payment and the entry that expenses the full amount at once.",
        ),
        mail_spec(
            ctx,
            "payment",
            "payment_confirmation_notability.eml",
            payment[0].subject,
            payment,
            "SUPPORTS_AMOUNT",
            "Confirms the cash payment that created the prepaid balance.",
            payment[0].sent,
        ),
        vendor_master_spec(ctx),
        gl_export_spec(
            ctx, "Ledger rows are mostly other vendors and do not isolate the Notability entries."
        ),
        slack_spec(
            ctx,
            "#it-tools",
            [
                ("riley", 12, 9, 10, "are we all set on Notability seats for the new hires?"),
                ("taylor", 12, 9, 11, "yes, admin added them yesterday"),
            ],
            "NOISE",
            "Seat administration chatter with no financial facts.",
        ),
        mail_spec(
            ctx,
            "email",
            "notability_product_update.eml",
            "Notability Teams product update",
            news,
            "NOISE",
            "Marketing update with public list prices that are not the contract price.",
            news[0].sent,
        ),
        make_spec(
            "invoice",
            "PDF",
            "invoice_np_2025_031.pdf",
            "Invoice NP-2025-031",
            ctx.legal,
            pilot,
            previews.skeleton(
                "Invoice NP-2025-031",
                ctx.legal,
                [("Invoice date", "11/03/2025")],
                ("Total", "$960.00"),
            ),
            "HARD_NEGATIVE",
            "A prior-year pilot invoice at a different amount.",
            at(11, 3, year=2025),
        ),
        _usage_summary_spec(
            ctx,
            "notability_seat_activity_nov.pdf",
            "Seat Activity Report",
            [
                ("Plan", "Teams"),
                ("Period", "November 2026"),
                ("Active seats", "96"),
                ("Notebooks created", "1,340"),
            ],
            "Seat activity metrics with no billing information.",
        ),
    ]


def late_specs(ctx: Ctx) -> list[Spec]:
    """Files that arrive after the close: the December invoice and any outreach replies."""
    specs: list[Spec] = []
    vid = ctx.vendor.vendor_id
    for event in sorted(ctx.world.events, key=lambda e: (e.available_at, e.event_id)):
        if event.table != "company_ap_invoices" or event.operation != "INSERT":
            continue
        if event.available_at <= CLOSE or event.record.get("vendor_id") != vid:
            continue
        invoice = APInvoiceRecord.model_validate(event.record)
        specs.append(
            invoice_spec(
                ctx,
                invoice,
                "LATE_ARRIVAL",
                "The real invoice arrives after the close and grades the accrual.",
                available_at=event.available_at,
                universe=False,
            )
        )
    for reply in ctx.world.outreach:
        if ctx.name.upper() not in reply.outreach_key.upper():
            continue
        sender = _reply_sender(ctx, reply.recipient_role)
        ap = ctx.cast.person("AP-001")
        if ctx.name == "OpenAI":
            _, through, _ = _partial_usage(ctx)
            earlier = _openai_messages(ctx, through)
        else:
            earlier = ()
        mail = Mail(
            addr(sender),
            addr(ap),
            reply.available_at,
            f"Re: {ctx.name} December confirmation",
            reply.response_text,
        )
        thread = (*earlier, mail)
        subject = thread[0].subject if earlier else mail.subject
        specs.append(
            mail_spec(
                ctx,
                "email",
                f"reply_{ctx.name.lower()}_{reply.available_at:%Y%m%d}.eml",
                subject,
                thread,
                "LATE_ARRIVAL",
                "An outreach reply that arrives after the close.",
                reply.available_at,
                False,
            )
        )
    return specs


def _reply_sender(ctx: Ctx, role: str):
    key = {"PO_OWNER": "po_owner_id", "PROCUREMENT_OWNER": "procurement_owner_id"}.get(
        role, "service_owner_id"
    )
    if role == "VENDOR_BILLING":
        return ctx.contact
    return ctx.cast.owner(ctx.vendor.vendor_id, key)


BUILDERS = {
    "Mintlify": mintlify,
    "OpenAI": openai,
    "ASUS": asus,
    "Meta": meta,
    "Notability": notability,
}
