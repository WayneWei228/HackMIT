"""Deterministic simulator for the demo company: PO database, contracts, card
statements, and a hidden future of invoices that arrive with lag.

`generate(engine, seed)` rebuilds the source tables. `release_invoices(engine, period)`
advances the simulated clock by moving invoices that arrive in `period` from the hidden
`future_invoices` table into AP and returning them, so the caller can trigger learning.
The simulator owns the answer key; agents must never read `future_invoices`.

Vendors are the four fee patterns from the demo brief. Amounts are fictional.
"""

from __future__ import annotations

import random

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from trueup.db import (
    APInvoice,
    CardStatement,
    Contract,
    FutureInvoice,
    POHeader,
    POLine,
    Vendor,
    get_session,
    init_db,
)

YEAR = 2026
PERIODS = [f"{YEAR}-{m:02d}" for m in range(1, 13)]


def _next_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:])
    return f"{year + (month == 12)}-{(month % 12) + 1:02d}"


def _future(session: Session, vendor: str, po: str, period: str, cents: int, cause=None) -> None:
    arrived = _next_period(period)
    session.add(
        FutureInvoice(
            vendor_id=vendor,
            po_number=po,
            invoice_number=f"{vendor}-{period}",
            invoice_date=f"{arrived}-03",
            service_period=period,
            amount_cents=cents,
            arrived_period=arrived,
            planted_cause=cause,
        )
    )


def generate(engine: Engine, seed: int = 42) -> None:
    rng = random.Random(seed)
    init_db(engine)
    with get_session(engine) as session:
        for name, vid in [
            ("Mintlify", "V-MINT"),
            ("OpenAI", "V-OAI"),
            ("ASUS", "V-ASUS"),
            ("Meta", "V-META"),
        ]:
            session.add(Vendor(vendor_id=vid, name=name))

        # Recurring fixed: Mintlify. Contract price rose to $1,400 on 2026-07-01, PO is stale.
        session.add_all(
            [
                Contract(
                    contract_id="CON-1001-V1",
                    vendor_id="V-MINT",
                    monthly_rate_cents=120_000,
                    effective_start="2026-01-01",
                    effective_end="2026-06-30",
                    status="Superseded",
                    version=1,
                ),
                Contract(
                    contract_id="CON-1001-V2",
                    vendor_id="V-MINT",
                    monthly_rate_cents=140_000,
                    effective_start="2026-07-01",
                    effective_end="2026-12-31",
                    status="Active",
                    version=2,
                ),
            ]
        )
        session.add(
            POHeader(
                po_number="PO-2026-1001",
                vendor_id="V-MINT",
                order_type="FO",
                created_date="2026-01-02",
                status="Open",
                total_amount_cents=1_560_000,
            )
        )
        session.add(
            POLine(
                po_line_id="PO-2026-1001-001",
                po_number="PO-2026-1001",
                item_category="P",
                gl_account_code="610200",
                quantity_ordered=1,
                unit_price_cents=120_000,
                quantity_received=None,
                quantity_billed=None,
                line_description="Mintlify documentation site, monthly subscription",
                valid_from="2026-01-01",
                valid_to="2026-12-31",
                contract_id="CON-1001-V1",
            )
        )
        for period in PERIODS:
            cents = 120_000 if period < "2026-07" else 140_000
            cause = "price_change" if period == "2026-07" else None
            _future(session, "V-MINT", "PO-2026-1001", period, cents, cause)

        # Recurring variable: OpenAI blanket order, usage grows about 4 percent a month.
        session.add(
            POHeader(
                po_number="PO-2026-1002",
                vendor_id="V-OAI",
                order_type="FO",
                created_date="2026-01-02",
                status="Open",
                total_amount_cents=30_000_000,
            )
        )
        session.add(
            POLine(
                po_line_id="PO-2026-1002-001",
                po_number="PO-2026-1002",
                item_category="B",
                gl_account_code="610300",
                quantity_ordered=None,
                unit_price_cents=3_000_000,
                quantity_received=None,
                quantity_billed=None,
                line_description="OpenAI API usage, billed monthly on consumption",
                valid_from="2026-01-01",
                valid_to="2026-12-31",
                contract_id=None,
            )
        )
        usage = 1_500_000
        for period in PERIODS:
            usage = int(usage * (1.04 + rng.uniform(-0.01, 0.02)))
            _future(session, "V-OAI", "PO-2026-1002", period, usage)

        # One-time fixed: ASUS, 25 ordered, 20 received.
        session.add(
            POHeader(
                po_number="PO-2026-1003",
                vendor_id="V-ASUS",
                order_type="NB",
                created_date="2026-11-10",
                status="Open",
                total_amount_cents=4_000_000,
            )
        )
        session.add(
            POLine(
                po_line_id="PO-2026-1003-001",
                po_number="PO-2026-1003",
                item_category="",
                gl_account_code="150100",
                quantity_ordered=25,
                unit_price_cents=160_000,
                quantity_received=20,
                quantity_billed=0,
                line_description="25 ASUS laptops for new engineers",
                contract_id=None,
            )
        )

        # One-time variable: Meta campaign, $30,000 budget, $24,700 delivered.
        session.add(
            POHeader(
                po_number="PO-2026-1004",
                vendor_id="V-META",
                order_type="NB",
                created_date="2026-11-01",
                status="Open",
                total_amount_cents=3_000_000,
            )
        )
        session.add(
            POLine(
                po_line_id="PO-2026-1004-001",
                po_number="PO-2026-1004",
                item_category="B",
                gl_account_code="620100",
                quantity_ordered=30_000,
                unit_price_cents=100,
                quantity_received=24_700,
                quantity_billed=0,
                line_description="Meta ads for the product launch campaign, billed on delivery",
                valid_from="2026-11-01",
                valid_to="2026-11-30",
                contract_id=None,
            )
        )

        # Non-PO card spend, accrued directly.
        for period in PERIODS:
            session.add(
                CardStatement(
                    issuer="Ramp",
                    period=period,
                    settled_cents=rng.randint(800_000, 1_100_000),
                    pending_cents=rng.randint(50_000, 150_000),
                )
            )


def release_invoices(engine: Engine, period: str) -> list[int]:
    """Advance the clock: invoices arriving in `period` land in AP. Returns new AP ids."""
    ids: list[int] = []
    with get_session(engine) as session:
        rows = session.query(FutureInvoice).filter(FutureInvoice.arrived_period == period).all()
        for row in rows:
            invoice = APInvoice(
                vendor_id=row.vendor_id,
                po_number=row.po_number,
                invoice_number=row.invoice_number,
                invoice_date=row.invoice_date,
                service_period=row.service_period,
                amount_cents=row.amount_cents,
                arrived_period=row.arrived_period,
            )
            session.add(invoice)
            session.flush()
            ids.append(invoice.id)
    return ids
