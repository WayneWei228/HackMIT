"""Database engine, session helpers, and ORM tables for the simulated finance systems.

The source tables mirror the systems the agents read (ERP AP, e-procurement PO
database, contract management, card issuer). The output tables hold what the
agents decide (close items, estimates, outreach, learning) plus the audit log.

All money is stored as integer cents. Never compare or sum floats.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DEFAULT_DB_PATH = "trueup.db"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# --- Source systems (simulated) -------------------------------------------------


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(30), unique=True)  # master vendor key
    name: Mapped[str] = mapped_column(String(120))


class Contract(Base):
    """Contract management platform. One row per contract version."""

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(30), index=True)  # e.g. CON-8821-V2
    vendor_id: Mapped[str] = mapped_column(String(30), index=True)
    monthly_rate_cents: Mapped[int]
    effective_start: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    effective_end: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))  # Active, Superseded
    version: Mapped[int]


class POHeader(Base):
    """E-procurement platform, table A: one row per order."""

    __tablename__ = "po_headers"

    po_number: Mapped[str] = mapped_column(String(30), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(30), index=True)
    order_type: Mapped[str] = mapped_column(String(4))  # NB standard, FO framework/blanket
    created_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))  # Approved, Open, Fully_Billed, Closed
    total_amount_cents: Mapped[int]


class POLine(Base):
    """E-procurement platform, table B: one or many rows per order."""

    __tablename__ = "po_lines"

    po_line_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    po_number: Mapped[str] = mapped_column(ForeignKey("po_headers.po_number"), index=True)
    item_category: Mapped[str] = mapped_column(String(4))  # P service, B limit, E enhanced, "" std
    gl_account_code: Mapped[str] = mapped_column(String(20))
    quantity_ordered: Mapped[float | None] = mapped_column(Numeric(14, 3, asdecimal=False))
    unit_price_cents: Mapped[int]  # monthly cap or rate for recurring lines
    quantity_received: Mapped[float | None] = mapped_column(Numeric(14, 3, asdecimal=False))
    quantity_billed: Mapped[float | None] = mapped_column(Numeric(14, 3, asdecimal=False))
    line_description: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[str | None] = mapped_column(String(10), default=None)
    valid_to: Mapped[str | None] = mapped_column(String(10), default=None)
    contract_id: Mapped[str | None] = mapped_column(String(30), default=None)


class APInvoice(Base):
    """ERP accounts payable. Invoices that have arrived."""

    __tablename__ = "ap_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(30), index=True)
    po_number: Mapped[str | None] = mapped_column(String(30), default=None, index=True)
    invoice_number: Mapped[str] = mapped_column(String(60))
    invoice_date: Mapped[str] = mapped_column(String(10))
    service_period: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM the bill covers
    amount_cents: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, paid, void
    arrived_period: Mapped[str] = mapped_column(String(7), index=True)  # month it landed in AP


class CardStatement(Base):
    """Corporate card issuer (Ramp, Brex, Amex). Non-PO spend, accrued directly."""

    __tablename__ = "card_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    issuer: Mapped[str] = mapped_column(String(40))
    period: Mapped[str] = mapped_column(String(7), index=True)
    settled_cents: Mapped[int]
    pending_cents: Mapped[int]


class DocumentRecord(Base):
    """A source document (PDF or text) and the fields the Evidence agent extracted from it.

    `text_sha256` is the extraction cache key: unchanged text is never re-sent to the model.
    """

    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    text_sha256: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str | None] = mapped_column(String(300), default=None)
    document_type: Mapped[str] = mapped_column(String(30))
    vendor_name: Mapped[str | None] = mapped_column(String(120), default=None)
    text: Mapped[str] = mapped_column(Text)
    extract_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class FutureInvoice(Base):
    """The simulated world's hidden future. Agents must never read this table.

    `release_invoices` in `trueup.datagen` moves rows into `ap_invoices` when the
    simulation clock reaches their arrival period. It doubles as the answer key.
    """

    __tablename__ = "future_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(30))
    po_number: Mapped[str | None] = mapped_column(String(30), default=None)
    invoice_number: Mapped[str] = mapped_column(String(60))
    invoice_date: Mapped[str] = mapped_column(String(10))
    service_period: Mapped[str] = mapped_column(String(7))
    amount_cents: Mapped[int]
    arrived_period: Mapped[str] = mapped_column(String(7))
    planted_cause: Mapped[str | None] = mapped_column(String(60), default=None)


# --- Agent outputs --------------------------------------------------------------


class LineClassification(Base):
    """Classifier cache. Keyed by a hash of the row so unchanged rows never re-call Jev."""

    __tablename__ = "line_classifications"

    po_line_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    row_hash: Mapped[str] = mapped_column(String(64))
    rules_json: Mapped[dict] = mapped_column(JSON)
    jev_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    final_json: Mapped[dict] = mapped_column(JSON)
    agreed: Mapped[bool]
    needs_human: Mapped[bool]
    contradictions_json: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class CloseItem(Base):
    """One obligation for one period. The status is what the UI shows."""

    __tablename__ = "close_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    obligation_key: Mapped[str] = mapped_column(String(80))  # po_line_id or "card:<issuer>"
    vendor_id: Mapped[str | None] = mapped_column(String(30), default=None)
    source: Mapped[str] = mapped_column(String(10))  # po, card
    kind: Mapped[str | None] = mapped_column(String(30), default=None)  # fixed_recurring, ...
    status: Mapped[str] = mapped_column(String(20))  # done, waiting, blocked, needs_review
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class AccrualEstimate(Base):
    __tablename__ = "accrual_estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    close_item_id: Mapped[int] = mapped_column(ForeignKey("close_items.id"))
    model: Mapped[str] = mapped_column(String(40))  # fixed_contract, received_qty, run_rate, card
    amount_cents: Mapped[int]
    inputs_json: Mapped[dict] = mapped_column(JSON)
    reasoning: Mapped[str] = mapped_column(Text)  # chain of thought the learning agent reads
    playbook_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class OutreachRequest(Base):
    __tablename__ = "outreach_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    close_item_id: Mapped[int] = mapped_column(ForeignKey("close_items.id"))
    reason: Mapped[str] = mapped_column(String(60))  # missing_usage, classifier_mismatch, ...
    question: Mapped[str] = mapped_column(Text)
    to_role: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, answered, timed_out
    deadline: Mapped[str] = mapped_column(String(25))  # ISO timestamp
    answer_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class LearningEntry(Base):
    """One lesson: a gap between an estimate and the real invoice, and what to change."""

    __tablename__ = "learning_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int | None] = mapped_column(  # None: an invoice we never accrued
        ForeignKey("accrual_estimates.id"), default=None
    )
    invoice_id: Mapped[int] = mapped_column(ForeignKey("ap_invoices.id"))
    delta_cents: Mapped[int]  # invoice minus estimate
    cause: Mapped[str] = mapped_column(String(60))
    evidence_json: Mapped[list] = mapped_column(JSON)
    scope_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    # proposed, provisional, adopted, rejected, revoked
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ProposedJERow(Base):
    __tablename__ = "proposed_jes"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    close_item_id: Mapped[int | None] = mapped_column(ForeignKey("close_items.id"), default=None)
    rule: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))  # see schemas.ProposedJE
    evidence_json: Mapped[list] = mapped_column(JSON)  # serialized schemas.Evidence list
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class JELineRow(Base):
    __tablename__ = "je_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    je_id: Mapped[int] = mapped_column(ForeignKey("proposed_jes.id"))
    account_code: Mapped[str] = mapped_column(String(20))
    debit_cents: Mapped[int] = mapped_column(default=0)
    credit_cents: Mapped[int] = mapped_column(default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=_utcnow)
    actor: Mapped[str] = mapped_column(String(60))  # agent name, human username
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)


def get_engine(path: str | None = None) -> Engine:
    """Create a SQLite engine. Falls back to the TRUEUP_DB env var, then a local file."""
    if path is None:
        path = os.environ.get("TRUEUP_DB", DEFAULT_DB_PATH)
    return create_engine(f"sqlite:///{path}")


def init_db(engine: Engine) -> None:
    """Create all tables if they do not exist."""
    Base.metadata.create_all(engine)


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    """Yield a session, committing on success and rolling back on error."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
