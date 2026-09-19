"""Ground truth per obligation (answer key; never show to the agent) and scripted inbox replies."""
from datetime import date

from . import world as w
from .records import cutoff, first, last, shift, ym_of, r2, fixed_fee, tiered, helpline_fee

REVIEW_AT, CONTROLLER_AT = 10000.0, 25000.0  # must match policies.json v1.0


def true_expense(vid, ym):
    """What the period's expense should be once all facts are known."""
    if vid in w.FIXED_FEES:
        return fixed_fee(vid, ym)
    if vid == "V002":
        return tiered(w.CLOUDHARBOR, w.CLOUDHARBOR_HOURS[ym], "included_hours")
    if vid == "V013":
        return tiered(w.STREAMGRID, w.STREAMGRID_GB[ym], "included_gb")
    if vid == "V003":
        return helpline_fee(ym)
    if vid == "V006":
        return r2(w.BRIGHTWORK["hours"].get(ym, 0) * w.BRIGHTWORK["rate"])
    if vid == "V007":
        return w.MERIDIAN_FEES.get(ym, 0.0)
    if vid == "V010":
        return 0.0  # prepaid; amortization is outside the accrual workstream
    if vid == "V011":
        return r2(sum(s * p for d, _, s, p in w.TALENTBRIDGE_HIRES if ym_of(d) == ym))
    if vid == "V012":
        return r2(sum(a for m, _, _, a in w.PRINTWORKS_JOBS if m == ym))
    if vid == "V015":
        return {"2026-12": 5100.0, "2027-01": 9300.0}.get(ym, 0.0)
    if vid == "V016":
        return w.NORTHWIND_FEES[ym]
    raise KeyError(vid)


def static_estimate(vid, ym):
    """What a policy-v1.0 agent with no learning computes: base contract terms, no schedule lookups."""
    if vid in w.FIXED_FEES:
        return w.FIXED_FEES[vid][0][1]
    if vid == "V002":
        return r2(max(w.CLOUDHARBOR["commit_fee"], w.CLOUDHARBOR_HOURS[ym] * w.CLOUDHARBOR["base_rate"]))
    if vid == "V013":
        return r2(max(w.STREAMGRID["commit_fee"], w.STREAMGRID_GB[ym] * w.STREAMGRID["base_rate"]))
    if vid == "V003":
        return r2(w.HELPLINE["base_seats"] * w.HELPLINE["seat_price"])
    return true_expense(vid, ym)


def trailing_avg(vid, ym):
    prev = [true_expense(vid, shift(ym, -k)) if shift(ym, -k) >= w.ALL_MONTHS[0] else None for k in (1, 2, 3)]
    prev = [p for p in prev if p is not None]
    return r2(sum(prev) / len(prev)) if prev else 0.0


# (vendor, period) -> overrides on the default row
SPECIAL = {
    ("V001", "2026-12"): dict(split="TRAIN", scenario="ESCALATOR_MISS", root_cause="SCHEDULED_ESCALATOR",
        notes="Contract s4.3: 5% uplift on each anniversary (Dec 1). Order form still shows $50,000."),
    ("V001", "2027-01"): dict(split="HELDOUT_SAME_VENDOR", scenario="ESCALATOR_PRECEDENT", root_cause="SCHEDULED_ESCALATOR"),
    ("V004", "2027-01"): dict(split="HELDOUT", scenario="ESCALATOR_HELDOUT", root_cause="SCHEDULED_ESCALATOR",
        notes="Order form footnote: 4% uplift each January 1."),
    ("V005", "2027-01"): dict(split="HELDOUT", scenario="ESCALATOR_HELDOUT_NEEDS_OUTREACH", root_cause="SCHEDULED_ESCALATOR",
        verifier="OUTREACH_REQUIRED", outreach_target="VENDOR_BILLING", outreach_fact="SCOPE_OR_RATE_CHANGE",
        notes="Uplift is vendor-notified (cap 7%); rate is not in any internal document."),
    ("V002", "2026-12"): dict(split="TRAIN", scenario="TIERED_OVERAGE_MISS", root_cause="TIERED_OVERAGE_RATE"),
    ("V002", "2027-01"): dict(split="HELDOUT_SAME_VENDOR", scenario="TIERED_OVERAGE_PRECEDENT", root_cause="TIERED_OVERAGE_RATE"),
    ("V013", "2027-01"): dict(split="HELDOUT", scenario="TIERED_OVERAGE_HELDOUT", root_cause="TIERED_OVERAGE_RATE"),
    ("V003", "2026-12"): dict(split="TRAIN", scenario="CHANGE_ORDER_MISS", root_cause="CHANGE_ORDER_SEAT_EXPANSION",
        outreach_target="REQUESTER", outreach_fact="SCOPE_OR_RATE_CHANGE",
        notes="CO-1 adds 30 seats from Dec 10; vendor never replies, PO requester does."),
    ("V006", "2026-12"): dict(scenario="MISSING_SERVICE_CONFIRMATION", verifier="OUTREACH_REQUIRED",
        outreach_target="OPERATIONAL_OWNER", outreach_fact="SERVICE_RECEIVED",
        notes="Last two weekly timesheets unapproved at cutoff."),
    ("V007", "2026-11"): dict(scenario="NO_ALLOWED_METHOD", classification="NO_INVOICE_SERVICE_UNCLEAR",
        method="NONE", verifier="ESCALATE", outcome="ESCALATED", outreach_target="OPERATIONAL_OWNER",
        outreach_fact="SERVICE_RECEIVED"),
    ("V007", "2026-12"): dict(scenario="CONFLICTING_EVIDENCE", classification="NO_INVOICE_SERVICE_UNCLEAR",
        method="NONE", verifier="ESCALATE", outcome="ESCALATED", outreach_target="CONTROLLER",
        outreach_fact="TREATMENT", notes="GC says ~$35-45k; vendor WIP report says $58k unbilled. Material."),
    ("V007", "2027-01"): dict(scenario="SERVICE_NOT_RECEIVED", classification="NO_INVOICE_SERVICE_NOT_RECEIVED",
        method="NONE", verifier="PASS", outcome="NO_ACCRUAL_DOCUMENTED", outreach_target="OPERATIONAL_OWNER",
        outreach_fact="SERVICE_RECEIVED"),
    ("V009", "2026-12"): dict(scenario="INVOICE_MISMATCH", classification="INVOICE_MISMATCHED",
        verifier="BLOCK", outcome="ESCALATED", outreach_target="REQUESTER", outreach_fact="SCOPE_OR_RATE_CHANGE",
        notes="Invoice $4,980 includes an $830 module nobody ordered; credit memo arrives Jan 20."),
    ("V011", "2026-12"): dict(scenario="SERVICE_NOT_RECEIVED", classification="NO_INVOICE_SERVICE_NOT_RECEIVED",
        method="NONE", verifier="PASS", outcome="NO_ACCRUAL_DOCUMENTED"),
    ("V012", "2026-12"): dict(scenario="SERVICE_NOT_RECEIVED", classification="NO_INVOICE_SERVICE_NOT_RECEIVED",
        method="NONE", verifier="PASS", outcome="NO_ACCRUAL_DOCUMENTED"),
    ("V015", "2026-12"): dict(scenario="MULTI_PERIOD_INVOICE", classification="INVOICE_SPANS_PERIODS",
        method="PRORATED_FEE", notes="$9,300 covers Dec 15-Jan 14: 17/31 days to Dec, rest is prepaid."),
    ("V015", "2027-01"): dict(scenario="MULTI_PERIOD_INVOICE", classification="INVOICE_SPANS_PERIODS",
        method="PRORATED_FEE", notes="Jan = 14 days of first invoice ($4,200) + 17 days of second ($5,100)."),
    ("V016", "2026-11"): dict(scenario="VENDOR_OUTREACH_FINDS_INVOICE", verifier="OUTREACH_REQUIRED",
        outreach_target="VENDOR_BILLING", outreach_fact="INVOICE_WHEREABOUTS", outcome="CLOSE_READY",
        notes="Invoice went to a retired AP mailbox; vendor re-sends it, so book actual not estimate."),
    ("V017", "2026-12"): dict(scenario="ENTITY_MISMATCH", classification="INVOICE_MISMATCHED",
        verifier="BLOCK", outcome="ESCALATED", outreach_target="AP_SPECIALIST", outreach_fact="AP_STATUS",
        notes="Invoice billed to and coded as NS-US; contract and service are NS-UK."),
}
METHOD = {"V001": "FIXED_CONTRACT_FEE", "V004": "FIXED_CONTRACT_FEE", "V005": "FIXED_CONTRACT_FEE",
          "V008": "FIXED_CONTRACT_FEE", "V009": "FIXED_CONTRACT_FEE", "V014": "FIXED_CONTRACT_FEE",
          "V017": "FIXED_CONTRACT_FEE", "V002": "USAGE_X_RATE", "V013": "USAGE_X_RATE",
          "V003": "USAGE_X_RATE", "V006": "USAGE_X_RATE", "V011": "FIXED_CONTRACT_FEE",
          "V012": "PO_BASED", "V015": "PRORATED_FEE", "V016": "HISTORICAL_RUN_RATE", "V007": "NONE",
          "V010": "NONE"}


def build_truth(invoices):
    rows = []
    for v in w.VENDORS:
        vid = v["vendor_id"]
        for ym in w.CLOSE_PERIODS:
            if vid == "V015" and ym == "2026-11":
                continue  # contract not started
            matching = [i for i in invoices if i["vendor_id"] == vid and i["amount"] > 0
                        and i["service_period_start"] <= last(ym).isoformat()
                        and i["service_period_end"] >= first(ym).isoformat()
                        and not i["invoice_number"].endswith("-R")]
            on_time = [i for i in matching if date.fromisoformat(i["received_date"]) <= cutoff(ym)]
            true_amt, static = true_expense(vid, ym), static_estimate(vid, ym)
            row = dict(obligation_key=f"OBL-{vid}-{ym}", vendor_id=vid, vendor_name=v["name"], period=ym,
                       split="STANDARD", scenario="", root_cause="", outreach_target="", outreach_fact="", notes="")
            if vid == "V010":
                row.update(scenario="PREPAID_NOT_AN_ACCRUAL", classification="NO_ACCRUAL_PREPAID", method="NONE",
                           verifier="PASS", outcome="NO_ACCRUAL_DOCUMENTED", invoice_status_at_cutoff="NONE_EXPECTED",
                           notes="Annual invoice already booked to prepaid; a run-rate estimator would wrongly accrue.")
            elif on_time and vid != "V014":
                row.update(scenario="RECURRING_INVOICE_MATCH", classification="VALID_INVOICE_MATCHES",
                           method="ACTUAL_INVOICE", verifier="PASS", outcome="CLOSE_READY",
                           invoice_status_at_cutoff="RECEIVED")
            else:
                need = "REVIEW_REQUIRED" if true_amt >= REVIEW_AT else "PASS"
                row.update(scenario="SUPPORTED_ACCRUAL" if true_amt else "SERVICE_NOT_RECEIVED",
                           classification="NO_INVOICE_SERVICE_RECEIVED", method=METHOD[vid], verifier=need,
                           outcome="ACCRUED_THEN_RECONCILED", invoice_status_at_cutoff="MISSING")
            if vid == "V014":
                row.update(scenario="QUARTERLY_ARREARS", notes="One invoice for Nov-Jan arrives Feb 8 and must match three obligations.")
            row.update(SPECIAL.get((vid, ym), {}))
            if row["outcome"] == "NO_ACCRUAL_DOCUMENTED":
                row["invoice_status_at_cutoff"] = "NONE_EXPECTED"
            needs = row["invoice_status_at_cutoff"] == "MISSING"
            if not needs or row["method"] == "NONE":
                static = "" if needs else true_amt  # no allowed method: a rules-only agent cannot estimate
            elif row["method"] == "HISTORICAL_RUN_RATE":
                static = trailing_avg(vid, ym)
            row.update(
                needs_estimate="Y" if needs else "N",
                approval_required=("CONTROLLER" if true_amt >= CONTROLLER_AT else "REVIEWER" if true_amt >= REVIEW_AT else "NONE")
                if row["outcome"] in ("ACCRUED_THEN_RECONCILED", "ESCALATED") else "NONE",
                true_expense=true_amt, static_rules_estimate=static, trailing_avg_estimate=trailing_avg(vid, ym),
                static_error="" if static == "" else r2(static - true_amt),
                actual_invoice_ids=";".join(i["invoice_id"] for i in matching),
                actual_invoice_total=r2(sum(i["amount"] for i in matching)),
                invoice_received_dates=";".join(i["received_date"] for i in matching))
            rows.append(row)
    return rows


EXTRA_EXCEPTIONS = [
    dict(exception_key="EXC-DUPLICATE-V012", vendor_id="V012", surfaces_in_period="2026-12",
         invoice_number="7731-R", expected_state="HOLD_DO_NOT_POST", type="DUPLICATE_INVOICE",
         notes="Same PO, amount, service period and description as invoice 7731 received Dec 1."),
    dict(exception_key="EXC-LATE-V011", vendor_id="V011", surfaces_in_period="2026-12",
         invoice_number="(October placement fee, received 2026-12-09)", expected_state="ESCALATED",
         type="LATE_PRIOR_PERIOD_UNACCRUED",
         notes="$31,000 for an Oct 19 start; October is closed and nothing was accrued. Material: Controller decides treatment."),
]


def build_inbox(truth):
    """Scripted replies. Match on vendor_id + period + target_role + missing_fact; anything unmatched gets NO_RESPONSE."""
    out = []

    def add(vid, ym, role, fact, responder, hours, rtype, body, facts=None, attachments=None):
        out.append(dict(response_id=f"RSP-{len(out) + 1:03d}", vendor_id=vid, period=ym, target_role=role,
                        missing_fact=fact, responder=responder, delay_hours=hours, response_type=rtype,
                        body=body, structured_facts=facts or {}, attachments=attachments or []))

    add("V016", "2026-11", "VENDOR_BILLING", "INVOICE_WHEREABOUTS", "Northwind Business Billing", 5, "DATA",
        "Invoice NT-2249 for $5,480.00 was issued Nov 30 and emailed to ap-old@northstar.example. Re-sending to your current AP address now.",
        {"invoice_number": "NT-2249", "amount": 5480.0, "issued": "2026-11-30"}, ["INV-V016-007"])
    add("V006", "2026-12", "OPERATIONAL_OWNER", "SERVICE_RECEIVED", "E014", 20, "CONFIRMATION",
        "Confirmed. Brightwork worked 142 hours in December; I have now approved the last two timesheets (holiday backlog, sorry).",
        {"service_received": True, "hours": 142})
    add("V006", "2026-12", "REQUESTER", "SERVICE_RECEIVED", "E032", 6, "CONFIRMATION",
        "Yes, they were on site through Dec 23. I count 142 hours across the five weekly sheets. Nina still has to approve two.",
        {"service_received": True, "hours": 142})
    add("V003", "2026-12", "VENDOR_BILLING", "SCOPE_OR_RATE_CHANGE", "", 0, "NO_RESPONSE", "")
    add("V003", "2026-12", "REQUESTER", "SCOPE_OR_RATE_CHANGE", "E031", 3, "DATA",
        "Yes. Change order CO-1 added 30 seats effective Dec 10 at the same $85 rate, and we are keeping them in January.",
        {"seat_delta": 30, "effective_date": "2026-12-10", "unit_price": 85.0}, ["CO-1"])
    add("V005", "2027-01", "VENDOR_BILLING", "SCOPE_OR_RATE_CHANGE", "Tessa Byrne", 9, "DATA",
        "Per our Oct 28 renewal notice, the annual uplift effective Jan 1, 2027 is 5.5%. Your new monthly fee is $6,752.00. Notice attached.",
        {"uplift_pct": 5.5, "effective_date": "2027-01-01", "new_monthly_fee": 6752.0}, ["DOC-PAGERLOOP-UPLIFT-NOTICE"])
    add("V005", "2027-01", "OPERATIONAL_OWNER", "SCOPE_OR_RATE_CHANGE", "E011", 12, "CONFIRMATION",
        "No change in plan or users on our side. I remember a renewal email but I don't have the number.", {"scope_changed": False})
    add("V001", "2026-12", "VENDOR_BILLING", "INVOICE_WHEREABOUTS", "Amira Khan", 30, "DATA",
        "We are migrating billing systems, so December invoices will go out around Jan 11. Apologies for the delay.",
        {"expected_issue_date": "2027-01-11"})
    add("V007", "2026-11", "OPERATIONAL_OWNER", "SERVICE_RECEIVED", "E015", 8, "CONFIRMATION",
        "Light month. A few contract reviews, I'd guess around $6k but I have nothing in writing.",
        {"service_received": True, "owner_estimate": 6000.0, "documented": False})
    add("V007", "2026-12", "OPERATIONAL_OWNER", "SERVICE_RECEIVED", "E015", 10, "CONFLICTING",
        "Heavy month: they ran the financing documents. My guess is $35-45k.",
        {"service_received": True, "owner_estimate_low": 35000.0, "owner_estimate_high": 45000.0})
    add("V007", "2026-12", "VENDOR_BILLING", "INVOICE_WHEREABOUTS", "Meridian Billing Dept", 26, "CONFLICTING",
        "Final December invoice will issue around Jan 20. Unbilled WIP currently shows $58,000 before partner write-downs.",
        {"unbilled_wip": 58000.0, "expected_issue_date": "2027-01-20"})
    add("V007", "2026-12", "CONTROLLER", "TREATMENT", "E001", 4, "DECISION",
        "Accrue $40,000 (midpoint of GC range; WIP is pre-write-down). Flag for true-up when the invoice lands.",
        {"approved_amount": 40000.0, "decision": "ACCRUE_AT_OWNER_MIDPOINT"})
    add("V007", "2027-01", "OPERATIONAL_OWNER", "SERVICE_RECEIVED", "E015", 5, "CONFIRMATION",
        "Nothing from Meridian in January.", {"service_received": False})
    add("V009", "2026-12", "REQUESTER", "SCOPE_OR_RATE_CHANGE", "E017", 7, "DATA",
        "We never ordered Benefits Admin. Please dispute the $830; the base $4,150 is correct.",
        {"scope_changed": False, "disputed_amount": 830.0})
    add("V017", "2026-12", "AP_SPECIALIST", "AP_STATUS", "E003", 2, "DATA",
        "It's in the queue coded to NS-US because the invoice says Northstar Analytics, Inc. The lease is with the UK entity, so I'll ask Thames to reissue.",
        {"coded_entity": "NS-US", "correct_entity": "NS-UK"})
    add("V011", "2026-12", "OPERATIONAL_OWNER", "SERVICE_RECEIVED", "E017", 6, "CONFIRMATION",
        "No TalentBridge placements started in December. The Oct 19 data scientist hire was theirs though; has that been billed?",
        {"service_received": False, "prior_period_flag": "2026-10"})
    add("V011", "2026-12", "CONTROLLER", "TREATMENT", "E001", 5, "DECISION",
        "October is closed and $31,000 is below our restatement threshold. Book it in December as an out-of-period item and disclose in the close memo.",
        {"decision": "BOOK_CURRENT_PERIOD_OUT_OF_PERIOD", "amount": 31000.0})
    # generic owner confirmations for every obligation where service really was received
    seen = {(r["vendor_id"], r["period"], r["target_role"], r["missing_fact"]) for r in out}
    for t in truth:
        key = (t["vendor_id"], t["period"], "OPERATIONAL_OWNER", "SERVICE_RECEIVED")
        if key in seen:
            continue
        got = t["true_expense"] > 0 or t["vendor_id"] == "V010"
        add(t["vendor_id"], t["period"], "OPERATIONAL_OWNER", "SERVICE_RECEIVED",
            w.VENDOR[t["vendor_id"]]["operational_owner"], 6, "CONFIRMATION",
            f"{'Yes' if got else 'No'}, {t['vendor_name']} {'was' if got else 'was not'} in use for {t['period']}.",
            {"service_received": got})
    return out
