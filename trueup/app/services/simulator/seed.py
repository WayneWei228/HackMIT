"""Build the synthetic company.

Everything here is deterministic: no RNG without a fixed seed, no wall clock. Two
runs produce byte-identical databases, so a diff in a backtest number always
means a real behaviour change rather than noise.

Critically, ALL AP invoices for ALL twelve months are inserted up front, each
carrying a truthful `received_at`. The backtest does not delete future rows — it
relies on the as-of guard to hide them. That is a much stronger test of the
leakage boundary than rewinding the database would be.
"""
from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import HISTORICAL_PERIODS, LIVE_PERIOD, PDF_DIR
from app.models import (
    CompanyApInvoice,
    CompanyConfig,
    CompanyContract,
    CompanyNonPoSpend,
    CompanyPurchaseOrder,
    CompanyServiceEvidence,
    CompanyVendor,
)
from app.money import money, rate
from app.services.pdf.extract import load_corpus
from app.services.simulator import profile as P
from app.services.simulator.clock import close_cutoff, period_dates

ALL_PERIODS = HISTORICAL_PERIODS + [LIVE_PERIOD]


# ---------------------------------------------------------------------------
# Deterministic quantities
# ---------------------------------------------------------------------------

def usage_quantity(vendor_id: str, period: str) -> Decimal | None:
    if (vendor_id, period) in P.PDF_USAGE_OVERRIDES:
        return Decimal(P.PDF_USAGE_OVERRIDES[(vendor_id, period)])
    base = P.USAGE_BASE.get(vendor_id)
    if base is None:
        return None
    m = int(period.split("-")[1])
    # Steady growth plus a fixed seasonal wobble — pure function of the month.
    factor = Decimal(1) + Decimal("0.028") * (m - 1) + Decimal(str(round(0.035 * math.sin(m * 1.3), 6)))
    return Decimal(int(base * factor))


def effective_rate(contract_row: CompanyContract, service_start: dt.date) -> Decimal:
    """The rate that actually applies — escalator included.

    This is the arithmetic the naive estimator skips.
    """
    r = rate(contract_row.base_rate)
    if contract_row.escalator_percent and contract_row.escalator_effective_date:
        if contract_row.escalator_effective_date <= service_start:
            r = r * (Decimal(1) + rate(contract_row.escalator_percent) / Decimal(100))
    return r


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed_all(session: Session) -> dict:
    corpus = load_corpus(PDF_DIR)
    stats = {"pdf_documents": len(corpus)}

    _seed_config(session)
    _seed_vendors(session)
    contract_rows = _seed_contracts(session, corpus)
    _seed_purchase_orders(session, corpus)
    _seed_service_evidence(session, corpus, contract_rows)
    _seed_ap_invoices(session, corpus, contract_rows)
    _seed_non_po_spend(session)
    session.flush()

    stats |= {
        "vendors": session.query(CompanyVendor).count(),
        "contract_versions": session.query(CompanyContract).count(),
        "purchase_orders": session.query(CompanyPurchaseOrder).count(),
        "service_evidence": session.query(CompanyServiceEvidence).count(),
        "ap_invoices": session.query(CompanyApInvoice).count(),
        "non_po_spend": session.query(CompanyNonPoSpend).count(),
        "periods": ALL_PERIODS,
    }
    return stats


def _seed_config(session: Session) -> None:
    now = dt.datetime(2026, 1, 1)
    rows = {
        "people": P.PEOPLE,
        "ownership_map": {
            "CONTROLLER": "P-CONTROLLER", "AP_OWNER": "P-AP",
            "PROCUREMENT_OWNER": "P-PROC", "PO_OWNER": "P-IT",
            "SERVICE_OWNER": "P-ENG", "CARDHOLDER": "P-IT",
        },
        "accounting_periods": {
            p: {"status": "OPEN", "cutoff": close_cutoff(p).isoformat()} for p in ALL_PERIODS
        },
        "approval_thresholds": P.APPROVAL_THRESHOLDS,
        "policy_rules": P.POLICY_RULES,
        "allowed_gl_accounts": {"accounts": P.ALLOWED_GL_ACCOUNTS,
                                "accrual_liability": P.ACCRUAL_LIABILITY},
    }
    for k, v in rows.items():
        session.merge(CompanyConfig(config_key=k, config_value_json=v, updated_at=now))


def _seed_vendors(session: Session) -> None:
    for v in P.VENDORS:
        session.merge(CompanyVendor(
            vendor_id=v["vendor_id"], vendor_name=v["vendor_name"],
            vendor_category=v["vendor_category"], billing_cadence=v["billing_cadence"],
            default_currency=P.CURRENCY, billing_contact_email=v["email"], is_active=True,
        ))


def _seed_contracts(session: Session, corpus: dict[str, str]) -> dict[str, list[CompanyContract]]:
    out: dict[str, list[CompanyContract]] = {}
    for c in P.CONTRACTS:
        text = corpus.get(c.get("pdf", ""), "")
        if not text:
            text = _synth_contract_text(c)
        rows = []
        for ver in c["versions"]:
            row = CompanyContract(
                contract_row_id=f"{c['contract_id']}-V{ver['v']}",
                contract_id=c["contract_id"], contract_version=ver["v"],
                vendor_id=c["vendor_id"], contract_name=c["name"], status="ACTIVE",
                effective_start_date=dt.date.fromisoformat(ver["start"]),
                effective_end_date=dt.date.fromisoformat(ver["end"]) if ver["end"] else None,
                billing_model=c["billing_model"], base_rate=c["base_rate"],
                rate_unit=c["rate_unit"], billing_frequency="MONTHLY",
                escalator_percent=ver["escalator"],
                escalator_effective_date=(
                    dt.date.fromisoformat(ver["escalator_date"]) if ver["escalator_date"] else None
                ),
                service_owner_id=c["service_owner"], procurement_owner_id=c["procurement_owner"],
                contract_text=text,
            )
            session.merge(row)
            rows.append(row)
        out[c["contract_id"]] = rows
    return out


def _synth_contract_text(c: dict) -> str:
    unit = c["rate_unit"]
    if c["billing_model"] == "FIXED_RECURRING":
        commercial = f"Fee is ${c['base_rate']} per month, billed monthly."
    else:
        commercial = f"Billed monthly based on measured usage. Contracted rate is ${c['base_rate']} per {unit}."
    return (
        f"SERVICE ORDER FORM\n{c['contract_id']} | Orbit Labs, Inc. and contracted vendor\n"
        f"COMMERCIAL SUMMARY\n{commercial}\n"
        f"TERMS\n1. Services: vendor provides the service described in this order form.\n"
        f"2. Commercial terms: {commercial}\n"
        f"3. Service records: vendor usage or active-service records support each billing period.\n"
        f"4. Invoice timing: invoices are issued after the applicable monthly service period, Net 30.\n"
        f"5. Changes: {c.get('text_extra', 'Pricing changes require a written amendment.')}\n"
    )


def _seed_purchase_orders(session: Session, corpus: dict[str, str]) -> None:
    # PO-003 / ASUS laptops — straight from the PDF.
    session.merge(CompanyPurchaseOrder(
        po_id="PO-003", po_number="PO-003", vendor_id="V003", contract_id=None,
        status="APPROVED", order_type="ONE_TIME", entity_id=P.ENTITY, cost_center="CC-IT",
        po_owner_id="P-IT", approved_total=money("40000.00"), currency="USD",
        service_start_date=dt.date(2026, 12, 10), service_end_date=dt.date(2026, 12, 31),
        gl_account="6400-IT-EQUIPMENT",
        description="One-time purchase of 25 laptop packages for new engineers",
        line_items_json=[{
            "po_line_id": "PO-003-L1", "item_category": "HARDWARE",
            "gl_account_code": "6400-IT-EQUIPMENT", "quantity_ordered": "25",
            "unit_price": "1600.00", "quantity_received": "20", "quantity_billed": "0",
            "line_description": "Laptop package for new engineers",
            "service_start_date": "2026-12-10", "service_end_date": "2026-12-31",
            "receipt_required": True,
        }],
    ))
    # PO-011 / Dell — raised at $2,400 against a contract that says $2,100.
    session.merge(CompanyPurchaseOrder(
        po_id="PO-011", po_number="PO-011", vendor_id="V011", contract_id="CTR-011",
        status="APPROVED", order_type="ONE_TIME", entity_id=P.ENTITY, cost_center="CC-IT",
        po_owner_id="P-IT", approved_total=money("19200.00"), currency="USD",
        service_start_date=dt.date(2026, 12, 5), service_end_date=dt.date(2026, 12, 31),
        gl_account="6400-IT-EQUIPMENT",
        description="Eight engineering workstations for the platform team",
        line_items_json=[{
            "po_line_id": "PO-011-L1", "item_category": "HARDWARE",
            "gl_account_code": "6400-IT-EQUIPMENT", "quantity_ordered": "8",
            "unit_price": "2400.00", "quantity_received": "8", "quantity_billed": "0",
            "line_description": "Engineering workstation",
            "service_start_date": "2026-12-05", "service_end_date": "2026-12-31",
            "receipt_required": True,
        }],
    ))
    # CAMPAIGN-004 / Meta — a milestone/delivery-billed order.
    session.merge(CompanyPurchaseOrder(
        po_id="CAMPAIGN-004", po_number="CAMPAIGN-004", vendor_id="V004", contract_id=None,
        status="APPROVED", order_type="MILESTONE", entity_id=P.ENTITY, cost_center="CC-MKT",
        po_owner_id="P-MKT", approved_total=money("30000.00"), currency="USD",
        service_start_date=dt.date(2026, 12, 1), service_end_date=dt.date(2026, 12, 31),
        gl_account="6300-MARKETING",
        description="One-time product-launch advertising campaign. Final charge is based on "
                    "advertising actually delivered; the maximum budget is a spending limit.",
        line_items_json=[{
            "po_line_id": "CAMPAIGN-004-L1", "item_category": "ADVERTISING",
            "gl_account_code": "6300-MARKETING", "quantity_ordered": "1",
            "unit_price": "30000.00", "quantity_received": "0", "quantity_billed": "0",
            "line_description": "Product-launch advertising delivery",
            "service_start_date": "2026-12-01", "service_end_date": "2026-12-31",
            "receipt_required": True,
        }],
    ))


def _seed_service_evidence(session, corpus, contract_rows) -> None:
    """Usage meters, the goods receipt and the campaign delivery report."""
    # --- monthly usage meters for every usage vendor -------------------------
    for c in P.CONTRACTS:
        if c["billing_model"] != "USAGE_BASED":
            continue
        vid = c["vendor_id"]
        for period in ALL_PERIODS:
            qty = usage_quantity(vid, period)
            if qty is None:
                continue
            start, end = period_dates(period)
            # A chronically late meter: exercises the missing-evidence,
            # fallback and outreach paths, repeatedly enough to be a pattern.
            if (vid, period) in P.LATE_USAGE_METERS:
                created = dt.datetime.combine(end, dt.time(2, 0)) + dt.timedelta(days=9)
            else:
                created = dt.datetime.combine(end, dt.time(2, 0)) + dt.timedelta(days=1)
            session.merge(CompanyServiceEvidence(
                service_evidence_id=f"USG-{vid}-{period}",
                vendor_id=vid, contract_id=c["contract_id"], po_id=None,
                service_start_date=start, service_end_date=end,
                evidence_type="USAGE_METER", quantity=qty, unit=c["rate_unit"],
                accepted_amount=None, source_system="USAGE_OPS",
                confirmed_by_person_id=None, confirmation_status="CONFIRMED",
                created_at=created,
            ))
    # --- goods receipt (GR-ASUS-DEC) ----------------------------------------
    session.merge(CompanyServiceEvidence(
        service_evidence_id="GR-ASUS-DEC", vendor_id="V003", contract_id=None, po_id="PO-003",
        service_start_date=dt.date(2026, 12, 10), service_end_date=dt.date(2026, 12, 28),
        evidence_type="GOODS_RECEIPT", quantity=Decimal(20), unit="package",
        accepted_amount=money("32000.00"), source_system="RECEIVING",
        confirmed_by_person_id="P-IT", confirmation_status="CONFIRMED",
        created_at=dt.datetime(2026, 12, 28, 15, 42),
    ))
    # --- goods receipt for the conflicted PO --------------------------------
    session.merge(CompanyServiceEvidence(
        service_evidence_id="GR-DELL-DEC", vendor_id="V011", contract_id="CTR-011", po_id="PO-011",
        service_start_date=dt.date(2026, 12, 5), service_end_date=dt.date(2026, 12, 20),
        evidence_type="GOODS_RECEIPT", quantity=Decimal(8), unit="workstation",
        accepted_amount=money("19200.00"), source_system="RECEIVING",
        confirmed_by_person_id="P-IT", confirmation_status="CONFIRMED",
        created_at=dt.datetime(2026, 12, 20, 11, 15),
    ))
    # --- campaign delivery report (META-DELIVERY-DEC) ------------------------
    session.merge(CompanyServiceEvidence(
        service_evidence_id="META-DELIVERY-DEC", vendor_id="V004", contract_id=None,
        po_id="CAMPAIGN-004",
        service_start_date=dt.date(2026, 12, 1), service_end_date=dt.date(2026, 12, 31),
        evidence_type="DELIVERY_REPORT", quantity=None, unit=None,
        accepted_amount=money("24700.00"), source_system="CAMPAIGN_BILLING_OPS",
        confirmed_by_person_id="P-MKT", confirmation_status="CONFIRMED",
        created_at=dt.datetime(2027, 1, 2, 9, 30),
    ))


def _seed_ap_invoices(session, corpus, contract_rows) -> None:
    """Every invoice for every month, each with a truthful received_at.

    The invoice is the ground truth that grades the accrual. It is never hidden
    from the database — only from the estimator, by the as-of guard.
    """
    for c in P.CONTRACTS:
        vid, cid = c["vendor_id"], c["contract_id"]
        for period in ALL_PERIODS:
            start, end = period_dates(period)
            versions = contract_rows[cid]
            ver = _version_for(versions, start, end)
            if ver is None:
                continue

            if c["billing_model"] == "FIXED_RECURRING":
                amount = money(effective_rate(ver, start))
                desc = "Team documentation plan - monthly service"
                qty, unit = Decimal(1), "monthly service"
            else:
                qty = usage_quantity(vid, period)
                if qty is None:
                    continue
                amount = money(rate(qty) * effective_rate(ver, start))
                desc = f"{c['name']} - measured usage"
                unit = c["rate_unit"]

            lines = [{"description": desc, "quantity": str(qty),
                      "unit": unit, "amount": str(amount)}]
            note = ""
            ue = P.UNEXPLAINED_EVENT
            if vid == ue["vendor_id"] and period == ue["period"]:
                # The surprise is a SEPARATE line, not extra usage. The metered
                # quantity still reconciles exactly - which is precisely why no
                # recorded fact can explain the difference.
                amount = money(amount + ue["extra_amount"])
                note = " " + ue["invoice_note"]
                lines.append({"description": "Reserved capacity commitment adjustment",
                              "quantity": None, "unit": None,
                              "amount": str(ue["extra_amount"])})

            lag = 2 if vid in P.FAST_INVOICERS else 7
            received = dt.datetime.combine(end, dt.time(9, 0)) + dt.timedelta(days=lag)

            inv_id = _pdf_invoice_id(vid, period) or f"INV-{vid}-{period}"
            session.merge(CompanyApInvoice(
                invoice_id=inv_id, vendor_id=vid, invoice_number=inv_id,
                invoice_date=end, received_at=received,
                service_start_date=start, service_end_date=end,
                amount=amount, currency="USD", po_id=None, contract_id=cid,
                status="POSTED" if period < LIVE_PERIOD else "IN_QUEUE",
                duplicate_flag=False, credit_flag=False,
                description=desc + note,
                line_items_json=lines,
                created_at=received, updated_at=received,
            ))

    # --- ASUS: bills only the 20 accepted units, and only in January ---------
    session.merge(CompanyApInvoice(
        invoice_id="INV-ASUS-JAN", vendor_id="V003", invoice_number="INV-ASUS-JAN",
        invoice_date=dt.date(2027, 1, 8), received_at=dt.datetime(2027, 1, 8, 11, 0),
        service_start_date=dt.date(2026, 12, 10), service_end_date=dt.date(2026, 12, 28),
        amount=money("32000.00"), currency="USD", po_id="PO-003", contract_id=None,
        status="IN_QUEUE", duplicate_flag=False, credit_flag=False,
        description="20 laptop packages received and accepted against PO-003",
        line_items_json=[{"po_line_id": "PO-003-L1", "quantity": "20",
                          "unit_price": "1600.00", "amount": "32000.00"}],
        created_at=dt.datetime(2027, 1, 8, 11, 0), updated_at=dt.datetime(2027, 1, 8, 11, 0),
    ))
    # --- Dell: bills at the CONTRACT rate, not the PO rate -------------------
    session.merge(CompanyApInvoice(
        invoice_id="INV-DELL-JAN", vendor_id="V011", invoice_number="INV-DELL-JAN",
        invoice_date=dt.date(2027, 1, 9), received_at=dt.datetime(2027, 1, 9, 10, 0),
        service_start_date=dt.date(2026, 12, 5), service_end_date=dt.date(2026, 12, 20),
        amount=money("16800.00"), currency="USD", po_id="PO-011", contract_id="CTR-011",
        status="IN_QUEUE", duplicate_flag=False, credit_flag=False,
        description="8 engineering workstations at the contracted rate of $2,100.00",
        line_items_json=[{"po_line_id": "PO-011-L1", "quantity": "8",
                          "unit_price": "2100.00", "amount": "16800.00"}],
        created_at=dt.datetime(2027, 1, 9, 10, 0), updated_at=dt.datetime(2027, 1, 9, 10, 0),
    ))
    # --- Meta: bills delivered advertising only ------------------------------
    session.merge(CompanyApInvoice(
        invoice_id="INV-META-JAN", vendor_id="V004", invoice_number="INV-META-JAN",
        invoice_date=dt.date(2027, 1, 6), received_at=dt.datetime(2027, 1, 6, 14, 0),
        service_start_date=dt.date(2026, 12, 1), service_end_date=dt.date(2026, 12, 31),
        amount=money("24700.00"), currency="USD", po_id="CAMPAIGN-004", contract_id=None,
        status="IN_QUEUE", duplicate_flag=False, credit_flag=False,
        description="Delivered advertising for product-launch campaign CAMPAIGN-004",
        line_items_json=[{"description": "Delivered advertising", "amount": "24700.00"}],
        created_at=dt.datetime(2027, 1, 6, 14, 0), updated_at=dt.datetime(2027, 1, 6, 14, 0),
    ))
    # --- monthly card statements: the ground truth for non-PO accruals -------
    for period in ALL_PERIODS:
        start, end = period_dates(period)
        total = _card_statement_total(period)
        received = dt.datetime.combine(end, dt.time(8, 0)) + dt.timedelta(days=8)
        session.merge(CompanyApInvoice(
            invoice_id=f"STMT-CARD-{period}", vendor_id="V010",
            invoice_number=f"STMT-CARD-{period}", invoice_date=end, received_at=received,
            service_start_date=start, service_end_date=end, amount=total, currency="USD",
            po_id=None, contract_id=None,
            status="POSTED" if period < LIVE_PERIOD else "IN_QUEUE",
            duplicate_flag=False, credit_flag=False,
            description=f"Corporate card statement for {period}",
            # Per-group subtotals, as a real statement provides. Without these the
            # reconciler would have to split one statement across several accrual
            # groups by date overlap, which is meaningless when they share a month.
            line_items_json=_card_statement_lines(period),
            created_at=received, updated_at=received,
        ))


def _pdf_invoice_id(vendor_id: str, period: str) -> str | None:
    """Reuse the exact document ids that exist as PDFs, so the fixture months
    reconcile against a real document rather than a generated one."""
    mon = {"2026-09": "SEP", "2026-10": "OCT", "2026-11": "NOV", "2026-12": "DEC"}.get(period)
    if not mon:
        return None
    if vendor_id == "V001":
        return f"INV-MINTLIFY-{mon}"
    if vendor_id == "V002" and mon != "DEC":  # December has a usage report, not an invoice
        return f"INV-OPENAI-{mon}"
    return None


def _version_for(versions, start, end):
    cands = [
        v for v in versions
        if v.effective_start_date <= end and (v.effective_end_date is None or v.effective_end_date >= start)
    ]
    if not cands:
        return None
    return sorted(cands, key=lambda v: (v.effective_start_date, v.contract_version))[-1]


# ---------------------------------------------------------------------------
# Non-PO spend
# ---------------------------------------------------------------------------

def _card_rows(period: str) -> list[dict]:
    """Deterministic card activity for a month.

    Includes, on purpose: a voided charge, a refund, a disputed charge, a charge
    that already carries an AP link (the duplicate-accrual trap), and — for
    later months — transactions that only post AFTER the close cutoff, which is
    what produces an honest timing variance.
    """
    y, m = (int(x) for x in period.split("-"))
    _, end = period_dates(period)
    rows = []
    for i, (merchant, gl, cc, holder) in enumerate(P.CARD_MERCHANTS):
        amt = Decimal(240 + i * 137 + m * 23)
        day = min(3 + i * 4, 27)
        status = "PENDING" if i >= len(P.CARD_MERCHANTS) - 2 else "SETTLED"
        rows.append(dict(
            idx=i, merchant=merchant, gl=gl, cc=cc, holder=holder, amount=amt,
            day=day, status=status, source="PCARD" if i % 2 == 0 else "CORPORATE_CARD",
            ap_link=None, late=False,
        ))
    # voided — must be excluded from the accrual population
    rows.append(dict(idx=90, merchant="Uber", gl="6500-TRAVEL", cc="CC-ENG", holder="P-ENG",
                     amount=Decimal(118), day=12, status="VOIDED",
                     source="CORPORATE_CARD", ap_link=None, late=False))
    # refund — a negative amount that reduces the accrual
    rows.append(dict(idx=91, merchant="Figma", gl="6100-SOFTWARE", cc="CC-MKT", holder="P-MKT",
                     amount=Decimal(-95), day=19, status="REFUND",
                     source="CORPORATE_CARD", ap_link=None, late=False))
    # already invoiced through AP — the duplicate-accrual trap
    rows.append(dict(idx=92, merchant="Notion", gl="6100-SOFTWARE", cc="CC-OPS", holder="P-IT",
                     amount=Decimal(410), day=9, status="SETTLED",
                     source="DIRECT_INVOICE", ap_link=f"AP-DIRECT-{period}", late=False))
    if m >= 6:
        # disputed — excluded from the auto-accrual and routed to the Controller
        rows.append(dict(idx=93, merchant="Amazon Business", gl="6600-OFFICE", cc="CC-OPS",
                         holder="P-IT", amount=Decimal(640), day=21, status="DISPUTED",
                         source="PCARD", ap_link=None, late=False))
        # posts after the cutoff: invisible at close, present on the statement
        rows.append(dict(idx=94, merchant="GitHub", gl="6100-SOFTWARE", cc="CC-ENG",
                         holder="P-ENG", amount=Decimal(300 + m * 11), day=29,
                         status="SETTLED", source="PCARD", ap_link=None, late=True))
    return rows


def _card_statement_total(period: str) -> Decimal:
    """What the card issuer actually bills: every non-voided, non-disputed,
    non-AP-linked charge — including the ones that posted after close."""
    total = Decimal(0)
    for r in _card_rows(period):
        if r["status"] in ("VOIDED", "DISPUTED") or r["ap_link"]:
            continue
        total += r["amount"]
    return money(total)


def _card_statement_lines(period: str) -> list[dict]:
    """Break the statement down by the same key the accrual groups on."""
    groups: dict[str, Decimal] = {}
    for r in _card_rows(period):
        if r["status"] in ("VOIDED", "DISPUTED") or r["ap_link"]:
            continue
        key = f"{period}|{r['source']}|{r['cc']}|{r['gl']}"
        groups[key] = groups.get(key, Decimal(0)) + r["amount"]
    return [{"group_key": k, "amount": str(money(v))} for k, v in sorted(groups.items())]


def _seed_non_po_spend(session: Session) -> None:
    for period in ALL_PERIODS:
        y, m = (int(x) for x in period.split("-"))
        _, end = period_dates(period)
        cutoff = close_cutoff(period)
        for r in _card_rows(period):
            tdate = dt.date(y, m, r["day"])
            if r["late"]:
                created = cutoff + dt.timedelta(days=2)     # posts after the close
            else:
                created = dt.datetime.combine(tdate, dt.time(20, 0)) + dt.timedelta(days=1)
            session.merge(CompanyNonPoSpend(
                non_po_spend_id=f"NPO-{period}-{r['idx']:02d}",
                transaction_date=tdate, month=period, vendor_id=None,
                merchant_name=r["merchant"], spend_source=r["source"],
                cardholder_id=r["holder"], cost_center=r["cc"], gl_account=r["gl"],
                amount=money(r["amount"]), currency="USD",
                transaction_status=r["status"], ap_invoice_id=r["ap_link"],
                description=f"{r['merchant']} charge {period}",
                is_accrued=False, gl_entry_id=None,
                created_at=created, updated_at=created,
            ))
