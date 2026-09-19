# Simplification and causality pass: binding decisions (v2)

Applies to `data/WORLD_SPEC.md` (sections in `data/spec/01..05`) and `data/DEMO_SPEC.md` (sections in `data/demo_spec/00..05`).
Specification only. Do not touch code, generated fixtures (`data/northstar/`), `data/gen/`, `data/README.md`, or `BRIEF.md`.
No new scope. Preserve: simulator, hidden future truth (`world/private`, `release_at`), human approval, replay gate (G1, G2), judge controls, Advance Time, Reset World / Reset Demo, Frozen vs Learned comparison, deterministic arithmetic, SQLite playbook memory, SSE evidence trail.
Where this file is silent, keep the existing spec's value (clock timestamps, id formats, table names, endpoint names, state names) rather than inventing a new one.
Style: plain English, no em dashes, all data labelled synthetic.

The one sentence everything must reinforce:
"A tech company estimates vendor costs before invoices arrive. TrueUp gets one wrong, the actual invoice proves it, it investigates why, a Controller approves what it learned, and that lesson prevents the same class of mistake on a different vendor."
Loop: EXECUTE -> FAIL -> DIAGNOSE -> HUMAN APPROVAL -> LEARN -> IMPROVE. Cut whatever does not serve it.

## D1. Company
- Rename Northstar Analytics to **Acme AI, Inc.** (synthetic, fictional tech company). One legal entity `ACME-US`, USD only. Delete NS-UK, FX, wrong-entity cases.
- Cost centers: exactly 3 (`ENG` Engineering, `DATA` Data and ML, `GA` General and Admin).
- Chart of accounts subset: 2000 Accounts Payable, 2100 Accrued Liabilities, plus four expense accounts (Software and Data Subscriptions, Cloud and AI Infrastructure, Professional Services, Rent). Reuse existing account numbers where they exist. Delete prepaid amortization (1300) and anything else.
- Fixture root directory name becomes `acme/` (was `northstar/`). Playbook is "the Acme AI playbook".
- Org directory: keep only the roles the demo uses (Controller, AP specialist, one budget owner per judge-facing vendor).

## D2. Vendors
Six judge-facing vendors. Keep existing vendor ids when a vendor survives or is renamed in place.

| Vendor | id | Simple meaning | Estimation basis | Baseline |
|---|---|---|---|---|
| DataForge | V001 | data/SaaS subscription | CONTRACT_PRICE (flat monthly fee) | $50,000/month, Contract Year 1; Contract Year 2 starts 2026-12-01 |
| AWS | reuse CloudHarbor's id | cloud infrastructure | USAGE_X_RATE | single rate, no tiers, no included allowance |
| ModelAPI | reuse StreamGrid's id | AI/API inference | USAGE_X_RATE | input and output token meters, two rates |
| PagerLoop | V005 | recurring SaaS, per seat | CONTRACT_PRICE (seats x per-seat price) | 120 seats x $100 = $12,000/month, no proration |
| Brightwork | V006 | consultants | HOURS_X_RATE | 142 h x $185 = $26,270 in December |
| OfficeLease | reuse Atlas Office Park's id (V014) | office rent | CONTRACT_PRICE (fixed) | monthly, no cadence tricks |

Background vendors: at most 4, chosen from the existing world, never shown in the Judge Scenario Lab, visible only as rows in the replay report and metrics. Two must match the POL-0001 predicates and have no pricing documents on file (regression controls); two must not match. Delete every other vendor, including SignalStack (V018), Meridian, PrintWorks, OfficeNest, TalentBridge, SecureLayer, Thames, PayCircle, Quantive, Northwind, Helpline unless one is picked as background.
AWS is used only as an intuitive label on synthetic data; every document carries the synthetic label.

Purchase orders: only Brightwork keeps a PO (project, not-to-exceed). SaaS, cloud, API and rent vendors have no PO. PO-1063 and its $415,000 discussion are deleted. LK11 becomes generic: no visible document lets the agent back-solve a hidden invoice amount.

Planted cases kept: on-time invoice (CLOSE_READY), missing invoice with supported accrual (AWS, ModelAPI, OfficeLease), DataForge procedure gap, PagerLoop transfer, Brightwork unexplained surcharge (ESCALATED). Delete: duplicate invoice, multi-period invoice, conflicting-evidence (Meridian), mismatch/credit memo, change-order seat expansion, tiered overage learning split, retired-mailbox outreach, no-response outreach, never-accrued prior period, prepaid.

## D3. DataForge learning causality (the main fix)
The old spec let `ContractFeatures` hold `pricing_structure=ANNIVERSARY_ESCALATOR`, `has_scheduled_price_change=true` and knowledge of PS-001 before the December failure. Remove that everywhere.

- PS-001 (DataForge Pricing Schedule) exists in the company contract repository under `runtime/visible/` from the start. It is visible company data, not hidden truth. It is a separate related document of CTR-001, not part of the order form.
- Playbook v1.0 defines, per estimation basis, an **evidence plan** for CLOSE mode. For CONTRACT_PRICE it is: vendor master, last 3 invoices, contract order form (primary document only), service confirmation, AP queue. It does not include related pricing documents.
- The tool gateway enforces the evidence plan deterministically: in CLOSE mode a tool call outside the active playbook's plan is refused and logged. `list_related_documents(contract_id)` and `open_document(doc_id)` for related documents are allowed only in INVESTIGATE mode, or in CLOSE mode when an ACTIVE policy requires them. This is what makes Frozen and Learned differ, and what makes Reject have a real consequence.
- At v1.0, `ContractFeatures` is built from the order form only: `spend_type=RECURRING`, `estimation_basis=CONTRACT_PRICE`, `unit_price=50000.00`, `price_label="Contract Year 1"`, term dates, billing frequency. No `pricing_structure`, no `has_scheduled_price_change`, no reference to PS-001.
- December close, what baseline sees: DataForge is an active recurring subscription; prior invoices are $50,000; order form shows $50,000 / Contract Year 1; service was received; December invoice is missing. It accrues $50,000 (deterministic estimator).
- Hidden invoice (released by Advance Time) = 50,000 x (1 + judge-selected increase). Deterministic true-up detects the miss.
- Only then INVESTIGATE mode expands retrieval: invoice -> contract CTR-001 -> related pricing documents -> PS-001. The LLM extracts a typed `PriceTerm {basis, value, effective_from, source_doc_id, quote}`; deterministic code checks the quote is a verbatim substring of the document text and computes the effective price. The LLM never computes the amount.
- Diagnosis: root cause `PROCEDURE_GAP`, detail `EFFECTIVE_PRICE_NOT_RETRIEVED` ("effective pricing was not retrieved before estimation"). Root-cause taxonomy for the demo: `PROCEDURE_GAP`, `UNKNOWN`. Delete SCHEDULED_ESCALATOR, TIERED_OVERAGE_RATE, CHANGE_ORDER_SEAT_EXPANSION as learned root causes.

### POL-0001 (redefined), VERIFY_EFFECTIVE_CONTRACT_PRICE
- Plain text: "For recurring contract-based spend where pricing may vary by contract period, retrieve and validate the price effective for the current service period before estimation."
- trigger: obligation needs an estimate (invoice missing at cutoff).
- predicates, all observable before any pricing document is opened: `spend_type = RECURRING` AND `estimation_basis = CONTRACT_PRICE`. No `vendor_id`, no percent, no dollar amount, no `has_scheduled_price_change` (that is a result of retrieval, not a pre-retrieval feature; remove it from the G1 whitelist).
- required evidence: `EFFECTIVE_PRICE_CHECK` for the service period, produced by `resolve_effective_price(contract_id, service_period)`: list related pricing documents (pricing schedule, amendment, vendor price notice), extract PriceTerms, pick the one effective for the service period. Result is either a PriceTerm with source quote, or `NO_PRICING_DOCUMENTS_ON_FILE` (then the order form price stands and nothing changes).
- behavior change: the evidence plan for matching obligations gains the related-documents step; the estimator's unit price comes from the effective PriceTerm; the verifier returns BLOCK on an ACCRUE proposal that lacks the check; conflicting or unparseable terms give OUTREACH_REQUIRED.
- approval status and version as in the existing lifecycle: CANDIDATE -> (G1, G2) -> Controller APPROVE -> ACTIVE in playbook 1.1, or REJECT -> playbook stays 1.0.
- Matches DataForge, PagerLoop, OfficeLease and the two background regression controls. Does not match AWS, ModelAPI, Brightwork.
- G2 replay report must show: cases replayed, cases matched by predicates, cases changed (DataForge December only, error to $0), regressions 0 (OfficeLease and background controls resolve to NO_PRICING_DOCUMENTS_ON_FILE, amount unchanged), signed bias before and after.

## D4. Three hero scenarios only
- **SCN-A Learnable failure, DataForge (V001).** Control: effective price increase 0 / 5 / 8 / 12 percent. PS-001 rate becomes 50,000 / 52,500 / 54,000 / 56,000; hidden December invoice the same; baseline accrual stays 50,000; tolerance max(500, 2% of accrued) = 1,000; variance 0 / 2,500 / 4,000 / 6,000. 0% gives the no-miss branch. Default walkthrough value 8%. Controller APPROVE or REJECT.
- **SCN-B Prove transfer, PagerLoop (V005).** TrueUp has never accrued PagerLoop (its invoices always arrived before cutoff). For January 2027 the invoice is late. Structure differs from DataForge: per-seat pricing, and the authoritative new rate is in a **vendor renewal price notice** (a related document of CTR-005, document type VENDOR_PRICE_NOTICE, not a pricing schedule), effective for service from 2027-01-01. Control: per-seat price change 0 / 10 / 15 / 25 percent -> $100 / $110 / $115 / $125 per seat -> 12,000 / 13,200 / 13,800 / 15,000. Tolerance 500. Frozen v1.0 uses the order form: accrues 12,000, misses by 0 / 1,200 / 1,800 / 3,000. Learned 1.1: POL-0001 predicates match, the gateway allows related documents, it finds the notice and accrues the effective amount, variance 0. It books the right number; it does not merely block. If the Controller rejected in SCN-A, both arms run playbook 1.0 and are identical. Default walkthrough value 15%. Replace every SignalStack reference.
- **SCN-C Know when not to learn, Brightwork (V006).** Control: unexplained surcharge 0 / 900 / 2,400 / 6,000 added as an invoice line with no basis in the contract, PO, or timesheets. Accrual 26,270, tolerance 525.40. Investigation finds no supporting document: root cause UNKNOWN, outcome ESCALATED, EscalationNote to the Controller, no candidate policy. Default 2,400. Remove the Meridian alternate.

## D5. Judge Scenario Lab: exactly five controls
`CTL-DATAFORGE-INCREASE`, `CTL-AWS-USAGE`, `CTL-MODELAPI-USAGE`, `CTL-PAGERLOOP-PRICE`, `CTL-BRIGHTWORK-SURCHARGE`. Delete the other old controls (effective date, cadence, terminate, delay invoice, service confirmation missing, duplicate invoice) and the "lab extras" tier and cut order.
- AWS and ModelAPI usage level: Low 0.7x / Normal 1.0x / High 1.3x / Spike 1.6x. The mutation regenerates the visible daily usage meter and the hidden invoice = metered usage x contract rate. Expected result: ACCRUED, variance $0, nothing to learn. Their job is to show that any judge input flows through deterministic code and that usage-based spend does not match POL-0001.
- Each control is a dropdown on one vendor card. The baseline value is labelled "(current)" and Apply is disabled on it. No free-form fields.
- Every mutation is a ScenarioOverride on generator parameters; the simulator re-derives visible records and hidden events and truth from the same pricing functions. The judge never sets an expected error, a variance, or an invoice amount.
- A control locks once a close run has consumed its target obligation. PagerLoop stays editable until the transfer close runs, so the judge can configure it after the SCN-A decision.
- Worked example to keep verbatim in the mutation section: judge sets DataForge increase to 8% -> contract pricing schedule effective rate $54,000 -> hidden future invoice $54,000 -> baseline accrual still $50,000 -> true-up +$4,000.

## D6. Human-in-the-loop proof
Visible lifecycle: failure -> investigation -> proposed policy -> replay/regression test -> Controller APPROVE / REJECT -> versioned playbook -> later behavior changes. Rejection consequence: Learned arm equals Frozen arm on PagerLoop, byte-identical amounts and tool calls.

## D7. Three-minute flow
Rewrite the 180 s beat table around: reset, judge picks DataForge increase, what-changed diff (PS-001 and only PS-001 on the visible side), Run Close (evidence trail shows the v1.0 plan, no pricing document opened), Approve JE, Advance Time, miss highlighted, investigation trail (invoice -> contract -> related documents -> PS-001 with quote), PROCEDURE_GAP, candidate POL-0001, replay report, judge presses APPROVE or REJECT, judge picks PagerLoop price change, Frozen vs Learned side by side, Advance Time, result. SCN-C is a 20 to 30 second closing beat or Q&A backup. Keep two real judge choices minimum, a fallback, and the 60 s expo variant.

## D8. Consequences for the old open decisions
PO-1063 amount, LK11 scoping, CTL-CADENCE on closed November, CTL-DUP-INVOICE on V008/V012: all moot, delete. No-op baseline dropdown values: resolved by D5. Run-id restart after Reset World: accept as is.
