"""Invoices and operational evidence (usage, seats, timesheets, hires, deliveries, POs)."""
import calendar
import random
from datetime import date, timedelta

from . import world as w


# ---- date helpers -----------------------------------------------------------
def ym_parts(ym):
    y, m = ym.split("-")
    return int(y), int(m)


def first(ym):
    y, m = ym_parts(ym)
    return date(y, m, 1)


def last(ym):
    y, m = ym_parts(ym)
    return date(y, m, calendar.monthrange(y, m)[1])


def shift(ym, n):
    y, m = ym_parts(ym)
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def cutoff(ym):
    return first(shift(ym, 1)).replace(day=w.CUTOFF_DAY)


def ym_of(d):
    return f"{d.year:04d}-{d.month:02d}"


def r2(x):
    return round(x + 1e-9, 2)


# ---- true pricing -----------------------------------------------------------
def fixed_fee(vid, ym):
    fee = None
    for eff, amt in w.FIXED_FEES[vid]:
        if ym >= eff:
            fee = amt
    return fee


def tiered(cfg, qty, included_key):
    over = max(0, qty - cfg[included_key])
    return r2(cfg["commit_fee"] + over * cfg["overage_rate"])


def helpline_fee(ym):
    h = w.HELPLINE
    base = h["base_seats"] * h["seat_price"]
    co = h["co_effective"]
    if ym < ym_of(co):
        return r2(base)
    if ym == ym_of(co):
        dim = last(ym).day
        return r2(base + h["co_seats"] * h["seat_price"] * (dim - co.day + 1) / dim)
    return r2((h["base_seats"] + h["co_seats"]) * h["seat_price"])


# ---- invoices ---------------------------------------------------------------
PREFIX = {"V001": "DF", "V002": "CH", "V003": "HD", "V004": "LC", "V005": "PL", "V006": "BW",
          "V007": "ML", "V008": "ON", "V009": "PC", "V010": "SL", "V011": "TB", "V012": "PW",
          "V013": "SG", "V014": "AF", "V015": "QB", "V016": "NT", "V017": "TW"}
RECEIPT_DAY = {"V001": 2, "V002": 8, "V003": 3, "V004": 2, "V005": 4, "V006": 15, "V007": 20,
               "V009": 2, "V013": 9, "V016": 2, "V017": 2}
RECEIPT_OVERRIDE = {
    ("V001", "2026-12"): date(2027, 1, 12), ("V001", "2027-01"): date(2027, 2, 10),
    ("V003", "2026-12"): date(2027, 1, 9),
    ("V004", "2027-01"): date(2027, 2, 11),
    ("V005", "2027-01"): date(2027, 2, 9),
    ("V007", "2026-11"): date(2026, 12, 18), ("V007", "2026-12"): date(2027, 1, 22),
    ("V016", "2026-11"): date(2026, 12, 9),
}


def build_invoices():
    invs, seq = [], {}

    def add(vid, inv_date, recv, sp_start, sp_end, lines, number=None, channel="ap@northstar.example",
            bill_to=None, notes=""):
        seq[vid] = seq.get(vid, 0) + 1
        v = w.VENDOR[vid]
        amount = r2(sum(l["amount"] for l in lines))
        invs.append({
            "invoice_id": f"INV-{vid}-{seq[vid]:03d}",
            "invoice_number": number or f"{PREFIX[vid]}-{2200 + seq[vid] * 7}",
            "vendor_id": vid, "vendor_name": v["name"],
            "bill_to": bill_to or next(e["name"] for e in w.COMPANY["entities"]
                                       if e["entity_id"] == v["legal_entity_id"]),
            "invoice_date": inv_date.isoformat(), "received_date": recv.isoformat(),
            "service_period_start": sp_start.isoformat(), "service_period_end": sp_end.isoformat(),
            "po_id": v["po_id"], "currency": "USD", "amount": amount, "line_items": lines,
            "payment_terms": v["payment_terms"], "received_channel": channel, "notes": notes,
        })
        return invs[-1]

    def line(desc, qty, unit, amount=None):
        return {"description": desc, "quantity": qty, "unit_price": unit,
                "amount": r2(qty * unit) if amount is None else amount}

    for ym in w.ALL_MONTHS:
        nxt = shift(ym, 1)

        def recv(vid):
            return RECEIPT_OVERRIDE.get((vid, ym), first(nxt).replace(day=RECEIPT_DAY[vid]))

        label = first(ym).strftime("%B %Y")
        # simple fixed-fee vendors billed in arrears
        for vid, desc in [("V001", "DataForge Platform subscription"), ("V004", "Lumen CRM Enterprise"),
                          ("V005", "PagerLoop Business plan"), ("V017", "Serviced office, Floor 3")]:
            ln = [line(f"{desc} - {label}", 1, fixed_fee(vid, ym))]
            bill_to = "Northstar Analytics, Inc." if (vid, ym) == ("V017", "2026-12") else None
            add(vid, last(ym), recv(vid), first(ym), last(ym), ln, bill_to=bill_to)
        # PayCircle, with the unordered add-on in December and a later credit memo
        ln = [line(f"Payroll platform - {label}", 1, fixed_fee("V009", ym))]
        if ym == "2026-12":
            ln.append(line("Benefits Admin module", 1, 830.0))
        add("V009", last(ym), recv("V009"), first(ym), last(ym), ln)
        if ym == "2027-01":
            add("V009", date(2027, 1, 19), date(2027, 1, 20), first("2026-12"), last("2026-12"),
                [line("Credit: Benefits Admin module billed in error (Dec 2026)", 1, -830.0)],
                number="PC-CM-0114", notes="Credit memo")
        # usage vendors
        ch, hrs = w.CLOUDHARBOR, w.CLOUDHARBOR_HOURS[ym]
        ln = [line(f"Committed compute, {ch['included_hours']:,} hrs - {label}", 1, ch["commit_fee"])]
        if hrs > ch["included_hours"]:
            ln.append(line("Overage compute hours", hrs - ch["included_hours"], ch["overage_rate"]))
        add("V002", first(nxt).replace(day=3), recv("V002"), first(ym), last(ym), ln)
        sg, gb = w.STREAMGRID, w.STREAMGRID_GB[ym]
        ln = [line(f"Committed egress, {sg['included_gb']:,} GB - {label}", 1, sg["commit_fee"])]
        if gb > sg["included_gb"]:
            ln.append(line("Overage egress GB", gb - sg["included_gb"], sg["overage_rate"]))
        add("V013", first(nxt).replace(day=4), recv("V013"), first(ym), last(ym), ln)
        # Helpline seats
        h = w.HELPLINE
        ln = [line(f"Agent seats - {label}", h["base_seats"] if ym < "2027-01" else 150, h["seat_price"])]
        if ym == "2026-12":
            ln.append(line("Added seats (CO-1), prorated Dec 10-31", 30, h["seat_price"],
                           r2(helpline_fee(ym) - 120 * h["seat_price"])))
        add("V003", last(ym), recv("V003"), first(ym), last(ym), ln)
        # Brightwork T&M
        if ym in w.BRIGHTWORK["hours"]:
            add("V006", first(nxt).replace(day=10), recv("V006"), first(ym), last(ym),
                [line(f"Implementation consulting - {label}", w.BRIGHTWORK["hours"][ym], w.BRIGHTWORK["rate"])])
        # Meridian legal
        if ym in w.MERIDIAN_FEES:
            add("V007", recv("V007") - timedelta(days=2), recv("V007"), first(ym), last(ym),
                [line(f"Professional services rendered - {label}", 1, w.MERIDIAN_FEES[ym])])
        # OfficeNest rent, billed in advance
        prior = shift(ym, -1)
        add("V008", first(prior).replace(day=24), first(prior).replace(day=25), first(ym), last(ym),
            [line(f"Office rent, Suite 400 - {label}", 1, fixed_fee("V008", ym))])
        # Northwind telecom; November invoice went to a retired mailbox
        chan = "ap-old@northstar.example (retired mailbox)" if ym == "2026-11" else "ap@northstar.example"
        add("V016", last(ym), recv("V016"), first(ym), last(ym),
            [line(f"Business voice and data - {label}", 1, w.NORTHWIND_FEES[ym])], channel=chan,
            notes="Re-sent by vendor on request" if ym == "2026-11" else "")

    # SecureLayer annual prepaid
    s = w.SECURELAYER
    add("V010", date(2026, 8, 1), date(2026, 8, 3), s["term_start"], s["term_end"],
        [line("SecureLayer Platform, annual subscription Aug 2026 - Jul 2027", 1, s["annual_fee"])])
    # Atlas quarterly in arrears
    for months, recv_d in [(["2026-05", "2026-06", "2026-07"], date(2026, 8, 6)),
                           (["2026-08", "2026-09", "2026-10"], date(2026, 11, 6)),
                           (["2026-11", "2026-12", "2027-01"], date(2027, 2, 8))]:
        add("V014", recv_d - timedelta(days=3), recv_d, first(months[0]), last(months[-1]),
            [line(f"Janitorial and maintenance - {first(m).strftime('%B %Y')}", 1, fixed_fee("V014", m))
             for m in months])
    # Quantive, monthly in advance from the 15th
    for start, end in [(date(2026, 12, 15), date(2027, 1, 14)), (date(2027, 1, 15), date(2027, 2, 14))]:
        add("V015", start, start + timedelta(days=1), start, end,
            [line(f"Quantive BI Team plan, {start:%b %d} - {end:%b %d, %Y}", 1, w.QUANTIVE["monthly_fee"])])
    # TalentBridge placements
    tb_recv = [date(2026, 7, 10), date(2026, 12, 9), date(2026, 12, 14), date(2027, 2, 8)]
    for (start, role, salary, pct), recv_d in zip(w.TALENTBRIDGE_HIRES, tb_recv):
        add("V011", recv_d - timedelta(days=4 if recv_d != date(2026, 12, 9) else 19), recv_d, start, start,
            [line(f"Placement fee, {role} (start {start:%b %d, %Y}), {int(pct * 100)}% of ${salary:,}",
                  1, r2(salary * pct))])
    # PrintWorks jobs, plus a re-sent duplicate of the November invoice
    pw_recv = {"2026-07": date(2026, 8, 3), "2026-09": date(2026, 10, 2),
               "2026-11": date(2026, 12, 1), "2027-01": date(2027, 2, 6)}
    for ym, po, desc, amt in w.PRINTWORKS_JOBS:
        inv = add("V012", pw_recv[ym] - timedelta(days=2), pw_recv[ym], first(ym), last(ym),
                  [line(desc, 1, amt)], number="7731" if ym == "2026-11" else None)
        inv["po_id"] = po
        if ym == "2026-11":
            dup = add("V012", date(2026, 12, 17), date(2026, 12, 18), first(ym), last(ym),
                      [line(desc, 1, amt)], number="7731-R", notes="Statement copy")
            dup["po_id"] = po
    invs.sort(key=lambda i: (i["received_date"], i["invoice_id"]))
    return invs


# ---- operational evidence ---------------------------------------------------
def _daily(vid, metric, totals, seed):
    rng, rows = random.Random(seed), []
    for ym, total in totals.items():
        days = [first(ym) + timedelta(days=i) for i in range(last(ym).day)]
        wts = [rng.uniform(0.85, 1.15) * (0.8 if d.weekday() >= 5 else 1.0) for d in days]
        vals = [int(total * x / sum(wts)) for x in wts]
        vals[-1] += total - sum(vals)
        rows += [{"vendor_id": vid, "date": d.isoformat(), "metric": metric, "quantity": q,
                  "source": "usage-export"} for d, q in zip(days, vals)]
    return rows


def build_usage():
    return (_daily("V002", "compute_hours", w.CLOUDHARBOR_HOURS, 11)
            + _daily("V013", "egress_gb", w.STREAMGRID_GB, 13))


def build_seats():
    rows = [{"vendor_id": "V003", "snapshot_date": first(ym).isoformat(),
             "active_seats": 120 if ym < "2027-01" else 150, "source": "helpline-admin-console"}
            for ym in w.ALL_MONTHS]
    rows.append({"vendor_id": "V003", "snapshot_date": "2026-12-10", "active_seats": 150,
                 "source": "helpline-admin-console"})
    return sorted(rows, key=lambda r: r["snapshot_date"])


def build_timesheets():
    """Weekly Brightwork timesheets. The last two December weeks are still unapproved at close."""
    rng, rows = random.Random(6), []
    for ym, total in w.BRIGHTWORK["hours"].items():
        fridays = [d for d in (first(ym) + timedelta(days=i) for i in range(last(ym).day)) if d.weekday() == 4]
        base = [rng.uniform(0.8, 1.2) for _ in fridays]
        hrs = [round(total * b / sum(base)) for b in base]
        hrs[-1] += total - sum(hrs)
        for i, (d, hq) in enumerate(zip(fridays, hrs)):
            pending = ym == "2026-12" and i >= len(fridays) - 2
            rows.append({"vendor_id": "V006", "po_id": "PO-1042", "week_ending": d.isoformat(),
                         "service_month": ym, "hours": hq, "rate": w.BRIGHTWORK["rate"],
                         "approval_status": "PENDING" if pending else "APPROVED",
                         "approved_by": "" if pending else "E032",
                         "approved_date": "" if pending else (d + timedelta(days=3)).isoformat()})
    return rows


def build_hires():
    return [{"vendor_id": "V011", "employee_start_date": s.isoformat(), "role": role,
             "base_salary": sal, "source_agency": "TalentBridge Partners", "hr_record_id": f"HR-{4100 + i}"}
            for i, (s, role, sal, _) in enumerate(w.TALENTBRIDGE_HIRES)]


def build_deliveries():
    return [{"vendor_id": "V012", "po_id": po, "delivery_date": last(ym).replace(day=20).isoformat(),
             "description": desc, "received_by": "E019", "receipt_id": f"GR-{po[3:]}"}
            for ym, po, desc, _ in w.PRINTWORKS_JOBS]


def build_pos():
    pos = []
    annual = {"V001": 600000, "V002": 480000, "V003": 125000, "V004": 216000, "V005": 80000,
              "V009": 50000, "V010": 96000, "V013": 110000, "V014": 54000, "V015": 111600}
    for vid, amt in annual.items():
        v = w.VENDOR[vid]
        pos.append({"po_id": v["po_id"], "vendor_id": vid, "owner": v["operational_owner"],
                    "requester": v["requester"], "cost_center": v["cost_center"],
                    "legal_entity_id": v["legal_entity_id"], "authorized_amount": float(amt),
                    "type": "BLANKET_ANNUAL", "valid_from": "2026-01-01", "valid_to": "2026-12-31"
                    if vid not in ("V010", "V015") else "2027-12-31", "status": "OPEN"})
    pos.append({"po_id": "PO-1042", "vendor_id": "V006", "owner": "E014", "requester": "E032",
                "cost_center": "CC-140", "legal_entity_id": "NS-US",
                "authorized_amount": w.BRIGHTWORK["po_amount"], "type": "PROJECT_TM",
                "valid_from": "2026-10-01", "valid_to": "2027-02-28", "status": "OPEN"})
    for ym, po, desc, amt in w.PRINTWORKS_JOBS:
        pos.append({"po_id": po, "vendor_id": "V012", "owner": "E019", "requester": "E019",
                    "cost_center": "CC-190", "legal_entity_id": "NS-US", "authorized_amount": amt,
                    "type": "ONE_TIME", "valid_from": first(ym).isoformat(),
                    "valid_to": last(ym).isoformat(), "status": "OPEN", "description": desc})
    change_orders = [{"change_order_id": "CO-1", "po_id": "PO-1017", "vendor_id": "V003",
                      "effective_date": "2026-12-10", "requested_by": "E031", "approved_by": "E012",
                      "description": "Add 30 agent seats for holiday support surge; retained going forward",
                      "seat_delta": 30, "unit_price": 85.0, "po_increase": 32000.0}]
    return pos, change_orders
