"""Deterministic Northstar Analytics world built on the four HackMIT sponsor scenarios.

Cast: Mintlify (recurring fixed), OpenAI (recurring variable), ASUS (one-time fixed), Meta
(one-time variable) and Notability (prepaid). Day one is 2026-12-01 with Sep to Nov already
closed, so static data holds the contracts, POs, paid invoices, usage evidence and GL history.
Everything that arrives later is a timed event released by the simulation clock. OpenAI's rate
stepped up 25 percent on 2026-09-01 (0.016 to 0.02); the Oct and Nov accruals were booked at the
stale rate, so history already contains a missed-escalator lesson for the Learning agent.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trueup.simulator import fixtures as fx
from trueup.simulator.scenario_models import (
    APInvoiceRecord,
    ConfigRecord,
    ContractRecord,
    GeneratedWorld,
    GLEntryRecord,
    OutreachResponse,
    PurchaseOrderRecord,
    ScenarioEvent,
    ServiceEvidenceRecord,
    StaticCompanyData,
    VendorRecord,
)
from trueup.simulator.scenario_truth import TruthBook, billed_amount

DEFAULT_SEED = 42
SIM_START = fx.utc(2026, 12, 1, 8, 0)
HISTORICAL = fx.periods("2026-09", "2026-11")
LIVE = fx.periods("2026-12", "2027-01")
ALL_PERIODS = HISTORICAL + LIVE
COMPANY = "Northstar Analytics, Inc."
OPENAI_STALE_RATE = Decimal("0.016")
OPENAI_RATE = Decimal("0.02")

PEOPLE = [
    ("CONTROLLER-001", "Rudraksh Awasthi", "Controller", "rudraksh.awasthi@northstar.example"),
    ("AP-001", "Jordan Patel", "AP Specialist", "jordan.patel@northstar.example"),
    ("PROC-001", "Avery Rivera", "Procurement Manager", "avery.rivera@northstar.example"),
    ("ENG-001", "Riley Kim", "Engineering Service Owner", "riley.kim@northstar.example"),
    ("OPS-001", "Taylor Morgan", "Operations Owner", "taylor.morgan@northstar.example"),
    ("MKT-001", "Priya Nair", "Marketing Owner", "priya.nair@northstar.example"),
]

GL_ACCOUNTS = [
    ("610100", "SaaS Expense", "EXPENSE"),
    ("610200", "Cloud & Data Expense", "EXPENSE"),
    ("610300", "Consulting Expense", "EXPENSE"),
    ("610400", "Office & Supplies Expense", "EXPENSE"),
    ("610500", "Marketing & Travel Expense", "EXPENSE"),
    ("610600", "Depreciation Expense", "EXPENSE"),
    ("150100", "Prepaid Expenses", "ASSET"),
    ("150200", "Fixed Assets - Computer Equipment", "ASSET"),
    ("150290", "Accumulated Depreciation", "CONTRA_ASSET"),
    ("210100", "Accrued Expenses", "LIABILITY"),
    ("210200", "Accrued Card Expenses", "LIABILITY"),
    ("200100", "Accounts Payable", "LIABILITY"),
]

VENDOR_ROWS = [
    ("VEN-MINTLIFY", "Mintlify", "SAAS", "MONTHLY", "billing@mintlify.example"),
    ("VEN-OPENAI", "OpenAI", "AI_CREDITS", "USAGE_BASED", "billing@openai.example"),
    ("VEN-ASUS", "ASUS", "OTHER", "AD_HOC", "orders@asus.example"),
    ("VEN-META", "Meta", "MARKETING", "AD_HOC", "ads-billing@meta.example"),
    ("VEN-NOTABILITY", "Notability", "SAAS", "ANNUAL", "billing@notability.example"),
]

VENDOR_OWNERS = {
    "VEN-MINTLIFY": ("ENG-001", "PROC-001", "ENG-001"),
    "VEN-OPENAI": ("ENG-001", "PROC-001", "ENG-001"),
    "VEN-ASUS": ("OPS-001", "PROC-001", "OPS-001"),
    "VEN-META": ("MKT-001", "PROC-001", "MKT-001"),
    "VEN-NOTABILITY": ("OPS-001", "PROC-001", None),
}

VENDOR_CONTACTS = {
    "VEN-MINTLIFY": ("VC-MINTLIFY-001", "Alex Chen", "Billing contact, Mintlify"),
    "VEN-OPENAI": ("VC-OPENAI-001", "Priya Nair", "Billing contact, OpenAI"),
    "VEN-ASUS": ("VC-ASUS-001", "Dana Cho", "Order desk contact, ASUS"),
    "VEN-META": ("VC-META-001", "Sam Ortiz", "Ads billing contact, Meta"),
    "VEN-NOTABILITY": ("VC-NOTABILITY-001", "Lee Hart", "Billing contact, Notability"),
}

CC_ENG, CC_OPS, CC_MKT = "CC-ENG-100", "CC-OPS-100", "CC-MKT-300"


class _World:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.vendors: list[VendorRecord] = []
        self.contracts: list[ContractRecord] = []
        self.pos: list[PurchaseOrderRecord] = []
        self.evidence: list[ServiceEvidenceRecord] = []
        self.invoices: list[APInvoiceRecord] = []
        self.gl: list[GLEntryRecord] = []
        self.config: list[ConfigRecord] = []
        self.events: list[ScenarioEvent] = []
        self.truth = TruthBook()
        self.outreach: list[OutreachResponse] = []
        self._invoice_numbers: dict[tuple[str, int], int] = {}

    def rng(self, name: str) -> random.Random:
        return random.Random(f"{self.seed}:{name}")

    def po(self, po_id: str) -> PurchaseOrderRecord:
        return next(po for po in self.pos if po.po_id == po_id)

    def insert(self, event_id: str, when: datetime, table: str, record: object) -> None:
        self.events.append(fx.insert_event(event_id, when, table, record))

    def update(
        self, event_id: str, when: datetime, table: str, key: dict[str, str], changes: dict
    ) -> None:
        self.events.append(fx.update_event(event_id, when, table, key, changes))

    def invoice(
        self,
        short: str,
        prefix: str,
        vendor_id: str,
        period: str,
        received: datetime,
        amount: Decimal,
        description: str,
        po_id: str | None = None,
        contract_id: str | None = None,
        service: tuple[date, date] | None = None,
        line_items: list[dict] | None = None,
    ) -> APInvoiceRecord:
        start, end = service or (fx.period_start(period), fx.period_end(period))
        key = (prefix, received.year)
        self._invoice_numbers[key] = self._invoice_numbers.get(key, 0) + 1
        issued = received.date() - timedelta(days=1)
        if issued < end:
            issued = received.date()
        return fx.ap_invoice(
            invoice_id=f"INV-{short}-{period}",
            vendor_id=vendor_id,
            invoice_number=f"{prefix}-{received.year}-{self._invoice_numbers[key]:03d}",
            invoice_date=issued,
            received_at=received,
            service_start_date=start,
            service_end_date=end,
            amount=amount,
            po_id=po_id,
            contract_id=contract_id,
            description=description,
            line_items_json=line_items,
        )

    def history_invoice(
        self, inv: APInvoiceRecord, status: str, settled: datetime
    ) -> APInvoiceRecord:
        inv = inv.model_copy(update={"status": status, "updated_at": settled})
        self.invoices.append(inv)
        return inv

    def ap_entry(self, short: str, inv: APInvoiceRecord, debit: str, posted: datetime) -> None:
        self.gl.append(
            fx.gl_entry(
                f"GL-{short}-{fx.period_of(inv.service_start_date)}",
                posted.date(),
                "AP_INVOICE",
                f"{inv.description} ({inv.invoice_number})",
                debit,
                fx.AP_ACCOUNT,
                inv.amount,
                inv.vendor_id,
                posted,
            )
        )

    def accrual(
        self,
        short: str,
        vendor_id: str,
        name: str,
        period: str,
        amount: Decimal,
        expense: str,
        reversed_at: datetime,
    ) -> None:
        end = fx.period_end(period)
        entry_id = f"GL-{short}-{period}-ACCRUAL"
        booked = fx.gl_entry(
            entry_id,
            end,
            "ACCRUAL",
            f"{name} {end:%B %Y} accrual",
            expense,
            "210100",
            amount,
            vendor_id,
            fx.at(end, 18),
        ).model_copy(update={"status": "REVERSED"})
        reversal = fx.gl_entry(
            f"{entry_id}-REV",
            reversed_at.date(),
            "ACCRUAL_REVERSAL",
            f"Reverse {name} {end:%B %Y} accrual",
            "210100",
            expense,
            amount,
            vendor_id,
            reversed_at,
        ).model_copy(update={"reversal_of_gl_entry_id": entry_id})
        self.gl += [booked, reversal]


def _month_name(period: str) -> str:
    return f"{fx.period_start(period):%B %Y}"


# When the vendor's reply to the variance question, and with it the signed amendment, arrives.
MINTLIFY_AMENDMENT_SENT_AT = fx.utc(2027, 2, 2, 10)


def _mintlify(w: _World, amendment_known: bool = True) -> None:
    fee_v1 = "4.1 Customer shall pay a monthly subscription fee of $1,200 for the Standard "
    fee_v1 += "Workspace plan, invoiced monthly in arrears."
    fee_v2 = "Amendment 1, signed November 18, 2026. 4.2 Commencing December 1, 2026, the "
    fee_v2 += "monthly subscription fee for the Standard Workspace plan shall increase from "
    fee_v2 += "$1,200 to $1,400 per month for the remainder of the term."
    common = dict(
        contract_id="CON-MINTLIFY",
        vendor_id="VEN-MINTLIFY",
        billing_model="FIXED_FEE",
        rate_unit="MONTH",
        billing_frequency="MONTHLY_IN_ARREARS",
        service_owner_id="ENG-001",
        procurement_owner_id="PROC-001",
    )
    original = fx.contract(
        **common,
        contract_version=1,
        contract_name="Mintlify Master Subscription Agreement",
        status="SUPERSEDED",
        effective_start_date=date(2026, 1, 1),
        effective_end_date=date(2026, 11, 30),
        base_rate=fx.money(1200),
        contract_text=fee_v1,
    )
    amended = fx.contract(
        **common,
        contract_version=2,
        contract_name="Mintlify Master Subscription Agreement, Amendment 1",
        status="ACTIVE",
        effective_start_date=date(2026, 12, 1),
        effective_end_date=date(2027, 11, 30),
        base_rate=fx.money(1400),
        contract_text=fee_v2,
    )
    if amendment_known:
        w.contracts += [original, amended]
    else:
        _mintlify_amendment_arrives_late(w, original, amended)
    w.pos.append(
        fx.purchase_order(
            po_id="PO-MINTLIFY-2026",
            po_number="PO-2026-1001",
            vendor_id="VEN-MINTLIFY",
            contract_id="CON-MINTLIFY",
            order_type="FRAMEWORK",
            cost_center=CC_ENG,
            po_owner_id="ENG-001",
            approved_total=fx.money(14400),
            service_start_date=date(2026, 1, 1),
            service_end_date=date(2026, 12, 31),
            gl_account="610100",
            description="Mintlify documentation platform, Standard Workspace plan, 2026",
            line_items_json=[
                fx.po_line(
                    po_line_id="PO-2026-1001-001",
                    item_category="SERVICE",
                    gl_account_code="610100",
                    quantity_ordered=fx.qty(12),
                    unit_price=fx.money(1200),
                    quantity_received=fx.qty(11),
                    quantity_billed=fx.qty(11),
                    line_description="Mintlify Standard Workspace plan, monthly subscription",
                    service_start_date=date(2026, 1, 1),
                    service_end_date=date(2026, 12, 31),
                )
            ],
        )
    )
    invoice_args = dict(vendor_id="VEN-MINTLIFY", po_id="PO-MINTLIFY-2026")
    invoice_args["contract_id"] = "CON-MINTLIFY"
    history = (
        (
            "2026-09",
            fx.utc(2026, 10, 1, 6),
            fx.utc(2026, 10, 2, 9),
            "PAID",
            fx.utc(2026, 10, 15, 10),
        ),
        (
            "2026-10",
            fx.utc(2026, 11, 1, 6),
            fx.utc(2026, 11, 2, 9),
            "PAID",
            fx.utc(2026, 11, 15, 10),
        ),
        (
            "2026-11",
            fx.utc(2026, 12, 1, 6),
            fx.utc(2026, 12, 1, 7, 30),
            "POSTED",
            fx.utc(2026, 12, 1, 7, 30),
        ),
    )
    for period, received, posted, status, settled in history:
        inv = w.invoice(
            "MINTLIFY",
            "MINT",
            period=period,
            received=received,
            amount=fx.money(1200),
            description=f"Mintlify Standard Workspace subscription, {_month_name(period)}",
            **invoice_args,
        )
        w.history_invoice(inv, status, settled)
        w.ap_entry("MINTLIFY", inv, "610100", posted)
    w.accrual(
        "MINTLIFY",
        "VEN-MINTLIFY",
        "Mintlify",
        "2026-11",
        fx.money(1200),
        "610100",
        fx.utc(2026, 12, 1, 6, 30),
    )
    w.truth.add(
        "2026-11",
        "VEN-MINTLIFY",
        "clean_fixed_history",
        "INV-MINTLIFY-2026-11",
        fx.money(1200),
        fx.utc(2026, 12, 1, 6),
        None,
        fx.money(1200),
    )

    received = fx.utc(2027, 1, 3, 9)
    dec = w.invoice(
        "MINTLIFY",
        "MINT",
        period="2026-12",
        received=received,
        amount=fx.money(1400),
        description="Mintlify Standard Workspace subscription, December 2026",
        **invoice_args,
    )
    w.insert("EVT-MINTLIFY-2027-01-INVOICE", received, "company_ap_invoices", dec)
    pending = fx.utc(2027, 1, 4, 9)
    w.update(
        "EVT-MINTLIFY-2027-01-PENDING",
        pending,
        "company_ap_invoices",
        {"invoice_id": dec.invoice_id},
        {"status": "PENDING_APPROVAL", "updated_at": fx.iso(pending)},
    )
    w.truth.add(
        "2026-12",
        "VEN-MINTLIFY",
        "clean_fixed",
        dec.invoice_id,
        dec.amount,
        received,
        None,
        fx.money(1400),
        "DONE",
    )
    if not amendment_known:
        w.outreach.append(
            OutreachResponse(
                outreach_key="MINTLIFY-2026-12-VARIANCE_EXPLANATION",
                available_at=MINTLIFY_AMENDMENT_SENT_AT,
                recipient_role="VENDOR_BILLING",
                response_text=(
                    f"Hi, invoice {dec.invoice_number} is correct. Amendment No. 1 to the Master "
                    "Subscription Agreement, signed on November 18, 2026, raised the Standard "
                    "Workspace fee from 1,200.00 to 1,400.00 per month from December 1, 2026. It "
                    "looks like the signed copy never reached your finance team, so it is attached "
                    "again here. The 1,400.00 stands.\n\nAlex Chen\nBilling, Mintlify"
                ),
                parsed_truth={"resolved": True, "confirmed_amount": "1400.00"},
            )
        )


def _mintlify_amendment_arrives_late(w: _World, original, amended) -> None:
    """The company holds only the original agreement until the vendor sends the amendment.

    December therefore closes on the original fee and January's invoice leaves a difference no
    record explains. The amendment is filed the moment the vendor's reply brings the signed copy,
    which is what lets Reconciliation explain the difference when it looks again.
    """
    on_file = {"status": "ACTIVE", "effective_end_date": amended.effective_end_date}
    w.contracts.append(original.model_copy(update=on_file))
    w.insert(
        "EVT-MINTLIFY-2027-02-AMENDMENT-FILED",
        MINTLIFY_AMENDMENT_SENT_AT,
        "company_contracts",
        amended,
    )
    w.update(
        "EVT-MINTLIFY-2027-02-ORIGINAL-SUPERSEDED",
        MINTLIFY_AMENDMENT_SENT_AT,
        "company_contracts",
        {"contract_row_id": original.contract_row_id},
        {
            "status": original.status,
            "effective_end_date": original.effective_end_date.isoformat(),
        },
    )


def _openai(w: _World) -> None:
    w.contracts.append(
        fx.contract(
            contract_id="CON-OPENAI",
            contract_version=1,
            vendor_id="VEN-OPENAI",
            contract_name="OpenAI API Services Agreement",
            effective_start_date=date(2026, 1, 1),
            effective_end_date=date(2027, 12, 31),
            billing_model="USAGE_BASED",
            base_rate=OPENAI_STALE_RATE,
            rate_unit="API_CALL",
            billing_frequency="VARIABLE",
            escalator_percent=Decimal(25),
            escalator_effective_date=date(2026, 9, 1),
            service_owner_id="ENG-001",
            procurement_owner_id="PROC-001",
            contract_text=(
                "3.1 Usage fees are $0.016 per API call. 3.2 Effective September 1, 2026, "
                "tier pricing increases all usage fees by 25 percent to $0.020 per API call."
            ),
        )
    )
    w.pos.append(
        fx.purchase_order(
            po_id="PO-OPENAI-2026",
            po_number="PO-2026-1002",
            vendor_id="VEN-OPENAI",
            contract_id="CON-OPENAI",
            order_type="BLANKET",
            cost_center=CC_ENG,
            po_owner_id="ENG-001",
            approved_total=fx.money(240000),
            service_start_date=date(2026, 1, 1),
            service_end_date=date(2026, 12, 31),
            gl_account="610200",
            description="OpenAI API usage under annual commitment",
            line_items_json=[
                fx.po_line(
                    po_line_id="PO-2026-1002-001",
                    item_category="BLANKET_LIMIT",
                    gl_account_code="610200",
                    quantity_ordered=None,
                    unit_price=OPENAI_STALE_RATE,
                    line_description="OpenAI API consumption under annual commitment",
                    service_start_date=date(2026, 1, 1),
                    service_end_date=date(2026, 12, 31),
                )
            ],
        )
    )
    rng = w.rng("openai")
    usage = {
        period: 700_000 + 30_000 * i + rng.randint(-3, 3) * 10_000
        for i, period in enumerate(HISTORICAL)
    }
    common = dict(vendor_id="VEN-OPENAI", contract_id="CON-OPENAI", po_id="PO-OPENAI-2026")
    settle = {
        "2026-09": ("PAID", fx.utc(2026, 10, 16, 10)),
        "2026-10": ("PAID", fx.utc(2026, 11, 16, 10)),
    }
    settle["2026-11"] = ("POSTED", fx.utc(2026, 12, 1, 7, 30))
    for period, quantity in usage.items():
        start, end = fx.period_start(period), fx.period_end(period)
        w.evidence.append(
            fx.service_evidence(
                service_evidence_id=f"USE-OPENAI-{period}",
                **common,
                service_start_date=start,
                service_end_date=end,
                evidence_type="SYSTEM_USAGE",
                quantity=fx.qty(quantity),
                unit="API_CALL",
                source_system="ENGINEERING_PLATFORM",
                created_at=fx.at(end, 23),
            )
        )
        received = fx.at(end + timedelta(days=1), 5)
        inv = w.invoice(
            "OPENAI",
            "OA",
            "VEN-OPENAI",
            period,
            received,
            billed_amount(Decimal(quantity), OPENAI_RATE),
            f"OpenAI API usage, {_month_name(period)}",
            po_id="PO-OPENAI-2026",
            contract_id="CON-OPENAI",
        )
        status, settled = settle[period]
        w.history_invoice(inv, status, settled)
        w.ap_entry("OPENAI", inv, "610200", received + timedelta(hours=1, minutes=30))
        if period == "2026-09":
            continue
        stale = billed_amount(Decimal(quantity), OPENAI_STALE_RATE)
        w.accrual(
            "OPENAI",
            "VEN-OPENAI",
            "OpenAI",
            period,
            stale,
            "610200",
            received + timedelta(minutes=30),
        )
        w.truth.add(
            period,
            "VEN-OPENAI",
            "escalator_history",
            inv.invoice_id,
            inv.amount,
            received,
            "MISSED_ESCALATOR",
            stale,
        )

    partial = fx.service_evidence(
        service_evidence_id="USE-OPENAI-2026-12-PARTIAL",
        **common,
        service_start_date=date(2026, 12, 1),
        service_end_date=date(2026, 12, 19),
        evidence_type="SYSTEM_USAGE",
        quantity=fx.qty(576_000),
        unit="API_CALL",
        source_system="ENGINEERING_PLATFORM",
        confirmation_status="PENDING",
        created_at=fx.utc(2026, 12, 28, 18),
    )
    w.insert(
        "EVT-OPENAI-2026-12-USAGE-PARTIAL", partial.created_at, "company_service_evidence", partial
    )
    received = fx.utc(2027, 1, 5, 9)
    dec = w.invoice(
        "OPENAI",
        "OA",
        "VEN-OPENAI",
        "2026-12",
        received,
        billed_amount(Decimal(930_000), OPENAI_RATE),
        "OpenAI API usage, December 2026",
        po_id="PO-OPENAI-2026",
        contract_id="CON-OPENAI",
    )
    w.insert("EVT-OPENAI-2027-01-INVOICE", received, "company_ap_invoices", dec)
    w.truth.add(
        "2026-12",
        "VEN-OPENAI",
        "outreach_required",
        dec.invoice_id,
        dec.amount,
        received,
        "USAGE_VARIANCE",
        billed_amount(Decimal(576_000), OPENAI_RATE),
        "WAITING",
    )
    reply_at = fx.utc(2027, 1, 2, 10)
    w.outreach.append(
        OutreachResponse(
            outreach_key="OPENAI-2026-12-USAGE_CONFIRMATION",
            available_at=reply_at,
            recipient_role="SERVICE_OWNER",
            response_text=(
                "Riley here. The full December export is in: 930,000 API calls for "
                "December 1 through December 31."
            ),
            parsed_truth={
                "resolved": True,
                "service_received": True,
                "quantity": "930000",
                "unit": "API_CALL",
            },
            service_evidence_on_response=fx.service_evidence(
                service_evidence_id="USE-OPENAI-2026-12-CONFIRMED",
                **common,
                service_start_date=date(2026, 12, 1),
                service_end_date=date(2026, 12, 31),
                evidence_type="SYSTEM_USAGE",
                quantity=fx.qty(930_000),
                unit="API_CALL",
                source_system="ENGINEERING_PLATFORM",
                confirmed_by_person_id="ENG-001",
                created_at=reply_at,
            ),
        )
    )


def _asus(w: _World) -> None:
    w.pos.append(
        fx.purchase_order(
            po_id="PO-ASUS-2026",
            po_number="PO-2026-1003",
            vendor_id="VEN-ASUS",
            contract_id=None,
            service_start_date=None,
            service_end_date=None,
            order_type="STANDARD",
            cost_center=CC_OPS,
            po_owner_id="OPS-001",
            approved_total=fx.money(40000),
            gl_account="150200",
            description="25 laptops for new engineers",
            line_items_json=[
                fx.po_line(
                    po_line_id="PO-2026-1003-001",
                    item_category="MATERIAL",
                    gl_account_code="150200",
                    quantity_ordered=fx.qty(25),
                    unit_price=fx.money(1600),
                    line_description="ASUS ExpertBook laptop, 16 GB, 512 GB",
                    receipt_required=True,
                    useful_life_months=36,
                )
            ],
        )
    )
    key = {"po_id": "PO-ASUS-2026"}
    line = w.po("PO-ASUS-2026").line_items_json[0]
    quantities = {"received": 0, "billed": 0}

    def sync_po(event_id: str, when: datetime, **changes: int) -> None:
        quantities.update(changes)
        updated = line.model_copy(
            update={
                "quantity_received": fx.qty(quantities["received"]),
                "quantity_billed": fx.qty(quantities["billed"]),
            }
        )
        w.update(
            event_id,
            when,
            "company_purchase_orders",
            key,
            {"line_items_json": [updated.model_dump(mode="json")]},
        )

    def receipt(event_id: str, when: datetime, day: date, units: int) -> None:
        record = fx.service_evidence(
            service_evidence_id=f"USE-ASUS-{fx.period_of(day)}-{day.day:02d}",
            vendor_id="VEN-ASUS",
            po_id="PO-ASUS-2026",
            service_start_date=day,
            service_end_date=day,
            evidence_type="GOODS_RECEIPT",
            quantity=fx.qty(units),
            unit="EACH",
            accepted_amount=fx.money(units * 1600),
            source_system="WAREHOUSE",
            confirmed_by_person_id="OPS-001",
            confirmation_status="OWNER_CONFIRMED",
            created_at=when,
        )
        w.insert(event_id, when, "company_service_evidence", record)
        sync_po(
            f"{event_id}-PO", when + timedelta(minutes=5), received=quantities["received"] + units
        )

    receipt("EVT-ASUS-2026-12-RECEIPT", fx.utc(2026, 12, 18, 14), date(2026, 12, 18), 20)
    invoice_at = fx.utc(2027, 1, 8, 9)
    inv = w.invoice(
        "ASUS",
        "ASUS",
        "VEN-ASUS",
        "2026-12",
        invoice_at,
        fx.money(32000),
        "20 ASUS ExpertBook laptops delivered December 18, 2026",
        po_id="PO-ASUS-2026",
        service=(date(2026, 12, 18), date(2026, 12, 18)),
        line_items=[
            {
                "description": "ASUS ExpertBook laptop",
                "quantity": "20",
                "unit_price": "1600.00",
            }
        ],
    )
    w.insert("EVT-ASUS-2027-01-INVOICE", invoice_at, "company_ap_invoices", inv)
    sync_po("EVT-ASUS-2027-01-INVOICE-PO", invoice_at + timedelta(minutes=5), billed=20)
    receipt("EVT-ASUS-2027-01-RECEIPT", fx.utc(2027, 1, 14, 10), date(2027, 1, 14), 5)
    w.truth.add(
        "2026-12",
        "VEN-ASUS",
        "receipt_based_partial",
        inv.invoice_id,
        inv.amount,
        invoice_at,
        None,
        fx.money(32000),
        "NEEDS_REVIEW",
    )
    reply_at = fx.utc(2027, 1, 4, 10)
    w.outreach.append(
        OutreachResponse(
            outreach_key="ASUS-2026-12-IN_SERVICE_DATE",
            available_at=reply_at,
            recipient_role="SERVICE_OWNER",
            response_text=(
                "The laptops went out to the new engineers over the holidays. "
                "I do not have the exact in-service dates yet."
            ),
            parsed_truth={"resolved": False, "reason": "INSUFFICIENT_RESPONSE"},
        )
    )


def _meta(w: _World) -> None:
    w.pos.append(
        fx.purchase_order(
            po_id="PO-META-2026",
            po_number="PO-2026-1004",
            vendor_id="VEN-META",
            contract_id=None,
            order_type="PROJECT",
            cost_center=CC_MKT,
            po_owner_id="MKT-001",
            approved_total=fx.money(30000),
            service_start_date=date(2026, 12, 1),
            service_end_date=date(2026, 12, 31),
            gl_account="610500",
            description="Product launch advertising campaign, not to exceed $30,000",
            line_items_json=[
                fx.po_line(
                    po_line_id="PO-2026-1004-001",
                    item_category="BLANKET_LIMIT",
                    gl_account_code="610500",
                    quantity_ordered=fx.qty(1),
                    unit_price=fx.money(30000),
                    line_description="Meta ads for the product-launch campaign, billed on delivery",
                    service_start_date=date(2026, 12, 1),
                    service_end_date=date(2026, 12, 31),
                    receipt_required=True,
                )
            ],
        )
    )
    delivered_at = fx.utc(2026, 12, 30, 17)
    report = fx.service_evidence(
        service_evidence_id="USE-META-2026-12",
        vendor_id="VEN-META",
        po_id="PO-META-2026",
        service_start_date=date(2026, 12, 1),
        service_end_date=date(2026, 12, 31),
        evidence_type="MILESTONE_ACCEPTANCE",
        quantity=None,
        unit=None,
        accepted_amount=fx.money(24700),
        source_system="PROJECT_MANAGEMENT",
        confirmed_by_person_id="MKT-001",
        confirmation_status="OWNER_CONFIRMED",
        created_at=delivered_at,
    )
    w.insert("EVT-META-2026-12-DELIVERY", delivered_at, "company_service_evidence", report)
    received = fx.utc(2027, 1, 7, 9)
    inv = w.invoice(
        "META",
        "META",
        "VEN-META",
        "2026-12",
        received,
        fx.money(30000),
        "Product launch campaign, total campaign budget",
        po_id="PO-META-2026",
    )
    w.insert("EVT-META-2027-01-INVOICE", received, "company_ap_invoices", inv)
    review = fx.utc(2027, 1, 8, 9)
    w.update(
        "EVT-META-2027-01-REVIEW",
        review,
        "company_ap_invoices",
        {"invoice_id": inv.invoice_id},
        {"status": "PENDING_REVIEW", "updated_at": fx.iso(review)},
    )
    w.truth.add(
        "2026-12",
        "VEN-META",
        "wrong_invoice_amount",
        inv.invoice_id,
        inv.amount,
        received,
        "SOURCE_DATA_ERROR",
        fx.money(24700),
        "DONE",
    )
    # The vendor's side of the dispute the Controller raises after the wrong invoice is flagged.
    # It is dated after the January demo close, so it can only follow a request sent by then.
    reply_at = fx.utc(2027, 2, 2, 10)
    corrected_at = fx.utc(2027, 2, 3, 9)
    corrected = w.invoice(
        "META-CORR",
        "META",
        "VEN-META",
        "2026-12",
        corrected_at,
        fx.money(24700),
        "Corrected invoice replacing META-2027-001, billed at the delivered and accepted amount",
        po_id="PO-META-2026",
    )
    w.outreach.append(
        OutreachResponse(
            outreach_key="META-2026-12-INVOICE_DISPUTE",
            available_at=reply_at,
            recipient_role="VENDOR_BILLING",
            response_text=(
                "Hi, thanks for raising this. You are right: the campaign delivery report supports "
                "24,700.00, and the 30,000.00 on invoice META-2027-001 was the campaign budget, "
                "not what ran. We are voiding that invoice and will issue a corrected invoice for "
                "24,700.00 tomorrow.\n\nSam Ortiz\nAds Billing, Meta"
            ),
            parsed_truth={"resolved": True, "corrected_amount": "24700.00"},
        )
    )
    w.insert("EVT-META-2027-02-INVOICE-CORRECTED", corrected_at, "company_ap_invoices", corrected)
    voided_at = corrected_at + timedelta(minutes=5)
    w.update(
        "EVT-META-2027-02-INVOICE-VOIDED",
        voided_at,
        "company_ap_invoices",
        {"invoice_id": inv.invoice_id},
        {"status": "VOIDED", "updated_at": fx.iso(voided_at)},
    )


def _notability(w: _World) -> None:
    w.contracts.append(
        fx.contract(
            contract_id="CON-NOTABILITY",
            contract_version=1,
            vendor_id="VEN-NOTABILITY",
            contract_name="Notability Team Subscription",
            effective_start_date=date(2026, 12, 1),
            effective_end_date=date(2027, 11, 30),
            billing_model="FIXED_FEE",
            base_rate=fx.money(1800),
            rate_unit="MONTH",
            billing_frequency="ANNUAL",
            service_owner_id="OPS-001",
            procurement_owner_id="PROC-001",
            contract_text=(
                "Team plan, 12 months, $21,600 billed annually in advance. "
                "Service term December 1, 2026 through November 30, 2027."
            ),
        )
    )
    received = fx.utc(2026, 11, 24, 10)
    inv = w.invoice(
        "NOTABILITY",
        "NOTE",
        "VEN-NOTABILITY",
        "2026-12",
        received,
        fx.money(21600),
        "Notability team subscription, December 2026 to November 2027",
        contract_id="CON-NOTABILITY",
        service=(date(2026, 12, 1), date(2027, 11, 30)),
    )
    w.history_invoice(inv, "PAID", fx.utc(2026, 11, 28, 10))
    w.gl.append(
        fx.gl_entry(
            "GL-NOTABILITY-2026-12",
            date(2026, 11, 25),
            "AP_INVOICE",
            f"Notability annual subscription prepaid ({inv.invoice_number})",
            "150100",
            fx.AP_ACCOUNT,
            inv.amount,
            "VEN-NOTABILITY",
            fx.utc(2026, 11, 25, 9),
        )
    )
    w.gl.append(
        fx.gl_entry(
            "GL-NOTABILITY-2026-12-MANUAL",
            date(2026, 12, 1),
            "MANUAL_ADJUSTMENT",
            "Expense Notability annual subscription in full",
            "610100",
            "150100",
            inv.amount,
            "VEN-NOTABILITY",
            fx.utc(2026, 12, 1, 7),
        )
    )
    w.truth.add(
        "2026-12",
        "VEN-NOTABILITY",
        "prepaid_wrong_treatment",
        inv.invoice_id,
        inv.amount,
        received,
        None,
        fx.money(1800),
        "BLOCKED",
    )


def _config(w: _World) -> None:
    periods = {
        period: {
            "status": "CLOSED" if period in HISTORICAL else "OPEN",
            "phase": "HISTORICAL" if period in HISTORICAL else "LIVE",
            "period_start": fx.period_start(period).isoformat(),
            "period_end": fx.period_end(period).isoformat(),
            "close_cutoff": fx.iso(fx.close_cutoff(period)),
        }
        for period in ALL_PERIODS
    }
    values: dict[str, object] = {
        "people": [
            {"person_id": pid, "name": name, "role": role, "email": email}
            for pid, name, role, email in PEOPLE
        ],
        "ownership_map": {
            "controller": "CONTROLLER-001",
            "default_ap_owner": "AP-001",
            "vendors": {
                vid: {"service_owner_id": s, "procurement_owner_id": p, "po_owner_id": o}
                for vid, (s, p, o) in VENDOR_OWNERS.items()
            },
        },
        "vendor_contacts": {
            vendor_id: {
                "person_id": person_id,
                "name": name,
                "role": role,
                "email": next(row[4] for row in VENDOR_ROWS if row[0] == vendor_id),
            }
            for vendor_id, (person_id, name, role) in VENDOR_CONTACTS.items()
        },
        "accounting_periods": periods,
        "approval_thresholds": {
            "controller_review_above_usd": "25000",
            "mandatory_review_above_usd": "100000",
            "de_minimis_threshold_usd": "5000",
        },
        "policy_rules": [
            {"rule_id": "POL-01", "text": "Never auto-post a case that requires Controller review"},
            {"rule_id": "POL-02", "text": "Never accrue when a matching AP invoice exists"},
            {
                "rule_id": "POL-03",
                "text": "Require evidence of service receipt for receipt or usage-based spend",
            },
            {"rule_id": "POL-04", "text": "Require an open accounting period"},
            {"rule_id": "POL-05", "text": "Require a balanced journal entry"},
            {
                "rule_id": "POL-06",
                "text": "Require an active contract or PO, or an approved fallback",
            },
            {
                "rule_id": "POL-07",
                "text": "Capitalize equipment over the threshold and depreciate it over its life",
            },
            {
                "rule_id": "POL-08",
                "text": "Record prepaid services as an asset and expense them over the term",
            },
        ],
        "allowed_gl_accounts": [
            {"account_code": code, "name": name, "type": kind} for code, name, kind in GL_ACCOUNTS
        ],
        "capitalization_policy": {"threshold_usd": "5000", "useful_life_months": 36},
        "simulation_clock": {"current_time": fx.iso(SIM_START)},
        "company_profile": {
            "name": COMPANY,
            "currency": "USD",
            "close_cycle": "CALENDAR_MONTH",
            "entities": ["ENT-001"],
            "accounting_basis": "ACCRUAL",
        },
    }
    w.config = [
        ConfigRecord(config_key=key, config_value_json=value, updated_at=SIM_START)
        for key, value in values.items()
    ]


def generate(seed: int = DEFAULT_SEED, *, mintlify_amendment_known: bool = True) -> GeneratedWorld:
    """The five-vendor world. `mintlify_amendment_known=False` is the late-amendment variant:
    Mintlify's price rise is not on file at close, so January's invoice leaves $200 unexplained."""
    w = _World(seed)
    w.vendors = [fx.vendor(*row) for row in VENDOR_ROWS]
    _mintlify(w, mintlify_amendment_known)
    _openai(w)
    _asus(w)
    _meta(w)
    _notability(w)
    _config(w)
    events = sorted(w.events, key=lambda e: (e.available_at, e.event_id))
    truth = sorted(w.truth.entries, key=lambda t: (t.invoice_arrival_time, t.vendor_id, t.scenario))
    outreach = sorted(w.outreach, key=lambda o: (o.available_at, o.outreach_key))
    static = StaticCompanyData(
        meta={
            "generator": "trueup.simulator",
            "seed": seed,
            "company": COMPANY,
            "currency": "USD",
            "simulation_start": fx.iso(SIM_START),
            "historical_periods": HISTORICAL,
            "live_periods": LIVE,
        },
        company_vendors=w.vendors,
        company_contracts=w.contracts,
        company_purchase_orders=w.pos,
        company_service_evidence=w.evidence,
        company_non_po_spend=[],
        company_ap_invoices=w.invoices,
        company_gl_entries=w.gl,
        company_config=w.config,
    )
    return GeneratedWorld(static=static, events=events, truth=truth, outreach=outreach)


def _event_json(event: ScenarioEvent) -> dict:
    payload = event.model_dump(mode="json")
    if payload["key"] is None:
        del payload["key"]
    return payload


def render_files(world: GeneratedWorld) -> dict[str, str]:
    def dump(payload: object) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=True) + "\n"

    return {
        "static_company_data.json": dump(world.static.model_dump(mode="json")),
        "scenario_events.json": dump([_event_json(e) for e in world.events]),
        "historical_truth.json": dump(
            {"expected_outcomes": [t.model_dump(mode="json") for t in world.truth]}
        ),
        "outreach_responses.json": dump([o.model_dump(mode="json") for o in world.outreach]),
    }


def write_files(world: GeneratedWorld, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in render_files(world).items():
        path = out / name
        path.write_text(text)
        written.append(path)
    return written
