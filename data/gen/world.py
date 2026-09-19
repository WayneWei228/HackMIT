"""Static definition of the simulated company: Northstar Analytics.

Everything here is invented. Close periods are 2026-11, 2026-12 and 2027-01;
2026-05..2026-10 is history. Close cutoff is the 5th of the following month.
"""
from datetime import date

HISTORY = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
CLOSE_PERIODS = ["2026-11", "2026-12", "2027-01"]
ALL_MONTHS = HISTORY + CLOSE_PERIODS
CUTOFF_DAY = 5  # invoices received after the 5th of next month miss the close

COMPANY = {
    "name": "Northstar Analytics, Inc.",
    "description": "B2B analytics software company, ~260 employees",
    "base_currency": "USD",
    "entities": [
        {"entity_id": "NS-US", "name": "Northstar Analytics, Inc.", "country": "US"},
        {"entity_id": "NS-UK", "name": "Northstar Analytics UK Ltd", "country": "GB"},
    ],
    "cost_centers": [
        {"id": "CC-100", "name": "Data Engineering"}, {"id": "CC-110", "name": "Platform / SRE"},
        {"id": "CC-120", "name": "Customer Support"}, {"id": "CC-130", "name": "Sales"},
        {"id": "CC-140", "name": "PMO"}, {"id": "CC-150", "name": "Legal"},
        {"id": "CC-160", "name": "Workplace"}, {"id": "CC-170", "name": "People / HR"},
        {"id": "CC-180", "name": "Security"}, {"id": "CC-190", "name": "Marketing"},
        {"id": "CC-200", "name": "Business Intelligence"}, {"id": "CC-210", "name": "IT"},
        {"id": "CC-300", "name": "UK Operations"},
    ],
    "chart_of_accounts": [
        {"account": "1000", "name": "Cash", "type": "asset"},
        {"account": "1300", "name": "Prepaid Expenses", "type": "asset"},
        {"account": "2000", "name": "Accounts Payable", "type": "liability"},
        {"account": "2100", "name": "Accrued Expenses", "type": "liability"},
        {"account": "6100", "name": "Data Services Expense", "type": "expense"},
        {"account": "6110", "name": "Cloud Hosting Expense", "type": "expense"},
        {"account": "6120", "name": "Software Subscriptions", "type": "expense"},
        {"account": "6200", "name": "Professional Services", "type": "expense"},
        {"account": "6210", "name": "Legal Fees", "type": "expense"},
        {"account": "6300", "name": "Rent and Facilities", "type": "expense"},
        {"account": "6310", "name": "Facilities Maintenance", "type": "expense"},
        {"account": "6400", "name": "Recruiting Fees", "type": "expense"},
        {"account": "6500", "name": "Marketing Programs", "type": "expense"},
        {"account": "6600", "name": "Telecom", "type": "expense"},
    ],
    "close_calendar": [
        {"period": "2026-11", "cutoff": "2026-12-05", "status": "OPEN"},
        {"period": "2026-12", "cutoff": "2027-01-05", "status": "OPEN"},
        {"period": "2027-01", "cutoff": "2027-02-05", "status": "OPEN"},
    ],
    "closed_periods": HISTORY,
}

# (id, name, title, role tag, cost center, entity)
EMPLOYEES = [
    ("E001", "Dana Whitfield", "Controller", "CONTROLLER", None, "NS-US"),
    ("E002", "Marcus Oyelaran", "Accounting Manager", "ACCOUNTING_MANAGER", None, "NS-US"),
    ("E003", "Sofia Brandt", "AP Specialist", "AP_SPECIALIST", None, "NS-US"),
    ("E004", "Ken Ito", "Senior Close Accountant", "CLOSE_ACCOUNTANT", None, "NS-US"),
    ("E005", "Laila Haddad", "FP&A Manager", "FPA", None, "NS-US"),
    ("E006", "Tom Reyes", "Treasury Analyst", "TREASURY", None, "NS-US"),
    ("E010", "Priya Raman", "Head of Data", "BUDGET_OWNER", "CC-100", "NS-US"),
    ("E011", "Sam Okafor", "SRE Lead", "BUDGET_OWNER", "CC-110", "NS-US"),
    ("E012", "Maria Santos", "Head of Support", "BUDGET_OWNER", "CC-120", "NS-US"),
    ("E013", "Jordan Blake", "VP Sales", "BUDGET_OWNER", "CC-130", "NS-US"),
    ("E014", "Nina Petrov", "Head of PMO", "BUDGET_OWNER", "CC-140", "NS-US"),
    ("E015", "Rachel Kim", "General Counsel", "BUDGET_OWNER", "CC-150", "NS-US"),
    ("E016", "Omar Farouk", "Workplace Manager", "BUDGET_OWNER", "CC-160", "NS-US"),
    ("E017", "Grace Liu", "HR Director", "BUDGET_OWNER", "CC-170", "NS-US"),
    ("E018", "Victor Hale", "CISO", "BUDGET_OWNER", "CC-180", "NS-US"),
    ("E019", "Elena Rossi", "Marketing Director", "BUDGET_OWNER", "CC-190", "NS-US"),
    ("E020", "Dev Patel", "BI Lead", "BUDGET_OWNER", "CC-200", "NS-US"),
    ("E021", "Chris Novak", "IT Manager", "BUDGET_OWNER", "CC-210", "NS-US"),
    ("E022", "Harriet Cole", "UK General Manager", "BUDGET_OWNER", "CC-300", "NS-UK"),
    ("E030", "Ben Adler", "Data Platform Engineer", "REQUESTER", "CC-100", "NS-US"),
    ("E031", "Yuki Tanaka", "Support Operations Analyst", "REQUESTER", "CC-120", "NS-US"),
    ("E032", "Luis Moreno", "Program Manager", "REQUESTER", "CC-140", "NS-US"),
]


def _v(vid, name, category, account, cc, owner, requester, contact, contact_email,
       model, entity="NS-US", po=None, terms="Net 30", notes=""):
    return {
        "vendor_id": vid, "name": name, "category": category, "gl_account": account,
        "cost_center": cc, "legal_entity_id": entity, "operational_owner": owner,
        "requester": requester, "billing_contact": contact, "billing_email": contact_email,
        "pricing_model": model, "contract_id": "CTR-" + vid[1:], "po_id": po,
        "payment_terms": terms, "notes": notes,
    }


VENDORS = [
    _v("V001", "DataForge Inc.", "SAAS_OR_DATA", "6100", "CC-100", "E010", "E030",
       "Amira Khan", "billing@dataforge.example", "FIXED_MONTHLY", po="PO-1029"),
    _v("V002", "CloudHarbor LLC", "CLOUD_USAGE", "6110", "CC-110", "E011", "E011",
       "CloudHarbor Billing", "ar@cloudharbor.example", "USAGE_TIERED", po="PO-1011"),
    _v("V003", "Helpline Desk Co.", "SAAS_OR_DATA", "6120", "CC-120", "E012", "E031",
       "Paul Wenger", "invoices@helplinedesk.example", "PER_SEAT", po="PO-1017"),
    _v("V004", "Lumen CRM Corp.", "SAAS_OR_DATA", "6120", "CC-130", "E013", "E013",
       "Lumen Accounts", "accounts@lumencrm.example", "FIXED_MONTHLY", po="PO-1008"),
    _v("V005", "PagerLoop Inc.", "SAAS_OR_DATA", "6120", "CC-110", "E011", "E011",
       "Tessa Byrne", "billing@pagerloop.example", "FIXED_MONTHLY", po="PO-1021"),
    _v("V006", "Brightwork Consulting Group", "CONSULTING", "6200", "CC-140", "E014", "E032",
       "Henry Osei", "finance@brightwork.example", "TIME_AND_MATERIALS", po="PO-1042"),
    _v("V007", "Meridian Legal LLP", "LEGAL", "6210", "CC-150", "E015", "E015",
       "Meridian Billing Dept", "billing@meridianlegal.example", "HOURLY_NO_CAP",
       notes="Engagement letter only; no PO; invoices irregular."),
    _v("V008", "OfficeNest Properties", "RENT", "6300", "CC-160", "E016", "E016",
       "OfficeNest AR", "ar@officenest.example", "FIXED_MONTHLY_ADVANCE", terms="Due on 1st"),
    _v("V009", "PayCircle Inc.", "SAAS_OR_DATA", "6120", "CC-170", "E017", "E017",
       "PayCircle Billing", "billing@paycircle.example", "FIXED_MONTHLY", po="PO-1005"),
    _v("V010", "SecureLayer Systems", "SAAS_OR_DATA", "6120", "CC-180", "E018", "E018",
       "SecureLayer AR", "ar@securelayer.example", "ANNUAL_PREPAID", po="PO-1033"),
    _v("V011", "TalentBridge Partners", "RECRUITING", "6400", "CC-170", "E017", "E017",
       "Carla Mendes", "carla.mendes@talentbridge.example", "CONTINGENT_PER_HIRE"),
    _v("V012", "PrintWorks Studio", "MARKETING", "6500", "CC-190", "E019", "E019",
       "PrintWorks Accounts", "accounts@printworks.example", "PER_JOB_PO"),
    _v("V013", "StreamGrid Networks", "CLOUD_USAGE", "6110", "CC-110", "E011", "E011",
       "StreamGrid Billing", "billing@streamgrid.example", "USAGE_TIERED", po="PO-1014"),
    _v("V014", "Atlas Facilities Services", "FACILITIES", "6310", "CC-160", "E016", "E016",
       "Atlas AR", "ar@atlasfacilities.example", "FIXED_QUARTERLY_ARREARS", po="PO-1019"),
    _v("V015", "Quantive BI Ltd.", "SAAS_OR_DATA", "6120", "CC-200", "E020", "E020",
       "Quantive Billing", "billing@quantivebi.example", "FIXED_MONTHLY_ADVANCE_MIDMONTH",
       po="PO-1051"),
    _v("V016", "Northwind Telecom", "TELECOM", "6600", "CC-210", "E021", "E021",
       "Northwind Business Billing", "bizbilling@northwindtel.example", "VARIABLE_MONTHLY"),
    _v("V017", "Thames Workspace Ltd", "RENT", "6300", "CC-300", "E022", "E022",
       "Thames Workspace Accounts", "accounts@thamesworkspace.example", "FIXED_MONTHLY",
       entity="NS-UK"),
]
VENDOR = {v["vendor_id"]: v for v in VENDORS}

# ---- pricing facts (the truth the contracts encode) -------------------------
CLOUDHARBOR = {"commit_fee": 36000.0, "included_hours": 300000, "base_rate": 0.12, "overage_rate": 0.15}
CLOUDHARBOR_HOURS = dict(zip(ALL_MONTHS, [262000, 270000, 281000, 275000, 288000, 291000,
                                          296000, 352000, 310000]))
STREAMGRID = {"commit_fee": 8000.0, "included_gb": 400000, "base_rate": 0.02, "overage_rate": 0.03}
STREAMGRID_GB = dict(zip(ALL_MONTHS, [331000, 342000, 355000, 348000, 362000, 371000,
                                      350000, 390000, 520000]))
HELPLINE = {"seat_price": 85.0, "base_seats": 120, "co_seats": 30, "co_effective": date(2026, 12, 10)}
BRIGHTWORK = {"rate": 185.0, "po_amount": 120000.0,
              "hours": {"2026-10": 150, "2026-11": 160, "2026-12": 142, "2027-01": 96}}
MERIDIAN_FEES = {"2026-05": 8500.0, "2026-07": 22300.0, "2026-08": 4100.0, "2026-10": 12750.0,
                 "2026-11": 6200.0, "2026-12": 41870.0}
NORTHWIND_FEES = dict(zip(ALL_MONTHS, [5350.0, 5410.0, 5395.0, 5520.0, 5460.0, 5430.0,
                                       5480.0, 5515.0, 5440.0]))
# hires: (employee start date, role, base salary, fee pct)
TALENTBRIDGE_HIRES = [
    (date(2026, 6, 8), "Senior Backend Engineer", 135000, 0.20),
    (date(2026, 10, 19), "Staff Data Scientist", 155000, 0.20),
    (date(2026, 11, 16), "Engineering Manager", 150000, 0.20),
    (date(2027, 1, 11), "Product Designer", 140000, 0.20),
]
PRINTWORKS_JOBS = [  # (service month, po, description, amount)
    ("2026-07", "PO-0977", "Summer conference booth graphics", 5400.0),
    ("2026-09", "PO-1002", "Customer summit print collateral", 6950.0),
    ("2026-11", "PO-1046", "Year-end campaign brochures and banners", 7850.0),
    ("2027-01", "PO-1058", "Sales kickoff signage", 3200.0),
]
FIXED_FEES = {  # vendor -> list of (effective_from YYYY-MM, monthly fee)
    "V001": [("2025-12", 50000.0), ("2026-12", 52500.0)],   # 5% escalator on anniversary
    "V004": [("2025-01", 18000.0), ("2027-01", 18720.0)],   # 4% uplift every Jan 1
    "V005": [("2025-03", 6400.0), ("2027-01", 6752.0)],     # vendor-notified uplift, 5.5%
    "V008": [("2024-01", 22500.0)],
    "V009": [("2025-06", 4150.0)],
    "V014": [("2025-02", 4500.0)],
    "V017": [("2025-09", 6900.0)],
}
SECURELAYER = {"annual_fee": 96000.0, "term_start": date(2026, 8, 1), "term_end": date(2027, 7, 31)}
QUANTIVE = {"monthly_fee": 9300.0, "start": date(2026, 12, 15)}
