"""Context and builders shared by every vendor case."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trueup.simulator.files import previews
from trueup.simulator.files.doc import (
    Chat,
    ChatLine,
    Doc,
    Heading,
    KeyValues,
    Mail,
    Para,
    Sheet,
    Table,
)
from trueup.simulator.files.text import long_date, usd2
from trueup.simulator.files.world_view import WorldView
from trueup.simulator.scenario_models import APInvoiceRecord, GeneratedWorld, VendorRecord

CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
DAY_ONE = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)

VENDOR_FACTS = {
    "Mintlify": (
        "Mintlify, Inc.",
        "100 Example Way, Suite 4, San Francisco, CA 94100",
        "Alex Chen",
    ),
    "OpenAI": ("OpenAI Services LLC", "200 Sample Street, San Francisco, CA 94101", "Priya Nair"),
    "ASUS": ("ASUS Computer Distribution Inc.", "300 Demo Avenue, Fremont, CA 94538", "Dana Cho"),
    "Meta": ("Meta Ads Billing Ltd.", "400 Placeholder Road, Menlo Park, CA 94025", "Sam Ortiz"),
    "Notability": ("Notability Teams Inc.", "500 Fictional Lane, Austin, TX 78701", "Lee Hart"),
}


@dataclass
class Spec:
    kind: str
    fmt: str
    filename: str
    title: str
    subtitle: str
    content: object
    preview: dict
    role: str
    reason: str
    available_at: datetime
    universe: bool = True


class Cast:
    def __init__(self, view: WorldView) -> None:
        self.people = {p["person_id"]: p for p in view.config("people")}
        self.ownership = view.config("ownership_map")["vendors"]
        self.customer = view.config("company_profile")["name"]

    def person(self, person_id: str, fallback: str = "ENG-001") -> dict[str, str]:
        return self.people.get(person_id) or self.people[fallback]

    def owner(self, vendor_id: str, role: str = "service_owner_id") -> dict[str, str]:
        return self.person(self.ownership.get(vendor_id, {}).get(role, "ENG-001"))


@dataclass
class Ctx:
    world: GeneratedWorld
    view: WorldView
    cast: Cast
    rng: random.Random
    vendor: VendorRecord

    @property
    def name(self) -> str:
        return self.vendor.vendor_name

    @property
    def legal(self) -> str:
        return VENDOR_FACTS[self.name][0]

    @property
    def contact(self) -> tuple[str, str]:
        person = VENDOR_FACTS[self.name][2]
        domain = self.name.lower() + ".example"
        return person, f"{person.split()[0].lower()}@{domain}"


def addr(person: dict[str, str] | tuple[str, str]) -> str:
    if isinstance(person, tuple):
        return f"{person[0]} <{person[1]}>"
    return f"{person['name']} <{person['email']}>"


def at(month: int, day: int, hour: int = 9, minute: int = 0, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def make_spec(
    kind: str,
    fmt: str,
    filename: str,
    title: str,
    subtitle: str,
    content: object,
    preview: dict,
    role: str,
    reason: str,
    available_at: datetime = DAY_ONE,
    universe: bool = True,
) -> Spec:
    return Spec(
        kind, fmt, filename, title, subtitle, content, preview, role, reason, available_at, universe
    )


def vendor_master_spec(ctx: Ctx) -> Spec:
    legal, address, _ = VENDOR_FACTS[ctx.name]
    rows = (
        ("Vendor ID", ctx.vendor.vendor_id),
        ("Legal name", legal),
        ("Entity type", "Corporation"),
        ("Status", "Active" if ctx.vendor.is_active else "Inactive"),
        ("Pay terms", "Net 30"),
        ("Address", address),
        ("Billing contact", ctx.vendor.billing_contact_email or "not on file"),
        ("Tax ID", "XX-XXX7890"),
    )
    doc = Doc("Vendor Master", "Vendor record", (KeyValues(rows),))
    return make_spec(
        "vendor",
        "PDF",
        f"vendor_master_{ctx.name.lower()}.pdf",
        "Vendor Master",
        "Vendor record",
        doc,
        previews.record("Vendor Master", "VENDOR RECORD", list(rows[:6])),
        "NOISE",
        "Static vendor identity and payment terms carry no amount or period evidence.",
    )


def gl_export_spec(ctx: Ctx, note: str, limit: int = 48) -> Spec:
    names = {v.vendor_id: v.vendor_name for v in ctx.view.vendors()}
    rows: list[tuple[object, ...]] = []
    for entry in ctx.view.gl_entries():
        if entry.posting_date < date(2026, 9, 1):
            continue
        for line in entry.lines_json:
            amount = line.debit if line.debit else line.credit
            side = "Dr" if line.debit else "Cr"
            rows.append(
                (
                    entry.posting_date.isoformat(),
                    entry.gl_entry_id,
                    names.get(entry.vendor_id or "", "n/a"),
                    f"{entry.description} ({line.account_code} {side})",
                    amount,
                )
            )
    rows = rows[-limit:]
    sheet = Sheet("General ledger", ("Date", "JE", "Vendor", "Description", "Amount"), tuple(rows))
    preview_rows = [[str(r[0]), str(r[1]), usd2(r[4])] for r in rows]  # type: ignore[arg-type]
    return make_spec(
        "gl",
        "XLSX",
        "general_ledger_export_dec.xlsx",
        "General Ledger",
        "Account Activity",
        sheet,
        previews.table(
            "General Ledger",
            "Account Activity",
            ["DATE", "JE / DESCRIPTION", "AMOUNT"],
            preview_rows,
        ),
        "HARD_NEGATIVE",
        note,
    )


def ap_history_spec(ctx: Ctx, role: str, reason: str) -> Spec:
    invoices = [
        i for i in ctx.view.invoices(ctx.vendor.vendor_id) if i.invoice_date <= CLOSE.date()
    ]
    rows = tuple(
        (i.invoice_date.isoformat(), i.invoice_number, i.description, i.amount, i.status)
        for i in invoices
    )
    sheet = Sheet("AP history", ("Date", "Invoice #", "Description", "Amount", "Status"), rows)
    preview_rows = [[r[0], r[2], usd2(r[3])] for r in rows[::-1]]
    return make_spec(
        "ap",
        "XLSX",
        f"ap_history_{ctx.name.lower()}.xlsx",
        "Accounts Payable",
        "Vendor History",
        sheet,
        previews.table(
            "Accounts Payable", "Vendor History", ["DATE", "DESCRIPTION", "AMOUNT"], preview_rows
        ),
        role,
        reason,
    )


def invoice_doc(ctx: Ctx, inv: APInvoiceRecord) -> Doc:
    span = "n/a"
    if inv.service_start_date and inv.service_end_date:
        span = f"{long_date(inv.service_start_date)} to {long_date(inv.service_end_date)}"
    rows = [
        ("Invoice #", inv.invoice_number),
        ("Invoice date", long_date(inv.invoice_date)),
        ("Due date", long_date(inv.invoice_date + timedelta(days=30))),
        ("Bill to", ctx.cast.customer),
        ("PO reference", inv.po_id or "none"),
        ("Service period", span),
    ]
    return Doc(
        f"Invoice {inv.invoice_number}",
        ctx.legal,
        (
            KeyValues(tuple(rows)),
            Table(("Description", "Amount"), ((inv.description, usd2(inv.amount)),)),
            Para(f"Total due: {usd2(inv.amount)}"),
        ),
    )


def invoice_spec(
    ctx: Ctx,
    inv: APInvoiceRecord,
    role: str,
    reason: str,
    available_at: datetime | None = None,
    universe: bool = True,
) -> Spec:
    doc = invoice_doc(ctx, inv)
    rows = [
        ("Invoice #", inv.invoice_number),
        ("Date", inv.invoice_date.strftime("%m/%d/%Y")),
        ("Due date", (inv.invoice_date + timedelta(days=30)).strftime("%m/%d/%Y")),
    ]
    return make_spec(
        "invoice",
        "PDF",
        f"invoice_{inv.invoice_number.lower().replace(' ', '_')}.pdf",
        f"Invoice {inv.invoice_number}",
        ctx.legal,
        doc,
        previews.skeleton(
            f"Invoice {inv.invoice_number}", ctx.legal, rows, ("Total", usd2(inv.amount))
        ),
        role,
        reason,
        available_at or DAY_ONE,
        universe,
    )


def slack_spec(
    ctx: Ctx,
    channel: str,
    lines: list[tuple[str, int, int, int, str]],
    role: str,
    reason: str,
) -> Spec:
    """Each line is (sender, month, day, hour, text)."""
    chat_lines = tuple(ChatLine(s, at(m, d, h), t) for s, m, d, h, t in lines)
    chat = Chat(channel, chat_lines)
    return make_spec(
        "slack",
        "TXT",
        f"slack_export_{channel.strip('#').replace('-', '_')}.txt",
        "Slack export",
        channel,
        chat,
        previews.chat("Slack export", channel, chat_lines),
        role,
        reason,
    )


def mail_spec(
    ctx: Ctx,
    kind: str,
    filename: str,
    subject: str,
    thread: tuple[Mail, ...],
    role: str,
    reason: str,
    available_at: datetime = DAY_ONE,
    universe: bool = True,
) -> Spec:
    from trueup.simulator.files.doc import Thread

    return make_spec(
        kind,
        "EML",
        filename,
        subject,
        ctx.name,
        Thread(thread),
        previews.email(subject, ctx.name, thread[-1]),
        role,
        reason,
        available_at,
        universe,
    )


def memo_doc(
    title: str,
    fields: tuple[tuple[str, str], ...],
    paragraphs: list[str],
    table: Table | None = None,
) -> Doc:
    blocks: list = [KeyValues(fields)]
    blocks += [Para(p) for p in paragraphs]
    if table is not None:
        blocks.append(table)
    return Doc(title, "Memo", tuple(blocks))


def heading_para(heading: str, text: str) -> tuple[Heading, Para]:
    return Heading(heading), Para(text)


def latest_invoice(ctx: Ctx) -> APInvoiceRecord:
    invoices = [
        i for i in ctx.view.invoices(ctx.vendor.vendor_id) if i.invoice_date <= CLOSE.date()
    ]
    if not invoices:
        raise ValueError(f"{ctx.name}: the world has no invoices before the close")
    return invoices[-1]


def money_sum(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0"))
