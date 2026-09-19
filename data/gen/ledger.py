"""Simulated GL history (closed periods only) and the AP queue."""
from datetime import date, timedelta

from . import world as w
from .records import cutoff, first, last, shift, ym_of, r2

# Historical accruals the (human) team booked that were slightly off, to give true-up history.
HIST_ACCRUAL_OVERRIDE = {("V007", "2026-10"): 12000.0, ("V007", "2026-07"): 20000.0}
# Seeded miss: the October TalentBridge placement was never accrued.
NEVER_ACCRUED = {("V011", "2026-10")}


def build_gl(invoices):
    lines, n = [], [0]

    def post(posting_date, period, vid, entry_type, dr, cr, amount, ref, memo, reversal_of=""):
        n[0] += 1
        eid = f"JE-{n[0]:05d}"
        v = w.VENDOR[vid]
        for i, (acct, debit, credit) in enumerate([(dr, amount, 0.0), (cr, 0.0, amount)], 1):
            lines.append({"entry_id": eid, "line_no": i, "posting_date": posting_date.isoformat(),
                          "period": period, "legal_entity_id": v["legal_entity_id"], "account": acct,
                          "cost_center": v["cost_center"], "vendor_id": vid, "debit": r2(debit),
                          "credit": r2(credit), "entry_type": entry_type, "reference": ref,
                          "memo": memo, "reversal_of": reversal_of, "posted_by": "E004"})
        return eid

    hist_end = last(w.HISTORY[-1])
    for inv in invoices:
        vid, v = inv["vendor_id"], w.VENDOR[inv["vendor_id"]]
        recv = date.fromisoformat(inv["received_date"])
        sp_start = date.fromisoformat(inv["service_period_start"])
        sp_end = date.fromisoformat(inv["service_period_end"])
        if vid == "V010":  # prepaid: capitalise, then amortise monthly through history
            post(recv, ym_of(recv), vid, "INVOICE", "1300", "2000", inv["amount"], inv["invoice_id"],
                 "SecureLayer annual subscription, prepaid")
            for ym in w.HISTORY:
                if ym >= ym_of(sp_start):
                    post(last(ym), ym, vid, "AMORTIZATION", v["gl_account"], "1300",
                         r2(inv["amount"] / 12), inv["invoice_id"], f"Prepaid amortization {ym}")
            continue
        if sp_end > hist_end or (vid, ym_of(sp_start)) in NEVER_ACCRUED:
            continue  # close-period activity (and the seeded miss) is for the agent to handle
        months, m = [], ym_of(sp_start)
        while m <= ym_of(sp_end):
            months.append(m)
            m = shift(m, 1)
        per_month = ({mm: l["amount"] for mm, l in zip(months, inv["line_items"])}
                     if len(months) > 1 else {months[0]: inv["amount"]})
        # accrue each service month at every close that passed before the invoice arrived
        for mm in months:
            close = mm
            while close in w.HISTORY and recv > cutoff(close):
                amt = HIST_ACCRUAL_OVERRIDE.get((vid, mm), per_month[mm])
                eid = post(last(close), close, vid, "ACCRUAL" if close == mm else "ACCRUAL_CARRYFORWARD",
                           v["gl_account"], "2100", amt, f"ACR-{vid}-{mm}",
                           f"Accrual {v['name']} service {mm}")
                nxt = shift(close, 1)
                if nxt <= w.CLOSE_PERIODS[0]:
                    post(first(nxt), nxt, vid, "ACCRUAL_REVERSAL", "2100", v["gl_account"], amt,
                         f"ACR-{vid}-{mm}", f"Auto-reversal of {eid}", eid)
                close = nxt
        period = ym_of(sp_end) if recv <= cutoff(ym_of(sp_end)) else ym_of(recv)
        posting = min(max(recv, first(period)), last(period))
        post(posting, period, vid, "INVOICE", v["gl_account"], "2000", inv["amount"],
             inv["invoice_id"], f"{v['name']} {inv['invoice_number']}")
    lines.sort(key=lambda l: (l["posting_date"], l["entry_id"], l["line_no"]))
    return lines


def build_ap_queue(invoices):
    rows = []
    hist_end = last(w.HISTORY[-1])
    for inv in invoices:
        v = w.VENDOR[inv["vendor_id"]]
        recv = date.fromisoformat(inv["received_date"])
        historical = recv <= hist_end
        posted = (date.fromisoformat(inv["service_period_end"]) <= hist_end
                  and (inv["vendor_id"], inv["service_period_start"][:7]) not in NEVER_ACCRUED)
        entity = v["legal_entity_id"]
        if inv["bill_to"] == "Northstar Analytics, Inc." and entity == "NS-UK":
            entity = "NS-US"  # AP coded it to whatever the invoice said
        rows.append({
            "ap_id": "AP-" + inv["invoice_id"][4:], "invoice_id": inv["invoice_id"],
            "invoice_number": inv["invoice_number"], "vendor_id": inv["vendor_id"],
            "received_date": inv["received_date"], "received_channel": inv["received_channel"],
            "amount": inv["amount"], "coded_entity": entity, "coded_account": v["gl_account"],
            "coded_cost_center": v["cost_center"], "po_id": inv["po_id"] or "",
            "status": "PAID" if historical else "APPROVED" if posted else "PENDING_APPROVAL",
            "approver": v["operational_owner"],
            "due_date": (date.fromisoformat(inv["invoice_date"]) + timedelta(days=30)).isoformat(),
            "paid_date": (recv + timedelta(days=24)).isoformat() if historical else "",
        })
    return rows
