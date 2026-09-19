# v2 shared contract: every value the ten section writers must use

Binding. Derived from `SIMPLIFY_BRIEF.md`, which overrides both existing specs. Where this file pins a value, no writer may invent a different one. Where this file is silent, keep the existing spec's value.

All data is synthetic. Every rendered document begins with the line:
`SYNTHETIC DATA - ACME AI, INC. (FICTIONAL). NOT A REAL COMPANY OR VENDOR.`

Applies to `data/spec/01..05` (assembled as `data/WORLD_SPEC.md`) and `data/demo_spec/00..05` (assembled as `data/DEMO_SPEC.md`).

---

## 1. Company

Name: **Acme AI, Inc.** One legal entity `ACME-US`, US, USD. No FX, no second entity.
Fixture root directory: `data/acme/` (was `data/northstar/`). Email domain `acme.example`. The playbook is "the Acme AI playbook".

### 1.1 Cost centers (exactly 3)

| cost_center | name |
|---|---|
| `ENG` | Engineering |
| `DATA` | Data and ML |
| `GA` | General and Admin |

### 1.2 Chart of accounts (exactly 6)

| account | name | type |
|---|---|---|
| 2000 | Accounts Payable | liability |
| 2100 | Accrued Liabilities | liability |
| 6110 | Cloud and AI Infrastructure | expense |
| 6120 | Software and Data Subscriptions | expense |
| 6200 | Professional Services | expense |
| 6300 | Rent | expense |

`entry_type` enum: `INVOICE`, `ACCRUAL`, `ACCRUAL_REVERSAL`, `TRUE_UP`. `posted_by` is an employee id or `TRUEUP`. `gl_entries.csv` keeps the `obligation_id` column, required on every `TRUEUP` row.

### 1.3 Org directory (7 people)

| employee_id | name | role | cost_center | does |
|---|---|---|---|---|
| E001 | Dana Whitfield | CONTROLLER | GA | approves accruals >= $25,000, every ESCALATE, every learned policy |
| E002 | Marcus Oyelaran | ACCOUNTING_MANAGER | GA | approves accruals $10,000.00 to $24,999.99, or any accrual with confidence < 0.85 below $25,000 |
| E003 | Sofia Brandt | AP_SPECIALIST | GA | owns the AP queue and mailbox; approves nothing |
| E004 | Ken Ito | CLOSE_ACCOUNTANT | GA | prepared the 2026-05..2026-10 accruals by hand; preparer of `erp/accrual_schedule_prior.csv`; approves nothing |
| E010 | Priya Raman | BUDGET_OWNER | DATA | owns V001, V013 |
| E011 | Sam Okafor | BUDGET_OWNER | ENG | owns V002, V005, V010 |
| E014 | Nina Petrov | BUDGET_OWNER | GA | owns V004, V006, V009, V011, V014 |

Preparer and approver are never the same person. TrueUp is the preparer from 2026-11 and writes `posted_by = "TRUEUP"`. Approval enum `NONE | REVIEWER | CONTROLLER`; `REVIEWER` resolves to E002, `CONTROLLER` to E001.

---

## 2. Vendors

Ten vendors: six judge-facing, four background. No other vendor exists.

### 2.1 Judge-facing vendors (six)

| id | name | account | CC | owner | contract | related documents | spend_type | estimation_basis | baseline |
|---|---|---|---|---|---|---|---|---|---|
| V001 | DataForge Inc. | 6120 | DATA | E010 | CTR-001 | `PS-001` | RECURRING | CONTRACT_PRICE | $50,000.00 / month, Contract Year 1; CY2 starts 2026-12-01 |
| V002 | AWS | 6110 | ENG | E011 | CTR-002 | none | USAGE | USAGE_X_RATE | compute_hours x $0.25 |
| V013 | ModelAPI | 6110 | DATA | E010 | CTR-013 | none | USAGE | USAGE_X_RATE | input $3.00 / M tokens, output $15.00 / M tokens |
| V005 | PagerLoop Inc. | 6120 | ENG | E011 | CTR-005 | `VPN-005` (filed 2027-01-20) | RECURRING | CONTRACT_PRICE | 120 seats x $100.00 = $12,000.00 / month, no proration |
| V006 | Brightwork Consulting Group | 6200 | GA | E014 | CTR-006 | none | SERVICES | HOURS_X_RATE | 142 h x $185.00 = $26,270.00 in December |
| V014 | OfficeLease | 6300 | GA | E014 | CTR-014 | none | RECURRING | CONTRACT_PRICE | $22,500.00 / month, fixed |

`vendors.json` `category` enum, four values: `SAAS_OR_DATA` (V001, V004, V005, V009), `CLOUD_USAGE` (V002, V013, V010), `CONSULTING` (V006, V011), `RENT` (V014). `spend_type` enum is the three values of `ContractFeatures`: `RECURRING`, `USAGE`, `SERVICES`.

`AWS` and `ModelAPI` are intuitive labels on synthetic data. Vendor billing emails: `billing@dataforge.example`, `billing@aws.example`, `billing@modelapi.example`, `billing@pagerloop.example`, `billing@brightwork.example`, `billing@officelease.example`.

### 2.2 Background vendors (four)

Never shown in the Judge Scenario Lab. They appear only as rows in the replay report, the close inventory and the metrics.

| id | name | account | CC | owner | contract | spend_type | estimation_basis | baseline | why it is here |
|---|---|---|---|---|---|---|---|---|---|
| V004 | Lumen CRM Corp. | 6120 | GA | E014 | CTR-004 | RECURRING | CONTRACT_PRICE | $18,000.00 / month | matches POL-0001 predicates, no pricing documents on file: regression control 1 |
| V009 | PayCircle Inc. | 6120 | GA | E014 | CTR-009 | RECURRING | CONTRACT_PRICE | $4,150.00 / month | matches POL-0001 predicates, no pricing documents on file: regression control 2 |
| V010 | SecureLayer Systems | 6120 | ENG | E011 | CTR-010 | USAGE | USAGE_X_RATE | 1,800,000 events x $0.003 = $5,400.00 / month | does not match POL-0001 (basis is not CONTRACT_PRICE) |
| V011 | TalentBridge Partners | 6200 | GA | E014 | CTR-011 | SERVICES | HOURS_X_RATE | 60 h x $150.00 = $9,000.00 / month | does not match POL-0001 (basis is not CONTRACT_PRICE) |

Deleted vendors: V003 Helpline, V007 Meridian, V008 OfficeNest, V012 PrintWorks, V015 Quantive, V016 Northwind, V017 Thames, V018 SignalStack, V019 Beacon.

### 2.3 Purchase orders

Exactly one PO in the world. `PO-1042`, vendor V006, type `PROJECT_TM`, not-to-exceed `authorized_amount = 400000.00`, valid 2026-07-01..2027-06-30, issued 2026-06-24, status `OPEN`, owner E014, description "Brightwork PMO delivery, FY27". Every other PO is deleted, including PO-1063 and its $415,000 declared departure. No SaaS, cloud, API or rent vendor has a PO.

### 2.4 Documents

`contracts/index.json` is the document index. It is reachable **only** through `list_related_documents(contract_id)`. Its record has exactly ten fields: `doc_id`, `doc_type`, `contract_id`, `vendor_id`, `title`, `effective_date`, `filed_date`, `filed_by` (always `E003`), `visible_from`, `files[]`. `counterparty_name` and `supersedes` are deleted.

| doc_id | doc_type | contract_id | title | effective_date | filed_date | visible from | path |
|---|---|---|---|---|---|---|---|
| CTR-001 .. CTR-014 | `MSA_ORDER_FORM` | itself | MSA and Order Form (Exhibit A) | contract start | before T0 | T0 | `contracts/CTR-0NN.pdf` + `.txt` |
| `PS-001` | `PRICING_SCHEDULE` | CTR-001 | Exhibit B - Pricing Schedule | 2025-12-01 | 2025-11-24 | T0 | `contracts/pricing_schedules/PS-001.pdf` + `.txt` |
| `VPN-005` | `VENDOR_PRICE_NOTICE` | CTR-005 | 2027 renewal price notice | 2027-01-01 | 2027-01-20 | 2027-01-20T10:00 | `contracts/price_notices/VPN-005.pdf` + `.txt` |

Contracts that exist: CTR-001, CTR-002, CTR-004, CTR-005, CTR-006, CTR-009, CTR-010, CTR-011, CTR-013, CTR-014. All others are deleted, along with `contracts/notices/`, TN-019, PS-018 and `DOC-PAGERLOOP-UPLIFT-NOTICE`.

**Causality rule, hard.** `CTR-001.txt` contains no sentence referring to a pricing schedule, an exhibit B, a contract year 2, an escalator or a future price. `CTR-005.txt` contains no sentence referring to a renewal notice or an uplift. The only path from a contract to its related documents is `list_related_documents(contract_id)`, which playbook 1.0 forbids in CLOSE mode.

`PS-001.txt` body, exactly (the CY2 figure is set by `CTL-DATAFORGE-INCREASE`; $52,500.00 shown at baseline):

```
SYNTHETIC DATA - ACME AI, INC. (FICTIONAL). NOT A REAL COMPANY OR VENDOR.
PRICING SCHEDULE (EXHIBIT B)   Document ID: PS-001   Contract ID: CTR-001
Contract Year | Start      | End        | Monthly Platform Fee
CY1           | 2025-12-01 | 2026-11-30 | $50,000.00
CY2           | 2026-12-01 | 2027-11-30 | $52,500.00
```

`VPN-005.txt` body, exactly (the per-seat figure is set by `CTL-PAGERLOOP-PRICE`; $100.00 shown at baseline):

```
SYNTHETIC DATA - ACME AI, INC. (FICTIONAL). NOT A REAL COMPANY OR VENDOR.
VENDOR PRICE NOTICE   Document ID: VPN-005   Contract ID: CTR-005
Issued by: PagerLoop Inc.   Notice date: 2027-01-18   Filed: 2027-01-20
Per seat, per month, effective 2027-01-01: $100.00
Seat count and all other terms of the Order Form are unchanged.
```

`CTR-001.txt` Order Form line, exactly: `$50,000.00 per month (Contract Year 1)`.
`CTR-005.txt` Order Form line, exactly: `120 seats at $100.00 per seat per month (Initial Term)`.
`CTR-006.txt` Fees clause, exactly: `Consultant shall bill actual hours worked at $185.00 per hour. No additional fees apply absent a signed change order.`

---

## 3. Usage meters and rates

`evidence/usage_daily.csv` columns: `vendor_id, date, meter, quantity, source`. Daily rows are generated by the pricing function: `floor(monthly_total / days_in_month)` per day, with the final day of the month carrying the remainder, so the month sums exactly to the pinned total. The hidden invoice equals the metered monthly total times the contract rate, to the cent.

| vendor | meter | rate | Normal monthly quantity |
|---|---|---|---|
| V002 AWS | `compute_hours` | $0.25 per hour | 120,000 |
| V013 ModelAPI | `input_tokens_m` | $3.00 per million | 2,000 |
| V013 ModelAPI | `output_tokens_m` | $15.00 per million | 400 |
| V010 SecureLayer | `events_scanned` | $0.003 per event | 1,800,000 |

No tiers, no included allowance, no commit fee anywhere.

Usage-level amounts, computed exactly:

| level | multiplier | AWS quantity | AWS amount | ModelAPI input / output | ModelAPI amount |
|---|---|---|---|---|---|
| Low | 0.7x | 84,000 h | $21,000.00 | 1,400 M / 280 M | $8,400.00 |
| Normal (current) | 1.0x | 120,000 h | $30,000.00 | 2,000 M / 400 M | $12,000.00 |
| High | 1.3x | 156,000 h | $39,000.00 | 2,600 M / 520 M | $15,600.00 |
| Spike | 1.6x | 192,000 h | $48,000.00 | 3,200 M / 640 M | $19,200.00 |

Working: AWS `84,000 x 0.25 = 21,000.00`, `120,000 x 0.25 = 30,000.00`, `156,000 x 0.25 = 39,000.00`, `192,000 x 0.25 = 48,000.00`. ModelAPI `1,400 x 3 + 280 x 15 = 4,200 + 4,200 = 8,400.00`, `2,000 x 3 + 400 x 15 = 6,000 + 6,000 = 12,000.00`, `2,600 x 3 + 520 x 15 = 7,800 + 7,800 = 15,600.00`, `3,200 x 3 + 640 x 15 = 9,600 + 9,600 = 19,200.00`.

The usage controls target the **2026-12** meter only. November and January meters stay at Normal in every world.

---

## 4. Close periods, obligations and outcomes

T0 = `2026-12-01T00:00:00`. T_END = `2027-02-15T23:59:59`. Cutoff instant is `23:59:59` on the cutoff date.

| period | role | OPEN from | cutoff date | playbook in force |
|---|---|---|---|---|
| 2026-05..2026-10 | history, CLOSED at T0 | n/a | n/a | human process |
| 2026-11 | warm-up | 2026-12-01T00:00 | 2026-12-05 | 1.0 |
| 2026-12 | the failure | 2027-01-01T00:00 | 2027-01-05 | 1.0 |
| 2027-01 | held out | 2027-02-01T00:00 | 2027-02-05 | 1.1 (learned arm) or 1.0 (frozen arm) |

Obligation id: `OBL-{vendor_id}-{period}`. **10 obligations per period, 30 in total.** Invoice ids are `INV-{vendor_id}-{seq}`: 001..006 history, 007 for 2026-11, 008 for 2026-12, 009 for 2027-01.

### 4.1 2026-11 (warm-up), 10 obligations

Every invoice arrives on time (2026-12-01..2026-12-04). Every obligation: `estimation_basis = ACTUAL_INVOICE`, verifier `PASS`, approval `NONE`, outcome `CLOSE_READY`. No accrual is posted. The demo never runs this period live; it is restored from checkpoint `CP-DEC`.

### 4.2 2026-12 (the failure), 10 obligations

Baseline world (DataForge increase 5 percent, usage Normal, surcharge $0.00).

| obligation | invoice at cutoff | basis | accrual | approval | outcome at cutoff | actual | released | variance |
|---|---|---|---|---|---|---|---|---|
| OBL-V001-2026-12 | missing | CONTRACT_PRICE | 50,000.00 | CONTROLLER | ACCRUED | 52,500.00 | 2027-01-12T09:00 | +2,500.00, outside 1,000.00 |
| OBL-V002-2026-12 | missing | USAGE_X_RATE | 30,000.00 | CONTROLLER | ACCRUED | 30,000.00 | 2027-01-08T09:00 | 0.00 |
| OBL-V013-2026-12 | missing | USAGE_X_RATE | 12,000.00 | REVIEWER | ACCRUED | 12,000.00 | 2027-01-08T09:00 | 0.00 |
| OBL-V005-2026-12 | on hand 2027-01-03 | ACTUAL_INVOICE | none | NONE | CLOSE_READY | 12,000.00 | 2027-01-03T09:00 | n/a |
| OBL-V006-2026-12 | missing | HOURS_X_RATE | 26,270.00 | CONTROLLER | ACCRUED | 26,270.00 | 2027-01-15T09:00 | 0.00 |
| OBL-V014-2026-12 | missing | CONTRACT_PRICE | 22,500.00 | REVIEWER | ACCRUED | 22,500.00 | 2027-01-09T09:00 | 0.00 |
| OBL-V004-2026-12 | missing | CONTRACT_PRICE | 18,000.00 | REVIEWER | ACCRUED | 18,000.00 | 2027-01-10T09:00 | 0.00 |
| OBL-V009-2026-12 | missing | CONTRACT_PRICE | 4,150.00 | NONE | ACCRUED | 4,150.00 | 2027-01-10T09:00 | 0.00 |
| OBL-V010-2026-12 | on hand 2027-01-02 | ACTUAL_INVOICE | none | NONE | CLOSE_READY | 5,400.00 | 2027-01-02T09:00 | n/a |
| OBL-V011-2026-12 | missing | HOURS_X_RATE | 9,000.00 | NONE | ACCRUED | 9,000.00 | 2027-01-11T09:00 | 0.00 |

Eight accruals, total `50,000 + 30,000 + 12,000 + 26,270 + 22,500 + 18,000 + 4,150 + 9,000 = 171,920.00`. Two `CLOSE_READY`.

Brightwork detail, kept: at cutoff `evidence/timesheets.csv` shows 68 h `APPROVED` and 74 h `PENDING` (weeks ending 2026-12-18 and 2026-12-25, 38 + 36). The verifier returns `OUTREACH_REQUIRED`, fact `SERVICE_RECEIVED`, target E014; the reply 20 hours later confirms 142 h and releases the timesheet approval patch. Then `142 x 185.00 = 26,270.00`.

Outreach is always sent by the close run that needs it, never before the run exists. The December close run starts 2027-01-04T09:00 and sends at 2027-01-04T09:30; the Brightwork reply lands 2027-01-05T05:30 (+20 h) and the DataForge reply 2027-01-05T15:30 (+30 h), both before the 2027-01-05T23:59:59 cutoff. Entries are proposed 2027-01-05T16:00. Each January transfer arm forks the `2027-01-open` snapshot at 2027-02-01T00:00 and sends its own DataForge outreach at 2027-02-02T10:00 inside its own fork, reply 2027-02-03T10:00 (+24 h).

`erp/accrual_schedule_prior.csv` carries 2026-05..2026-10 rows for eight vendors; V005 and V010 have none, because their invoices always arrived before cutoff. DataForge has six rows, each accrued 50,000.00 and actual 50,000.00, variance 0.00, basis "order form monthly fee", preparer E004, reviewer E002. That is the evidence the human procedure took the price off the order form and opened no pricing document.

### 4.3 2027-01 (held out), 10 obligations

| obligation | invoice at cutoff | basis | frozen 1.0 accrual | learned 1.1 accrual | approval | actual | released |
|---|---|---|---|---|---|---|---|
| OBL-V001-2027-01 | missing | CONTRACT_PRICE | 50,000.00 | CY2 effective rate | CONTROLLER | CY2 rate | 2027-02-10T09:00 |
| OBL-V002-2027-01 | missing | USAGE_X_RATE | 30,000.00 | 30,000.00 | CONTROLLER | 30,000.00 | 2027-02-08T09:00 |
| OBL-V013-2027-01 | missing | USAGE_X_RATE | 12,000.00 | 12,000.00 | REVIEWER | 12,000.00 | 2027-02-08T09:00 |
| OBL-V005-2027-01 | missing | CONTRACT_PRICE | 12,000.00 | 120 x effective per-seat price | REVIEWER | same as learned | 2027-02-12T09:00 |
| OBL-V006-2027-01 | on hand 2027-02-03 | ACTUAL_INVOICE | none | none | NONE | 26,270.00 | 2027-02-03T09:00 |
| OBL-V014-2027-01 | missing | CONTRACT_PRICE | 22,500.00 | 22,500.00 | REVIEWER | 22,500.00 | 2027-02-09T09:00 |
| OBL-V004-2027-01 | missing | CONTRACT_PRICE | 18,000.00 | 18,000.00 | REVIEWER | 18,000.00 | 2027-02-10T09:00 |
| OBL-V009-2027-01 | missing | CONTRACT_PRICE | 4,150.00 | 4,150.00 | NONE | 4,150.00 | 2027-02-10T09:00 |
| OBL-V010-2027-01 | on hand 2027-02-02 | ACTUAL_INVOICE | none | none | NONE | 5,400.00 | 2027-02-02T09:00 |
| OBL-V011-2027-01 | missing | HOURS_X_RATE | 9,000.00 | 9,000.00 | NONE | 9,000.00 | 2027-02-11T09:00 |

V014, V004 and V009 resolve to `NO_PRICING_DOCUMENTS_ON_FILE` under 1.1, so the order form price stands and the amount is unchanged. That is what makes "regressions 0" real.

---

## 5. Playbook v1.0: estimation bases, evidence plans, tool gateway

### 5.1 Estimation bases (exactly five values)

`ACTUAL_INVOICE`, `CONTRACT_PRICE`, `USAGE_X_RATE`, `HOURS_X_RATE`, `NONE`. Deleted: `FIXED_CONTRACT_FEE` (renamed to `CONTRACT_PRICE`), `PRORATED_FEE`, `PO_BASED`, `HISTORICAL_RUN_RATE`.

### 5.2 Evidence plan per basis (playbook 1.0, CLOSE mode)

| estimation_basis | evidence plan: the tool calls the agent is allowed to make |
|---|---|
| `ACTUAL_INVOICE` | `get_vendor`, `read_ap_queue`, `open_invoice`, `open_document(primary)`, `get_service_confirmation` |
| `CONTRACT_PRICE` | `get_vendor`, `list_invoices(limit=3)`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue` |
| `USAGE_X_RATE` | `get_vendor`, `read_usage_meter`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue` |
| `HOURS_X_RATE` | `get_vendor`, `read_timesheets`, `open_document(primary)`, `get_purchase_order`, `read_ap_queue` |
| `NONE` | none; escalate |

`open_document(primary)` means the contract's own `CTR-0NN` order form and nothing else. The plan for `CONTRACT_PRICE` **does not include related pricing documents**. `send_outreach` and `search_inbox` are always allowed in CLOSE mode.

### 5.3 Tool gateway modes

| mode | entered by | allowed |
|---|---|---|
| `CLOSE` | `POST /api/close/run` | exactly the active playbook's evidence plan for that obligation's basis, plus `get_vendor`, `read_ap_queue`, `send_outreach`, `search_inbox`, plus any tool added by an `ACTIVE` policy's `evidence_plan_delta` |
| `INVESTIGATE` | `POST /api/investigate` | every read tool, including `list_related_documents`, `open_document` for any doc_id, and `resolve_effective_price`. No proposal, no posting, no state write other than the `VarianceExplanation` |

A call outside the active mode's allowed set is refused, never executed. The gateway returns `{"refused": true, "reason": "OUTSIDE_EVIDENCE_PLAN", "playbook_version": "1.0"}`, writes a `ToolCall` row with `refused = true`, and streams it to `#evidence-trail` so the judge sees the refusal. Under playbook 1.0 in CLOSE mode, `list_related_documents`, `resolve_effective_price` and `open_document` of any non-primary document are always refused. This is what makes Frozen and Learned differ, and what gives Reject a real consequence.

`tool_calls` gains three columns: `mode` (`CLOSE` or `INVESTIGATE`), `refused` (bool), `refusal_reason` (text).

### 5.4 Control policy v1.0, other rules (unchanged in substance)

| rule | value |
|---|---|
| Cutoff day | 5th of the following month |
| Auto-prepare (`NONE`) | amount < $10,000.00 and confidence >= 0.85 |
| Reviewer approval (E002) | $10,000.00 to $24,999.99, or confidence < 0.85 below $25,000.00 |
| Controller approval (E001) | amount >= $25,000.00, or any verifier result `ESCALATE` |
| True-up tolerance | `max(500.00, 0.02 x accrued amount)` |
| True-up approver | the approver of that obligation's own accrual, whatever the amount |
| Outreach wait | 48 hours, then escalate |
| Accrual reversal | automatic on day 1 of the next period |
| Conflicting evidence or no allowed basis | never post; `ESCALATE` to the Controller |

Verifier invariants, nine: `ENTRY_BALANCES`, `PERIOD_OPEN`, `SERVICE_RECEIPT_SUPPORTED`, `NO_DUPLICATE_ACCRUAL`, `ALLOWED_BASIS`, `EVIDENCE_PLAN_COMPLETE`, `MATERIALITY_APPROVAL`, `UNCERTAINTY_CANNOT_POST`, `ACTION_TRACEABLE`. Result enum and precedence unchanged: `ESCALATE > BLOCK > OUTREACH_REQUIRED > REVIEW_REQUIRED > PASS`.

`policies.json` v1.0 keys: `policy_version`, `close_cutoff_day`, `approval_thresholds {auto_max 9999.99, reviewer_max 24999.99, min_auto_confidence 0.85}`, `true_up_tolerance {abs 500.0, pct 2.0}`, `outreach_wait_hours 48`, `evidence_plans {basis: [tool, ...]}`, `learned_policies []`. Deleted keys: `allowed_methods`, `historical_run_rate_limits`, `prior_period_controller_threshold`.

---

## 6. Schemas

### 6.1 ContractFeatures, v1.0 (order form only)

One record per `contract_id`, extracted by the Evidence Agent from the primary document and nothing else.

```json
{"contract_id":"CTR-001","vendor_id":"V001","source_doc_ids":["CTR-001"],
 "extracted_at":"2026-12-01T08:00:00",
 "spend_type":"RECURRING","estimation_basis":"CONTRACT_PRICE",
 "unit_price":50000.00,"unit":"MONTH","quantity":1,
 "price_label":"Contract Year 1","billing_frequency":"MONTHLY",
 "term_start":"2025-12-01","term_end":"2027-11-30",
 "citations":[{"feature":"unit_price","doc_id":"CTR-001","locator":"Order Form","quote":"$50,000.00 per month (Contract Year 1)"}]}
```

Field set, complete: `contract_id`, `vendor_id`, `source_doc_ids[]`, `extracted_at`, `spend_type` enum `RECURRING|USAGE|SERVICES`, `estimation_basis` enum (section 5.1), `unit_price` dec nullable, `unit` enum `MONTH|SEAT_MONTH|HOUR|COMPUTE_HOUR|MILLION_INPUT_TOKENS|MILLION_OUTPUT_TOKENS|EVENT`, `quantity` dec nullable, `price_label` str nullable, `billing_frequency` enum `MONTHLY`, `term_start` date, `term_end` date, `citations[]`.

Deleted fields: `contract_type`, `pricing_structure`, `billing_cadence`, `has_scheduled_price_change`, `has_pricing_exhibit`, `has_usage_component`, `termination_notice_on_file`, `termination_effective_date`, `auto_renews`, `notice_days`, `order_form_fee`.

PagerLoop record: `unit_price 100.00`, `unit SEAT_MONTH`, `quantity 120`, `price_label "Initial Term"`, `term_start 2026-01-01`, `term_end 2027-12-31`. Brightwork record: `unit_price 185.00`, `unit HOUR`, `quantity null`, `price_label null`, `term_start 2026-07-01`, `term_end 2027-06-30`.

`price_label` is a clue on the page, not knowledge. No v1.0 rule reads it, and it names no future price.

### 6.2 PriceTerm

Emitted by the LLM during INVESTIGATE or under an ACTIVE policy, then checked by deterministic code.

```json
{"basis":"PER_MONTH","value":54000.00,"effective_from":"2026-12-01","effective_to":"2027-11-30",
 "source_doc_id":"PS-001","quote":"CY2           | 2026-12-01 | 2027-11-30 | $54,000.00"}
```

`basis` enum `PER_MONTH | PER_SEAT_MONTH`. Deterministic checks, all three required: `quote` is a verbatim substring of the source document's text; `value` parses from `quote`; `effective_from <= service_period_start <= effective_to`. Then `effective_price = value` for `PER_MONTH`, or `value x ContractFeatures.quantity` for `PER_SEAT_MONTH`. The LLM never computes the amount.

`resolve_effective_price(contract_id, service_period)` returns exactly one of:

| status | meaning | consequence |
|---|---|---|
| `RESOLVED` | one PriceTerm covers the service period | the estimator's unit price comes from it |
| `NO_PRICING_DOCUMENTS_ON_FILE` | `list_related_documents` returned no pricing document | the order form price stands, nothing changes |
| `CONFLICTING_TERMS` | two or more PriceTerms cover the period | `OUTREACH_REQUIRED` |
| `UNPARSEABLE` | a pricing document exists but no quote validates | `OUTREACH_REQUIRED` |

### 6.3 Other schema deltas

`ActionProposal.action_type` enum, six values: `POST_ACCRUAL`, `MARK_CLOSE_READY`, `POST_INVOICE`, `POST_TRUE_UP`, `SEND_OUTREACH`, `ESCALATE`. Deleted: `ALLOCATE_INVOICE`, `HOLD_INVOICE`, `NO_ACCRUAL_DOCUMENTED`.

`VendorObligation`: `estimator_method` renamed `estimation_basis` with the five values of 5.1; `classification` enum trimmed to `VALID_INVOICE_MATCHES`, `NO_INVOICE_SERVICE_RECEIVED`, `NO_INVOICE_SERVICE_UNCLEAR`; `invoice_status` enum trimmed to `RECEIVED`, `MISSING`, `NOT_EXPECTED`; `outcome` enum trimmed to `CLOSE_READY`, `ACCRUED`, `RECONCILED`, `ESCALATED`; `root_cause` enum is `PROCEDURE_GAP | UNKNOWN | null`; `status` loses `HOLD_DO_NOT_POST`.

Deleted record types: `Exception` and every `EXC-` id, `CashForecastLine`, `AuditFinding`, `ChangeOrder`.

---

## 7. POL-0001, in full

```json
{"policy_id":"POL-0001",
 "policy_type":"VERIFY_EFFECTIVE_CONTRACT_PRICE",
 "plain_text":"For recurring contract-based spend where pricing may vary by contract period, retrieve and validate the price effective for the current service period before estimation.",
 "trigger":"OBLIGATION_NEEDS_ESTIMATE",
 "predicates":{"spend_type":"RECURRING","estimation_basis":"CONTRACT_PRICE"},
 "required_evidence":[{"evidence_key":"EFFECTIVE_PRICE_CHECK",
                       "must_cover":"service_period",
                       "produced_by":"resolve_effective_price(contract_id, service_period)",
                       "accepted_sources":["PRICING_SCHEDULE","AMENDMENT","VENDOR_PRICE_NOTICE"]}],
 "evidence_plan_delta":{"add_tools":["list_related_documents","open_document:RELATED","resolve_effective_price"]},
 "before_action":"CREATE_DRAFT_ACCRUAL",
 "behavior_change":"the estimator's unit price comes from the effective PriceTerm when resolve_effective_price returns RESOLVED; on NO_PRICING_DOCUMENTS_ON_FILE the order form price stands",
 "verifier_result_if_missing":{"check_absent":"BLOCK",
                               "conflicting_or_unparseable":"OUTREACH_REQUIRED",
                               "no_reply_at_cutoff":"ESCALATE"},
 "outreach_if_missing":{"target_role":"VENDOR_BILLING","missing_fact":"SCOPE_OR_RATE_CHANGE"},
 "autonomy_limit":"controller_review_if_material",
 "derived_from":{"outcome_id":"TU-V001-2026-12","root_cause_id":"VE-V001-2026-12"},
 "status":"CANDIDATE","created_at":"2027-01-13T09:30:00","policy_version_target":"1.1"}
```

Matches V001, V005, V014, V004, V009. Does not match V002, V013, V010 (usage) or V006, V011 (services). No `vendor_id`, no vendor name, no `contract_id`, no percent, no dollar amount, no `has_scheduled_price_change` anywhere in the record. Lifecycle unchanged: `CANDIDATE` -> G1 -> G2 -> Controller `APPROVE` -> `ACTIVE_PROVISIONAL` in playbook 1.1, or `REJECT` -> `REJECTED`, playbook stays 1.0.

### 7.1 G1 predicate whitelist

A candidate policy predicate may reference only `estimation_basis` and these ContractFeatures fields: `spend_type`, `unit`, `billing_frequency`, `price_label`, `term_start`, `term_end`.

Banned anywhere in a policy record: `vendor_id`, vendor name, `contract_id`, `cost_center`, `gl_account`, `po_id`, `unit_price`, `quantity`, any dollar amount, any percent, and any post-cutoff fact (`invoice_id`, `true_up_amount`, `actual_invoice_total`, `root_cause`). An unrecognized key is a G1 failure, not a pass-through.

Removed from the old whitelist: `contract_type`, `pricing_structure`, `billing_cadence`, `has_scheduled_price_change`, `has_pricing_exhibit`, `has_usage_component`, `termination_notice_on_file`, `auto_renews`, `notice_days`.

### 7.2 Root-cause taxonomy

| root_cause | process_detail | reached when | outcome |
|---|---|---|---|
| `PROCEDURE_GAP` | `EFFECTIVE_PRICE_NOT_RETRIEVED` | the invoice price equals a PriceTerm in a document that was on file at close and the evidence plan never named it | `ROOT_CAUSE_FOUND` -> candidate policy |
| `UNKNOWN` | `NO_CONTRACTUAL_BASIS` | no contract clause, no related document and no correspondence explains the variance | `ROOT_CAUSE_UNKNOWN` -> `ESCALATED`, no candidate |

Deleted: `SCHEDULED_PRICE_CHANGE`, `SCHEDULED_ESCALATOR`, `TIERED_OVERAGE_RATE`, `CHANGE_ORDER_SEAT_EXPANSION`, `SCOPE_CHANGE`, `USAGE_VARIANCE`, `PRORATION`, `ESTIMATE_JUDGMENT`, `TIMING_ONLY`, and the process causes `PROCEDURE_GAP_REQUIRED_EVIDENCE`, `SCOPE_CHANGE_NOT_CONFIRMED`, `NONE_CONTROLLER_JUDGEMENT`, `NO_OBSERVABLE_FEATURE`. Variance inside tolerance sets `root_cause = null` and goes to `NO_MISS`; no investigation runs.

---

## 8. Replay

**Replay set: the 20 obligations of 2026-11 and 2026-12.** Each is rebuilt from the simulator snapshot at its own cutoff (`2026-11-cutoff`, `2026-12-cutoff`); no private file is read. The pipeline runs twice, under 1.0 and under 1.0 + candidate, and both are compared against outcomes confirmed by 2027-01-13.

| field | value |
|---|---|
| `obligations_replayed` | 20 |
| `feature_matched` | 10 (V001, V005, V014, V004, V009 x 2026-11 and 2026-12) |
| `not_triggered` | 6 (all five 2026-11 rows plus OBL-V005-2026-12: invoice on hand at cutoff, no estimate ran) |
| triggered | 4 (OBL-V001-2026-12, OBL-V014-2026-12, OBL-V004-2026-12, OBL-V009-2026-12) |
| `touched` | 1: `OBL-V001-2026-12`, before 50,000.00, after the CY2 rate |
| `improved` / `regressed` / `unchanged` | 1 / 0 / 19 |
| `compared_on_action_only` | 1 (`OBL-V006-2026-12`; its invoice arrives 2027-01-15, after the replay) |
| `extra_outreach` / `extra_reviews` | 0 / 0 |
| `forward_scope_preview` | 5 ids, no amounts: OBL-V001-2027-01, OBL-V005-2027-01, OBL-V014-2027-01, OBL-V004-2027-01, OBL-V009-2027-01 |
| `recommendation` | `APPROVE_PROVISIONAL` |

`abs_error_before` / `abs_error_after` and signed bias by judge value (signed bias = sum of `accrued - actual` over triggered obligations):

| DataForge increase | CY2 rate | abs_error_before | abs_error_after | bias before | bias after |
|---|---|---|---|---|---|
| 5 percent (baseline) | 52,500.00 | 2,500.00 | 0.00 | -2,500.00 | 0.00 |
| 8 percent (default walkthrough) | 54,000.00 | 4,000.00 | 0.00 | -4,000.00 | 0.00 |
| 12 percent | 56,000.00 | 6,000.00 | 0.00 | -6,000.00 | 0.00 |

The other three triggered obligations return `NO_PRICING_DOCUMENTS_ON_FILE`, so their amount and approval level are byte-identical before and after. That is the regression evidence.

G2 fails on `regressed > 0`, on `abs_error_after >= abs_error_before`, or on any touched row whose approval level falls.

---

## 9. The five judge controls

`CTL-DATAFORGE-INCREASE`, `CTL-AWS-USAGE`, `CTL-MODELAPI-USAGE`, `CTL-PAGERLOOP-PRICE`, `CTL-BRIGHTWORK-SURCHARGE`. There are no other controls, no "lab extras" tier and no cut order.

Each control is one dropdown on one vendor card. The baseline option is labelled `(current)` and `Apply Change` is disabled while it is selected. No free-form fields anywhere.

| control_id | vendor | target obligation | options (baseline marked) | resulting world value | validator |
|---|---|---|---|---|---|
| `CTL-DATAFORGE-INCREASE` | V001 | `OBL-V001-2026-12` | 0 / **5 (current)** / 8 / 12 percent | PS-001 CY2 rate 50,000.00 / 52,500.00 / 54,000.00 / 56,000.00 | `VAL-DATAFORGE-INCREASE` |
| `CTL-AWS-USAGE` | V002 | `OBL-V002-2026-12` | Low 0.7x / **Normal 1.0x (current)** / High 1.3x / Spike 1.6x | December meter 84,000 / 120,000 / 156,000 / 192,000 compute_hours | `VAL-AWS-USAGE` |
| `CTL-MODELAPI-USAGE` | V013 | `OBL-V013-2026-12` | Low 0.7x / **Normal 1.0x (current)** / High 1.3x / Spike 1.6x | December meters as in section 3 | `VAL-MODELAPI-USAGE` |
| `CTL-PAGERLOOP-PRICE` | V005 | `OBL-V005-2027-01` | **0 (current)** / 10 / 15 / 25 percent | VPN-005 per-seat price 100.00 / 110.00 / 115.00 / 125.00 | `VAL-PAGERLOOP-PRICE` |
| `CTL-BRIGHTWORK-SURCHARGE` | V006 | `OBL-V006-2026-12` | **$0.00 (current)** / $900.00 / $2,400.00 / $6,000.00 | one extra invoice line on INV-V006-008 | `VAL-BRIGHTWORK-SURCHARGE` |

Default walkthrough values: DataForge 8 percent, PagerLoop 15 percent, Brightwork $2,400.00.

### 9.1 ScenarioOverride

One JSON object per judge change. Lives only in `runtime/mutation_log.jsonl` and `sim_state.json.overrides`. Never written under `runtime/visible/`.

```json
{"override_id":"OVR-0001",
 "control_id":"CTL-DATAFORGE-INCREASE","validator":"VAL-DATAFORGE-INCREASE",
 "vendor_id":"V001","target_obligation_id":"OBL-V001-2026-12",
 "param":{"price_increase_pct":8},"baseline_param":{"price_increase_pct":5},
 "visible_docs_changed":["contracts/pricing_schedules/PS-001.txt"],
 "hidden_records_rederived":["INV-V001-008","INV-V001-009"],
 "apply_mode":"COLD",
 "staged_at":"2027-01-04T09:00:00","applied_by":"JUDGE",
 "start_clock":"2027-01-04T09:00:00","world_hash":"9f2c41ab77d0"}
```

Field set, complete: `override_id`, `control_id`, `validator`, `vendor_id`, `target_obligation_id`, `param`, `baseline_param`, `visible_docs_changed[]`, `hidden_records_rederived[]`, `apply_mode`, `staged_at`, `applied_by`, `start_clock`, `world_hash`.

`apply_mode` is `COLD` or `HOT`. `COLD`: full regeneration, runtime reset, fast-forward to `start_clock`. `HOT`: allowed only when every record in `visible_docs_changed` and `hidden_records_rederived` is still unreleased at the current clock and the target obligation has not been consumed; the simulator rewrites only unreleased events and the clock is untouched. `CTL-PAGERLOOP-PRICE` is the only control that may apply `HOT`, because `VPN-005` is filed 2027-01-20 and `INV-V005-009` releases 2027-02-12. All other controls are `COLD`.

A control parameter never edits a truth file. The simulator re-runs the pricing functions with the override applied, then rebuilds `world/seed`, `world/private/events.jsonl` and `world/private/truth/`, so a document and its hidden invoice can never disagree. The judge never sets an expected error, a variance or an invoice amount. Regeneration budget: stage under 300 ms, apply under 2 seconds.

### 9.2 Derived records and validators, per control

| control | derived visible records | derived hidden events and truth | validator asserts |
|---|---|---|---|
| `CTL-DATAFORGE-INCREASE` | `contracts/pricing_schedules/PS-001.txt` CY2 fee cell, `PS-001.pdf` re-rendered | `INVOICE_RECEIVED` payload amount for `INV-V001-008` and `INV-V001-009`; truth rows `OBL-V001-2026-12` and `OBL-V001-2027-01` | pct in {0,5,8,12}; `rate = 50000.00 x (1 + pct/100)`, greater than 0; CY1 row, both date ranges and `CTR-001.txt` untouched; every invoice with a service period starting on or after 2026-12-01 re-derived from the same pricing function |
| `CTL-AWS-USAGE` | `evidence/usage_daily.csv` December rows for V002 | `INV-V002-008` amount = monthly total x 0.25 | multiplier in {0.7,1.0,1.3,1.6}; daily rows sum exactly to the monthly total; invoice equals total x rate to the cent; the rate in `CTR-002.txt` untouched; November and January meters untouched |
| `CTL-MODELAPI-USAGE` | `evidence/usage_daily.csv` December rows for V013, both meters | `INV-V013-008` amount = `input_m x 3.00 + output_m x 15.00` | same as AWS, on both meters, with the two rates in `CTR-013.txt` untouched |
| `CTL-PAGERLOOP-PRICE` | `contracts/price_notices/VPN-005.txt` price line, `VPN-005.pdf` re-rendered, both still unreleased | `INV-V005-009` amount = `120 x per-seat price`; truth row `OBL-V005-2027-01` | pct in {0,10,15,25}; `per_seat = 100.00 x (1 + pct/100)`; seat count stays 120; `CTR-005.txt` untouched; no proration; `VPN-005` release stays 2027-01-20T10:00 |
| `CTL-BRIGHTWORK-SURCHARGE` | none | `INV-V006-008` gains one line item `{"description":"Year end expedite premium","quantity":1,"unit_price":X,"amount":X}`; invoice total `26270.00 + X`; truth row `OBL-V006-2026-12` | amount in {0.00,900.00,2400.00,6000.00}; no contract text, no purchase order, no timesheet and no other pre-cutoff visible file changes |

Worked example, to appear verbatim in `01-scenario-lab-and-mutations.md`:

> The judge sets the DataForge increase to 8 percent. The contract pricing schedule effective rate becomes $54,000.00. The hidden future invoice becomes $54,000.00. The baseline accrual is still $50,000.00. The true-up is +$4,000.00.

### 9.3 Control locking

A control locks when a close run has consumed its target obligation, that is, when an `AgentRun` has written an `ActionProposal` for `target_obligation_id`. The dropdown is then disabled with the tooltip `Locked: the close has already used this obligation. Reset World to change it.`

`CTL-PAGERLOOP-PRICE` targets `OBL-V005-2027-01`, which no close consumes before the transfer run, so it stays editable through `POLICY_APPROVED` and `POLICY_REJECTED` and locks when `btn-run-transfer` is pressed. The other four lock when the December close runs.

One applied override per control. A second override on the same control returns `423 WORLD_LOCKED`. Overrides on different controls stack; the demo path applies `CTL-DATAFORGE-INCREASE` and then `CTL-PAGERLOOP-PRICE`. `allow_multi` is deleted. `Reset World` unlocks every control.

### 9.4 Consistency invariants after every apply

`POST /sim/overrides/apply` runs these in order against the rebuilt world before it is written. Any failure rejects the apply and leaves the world unchanged.

| # | Invariant |
|---|---|
| INV-1 | GL balanced: debits equal credits per `entry_id` and in total |
| INV-2 | Every hidden invoice tied to a mutated contract or meter equals the pricing function evaluated for its own service period, to the cent |
| INV-3 | No closed period is edited: no re-derived record has a service period or posting date inside 2026-05..2026-11 |
| INV-4 | No leaked future fact: no visible date field exceeds the clock, and the mutated amount appears in no visible file before its own `release_at` |
| INV-5 | Truth re-derived, never edited: `obligations_truth.csv`, `future_invoices.csv` and `expected_matches.csv` are fully regenerated, and the diff touches only rows for the mutated vendor |
| INV-6 | Policy scope untouched: the mutation never writes `policies.json`, `trueup_playbook.db` or any `POL-` record |
| INV-7 | One override, one log line: exactly one `MUT-000N` row per apply |
| INV-8 | Budget: stage under 300 ms, apply under 2 seconds |

Deleted invariants: cadence tiling, duplicate-key preservation.

---

## 10. State machine delta

All 19 existing states stay, with the same names and the same clocks. None is renamed, none is removed, none is added:

`IDLE_BASELINE`, `MUTATION_STAGED`, `MUTATION_APPLIED`, `CLOSE_RUNNING`, `CLOSE_AWAITING_APPROVAL`, `CLOSE_POSTED`, `TRUEUP_COMPUTED`, `NO_MISS`, `INVESTIGATING`, `ROOT_CAUSE_FOUND`, `ROOT_CAUSE_UNKNOWN`, `ESCALATED`, `CANDIDATE_READY`, `CANDIDATE_BLOCKED`, `REPLAY_REPORT_READY`, `POLICY_APPROVED`, `POLICY_REJECTED`, `TRANSFER_RUNNING`, `TRANSFER_COMPARED`.

Transition changes, three only:

1. Delete the transition `ROOT_CAUSE_FOUND -> ESCALATED` on `evidence_existed_at_close = false`. With the two-value taxonomy, `PROCEDURE_GAP` always has `evidence_existed_at_close = true`.
2. `INVESTIGATING -> ROOT_CAUSE_FOUND` guard becomes: the classifier returns `PROCEDURE_GAP` and a deterministic check confirms the source document's `filed_date` is on or before the period cutoff.
3. `MUTATION_APPLIED -> MUTATION_STAGED` is allowed when a second, different control is staged, so the PagerLoop control can be configured after the SCN-A decision.

The twelve buttons of the glossary are unchanged.

---

## 11. Clock timestamps

Reused from the existing spec wherever one exists.

| point | clock |
|---|---|
| T0 | 2027-01-04T09:00:00 is the demo start; the world's own T0 is 2026-12-01T00:00:00 |
| `IDLE_BASELINE`, `MUTATION_STAGED`, `MUTATION_APPLIED` | 2027-01-04T09:00:00 |
| `CLOSE_RUNNING` | 2027-01-04T09:00:00 to 2027-01-05T15:30:00 |
| `CLOSE_AWAITING_APPROVAL` | 2027-01-05T16:00:00 |
| `CLOSE_POSTED` | 2027-01-05T23:59:59 |
| SCN-A `TRUEUP_COMPUTED` / `NO_MISS` | 2027-01-12T09:00:00 |
| SCN-A `INVESTIGATING`, `ROOT_CAUSE_FOUND` | 2027-01-13T09:00:00 |
| SCN-A `CANDIDATE_READY`, `CANDIDATE_BLOCKED` (G1) | 2027-01-13T09:30:00 |
| SCN-A `REPLAY_REPORT_READY`, `CANDIDATE_BLOCKED` (G2) | 2027-01-13T11:00:00 |
| SCN-A `POLICY_APPROVED` / `POLICY_REJECTED` | 2027-01-15T10:00:00 |
| SCN-B `CTL-PAGERLOOP-PRICE` applied (HOT) | 2027-01-15T10:00:00, clock unchanged |
| SCN-B `VPN-005` released | 2027-01-20T10:00:00 |
| SCN-B `TRANSFER_RUNNING` | 2027-02-05T09:00:00 |
| SCN-B `TRANSFER_COMPARED` | 2027-02-12T09:00:00 |
| SCN-C `TRUEUP_COMPUTED` | 2027-01-15T09:00:00 |
| SCN-C `INVESTIGATING`, `ROOT_CAUSE_UNKNOWN` | 2027-01-15T11:00:00 |
| SCN-C `ESCALATED` | 2027-01-15T12:00:00 |

A clock above that no `Advance Time` reaches is stamped by the call that enters the state: `POST /api/investigate`, `POST /api/policy/candidate`, `POST /api/policy/replay` and `POST /api/policy/approve|reject` each set `demo_state.clock` to the pinned value for the state they enter.

`btn-advance-time` `target_ts` per source state: `CLOSE_POSTED` -> 2027-01-12T09:00:00 (SCN-A) or 2027-01-15T09:00:00 (SCN-C); `NO_MISS`, `POLICY_APPROVED`, `POLICY_REJECTED` -> 2027-02-05T09:00:00. Never a free-text field.

---

## 12. The three scenarios, in numbers

### SCN-A learnable failure, DataForge V001, `OBL-V001-2026-12`

Dr 6120 / Cr 2100 at accrual, Cr 2000 at invoice and true-up. Cost center DATA. Entry 2026-12-31, reversal 2027-01-01, true-up dated 2027-01-12. Accrual under 1.0 is always the CTR-001 order form Contract Year 1 fee of $50,000.00. Tolerance `max(500.00, 0.02 x 50000.00) = 1000.00`.

| increase | PS-001 CY2 rate | accrual | hidden INV-V001-008 | variance | vs 1,000.00 | JE-TRU | approval | branch |
|---|---|---|---|---|---|---|---|---|
| 0 percent | 50,000.00 | 50,000.00 | 50,000.00 | 0.00 | inside | none | CONTROLLER | `NO_MISS`, no candidate |
| 5 percent (current) | 52,500.00 | 50,000.00 | 52,500.00 | +2,500.00 | outside | 2,500.00 | CONTROLLER | POL-0001 candidate |
| 8 percent (default) | 54,000.00 | 50,000.00 | 54,000.00 | +4,000.00 | outside | 4,000.00 | CONTROLLER | POL-0001 candidate |
| 12 percent | 56,000.00 | 50,000.00 | 56,000.00 | +6,000.00 | outside | 6,000.00 | CONTROLLER | POL-0001 candidate |

Investigation trail, in order: `open_invoice(INV-V001-008)` -> `list_related_documents(CTR-001)` returns `["CTR-001","PS-001"]` -> `open_document(PS-001)` quoting the CY2 row -> `open_document(CTR-001)` quoting the Contract Year 1 line -> `compute_variance` (deterministic) -> `classify_root_cause`. Root cause `PROCEDURE_GAP`, detail `EFFECTIVE_PRICE_NOT_RETRIEVED`, `evidence_existed_at_close = true` because `PS-001.filed_date = 2025-11-24`.

### SCN-B prove transfer, PagerLoop V005, `OBL-V005-2027-01`

Dr 6120 / Cr 2100, cost center ENG, entry 2027-01-31, reversal 2027-02-01, true-up dated 2027-02-12. TrueUp has never accrued PagerLoop: its invoices always arrived before cutoff, so there is no memorised amount. Tolerance `max(500.00, 0.02 x 12000.00 = 240.00) = 500.00`.

| price change | VPN-005 per seat | frozen 1.0 accrual | hidden INV-V005-009 | frozen variance | vs 500.00 | learned 1.1 accrual | learned variance |
|---|---|---|---|---|---|---|---|
| 0 percent (current) | 100.00 | 12,000.00 | 12,000.00 | 0.00 | inside | 12,000.00 | 0.00 |
| 10 percent | 110.00 | 12,000.00 | 13,200.00 | +1,200.00 | outside | 13,200.00 | 0.00 |
| 15 percent (default) | 115.00 | 12,000.00 | 13,800.00 | +1,800.00 | outside | 13,800.00 | 0.00 |
| 25 percent | 125.00 | 12,000.00 | 15,000.00 | +3,000.00 | outside | 15,000.00 | 0.00 |

Working: `120 x 100.00 = 12,000.00`, `120 x 110.00 = 13,200.00`, `120 x 115.00 = 13,800.00`, `120 x 125.00 = 15,000.00`.

The structure differs from DataForge on purpose: per-seat rather than flat, and the authoritative rate is in a `VENDOR_PRICE_NOTICE` rather than a pricing schedule. The seat count of 120 comes from the CTR-005 order form in both arms; VPN-005 states only the per-seat price. Learned arm trail: `open_document(CTR-005)` -> draft 12,000.00 -> verifier `BLOCK` (EFFECTIVE_PRICE_CHECK missing) -> `list_related_documents(CTR-005)` returns `["CTR-005","VPN-005"]` -> `open_document(VPN-005)` -> PriceTerm `{PER_SEAT_MONTH, 115.00, 2027-01-01, VPN-005}` -> re-propose 13,800.00 -> `REVIEW_REQUIRED`, approval REVIEWER. It books the right number; it does not merely block.

Frozen arm makes one document call, `open_document(CTR-005)`, and one refused call is logged if the model attempts `list_related_documents`.

Second row on `#transfer-panel`, same policy, same vendor as the training case one period later: `OBL-V001-2027-01`, frozen 50,000.00, learned the CY2 rate, so at the default walkthrough the frozen January error is `4,000.00 + 1,800.00 = 5,800.00` and the learned error is `0.00`.

**Rejected path.** If the Controller rejected in SCN-A, `playbook_versions` never gains row 1.1, both arms load 1.0, and `GET /api/transfer/compare` returns identical `amount`, `approval_level`, `estimation_basis` and tool-call sequence for both columns. The panel prints `Learned == Frozen (policy rejected 2027-01-15, reason: "<reason>")`.

### SCN-C know when not to learn, Brightwork V006, `OBL-V006-2026-12`

Dr 6200 / Cr 2100, cost center GA, entry 2026-12-31, reversal 2027-01-01, true-up dated 2027-01-15. Accrual `142 x 185.00 = 26,270.00` by `HOURS_X_RATE`, approval CONTROLLER. Tolerance `max(500.00, 0.02 x 26270.00 = 525.40) = 525.40`.

| surcharge | accrual | hidden INV-V006-008 | variance | vs 525.40 | JE-TRU | outcome |
|---|---|---|---|---|---|---|
| $0.00 (current) | 26,270.00 | 26,270.00 | 0.00 | inside | none | `NO_MISS`, no review |
| $900.00 | 26,270.00 | 27,170.00 | +900.00 | outside | 900.00 | `UNKNOWN`, `ESCALATED`, no candidate |
| $2,400.00 (default) | 26,270.00 | 28,670.00 | +2,400.00 | outside | 2,400.00 | same |
| $6,000.00 | 26,270.00 | 32,270.00 | +6,000.00 | outside | 6,000.00 | same |

Investigation finds no supporting document: `list_related_documents(CTR-006)` returns `["CTR-006"]`, the Fees clause forbids fees without a signed change order, and `search_inbox` finds no thread. Root cause `UNKNOWN`, detail `NO_CONTRACTUAL_BASIS`, `EscalationNote` `ESC-V006-2026-12-01` to E001, no candidate policy. The Meridian alternate is deleted.

---

## 13. Endpoint delta

No endpoint is added and none is removed. Three payload changes:

1. `GET /sim/controls` returns the five controls of section 9.
2. `POST /sim/overrides/apply` request and response gain `apply_mode`. On `HOT` the response reports `runtime_reset: false` and the clock is unchanged.
3. `GET /api/obligations/{obligation_id}` gains `evidence_plan` (the tool list the gateway allowed for this obligation) and `refused_tool_calls[]`, so the workpaper can show "the v1.0 plan, and what it would not let the agent open".

`POST /api/investigate` switches the gateway to `INVESTIGATE` for that `AgentRun` and back to `CLOSE` when it ends. `allow_multi` is removed from `POST /sim/overrides/stage`.

---

## 14. Leakage tests

Kept unchanged: `LK1` no future-dated records; `LK2` visible root rejects escape; `LK3` no private references in the `trueup` package; `LK4` mutation log never visible; `LK5` fork parity; `LK10` advance time no overshoot.

Rewritten:

| # | Assertion |
|---|---|
| `LK6` | `test_no_banned_tokens`: a regex scan of every file under `runtime/visible/` for `EVT-\d`, `RSP-\d`, `OVR-\d`, `MUT-\d`, `TRAIN`, `HELDOUT`, `true_expense`, `scenario`, `root_cause`, `pricing_structure`, `has_scheduled_price_change` returns zero matches |
| `LK7` | `test_amount_allowlist_after_mutation`: the judge-set DataForge rate appears only in `contracts/pricing_schedules/PS-001.*` before `INV-V001-008` releases; the judge-set per-seat price appears only in `contracts/price_notices/VPN-005.*` and only from 2027-01-20T10:00 |
| `LK8` | `test_timing_replies_have_no_amount`: the regex `\$?\d{2,3}(,\d{3})+` matches nothing in the body or `structured_facts` of any `INVOICE_WHEREABOUTS` reply for V001 or V005 |
| `LK9` | `test_replay_inputs_bounded`: every obligation in a replay report belongs to 2026-11 or 2026-12; every cited evidence id exists in that period's cutoff snapshot; every cited actual has `received_date <= run_at` |
| `LK11` | `test_no_back_solve`: for every obligation whose estimate depends on a price the agent must retrieve, that price appears in exactly one visible document, and no other visible number (purchase order amount, prior invoice, GL row, ledger total, or that number divided by 12) falls within the obligation's tolerance of it |

Added:

| # | Assertion |
|---|---|
| `LK12` | `test_evidence_plan_enforced`: during a CLOSE run under playbook 1.0, every `ToolCall` for `list_related_documents`, `resolve_effective_price` or `open_document` of a non-primary document has `refused = true` and returned no content |
| `LK13` | `test_v1_0_knows_no_pricing`: `CTR-001.txt` and `CTR-005.txt` contain none of `Exhibit B`, `Pricing Schedule`, `PS-001`, `VPN-005`, `Contract Year 2`, `escalator`, `uplift`, `renewal price`; no v1.0 `ContractFeatures` record cites a doc_id other than its own `CTR-0NN`; `policies.json` at version 1.0 names no pricing document and no related-document tool |

WORLD_SPEC's own list `L1..L10` keeps L1, L2, L3, L4, L5, L7, L8, L10 unchanged; L6 becomes the LK7 statement; L9 becomes "the vendor master carries no pricing field: no `pricing_model`, `pricing_structure`, `escalator`, `uplift`, `unit_price`".

---

## 15. Files

Fixture root `data/acme/`.

Visible tree, complete: `company.json`, `org_directory.json`, `vendors.json`, `purchase_orders.json`, `policies.json`, `close_policy_manual.md`, `gl_entries.csv`, `ap_queue.csv`, `erp/accrual_schedule_prior.csv`, `contracts/index.json`, `contracts/CTR-0NN.pdf|.txt`, `contracts/pricing_schedules/PS-001.pdf|.txt`, `contracts/price_notices/VPN-005.pdf|.txt`, `invoices/invoices.json`, `invoices/pdf/`, `evidence/usage_daily.csv`, `evidence/service_activity.csv`, `evidence/timesheets.csv`, `inbox/messages.jsonl`.

Deleted files: `change_orders.json`, `contracts/notices/`, `evidence/seat_snapshots.csv`, `evidence/hr_hires.csv`, `evidence/goods_receipts.csv`, `world/private/truth/extra_exceptions.json`.

Private tree: `world/private/events.jsonl`, `world/private/documents/`, `world/private/inbox/scripted_responses.json`, `world/private/truth/{obligations_truth.csv, future_invoices.csv, expected_matches.csv, seeded_root_causes.json, learning_proof/}`.

`obligations_truth.csv`, 30 rows, 21 columns: `obligation_key`, `vendor_id`, `vendor_name`, `period`, `split`, `estimation_basis`, `classification`, `verifier`, `outcome`, `invoice_status_at_cutoff`, `needs_estimate`, `approval_required`, `true_expense`, `frozen_estimate`, `learned_estimate`, `frozen_error`, `root_cause`, `actual_invoice_ids`, `invoice_received_dates`, `true_contract_features`, `expected_safe_actions`. `split` values: `TRAIN` (OBL-V001-2026-12), `HELDOUT` (OBL-V005-2027-01, OBL-V001-2027-01), `STANDARD` (the other 27). Deleted columns: `case_id`, `scenario`, `outreach_target`, `outreach_fact`, `notes`, `trailing_avg_estimate`, `static_rules_estimate`, `policy_enabled_estimate`, `static_error`, `actual_invoice_total`, `frozen_agent_expected`, `policy_agent_expected`.

`seeded_root_causes.json` holds exactly one entry:

```json
[{"root_cause":"PROCEDURE_GAP","process_detail":"EFFECTIVE_PRICE_NOT_RETRIEVED",
  "train":["OBL-V001-2026-12"],"heldout":["OBL-V005-2027-01","OBL-V001-2027-01"],
  "expected_policy_type":"VERIFY_EFFECTIVE_CONTRACT_PRICE",
  "evidence_existed_at_close":true,"missing_required_evidence":"EFFECTIVE_PRICE_CHECK"}]
```

`expected_matches.csv` uses only `ONE_TO_ONE` with `allocation_basis = FULL`. Every invoice maps to exactly one obligation.

`learning_proof/` keeps its five files: `TU-V001-2026-12`, `VE-V001-2026-12`, `POL-0001`, `RPL-POL-0001`, `APR-POL-0001`.

Rubric criterion kinds, eight: `field_eq`, `amount_eq`, `amount_ne`, `evidence_cited`, `approval`, `je`, `no_post_before_approval`, `match`. Literal rubrics are written for three rows only: `OBL-V001-2026-12`, `OBL-V005-2027-01`, `OBL-V006-2026-12`.

Scripted inbox replies, exactly three (`world/private/inbox/scripted_responses.json`):

| key | responder | delay | body rule | releases |
|---|---|---|---|---|
| V001 / 2026-12 / VENDOR_BILLING / INVOICE_WHEREABOUTS | Amira Khan | 30 h | timing only, "December invoices go out around Jan 11", no amount | none |
| V006 / 2026-12 / OPERATIONAL_OWNER / SERVICE_RECEIVED | E014 | 20 h | confirms 142 hours | the timesheet approval patch event |
| V001 / 2027-01 / VENDOR_BILLING / INVOICE_WHEREABOUTS | Amira Khan | 24 h | timing only, "around Feb 10", no amount | none |

`missing_fact` enum, three values: `INVOICE_WHEREABOUTS`, `SERVICE_RECEIVED`, `SCOPE_OR_RATE_CHANGE`. `target_role` enum, three values: `VENDOR_BILLING`, `OPERATIONAL_OWNER`, `CONTROLLER`.

Checkpoints: `CP-DEC` only (clock 2027-01-04T09:00, November close complete under 1.0). `CP-REVEAL` and `CP-JAN` are deleted.

---

## 16. Three-minute flow, the beat spine

19 beats, 180 seconds. `04-scenarios-and-demo-flow.md` renders this table with the spoken line and the fallback column.

| # | window | actor | beat |
|---|---|---|---|
| 1 | 0-8 | presenter | Reset Demo done, pinned `BASELINE_FIXTURE_HASH`, playbook 1.0, clock 2027-01-04T09:00 |
| 2 | 8-14 | presenter | hands over the laptop |
| 3 | 14-26 | judge | picks the DataForge increase |
| 4 | 26-34 | (auto) | What Changed: `PS-001` and only `PS-001` on the visible side |
| 5 | 34-40 | judge | `btn-apply-mutation`, new `world_hash` |
| 6 | 40-56 | presenter | `btn-run-close`; the evidence trail shows the v1.0 plan and the refused related-document call; no pricing document is opened |
| 7 | 56-66 | (auto) | workpaper: $50,000.00, `REVIEW_REQUIRED`, CONTROLLER |
| 8 | 66-72 | presenter | `btn-approve-accrual`, JE posted |
| 9 | 72-82 | presenter | `btn-advance-time`, the real invoice lands |
| 10 | 82-88 | (auto) | miss highlighted, variance against tolerance |
| 11 | 88-104 | presenter | `btn-investigate`: invoice -> contract -> related documents -> PS-001 with the quoted row |
| 12 | 104-110 | (auto) | `PROCEDURE_GAP`, `EFFECTIVE_PRICE_NOT_RETRIEVED` |
| 13 | 110-118 | (auto) | candidate `POL-0001`, no vendor id in the record |
| 14 | 118-128 | presenter | `btn-run-replay`: 20 obligations, changed 1, regressed 0, bias to zero |
| 15 | 128-138 | judge | `btn-approve-policy` or `btn-reject-policy` |
| 16 | 138-146 | judge | picks the PagerLoop price change |
| 17 | 146-164 | presenter | `btn-run-transfer`, Frozen vs Learned side by side |
| 18 | 164-176 | presenter | `btn-advance-time`, result and the audit line |
| 19 | 176-180 | presenter | wrap |

Three real judge choices: beats 3, 15 and 16. SCN-C is a 20 to 30 second closing beat or a question-and-answer backup, not in the timed path. The 60 second expo variant is kept, SCN-A only, preset options. The Golden Path Fallback is kept: on a stall past 5 seconds, `btn-reset-world` and rerun on the override-free baseline world, which still misses by $2,500.00 and has a recording at `runtime/recorded/REC-<hash12>.jsonl`.

---

## 17. Cut list

Everything below is deleted outright from both specs. No stub, no "removed" note, no changelog.

**Company and world.** NS-UK, FX language, wrong-entity case, `Northstar` everywhere; the 13 cost centers CC-100..CC-300; accounts 1000, 1300, 2050, 6100, 6210, 6310, 6400, 6500, 6600; `entry_type` values `ACCRUAL_CARRYFORWARD`, `AMORTIZATION`, `CARD_EXPENSE`; `posted_by = CARD_FEED`; the corporate-card clearing section, `JE-CARD-0001`, `JE-CARD-0002` and every card-feed row; prepaid amortization.

**People.** E005, E006, E012, E013, E015, E017, E018, E019, E020, E021, E022, E030, E031, E032; the `requester` column on vendors and purchase orders; the `REQUESTER`, `FPA`, `TREASURY` and `ACCOUNTING_MANAGER` outreach targets.

**Vendors and documents.** V003, V007, V008, V012, V015, V016, V017, V018, V019; SignalStack, Meridian, PrintWorks, OfficeNest, Beacon, Quantive, Northwind, Helpline, Thames in every sentence; CTR-003, CTR-007, CTR-008, CTR-012, CTR-015, CTR-016, CTR-017, CTR-018, CTR-019; PS-018, TN-019, `DOC-PAGERLOOP-UPLIFT-NOTICE`; `contracts/notices/`; every purchase order except PO-1042, including PO-1063, PO-0962 and the $415,000 declared departure; `change_orders.json`, CO-1 and the seat-expansion story; `pricing_model` and `PRICING_MODEL_TRUE`.

**Cases.** The twelve-case table and every `C01`..`C12` reference; the `case_id` column; duplicate invoice, multi-period invoice, conflicting evidence, mismatch and credit memo, change-order seat expansion, tiered overage learning split, retired-mailbox outreach, no-response outreach, never-accrued prior period, prepaid, termination and proration.

**Methods and enums.** `FIXED_CONTRACT_FEE`, `PRORATED_FEE`, `PO_BASED`, `HISTORICAL_RUN_RATE`; `historical_run_rate_limits`; required-evidence keys `contract`, `service_period`, `usage_record`, `contract_rate`, `service_dates`, `purchase_order`, `service_receipt`, `prior_invoices_min_3`, `pricing_schedule_effective`; classification values `INVOICE_MISMATCHED`, `NO_INVOICE_SERVICE_NOT_RECEIVED`, `INVOICE_SPANS_PERIODS`, `NO_ACCRUAL_PREPAID`; outcome `NO_ACCRUAL_DOCUMENTED`; `invoice_status` `MISMATCHED`, `DUPLICATE_SUSPECTED`; status `HOLD_DO_NOT_POST`; invariants `REQUIRED_IDENTIFIERS`, `ENTITY_ACCOUNT_COMPATIBLE`, `NO_SILENT_POLICY_WEAKENING`; `Exception` and every `EXC-` id; `CashForecastLine`, `AuditFinding`, `CF-`, `AF-`, `HR-` ids.

**ContractFeatures and policy.** `contract_type`, `pricing_structure`, `billing_cadence`, `has_scheduled_price_change`, `has_pricing_exhibit`, `has_usage_component`, `termination_notice_on_file`, `termination_effective_date`, `auto_renews`, `notice_days`, `order_form_fee`; the old nine-field G1 whitelist; root causes `SCHEDULED_PRICE_CHANGE`, `SCHEDULED_ESCALATOR`, `TIERED_OVERAGE_RATE`, `CHANGE_ORDER_SEAT_EXPANSION`, `SCOPE_CHANGE`, `USAGE_VARIANCE`, `PRORATION`, `ESTIMATE_JUDGMENT`, `TIMING_ONLY`; process causes `PROCEDURE_GAP_REQUIRED_EVIDENCE`, `SCOPE_CHANGE_NOT_CONFIRMED`, `NONE_CONTROLLER_JUDGEMENT`, `NO_OBSERVABLE_FEATURE`.

**Lab.** Controls `CTL-ESCALATOR-PCT`, `CTL-ESCALATOR-DATE`, `CTL-SURCHARGE`, `CTL-INVOICE-DELAY`, `CTL-SVC-CONFIRM`, `CTL-USAGE-SPIKE`, `CTL-DUP-INVOICE`, `CTL-TERMINATE`, `CTL-CADENCE` and their validators; the lab-extras tier and the cut order; `allow_multi`; the eligible-vendor whitelist matrix; invariants INV-4 cadence tiling and INV-5 duplicate key; the `TN-005` and `PS-018` preview labels.

**Truth and evaluation.** `trailing_avg_estimate` and the trailing-average baseline everywhere; `static_rules_estimate` and `policy_enabled_estimate` column names; `extra_exceptions.json`; the 30-column truth schema; every literal rubric except the three named in section 15; the four-row held-out evaluation table and its MAPE row; `forward_scope_preview` amounts; `compared_on_action_only` rows other than OBL-V006-2026-12.

**Demo.** WORLD_SPEC section 5 Part A, the 11-beat demo script, in full: the single demo flow lives in `demo_spec/04`; checkpoints `CP-REVEAL` and `CP-JAN`; `demo_cache/beat-NN.json` references to deleted beats; the old PO back-solve attack and its PO-1063 discussion.

---

## 18. Per-file patch list

Every writer keeps the file's existing heading numbers and structure unless told otherwise. The hard rule is that every result is shorter than the file it replaces; the line figures below are targets, and a pinned row is never dropped to hit one.

### `data/spec/01-company-and-cases.md` (was 202 lines, target under 110)

- **Change.** 1.1 becomes Acme AI, Inc., one entity `ACME-US`, the three cost centers of section 1.1 here. 1.2 becomes the seven-person table of section 1.3 here. 1.3 becomes the six-account chart of section 1.2 here plus the `entry_type` enum. 1.5 becomes the control policy of section 5.4 here, with the evidence-plan table of 5.2 replacing the allowed-methods table. 1.6 becomes the ten-vendor master of sections 2.1 and 2.2 here, with the purchase order of 2.3 and the documents of 2.4.
- **Delete.** 1.4's January reveal table (it duplicates the master timeline in 03); 1.7 entirely, replaced by a short "planted situations" list naming the five kept situations: on-time invoice, missing invoice with supported accrual, DataForge procedure gap, PagerLoop transfer, Brightwork unexplained surcharge. Everything in the cut list touching this file.
- **Keep.** The four defined terms (accrual, true-up, cutoff, in arrears), 1.4's close calendar table and period status enum.

### `data/spec/02-sources-and-schemas.md` (was 221 lines, target under 130)

- **Change.** 2.1 file inventory becomes the list in section 15 here. 2.2 keeps only the schemas of surviving files and one example record each. 2.3 VendorObligation adopts the renames and trimmed enums of section 6.3 here, with one worked `OBL-V001-2026-12` record before and after reconciliation. 2.4 becomes the v1.0 ContractFeatures of 6.1 here plus the PriceTerm of 6.2. 2.5 keeps ActionProposal and PolicyEvaluation with the nine invariants and the `EFFECTIVE_PRICE_CHECK` evidence key.
- **Delete.** 2.6 entirely (the relationship table restates foreign keys already in 2.3 and 2.5). Every card-feed, change-order, seat-snapshot, hr-hire and goods-receipt schema.
- **Keep.** The type conventions paragraph, `inbox/messages.jsonl`, `gl_entries.csv`, `ap_queue.csv`.

### `data/spec/03-timeline-and-visibility.md` (was 205 lines, target under 120)

- **Change.** 3.2 master timeline is rebuilt from sections 4.1 to 4.3 here: the release timestamps for all 30 obligations plus `VPN-005` at 2027-01-20T10:00 and the six `PERIOD_STATUS_CHANGE` events. 3.3 keeps four snapshots but each table shrinks to the rows that matter. 3.5 keeps the mechanism and the three replies of section 15 here. 3.7 becomes the `L1..L10` list as amended in section 14 here.
- **Delete.** Every timeline row for a deleted vendor or case; the `USAGE_EXPORT` rows for deleted vendors; the harness pass schedule P1/P2/P3 if it no longer earns its place, otherwise one line.
- **Keep.** 3.1 clock conventions with T0, T_END and the release-time defaults; 3.4 events schema verbatim; 3.6 simulator clock contract verbatim.

### `data/spec/04-private-truth-and-learning.md` (was 262 lines, target under 140)

- **Change.** 4.1 file table drops `extra_exceptions.json` and states 30 obligations. 4.2 becomes the 21-column schema of section 15 here with the seven rubric kinds. 4.3 keeps literal rows for `OBL-V001-2026-12`, `OBL-V005-2027-01` and `OBL-V006-2026-12` only. 4.4 keeps `future_invoices.csv`, `expected_matches.csv` (ONE_TO_ONE only) and the one-entry `seeded_root_causes.json`. 4.5 rewrites the honesty argument around the evidence plan and the tool gateway, citing `erp/accrual_schedule_prior.csv` as proof the human team accrued fixed-fee vendors straight from the order form. 4.6 replaces POL-0001 with section 7 here and the replay report with section 8 here. 4.7 becomes a two-row held-out table, `OBL-V005-2027-01` and `OBL-V001-2027-01`.
- **Delete.** Every rubric table for a deleted obligation; the trailing-average baseline and its MAPE row; 4.8 metric rows that depend on deleted truth columns.
- **Keep.** 4.6 items 1, 2, 5 and 6 (confirmed outcome, root-cause classification, approval record, versioning) with amounts recomputed at the 8 percent default.

### `data/spec/05-demo-path-and-file-tree.md` (was 174 lines, target under 90)

- **Change.** Title becomes "Fixture file tree and build delta". Part B is the tree of section 15 here under `data/acme/`. Part C build delta is rewritten around: rename the root, collapse to ten vendors and six accounts, add the tool gateway and evidence plans, add `VPN-005`, drop the deleted modules.
- **Delete.** Part A, the 11-beat demo script, entirely. `CP-REVEAL` and `CP-JAN`. The `spend_type` map table. The literal V018 vendor record and the SignalStack events.
- **Keep.** `contracts/index.json` literal rows, now `PS-001` and `VPN-005`; the acceptance-check column on every build step.

### `data/demo_spec/01-scenario-lab-and-mutations.md` (was 246 lines, target under 120)

- **Change.** 1.2 becomes the five controls of section 9 here, each a dropdown with the `(current)` label and the locking tooltip of 9.3. 1.3 What Changed keeps both blocks, with the `VPN-005` release label. 2.1 to 2.5 become one subsection per control from the table in 9.2, each with a full `ScenarioOverride` and the arithmetic. Section 3 becomes the eight invariants of 9.4.
- **Delete.** Subsections 2.2 and 2.4 to 2.9 as they stand; the disabled-state notes for deleted controls; the eligible-vendor dropdown logic (each control has one vendor now).
- **Keep.** The 1.1 page layout diagram with panel names updated; 1.4 what the judge can and cannot see. Include the section 9.2 worked example verbatim.

### `data/demo_spec/02-state-machine-and-time.md` (was 240 lines, target under 130)

- **Change.** Section 1 state table keeps all 19 rows with the clocks of section 11 here. Section 2's diagram drops the `evidence_existed_at_close = false` edge. 3.1 `btn-run-close` gains the gateway initialisation in CLOSE mode. 3.2 `btn-advance-time` keeps its fixed `target_ts` values. Section 4 uses the SCN-A numbers at 8 percent. Section 5 becomes the `LK1..LK13` list of section 14 here.
- **Delete.** The PO-1063 and `VAL-PRODUCTION-FEE` discussion in LK11; references to deleted controls in every button's failure handling.
- **Keep.** 3.3 and 3.4 reset semantics verbatim, including "Reset World keeps `trueup_playbook.db`".

### `data/demo_spec/03-playbook-memory-and-api.md` (was 268 lines, target under 150)

- **Change.** Section 1 DDL keeps all four playbook tables and `demo_state`; `tool_calls` gains `mode`, `refused`, `refusal_reason`. Section 2 becomes the POL-0001 of section 7 here. Section 3 loader gains a step: the gateway is built from the active playbook's evidence plan plus every ACTIVE policy's `evidence_plan_delta`. Section 4 G1 uses the whitelist of 7.1; G2 is unchanged. Section 6 transfer runner pins the arms and uses the SCN-B numbers of section 12. Section 7 API tables carry the three payload changes of section 13.
- **Add.** One short subsection, "Tool gateway", holding section 5.2 and 5.3 here. This file owns the gateway.
- **Delete.** Every `has_scheduled_price_change` and `pricing_structure` mention; the `allow_multi` and `423 WORLD_LOCKED` second-override wording replaced by the per-control rule of 9.3; build-checklist rows for deleted work.
- **Keep.** Section 5 Approve and Reject including the rejected-path proof; section 8 SSE stream, with one added event type for a refused call.

### `data/demo_spec/04-scenarios-and-demo-flow.md` (was 206 lines, target under 120)

- **Change.** Sections 1 to 3 become SCN-A, SCN-B and SCN-C exactly as section 12 here gives them, with the tool-call trails named there. Section 4 becomes the 19-beat table of section 16 here. Section 5 keeps the 60 second variant. Section 6 keeps the pre-demo checklist with the five controls.
- **Delete.** Every SignalStack and V018 reference; the `CTL-ESCALATOR-DATE` bonus proof; the Meridian second-example paragraph in SCN-C.
- **Keep.** The `EscalationNote` literal, retargeted at V006 with the default $2,400.00; the Golden Path Fallback rule.

### `data/demo_spec/05-weaknesses-and-fixes.md` (was 124 lines, target under 95)

- **Change.** Section 0 arithmetic recomputed: SCN-A tolerance 1,000.00; 8 percent variance 4,000.00; 12 percent variance 6,000.00; PagerLoop tolerance 500.00 and 15 percent variance 1,800.00; replay coverage 1 touched of 20. W01's fix becomes the PagerLoop and DataForge-January rows already on `#transfer-panel`. W03's fix keeps only the live LK7 print; the free-entry half is removed because the brief forbids free-form fields. W05 uses 1 of 20. W11 is rewritten for five controls and the two-control stack of 9.3.
- **Delete.** The "spec applied" note in the file header, and W09 to W12 as they stand.
- **Keep.** Eight attacks only, W01 to W08, each pointing at a section rather than a line number, because every sibling file is rewritten in the same pass: strawman baseline, gateway-not-model, POL-0001 breadth, PagerLoop-equals-DataForge, decorative LLM, replay of n=1, approval is a JSON field, out-of-period true-up disclosure.
