"""The demo company: Orbit Labs, Inc.

Two clearly separated sources of truth, so a reviewer can always tell which rows
came from a document and which the simulator invented:

  PDF_DERIVED  - read out of the 14 synthetic PDFs in seed/pdf/. These drive the
                 December 2026 live close and the Evidence-Agent extraction demo.
  SYNTHETIC    - generated here: eleven months of prior closes, non-PO card
                 spend, contract escalators, the held-out vendor, and the
                 deliberately-unexplainable case. The PDFs contain none of these,
                 and the spec needs all of them.
"""
from __future__ import annotations

from decimal import Decimal

ENTITY = "ORBIT-LABS"
CURRENCY = "USD"

ACCRUAL_LIABILITY = "2150-ACCRUED-LIAB"

ALLOWED_GL_ACCOUNTS = [
    "6100-SOFTWARE", "6200-CLOUD", "6300-MARKETING", "6400-IT-EQUIPMENT",
    "6500-TRAVEL", "6600-OFFICE", "6700-PROF-SERVICES", ACCRUAL_LIABILITY,
]

PEOPLE = {
    "P-CONTROLLER": {"name": "Jordan Lee", "title": "VP Finance / Controller",
                     "email": "jordan.lee@orbitlabs.example", "role": "CONTROLLER"},
    "P-AP": {"name": "Riley Nguyen", "title": "AP Manager",
             "email": "riley.nguyen@orbitlabs.example", "role": "AP_OWNER"},
    "P-PROC": {"name": "Morgan Chen", "title": "IT Procurement",
               "email": "morgan.chen@orbitlabs.example", "role": "PROCUREMENT_OWNER"},
    "P-ENG": {"name": "Sam Ortiz", "title": "Director of Engineering",
              "email": "sam.ortiz@orbitlabs.example", "role": "SERVICE_OWNER"},
    "P-MKT": {"name": "Avery Patel", "title": "VP Marketing",
              "email": "avery.patel@orbitlabs.example", "role": "SERVICE_OWNER"},
    "P-IT": {"name": "Taylor Brooks", "title": "IT Operations",
             "email": "taylor.brooks@orbitlabs.example", "role": "PO_OWNER"},
}

# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------
#   origin: PDF  -> sourced from the fixture documents
#           SYNTH-> generated for history / coverage the PDFs don't provide
VENDORS = [
    # --- from the PDF corpus -------------------------------------------------
    dict(vendor_id="V001", vendor_name="Mintlify", origin="PDF",
         vendor_category="SOFTWARE", billing_cadence="MONTHLY",
         email="billing@mintlify.example", gl="6100-SOFTWARE", cc="CC-ENG"),
    dict(vendor_id="V002", vendor_name="OpenAI", origin="PDF",
         vendor_category="API_SERVICES", billing_cadence="MONTHLY",
         email="accounts@openai.example", gl="6200-CLOUD", cc="CC-ENG"),
    dict(vendor_id="V003", vendor_name="ASUS", origin="PDF",
         vendor_category="HARDWARE", billing_cadence="PER_ORDER",
         email="ar@asus.example", gl="6400-IT-EQUIPMENT", cc="CC-IT"),
    dict(vendor_id="V004", vendor_name="Meta", origin="PDF",
         vendor_category="ADVERTISING", billing_cadence="PER_CAMPAIGN",
         email="billing@meta.example", gl="6300-MARKETING", cc="CC-MKT"),
    # --- synthetic, to give the learning loop something to learn from --------
    dict(vendor_id="V005", vendor_name="Snowflake", origin="SYNTH",
         vendor_category="DATA_PLATFORM", billing_cadence="MONTHLY",
         email="ar@snowflake.example", gl="6200-CLOUD", cc="CC-DATA"),
    dict(vendor_id="V006", vendor_name="Datadog", origin="SYNTH",
         vendor_category="OBSERVABILITY", billing_cadence="MONTHLY",
         email="ar@datadog.example", gl="6200-CLOUD", cc="CC-ENG"),
    dict(vendor_id="V007", vendor_name="Twilio", origin="SYNTH",
         vendor_category="COMMUNICATIONS", billing_cadence="MONTHLY",
         email="ar@twilio.example", gl="6200-CLOUD", cc="CC-ENG"),
    dict(vendor_id="V008", vendor_name="Confluent", origin="SYNTH",
         vendor_category="DATA_PLATFORM", billing_cadence="MONTHLY",
         email="ar@confluent.example", gl="6200-CLOUD", cc="CC-DATA"),
    dict(vendor_id="V009", vendor_name="AWS", origin="SYNTH",
         vendor_category="CLOUD", billing_cadence="MONTHLY",
         email="ar@aws.example", gl="6200-CLOUD", cc="CC-ENG"),
    # Priced against a supply agreement whose rate DISAGREES with the PO line.
    # Exists to exercise the contract-vs-PO conflict route.
    dict(vendor_id="V011", vendor_name="Dell", origin="SYNTH",
         vendor_category="HARDWARE", billing_cadence="PER_ORDER",
         email="ar@dell.example", gl="6400-IT-EQUIPMENT", cc="CC-IT"),
    # Onboarded in December: no usage history at all, and its first meter lands
    # after the cutoff. No evidence AND no run-rate to fall back on, which is the
    # only honest route to outreach.
    dict(vendor_id="V012", vendor_name="Vanta", origin="SYNTH",
         vendor_category="COMPLIANCE", billing_cadence="MONTHLY",
         email="ar@vanta.example", gl="6100-SOFTWARE", cc="CC-OPS"),
    # The card program itself: the monthly statement is the AP document that
    # eventually grades every non-PO card accrual.
    dict(vendor_id="V010", vendor_name="Brex Card Program", origin="SYNTH",
         vendor_category="CARD_PROGRAM", billing_cadence="MONTHLY",
         email="statements@brex.example", gl="6600-OFFICE", cc="CC-OPS"),
]

# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------
# `escalator_percent` + `escalator_effective_date` are the trap. A naive estimator
# reads base_rate off the effective version and never checks whether an escalator
# clause has already kicked in. That is the repeatable failure the historical
# backtest is designed to surface.
#
# HELD_OUT vendors are excluded from rule *derivation* — they only appear in the
# live close, to prove a learned rule generalises rather than memorises.
CONTRACTS = [
    dict(contract_id="CTR-001", vendor_id="V001", origin="PDF",
         name="Mintlify team documentation plan",
         billing_model="FIXED_RECURRING", base_rate=Decimal("1200"), rate_unit="month",
         versions=[dict(v=1, start="2026-01-01", end="2026-12-31",
                        escalator=None, escalator_date=None)],
         service_owner="P-ENG", procurement_owner="P-PROC", pdf="CTR-001"),

    dict(contract_id="CTR-002", vendor_id="V002", origin="PDF",
         name="OpenAI API usage agreement",
         billing_model="USAGE_BASED", base_rate=Decimal("0.02"), rate_unit="API usage unit",
         versions=[dict(v=1, start="2026-01-01", end="2026-12-31",
                        escalator=None, escalator_date=None)],
         service_owner="P-ENG", procurement_owner="P-PROC", pdf="CTR-002"),

    # --- the primary learning scenario --------------------------------------
    # v2 is an amendment that records a 5% escalator clause WITHOUT restating the
    # rate. base_rate still reads 0.45; the true billed rate from July is 0.4725.
    dict(contract_id="CTR-005", vendor_id="V005", origin="SYNTH",
         name="Snowflake compute credits",
         billing_model="USAGE_BASED", base_rate=Decimal("0.45"), rate_unit="credit",
         versions=[
             dict(v=1, start="2026-01-01", end="2026-06-30", escalator=None, escalator_date=None),
             dict(v=2, start="2026-07-01", end="2026-12-31",
                  escalator=Decimal("5"), escalator_date="2026-07-01"),
         ],
         service_owner="P-ENG", procurement_owner="P-PROC",
         text_extra="Annual price adjustment: rates increase 5% effective 2026-07-01."),

    dict(contract_id="CTR-006", vendor_id="V006", origin="SYNTH",
         name="Datadog host monitoring",
         billing_model="USAGE_BASED", base_rate=Decimal("18.00"), rate_unit="host-month",
         versions=[
             dict(v=1, start="2026-01-01", end="2026-08-31", escalator=None, escalator_date=None),
             dict(v=2, start="2026-09-01", end="2026-12-31",
                  escalator=Decimal("8"), escalator_date="2026-09-01"),
         ],
         service_owner="P-ENG", procurement_owner="P-PROC",
         text_extra="Rates increase 8% effective 2026-09-01 per Section 4."),

    # --- negative case: usage-based, NO escalator. A learned escalator rule
    #     must NOT fire here, and replay must prove it.
    dict(contract_id="CTR-007", vendor_id="V007", origin="SYNTH",
         name="Twilio messaging",
         billing_model="USAGE_BASED", base_rate=Decimal("0.0075"), rate_unit="message",
         versions=[dict(v=1, start="2026-01-01", end="2026-12-31",
                        escalator=None, escalator_date=None)],
         service_owner="P-ENG", procurement_owner="P-PROC"),

    # --- HELD OUT: same escalator shape, never used to derive a rule ---------
    dict(contract_id="CTR-008", vendor_id="V008", origin="SYNTH", held_out=True,
         name="Confluent streaming",
         billing_model="USAGE_BASED", base_rate=Decimal("2.40"), rate_unit="GB",
         versions=[
             dict(v=1, start="2026-01-01", end="2026-09-30", escalator=None, escalator_date=None),
             dict(v=2, start="2026-10-01", end="2026-12-31",
                  escalator=Decimal("6"), escalator_date="2026-10-01"),
         ],
         service_owner="P-ENG", procurement_owner="P-PROC",
         text_extra="Rates increase 6% effective 2026-10-01."),

    # --- the contract-vs-PO pricing conflict --------------------------------
    # The supply agreement says $2,100 per workstation; PO-011 was raised at
    # $2,400. TrueUp must not silently pick one.
    dict(contract_id="CTR-011", vendor_id="V011", origin="SYNTH",
         name="Dell workstation supply agreement",
         billing_model="PER_ORDER", base_rate=Decimal("2100.00"), rate_unit="workstation",
         versions=[dict(v=1, start="2026-01-01", end="2026-12-31",
                        escalator=None, escalator_date=None)],
         service_owner="P-IT", procurement_owner="P-PROC",
         text_extra="Unit pricing is fixed at $2,100.00 per workstation for the term."),

    # --- newly onboarded, no history ----------------------------------------
    dict(contract_id="CTR-012", vendor_id="V012", origin="SYNTH",
         name="Vanta compliance monitoring",
         billing_model="USAGE_BASED", base_rate=Decimal("31.00"), rate_unit="monitored asset",
         versions=[dict(v=1, start="2026-12-01", end="2027-11-30",
                        escalator=None, escalator_date=None)],
         service_owner="P-IT", procurement_owner="P-PROC"),

    # --- the deliberately unexplainable case --------------------------------
    dict(contract_id="CTR-009", vendor_id="V009", origin="SYNTH",
         name="AWS infrastructure",
         billing_model="USAGE_BASED", base_rate=Decimal("1.00"), rate_unit="unit",
         versions=[dict(v=1, start="2026-01-01", end="2026-12-31",
                        escalator=None, escalator_date=None)],
         service_owner="P-ENG", procurement_owner="P-PROC"),
]

HELD_OUT_VENDORS = {"V008"}

# Monthly usage volumes. Deterministic, not random, so two runs of the backtest
# produce identical numbers and a diff means a real behaviour change.
USAGE_BASE = {
    "V012": 420,       # Vanta - first period is December 2026
    "V002": 700_000,   # OpenAI - matches the invoice PDFs (710k Sep, 775k Nov)
    "V005": 120_000,   # Snowflake credits
    "V006": 300,       # Datadog hosts
    "V007": 900_000,   # Twilio messages
    "V008": 4_000,     # Confluent GB
    "V009": 41_000,    # AWS units
}

# Exact quantities the PDFs state, so the fixture months reconcile to the documents.
PDF_USAGE_OVERRIDES = {
    ("V002", "2026-09"): 710_000,
    ("V002", "2026-10"): 742_500,
    ("V002", "2026-11"): 775_000,
    ("V002", "2026-12"): 930_000,
}

# The surprise. In 2026-08 AWS bills a reserved-capacity adjustment that no
# internal record predicts or explains. TrueUp must escalate this, not invent a
# rule to cover it.
UNEXPLAINED_EVENT = {
    "vendor_id": "V009",
    "period": "2026-08",
    "extra_amount": Decimal("12400.00"),
    "invoice_note": "Includes reserved capacity commitment adjustment (ref RI-TRUEUP-Q3).",
}

# Vendors that invoice fast enough to land before the accrual cutoff. These are
# the correct NO-ACCRUAL cases and guard against double-counting.
FAST_INVOICERS = {"V007"}

# Months where the usage meter does not land before the accrual cutoff. Datadog's
# meter is chronically late, which forces a run-rate fallback and produces the
# second learnable pattern.
LATE_USAGE_METERS = {
    ("V006", "2026-03"), ("V006", "2026-05"), ("V006", "2026-07"),
    # Vanta's very first meter is late. With no history either, there is nothing
    # to fall back on — so the only correct move is to ask a human.
    ("V012", "2026-12"),
}

# Non-PO card spend merchants
CARD_MERCHANTS = [
    ("GitHub", "6100-SOFTWARE", "CC-ENG", "P-ENG"),
    ("Figma", "6100-SOFTWARE", "CC-MKT", "P-MKT"),
    ("United Airlines", "6500-TRAVEL", "CC-ENG", "P-ENG"),
    ("WeWork", "6600-OFFICE", "CC-OPS", "P-IT"),
    ("Notion", "6100-SOFTWARE", "CC-OPS", "P-IT"),
    ("Amazon Business", "6600-OFFICE", "CC-OPS", "P-IT"),
]

APPROVAL_THRESHOLDS = {
    "de_minimis": "500.00",          # below this, no accrual at all
    "controller_review": "25000.00",  # at or above this, Controller must approve
    "material_variance": "5000.00",   # true-up variance requiring adjustment
    "material_variance_pct": "10.0",
}

POLICY_RULES = {
    "allow_historical_run_rate_fallback": True,
    "historical_run_rate_max_amount": "15000.00",
    "require_evidence_for_usage": True,
    "block_unbalanced_entries": True,
    "block_closed_period_posting": True,
    "simulated_posting_only": True,
}
