# TrueUp Close: Acme AI synthetic world and dataset specification

Status: specification only, no code changed. Builds on the existing generator in `data/gen/` and fixture set in `data/acme/`.
Product direction is frozen in `trueup_close_team_spec.pdf`. Sections are also kept separately under `data/spec/`.
v2: simplified to Acme AI, six judge-facing vendors, causality fix.

## 1. Acme AI company model and planted situations

Scope: the static company world that every other section builds on. All data is synthetic; every rendered document begins with the line `SYNTHETIC DATA - ACME AI, INC. (FICTIONAL). NOT A REAL COMPANY OR VENDOR.` Terms used once and then assumed:
- **Accrual**: an expense booked at month-end for service received but not yet invoiced. It auto-reverses on day 1 of the next month.
- **True-up**: the difference between the later actual invoice and the accrual (`actual - accrued`).
- **Cutoff**: the last moment an invoice counts as "on hand" for a period.
- **In arrears / in advance**: invoiced after / before the service period.

### 1.1 Entity and cost centers

Acme AI, Inc., one legal entity `ACME-US`, US, USD only. No FX, no second entity. Fixture root directory `data/acme/`. Email domain `acme.example`. The playbook is "the Acme AI playbook".

| cost_center | name |
|---|---|
| `ENG` | Engineering |
| `DATA` | Data and ML |
| `GA` | General and Admin |

### 1.2 Finance roles and who approves what

| employee_id | name | role | cost_center | does |
|---|---|---|---|---|
| E001 | Dana Whitfield | CONTROLLER | GA | approves accruals >= $25,000.00, every ESCALATE, every learned policy |
| E002 | Marcus Oyelaran | ACCOUNTING_MANAGER | GA | approves accruals $10,000.00 to $24,999.99, or any accrual with confidence < 0.85 below $25,000.00 |
| E003 | Sofia Brandt | AP_SPECIALIST | GA | owns the AP queue and mailbox; approves nothing |
| E004 | Ken Ito | CLOSE_ACCOUNTANT | GA | prepared the 2026-05..2026-10 accruals by hand; preparer of `erp/accrual_schedule_prior.csv`; approves nothing |
| E010 | Priya Raman | BUDGET_OWNER | DATA | owns V001, V013 |
| E011 | Sam Okafor | BUDGET_OWNER | ENG | owns V002, V005, V010 |
| E014 | Nina Petrov | BUDGET_OWNER | GA | owns V004, V006, V009, V011, V014 |

Preparer and approver are never the same person. TrueUp is the preparer from 2026-11 and writes `posted_by = "TRUEUP"`. Approval enum `NONE | REVIEWER | CONTROLLER`; `REVIEWER` resolves to E002, `CONTROLLER` to E001.

### 1.3 Chart of accounts

| account | name | type |
|---|---|---|
| 2000 | Accounts Payable | liability |
| 2100 | Accrued Liabilities | liability |
| 6110 | Cloud and AI Infrastructure | expense |
| 6120 | Software and Data Subscriptions | expense |
| 6200 | Professional Services | expense |
| 6300 | Rent | expense |

`entry_type` enum: `INVOICE`, `ACCRUAL`, `ACCRUAL_REVERSAL`, `TRUE_UP`. `posted_by` is an employee id or `TRUEUP`. `gl_entries.csv` keeps the `obligation_id` column, required on every `TRUEUP` row.

### 1.4 Close calendar and period statuses

Period status enum: `FUTURE` (month still running, postings allowed), `OPEN` (month ended, TrueUp is closing it), `CLOSED` (Controller signed off, no postings allowed). Cutoff is `23:59:59` on the cutoff date; the period goes `CLOSED` at that instant. An invoice received after a period's own cutoff is never booked into that period; it is booked in the next period and matched to the accrual.

| period | type | OPEN from | cutoff date | playbook in force |
|---|---|---|---|---|
| 2026-05..2026-10 | history, CLOSED at T0 | n/a | n/a | human process |
| 2026-11 | warm-up | 2026-12-01T00:00 | 2026-12-05 | 1.0 |
| 2026-12 | the failure | 2027-01-01T00:00 | 2027-01-05 | 1.0 |
| 2027-01 | held out | 2027-02-01T00:00 | 2027-02-05 | 1.1 (learned arm) or 1.0 (frozen arm) |

### 1.5 Control policy v1.0

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

| estimation_basis | evidence plan (playbook 1.0, CLOSE mode) |
|---|---|
| `ACTUAL_INVOICE` | `get_vendor`, `read_ap_queue`, `open_invoice`, `open_document(primary)`, `get_service_confirmation` |
| `CONTRACT_PRICE` | `get_vendor`, `list_invoices(limit=3)`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue` |
| `USAGE_X_RATE` | `get_vendor`, `read_usage_meter`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue` |
| `HOURS_X_RATE` | `get_vendor`, `read_timesheets`, `open_document(primary)`, `get_purchase_order`, `read_ap_queue` |
| `NONE` | none; escalate |

`open_document(primary)` is the contract's own order form and nothing else. The `CONTRACT_PRICE` plan does not include related pricing documents: under playbook 1.0 in CLOSE mode the agent never lists or opens a contract's related documents, so it never sees a pricing schedule or price notice and never knows one exists. That retrieval opens only in INVESTIGATE mode, or in CLOSE mode when an ACTIVE policy's `evidence_plan_delta` adds it. `send_outreach` and `search_inbox` are always allowed in CLOSE mode.

### 1.6 Vendors, purchase order and documents

Ten vendors: six judge-facing, four background. No other vendor exists. `vendors.json` columns: `vendor_id, name, category, spend_type, gl_account, cost_center, operational_owner, billing_contact, billing_email, contract_id, po_id, payment_terms, onboarded_date, status, notes`. `status` is always `ACTIVE`. `AWS` and `ModelAPI` are intuitive labels on synthetic data; every document they generate carries the synthetic label.

| id | name | account | CC | owner | contract | related documents | spend_type | estimation_basis | baseline |
|---|---|---|---|---|---|---|---|---|---|
| V001 | DataForge Inc. | 6120 | DATA | E010 | CTR-001 | `PS-001` | RECURRING | CONTRACT_PRICE | $50,000.00/month, Contract Year 1; Year 2 starts 2026-12-01 |
| V002 | AWS | 6110 | ENG | E011 | CTR-002 | none | USAGE | USAGE_X_RATE | `compute_hours x $0.25` |
| V013 | ModelAPI | 6110 | DATA | E010 | CTR-013 | none | USAGE | USAGE_X_RATE | input $3.00/M tokens, output $15.00/M tokens |
| V005 | PagerLoop Inc. | 6120 | ENG | E011 | CTR-005 | `VPN-005` (filed 2027-01-20) | RECURRING | CONTRACT_PRICE | 120 seats x $100.00 = $12,000.00/month, no proration |
| V006 | Brightwork Consulting Group | 6200 | GA | E014 | CTR-006 | none | SERVICES | HOURS_X_RATE | 142 h x $185.00 = $26,270.00 in December |
| V014 | OfficeLease | 6300 | GA | E014 | CTR-014 | none | RECURRING | CONTRACT_PRICE | $22,500.00/month, fixed |

Background (four), never shown in the Judge Scenario Lab, visible only as rows in the replay report, the close inventory and the metrics:

| id | name | account | CC | owner | contract | spend_type | estimation_basis | baseline | why it is here |
|---|---|---|---|---|---|---|---|---|---|
| V004 | Lumen CRM Corp. | 6120 | GA | E014 | CTR-004 | RECURRING | CONTRACT_PRICE | $18,000.00/month | matches POL-0001, no pricing documents on file: regression control 1 |
| V009 | PayCircle Inc. | 6120 | GA | E014 | CTR-009 | RECURRING | CONTRACT_PRICE | $4,150.00/month | matches POL-0001, no pricing documents on file: regression control 2 |
| V010 | SecureLayer Systems | 6120 | ENG | E011 | CTR-010 | USAGE | USAGE_X_RATE | 1,800,000 events x $0.003 = $5,400.00/month | does not match POL-0001 (basis is not CONTRACT_PRICE) |
| V011 | TalentBridge Partners | 6200 | GA | E014 | CTR-011 | SERVICES | HOURS_X_RATE | 60 h x $150.00 = $9,000.00/month | does not match POL-0001 (basis is not CONTRACT_PRICE) |

One purchase order in the world: `PO-1042`, vendor V006, type `PROJECT_TM`, not-to-exceed `authorized_amount = 400000.00`, valid 2026-07-01..2027-06-30, issued 2026-06-24, status `OPEN`, owner E014, description "Brightwork PMO delivery, FY27". No SaaS, cloud, API or rent vendor has a PO. `contracts/index.json` is the document index, reachable only through `list_related_documents(contract_id)`. Ten contracts exist, one per vendor above: CTR-001, CTR-002, CTR-004, CTR-005, CTR-006, CTR-009, CTR-010, CTR-011, CTR-013, CTR-014, each an `MSA_ORDER_FORM` visible from T0. Two related documents also exist: `PS-001` (`PRICING_SCHEDULE`, contract CTR-001, effective 2025-12-01, filed 2025-11-24, visible from T0) and `VPN-005` (`VENDOR_PRICE_NOTICE`, contract CTR-005, effective 2027-01-01, filed 2027-01-20, visible from 2027-01-20T10:00). Causality rule, hard: `CTR-001.txt` contains no sentence referring to a pricing schedule, an exhibit, a contract year 2, an escalator or a future price; `CTR-005.txt` contains no sentence referring to a renewal notice or an uplift; a contract's related documents are reachable only through `list_related_documents(contract_id)`, which playbook 1.0 forbids in CLOSE mode; every `ContractFeatures` record built under playbook 1.0 comes from the order form alone, and none carries a `pricing_structure` field or cites a doc_id other than its own contract.

### 1.7 Planted situations

Five, walked in full in `04-scenarios-and-demo-flow.md`:

- **On-time invoice.** Invoice on hand at cutoff, no estimate needed, outcome `CLOSE_READY`.
- **Missing invoice with supported accrual.** AWS, ModelAPI and OfficeLease: no invoice at cutoff, but the usage meter, rate card or contract price supports a confident accrual; the true-up lands at $0.00.
- **DataForge procedure gap.** V001, December 2026: the order form alone supports $50,000.00. The effective price is on file in `PS-001`, but playbook 1.0 never retrieves it, so the accrual misses. Root cause `PROCEDURE_GAP`.
- **PagerLoop transfer.** V005, January 2027: never accrued before, since its invoices always arrived on time. The effective per-seat price sits in `VPN-005`, a vendor price notice, not a pricing schedule. Proves the learned policy generalizes to a document TrueUp has never seen.
- **Brightwork unexplained surcharge.** V006, December 2026: an invoice line with no basis in the contract, the purchase order or the timesheets. No supporting document exists, so the outcome is `ESCALATED`, root cause `UNKNOWN`, no candidate policy.

## 2. Source systems, files and schemas

All paths are relative to `runtime/visible/` under the fixture root `data/acme/`. The simulator copies `world/seed/` there at T0 = `2026-12-01T00:00:00` and then appends rows or adds files as events release. TrueUp tools get this root only.

Conventions. Types: `str`, `int`, `dec` (number, 2 decimals, USD), `bool`, `date` (`YYYY-MM-DD`), `ym` (`YYYY-MM`), `ts` (`YYYY-MM-DDTHH:MM:SS`, company local time, no offset), `enum`, `[]` = list. CSV blanks mean null. An `evidence_id` is the primary key of a visible record (for example `CTR-001`, `PS-001`, `INV-V001-008`, `SA-DATAFORGE-2026-12`). Files with a composite key use the form given in the table.

### 2.1 File inventory

| Path | Imitates | Format | Primary key | Grows after T0 via |
|---|---|---|---|---|
| `company.json` | ERP setup | JSON object | n/a | `PERIOD_STATUS_CHANGE` rewrites `close_calendar[].status` |
| `org_directory.json` | Org directory / HRIS | JSON object | `employee_id`; contacts `(vendor_id, role)` | static after T0 |
| `vendors.json` | Procurement vendor master | JSON list | `vendor_id` | static after T0 |
| `purchase_orders.json` | Procurement | JSON list | `po_id` | static after T0 |
| `contracts/index.json` and its `CTR-0NN`, `PS-001`, `VPN-005` PDF+text files | Contract repository | JSON list + PDF + text | `doc_id` | `VPN-005` becomes visible 2027-01-20T10:00; the rest is static |
| `invoices/invoices.json`, `invoices/pdf/`, `ap_queue.csv` | AP inbox capture and subledger | JSON list + PDF + CSV | `invoice_id` / `ap_id` | `INVOICE_RECEIVED` (one event, both files) |
| `gl_entries.csv` | ERP GL extract | CSV | `(entry_id, line_no)`; evidence_id = `entry_id` | TrueUp posting tool |
| `erp/accrual_schedule_prior.csv` | Close team spreadsheet | CSV | `(vendor_id, period)` | seed only |
| `evidence/usage_daily.csv` | Usage / metering export | CSV | `(vendor_id, date, meter)` | `USAGE_EXPORT`, whole month at 06:00 on day 1 of next month |
| `evidence/service_activity.csv` | SSO + vendor admin consoles | CSV | `activity_id` | `EVIDENCE_UPDATE`, whole month at 06:00 on day 1 of next month |
| `evidence/timesheets.csv` | PMO timesheet tool | CSV | `(vendor_id, week_ending)` | `EVIDENCE_UPDATE` (new weeks, approvals) |
| `policies.json`, `close_policy_manual.md` | Policy manual, data and prose | JSON + Markdown | `policy_version` | rewritten by TrueUp on activation of v1.1 |
| `inbox/messages.jsonl` | Shared close inbox | JSON lines | `message_id` | simulator only: OUTBOUND row on `send_outreach`, INBOUND row after `delay_hours` |

`world/private/inbox/scripted_responses.json` and `world/private/truth/` are never visible; TrueUp tools cannot reach them.

### 2.2 Schemas and example records

**company.json**: `name`, `description`, `base_currency` "USD", `entities[]` {`entity_id` "ACME-US", `name`, `country`}, `cost_centers[]` {`id`, `name`}, `chart_of_accounts[]` {`account`, `name`, `type` enum asset/liability/expense}, `close_calendar[]` {`period` ym, `cutoff` date, `status` enum FUTURE/OPEN/CLOSED}, `closed_periods[]` ym. FUTURE = month still running (postings allowed); OPEN = month ended and in close; CLOSED = no postings. OPEN starts 00:00 on day 1 of the next month, CLOSED at the cutoff instant (23:59:59). Verifier check `PERIOD_OPEN` passes when status is not CLOSED. At T0: 2026-11 OPEN, 2026-12 and 2027-01 FUTURE. Example: `{"period": "2026-12", "cutoff": "2027-01-05", "status": "FUTURE"}`.

**org_directory.json** `employees[]`: `employee_id` PK, `name`, `title`, `role` enum (CONTROLLER, ACCOUNTING_MANAGER, AP_SPECIALIST, CLOSE_ACCOUNTANT, BUDGET_OWNER), `cost_center` FK nullable, `legal_entity_id` "ACME-US", `email`. `vendor_contacts[]`: `vendor_id` FK, `name`, `email`, `role` enum VENDOR_BILLING/VENDOR_ACCOUNT_MANAGER. Example: `{"employee_id": "E010", "name": "Priya Raman", "role": "BUDGET_OWNER", "cost_center": "DATA", "legal_entity_id": "ACME-US", "email": "priya.raman@acme.example"}`.

**vendors.json**: `vendor_id` PK, `name`, `category` enum (SAAS_OR_DATA, CLOUD_USAGE, CONSULTING, RENT), `spend_type` enum (RECURRING, USAGE, SERVICES), `gl_account` FK, `cost_center` FK, `legal_entity_id` "ACME-US", `operational_owner` FK employee, `billing_contact`, `billing_email`, `contract_id` FK, `po_id` FK nullable (only V006 has one), `payment_terms`, `onboarded_date` date, `status` "ACTIVE" (all ten vendors, always), `notes`. Example: `{"vendor_id": "V001", "name": "DataForge Inc.", "category": "SAAS_OR_DATA", "spend_type": "RECURRING", "gl_account": "6120", "cost_center": "DATA", "legal_entity_id": "ACME-US", "operational_owner": "E010", "billing_contact": "Amira Khan", "billing_email": "billing@dataforge.example", "contract_id": "CTR-001", "po_id": null, "payment_terms": "Net 30", "onboarded_date": "2025-11-20", "status": "ACTIVE", "notes": ""}`.

**purchase_orders.json**: `po_id` PK, `vendor_id` FK, `owner` FK employee, `cost_center` FK, `legal_entity_id` "ACME-US", `authorized_amount` dec, `type` enum BLANKET_ANNUAL/PROJECT_TM/ONE_TIME, `valid_from`, `valid_to`, `issued_date`, `status` enum OPEN/CLOSED, `description`. Exactly one PO exists: `{"po_id": "PO-1042", "vendor_id": "V006", "owner": "E014", "cost_center": "GA", "legal_entity_id": "ACME-US", "authorized_amount": 400000.00, "type": "PROJECT_TM", "valid_from": "2026-07-01", "valid_to": "2027-06-30", "issued_date": "2026-06-24", "status": "OPEN", "description": "Brightwork PMO delivery, FY27"}`.

**contracts/index.json**: `doc_id` PK, `doc_type` enum (MSA_ORDER_FORM = every `CTR-0NN` file, PRICING_SCHEDULE, VENDOR_PRICE_NOTICE), `contract_id` str (groups documents of one agreement), `vendor_id` FK, `title`, `effective_date`, `filed_date`, `filed_by` "E003" (AP specialist, files every document), `visible_from` ts, `files[]`. Those ten fields are the whole record. Ten `CTR-0NN` order forms exist, one per vendor. `PS-001` (related to CTR-001) and `VPN-005` (related to CTR-005) are the only related documents in the world; the full document table and exact text bodies live in `01-company-and-cases.md`, the literal rows in `05-demo-path-and-file-tree.md`. Example: `{"doc_id": "PS-001", "doc_type": "PRICING_SCHEDULE", "contract_id": "CTR-001", "vendor_id": "V001", "title": "Exhibit B - Pricing Schedule", "effective_date": "2025-12-01", "filed_date": "2025-11-24", "filed_by": "E003", "visible_from": "2026-12-01T00:00:00", "files": ["contracts/pricing_schedules/PS-001.pdf", "contracts/pricing_schedules/PS-001.txt"]}`.

Hard rule: `CTR-001.txt` and `CTR-005.txt` contain no sentence referring to a pricing schedule, a renewal notice, an escalator or a future price. The only path from a contract to its related documents is `list_related_documents(contract_id)`, which playbook 1.0 forbids in CLOSE mode (2.4, 2.5).

**invoices/invoices.json**: `invoice_id` PK, `invoice_number`, `vendor_id` FK, `vendor_name`, `bill_to` "Acme AI, Inc.", `invoice_date`, `received_date`, `service_period_start`, `service_period_end`, `po_id` FK nullable, `currency` "USD", `amount` dec, `line_items[]` {`description`, `quantity` dec, `unit_price` dec, `amount` dec}, `payment_terms`, `received_channel`, `notes`. Example: `{"invoice_id": "INV-V001-008", "invoice_number": "DF-2256", "vendor_id": "V001", "vendor_name": "DataForge Inc.", "bill_to": "Acme AI, Inc.", "invoice_date": "2026-12-31", "received_date": "2027-01-12", "service_period_start": "2026-12-01", "service_period_end": "2026-12-31", "po_id": null, "currency": "USD", "amount": 52500.00, "line_items": [{"description": "DataForge Platform subscription - December 2026", "quantity": 1, "unit_price": 52500.00, "amount": 52500.00}], "payment_terms": "Net 30", "received_channel": "ap@acme.example", "notes": ""}`.

**ap_queue.csv**: `ap_id` PK, `invoice_id` FK, `invoice_number`, `vendor_id` FK, `received_date`, `received_channel`, `amount` dec, `coded_entity` "ACME-US", `coded_account` FK, `coded_cost_center` FK, `po_id` FK nullable, `status` enum PENDING_APPROVAL/APPROVED/ON_HOLD/PAID, `approver` FK employee, `due_date`, `paid_date` nullable. Example row: `AP-V001-008,INV-V001-008,DF-2256,V001,2027-01-12,ap@acme.example,52500.00,ACME-US,6120,DATA,,PENDING_APPROVAL,E001,2027-02-11,`.

**gl_entries.csv**: `entry_id`, `line_no` int, `posting_date`, `period` ym, `legal_entity_id` "ACME-US", `account` FK, `cost_center` FK, `vendor_id` FK nullable, `debit` dec, `credit` dec, `entry_type` enum (INVOICE, ACCRUAL, ACCRUAL_REVERSAL, TRUE_UP), `reference`, `memo`, `reversal_of` entry_id nullable, `posted_by` (employee id or `TRUEUP`), `obligation_id` nullable (required on every `TRUEUP` row). TrueUp entries are `JE-ACR-`, `JE-REV-`, `JE-INV-`, `JE-TRU-` + obligation or invoice suffix. Example pair: `JE-ACR-V001-2026-12,1,2026-12-31,2026-12,ACME-US,6120,DATA,V001,50000.00,0.00,ACCRUAL,ACR-V001-2026-12,Accrual DataForge Inc. service 2026-12,,TRUEUP,OBL-V001-2026-12` and its balancing line `JE-ACR-V001-2026-12,2,2026-12-31,2026-12,ACME-US,2100,DATA,V001,0.00,50000.00,ACCRUAL,ACR-V001-2026-12,Accrual DataForge Inc. service 2026-12,,TRUEUP,OBL-V001-2026-12`.

**erp/accrual_schedule_prior.csv** (human team's rollforward, one row per vendor-month accrued 2026-05..2026-10): `vendor_id`, `vendor_name`, `period` ym, `gl_account` FK, `cost_center` FK, `basis` str, `accrued` dec, `actual` dec nullable, `variance` dec nullable (= actual - accrued), `invoice_number` nullable, `invoice_received` date nullable, `je_ref` FK, `preparer` "E004", `reviewer` "E002", `note`. Eight vendors have rows; V005 PagerLoop and V010 SecureLayer have none, because their invoices always arrived before cutoff in history. DataForge has six rows, 2026-05 to 2026-10, each accrued 50,000.00 and actual 50,000.00, variance 0.00, basis "order form monthly fee": this is the proof the human team accrued fixed-fee vendors straight from the order form and never opened a pricing document. Example: `V001,DataForge Inc.,2026-10,6120,DATA,order form monthly fee,50000.00,50000.00,0.00,DF-2241,2026-11-09,ACR-V001-2026-10,E004,E002,Contract Year 1 rate per order form`.

**evidence/usage_daily.csv**: `vendor_id`, `date`, `meter` enum (`compute_hours`, `input_tokens_m`, `output_tokens_m`, `events_scanned`), `quantity` int, `source`. Daily rows are `floor(monthly_total / days_in_month)`, with the final day carrying the remainder. Example: `V002,2026-12-01,compute_hours,3870,usage-export`.

**evidence/service_activity.csv**: `activity_id` PK (`SA-<APPKEY>-<period>`), `period` ym, `application`, `vendor_id` FK, `source_system`, `active_users` int, `active_days` int, `api_calls` int, `first_activity_date`, `last_activity_date`, `service_status` enum ACTIVE/PARTIAL/INACTIVE. Covers every RECURRING vendor, so `get_service_confirmation` always has a row: V001, V004, V005, V009 from SSO and vendor admin APIs, V014 from the building access system. Example: `SA-DATAFORGE-2026-12,2026-12,DataForge Platform,V001,okta-sso+dataforge-admin-api,41,31,1284000,2026-12-01,2026-12-31,ACTIVE`.

**evidence/timesheets.csv**: `vendor_id`, `po_id` FK, `week_ending`, `service_month` ym, `hours` int, `rate` dec, `approval_status` enum APPROVED/PENDING, `approved_by` FK nullable, `approved_date` nullable. Only Brightwork (V006) has timesheets. At the December cutoff the weeks ending 2026-12-18 (38h) and 2026-12-25 (36h) are still PENDING; earlier December weeks are APPROVED for 68 hours. `68 + 38 + 36 = 142`, `142 x 185.00 = 26,270.00`.

**policies.json**: `policy_version`, `close_cutoff_day` int, `approval_thresholds` {`auto_max` 9999.99, `reviewer_max` 24999.99, `min_auto_confidence` 0.85}, `true_up_tolerance` {`abs` 500.0, `pct` 2.0}, `outreach_wait_hours` 48, `evidence_plans` {basis: [tool, ...]} (2.5), `learned_policies[]`. **close_policy_manual.md** is its prose mirror; a new version file is written when a policy activates.

**inbox/messages.jsonl**: `message_id` PK (`MSG-<outreach_id>-O` outbound, `-R` reply), `thread_id` = `outreach_id`, `obligation_id` FK, `direction` enum OUTBOUND/INBOUND, `from`, `to`, `target_role` enum (VENDOR_BILLING, OPERATIONAL_OWNER, CONTROLLER), `missing_fact` enum (INVOICE_WHEREABOUTS, SERVICE_RECEIVED, SCOPE_OR_RATE_CHANGE), `sent_at` ts, `response_type` enum DATA/CONFIRMATION/CONFLICTING/DECISION nullable, `body`, `structured_facts` object, `attachments[]`. Silence produces no row. Example: `{"message_id": "MSG-OUT-V001-2026-12-01-R", "obligation_id": "OBL-V001-2026-12", "direction": "INBOUND", "from": "billing@dataforge.example", "to": "close@acme.example", "target_role": "VENDOR_BILLING", "missing_fact": "INVOICE_WHEREABOUTS", "sent_at": "2027-01-05T15:30:00", "response_type": "DATA", "body": "December invoices will go out around Jan 11.", "structured_facts": {"expected_issue_date": "2027-01-11"}, "attachments": []}`.

### 2.3 Canonical VendorObligation

One record per vendor per service month, id `OBL-<vendor_id>-<ym>`. Stored in the TrueUp state store, not under `runtime/visible/`.

| Field | Type |
|---|---|
| `obligation_id`, `vendor_id`, `legal_entity_id`, `service_period_start/end`, `close_period`, `category`, `cost_center`, `contract_id`, `po_id` nullable, `expected_bill_date` | str, FK, FK, date x2, ym, enum, FK, FK, FK, date |
| `invoice_status` | enum RECEIVED, MISSING, NOT_EXPECTED |
| `service_received_status` | enum CONFIRMED, PARTIAL, UNCLEAR, NOT_RECEIVED |
| `evidence_ids` | evidence_id[] (append only) |
| `classification` | enum VALID_INVOICE_MATCHES, NO_INVOICE_SERVICE_RECEIVED, NO_INVOICE_SERVICE_UNCLEAR |
| `estimation_basis` | enum ACTUAL_INVOICE, CONTRACT_PRICE, USAGE_X_RATE, HOURS_X_RATE, NONE |
| `estimated_amount`, `confidence_score`, `risk_score` | dec nullable (deterministic estimator only), float 0..1, float 0..1 |
| `policy_version_used`, `approval_history`, `outreach_history` | str, Approval[], OutreachTask[] |
| `accrual_entry_id` | FK gl_entries.entry_id nullable |
| `invoice_id`, `true_up_amount`, `root_cause` | FK nullable, dec nullable, enum nullable (PROCEDURE_GAP, UNKNOWN) |
| `outcome` | enum nullable: CLOSE_READY, ACCRUED, RECONCILED, ESCALATED |
| `status` | enum DISCOVERED, IN_EVIDENCE_GATHERING, INVOICE_VALIDATED, ACCRUAL_CANDIDATE, PENDING_REVIEW, ACCRUED, INVOICE_RECEIVED, MATCHED, TRUE_UP_REQUIRED, RECONCILED, OUTREACH_PENDING, ESCALATED |

`OBL-V001-2026-12` right after accrual (2027-01-05, policy 1.0, baseline world: DataForge increase 5 percent): `{"obligation_id": "OBL-V001-2026-12", "vendor_id": "V001", "legal_entity_id": "ACME-US", "service_period_start": "2026-12-01", "service_period_end": "2026-12-31", "close_period": "2026-12", "category": "SAAS_OR_DATA", "cost_center": "DATA", "contract_id": "CTR-001", "po_id": null, "expected_bill_date": "2027-01-11", "invoice_status": "MISSING", "service_received_status": "CONFIRMED", "evidence_ids": ["CTR-001", "SA-DATAFORGE-2026-12", "MSG-OUT-V001-2026-12-01-R"], "classification": "NO_INVOICE_SERVICE_RECEIVED", "estimation_basis": "CONTRACT_PRICE", "estimated_amount": 50000.00, "confidence_score": 0.91, "risk_score": 0.30, "accrual_entry_id": "JE-ACR-V001-2026-12", "invoice_id": null, "true_up_amount": null, "root_cause": null, "status": "ACCRUED", "outcome": "ACCRUED", "policy_version_used": "1.0", "approval_history": [{"approval_id": "APR-V001-2026-12-01", "level": "CONTROLLER", "approver_id": "E001", "decision": "APPROVED", "decided_at": "2027-01-05T17:30:00"}]}`.

After reconciliation (2027-01-12), only these fields change: `{"invoice_status": "RECEIVED", "invoice_id": "INV-V001-008", "true_up_amount": 2500.00, "root_cause": "PROCEDURE_GAP", "status": "RECONCILED", "outcome": "RECONCILED", "evidence_ids": ["CTR-001", "SA-DATAFORGE-2026-12", "MSG-OUT-V001-2026-12-01-R", "INV-V001-008", "PS-001"]}`.

The accrual auto-reverses on 2027-01-01 (`JE-REV-V001-2026-12`). The invoice posts as `JE-INV-V001-008` Dr 6120 / Cr 2000 $50,000.00 (the accrued portion, `entry_type = INVOICE`) and `JE-TRU-V001-2026-12` Dr 6120 / Cr 2000 $2,500.00 (`entry_type = TRUE_UP`, dated 2027-01-12). $2,500.00 exceeds tolerance (`max(500.00, 0.02 x 50000.00) = 1000.00`), so the path is INVOICE_RECEIVED -> TRUE_UP_REQUIRED -> RECONCILED.

### 2.4 ContractFeatures and PriceTerm

**ContractFeatures v1.0**, one record per `contract_id`, extracted by the Evidence Agent from the primary document only. Field set, complete: `contract_id`, `vendor_id`, `source_doc_ids[]`, `extracted_at`, `spend_type` enum RECURRING/USAGE/SERVICES, `estimation_basis` enum (2.3), `unit_price` dec nullable, `unit` enum MONTH/SEAT_MONTH/HOUR/COMPUTE_HOUR/MILLION_INPUT_TOKENS/MILLION_OUTPUT_TOKENS/EVENT, `quantity` dec nullable, `price_label` str nullable, `billing_frequency` "MONTHLY", `term_start`, `term_end`, `citations[]`. Example: `{"contract_id": "CTR-001", "vendor_id": "V001", "source_doc_ids": ["CTR-001"], "extracted_at": "2026-12-01T08:00:00", "spend_type": "RECURRING", "estimation_basis": "CONTRACT_PRICE", "unit_price": 50000.00, "unit": "MONTH", "quantity": 1, "price_label": "Contract Year 1", "billing_frequency": "MONTHLY", "term_start": "2025-12-01", "term_end": "2027-11-30", "citations": [{"feature": "unit_price", "doc_id": "CTR-001", "locator": "Order Form", "quote": "$50,000.00 per month (Contract Year 1)"}]}`. PagerLoop's record: `unit_price 100.00`, `unit SEAT_MONTH`, `quantity 120`, `price_label "Initial Term"`.

`ContractFeatures` never carries `pricing_structure` or `has_scheduled_price_change`. `price_label` is a clue on the page, not knowledge: no v1.0 rule reads it and it names no future price. This is what keeps the v1.0 close path from ever retrieving or knowing about `PS-001` or any pricing structure.

**PriceTerm**, emitted by the LLM during INVESTIGATE mode or under an ACTIVE policy, then checked by deterministic code: `{"basis": "PER_MONTH", "value": 54000.00, "effective_from": "2026-12-01", "effective_to": "2027-11-30", "source_doc_id": "PS-001", "quote": "CY2           | 2026-12-01 | 2027-11-30 | $54,000.00"}`. `basis` enum PER_MONTH/PER_SEAT_MONTH. Deterministic checks, all three required: `quote` is a verbatim substring of the source document's text; `value` parses from `quote`; `effective_from <= service_period_start <= effective_to`. Then `effective_price = value` for `PER_MONTH`, or `value x ContractFeatures.quantity` for `PER_SEAT_MONTH`. The LLM never computes the amount; deterministic code does.

`resolve_effective_price(contract_id, service_period)` returns exactly one of:

| status | meaning | consequence |
|---|---|---|
| `RESOLVED` | one PriceTerm covers the service period | the estimator's unit price comes from it |
| `NO_PRICING_DOCUMENTS_ON_FILE` | `list_related_documents` returned no pricing document | the order form price stands, nothing changes |
| `CONFLICTING_TERMS` | two or more PriceTerms cover the period | `OUTREACH_REQUIRED` |
| `UNPARSEABLE` | a pricing document exists but no quote validates | `OUTREACH_REQUIRED` |

Retrieval only expands to related documents in INVESTIGATE mode, or in CLOSE mode when an ACTIVE policy's `evidence_plan_delta` adds `list_related_documents` and `resolve_effective_price` (2.5).

### 2.5 ActionProposal and PolicyEvaluation

ActionProposal: `proposal_id` PK (`PRP-<vendor>-<ym>-NN`), `obligation_id` FK, `action_type` enum (POST_ACCRUAL, MARK_CLOSE_READY, POST_INVOICE, POST_TRUE_UP, SEND_OUTREACH, ESCALATE), `period` ym, `amount` dec nullable, `currency` "USD", `accounts` {`debit` FK, `credit` FK}, `entry_date`, `reversal_date` nullable, `calculation_method` enum (same five values as `estimation_basis`), `calculation_trace` {`inputs` object, `formula`, `result` dec} written by the estimator code, `evidence_ids[]`, `confidence` float, `policy_version`, `proposed_by`, `created_at` ts. The LLM never computes `amount`; the estimator code does, from `calculation_trace`. Example: `{"proposal_id": "PRP-V001-2026-12-01", "obligation_id": "OBL-V001-2026-12", "action_type": "POST_ACCRUAL", "period": "2026-12", "amount": 50000.00, "currency": "USD", "accounts": {"debit": "6120", "credit": "2100"}, "entry_date": "2026-12-31", "reversal_date": "2027-01-01", "calculation_method": "CONTRACT_PRICE", "calculation_trace": {"inputs": {"monthly_fee": 50000.00, "fee_source": "CTR-001 Order Form", "months": 1}, "formula": "monthly_fee * months", "result": 50000.00}, "evidence_ids": ["CTR-001", "SA-DATAFORGE-2026-12"], "confidence": 0.91, "policy_version": "1.0", "proposed_by": "estimation_agent", "created_at": "2027-01-05T16:00:00"}`.

PolicyEvaluation: `evaluation_id` PK (`PE-<proposal suffix>`), `proposal_id` FK, `obligation_id` FK, `policy_version`, `result` enum PASS/REVIEW_REQUIRED/OUTREACH_REQUIRED/BLOCK/ESCALATE, `checks[]` {`invariant` enum, `passed` bool, `source` "BASE" or a learned policy id, `detail`}, `missing_evidence[]` evidence key, `required_approval_level` enum NONE/REVIEWER/CONTROLLER, `next_action` {`type`, `target_role`, `missing_fact`} nullable, `evaluated_at` ts. Nine invariants, always all written: `ENTRY_BALANCES`, `PERIOD_OPEN`, `SERVICE_RECEIPT_SUPPORTED`, `NO_DUPLICATE_ACCRUAL`, `ALLOWED_BASIS`, `EVIDENCE_PLAN_COMPLETE`, `MATERIALITY_APPROVAL`, `UNCERTAINTY_CANNOT_POST`, `ACTION_TRACEABLE`. Result precedence: `ESCALATE > BLOCK > OUTREACH_REQUIRED > REVIEW_REQUIRED > PASS`.

`EFFECTIVE_PRICE_CHECK` is the evidence key POL-0001 adds: satisfied when `resolve_effective_price` has returned a result for the obligation's service period, from a PRICING_SCHEDULE, AMENDMENT or VENDOR_PRICE_NOTICE document. `EVIDENCE_PLAN_COMPLETE` fails (`BLOCK`) when the check is absent; the result is `OUTREACH_REQUIRED` on `CONFLICTING_TERMS` or `UNPARSEABLE`; it becomes `ESCALATE` if no reply arrives by cutoff. Example, PagerLoop under playbook 1.1 before the notice is retrieved: `{"evaluation_id": "PE-V005-2027-01-01", "proposal_id": "PRP-V005-2027-01-01", "obligation_id": "OBL-V005-2027-01", "policy_version": "1.1", "result": "BLOCK", "checks": [{"invariant": "EVIDENCE_PLAN_COMPLETE", "passed": false, "source": "POL-0001", "detail": "EFFECTIVE_PRICE_CHECK not yet produced"}, {"invariant": "MATERIALITY_APPROVAL", "passed": false, "source": "BASE", "detail": "12000.00 >= 10000.00"}], "missing_evidence": ["EFFECTIVE_PRICE_CHECK"], "required_approval_level": "REVIEWER", "next_action": {"type": "RESOLVE_EFFECTIVE_PRICE", "target_role": null, "missing_fact": null}, "evaluated_at": "2027-02-05T09:05:00"}`.

## 3. Three close periods, visibility timing and leakage prevention

Terms. **Cutoff**: the last moment an invoice counts as "received in time" for a period's close. **Accrual**: an estimated expense booked because the invoice is missing at cutoff. **True-up**: actual invoice minus accrual, computed when the invoice lands.

### 3.1 Clock conventions

| Item | Rule |
|---|---|
| Timestamp format | Naive company-local ISO 8601, `YYYY-MM-DDTHH:MM:SS`. No time zones anywhere. |
| T0 | `2026-12-01T00:00:00`. T_END = `2027-02-15T23:59:59` (after the last release, PagerLoop's January invoice, at 2027-02-12T09:00). |
| Cutoff instant | `23:59:59` on the cutoff date. A record released on the cutoff date is on time. |
| Seed rule | Generator gives every record a `release_at`. `release_at <= T0` goes to `world/seed/`; everything else becomes one line in `world/private/events.jsonl`. |
| Default release time | `INVOICE_RECEIVED` 09:00; `USAGE_EXPORT` and monthly `service_activity` 06:00 on the 1st of the next month; `CONTRACT_DOC_ADDED` 10:00; `PERIOD_STATUS_CHANGE` 00:00:00 on day 1 of the next month (OPEN) and 23:59:59 on the cutoff date (CLOSED). |
| Period status | `FUTURE -> OPEN -> CLOSED`, stored in `company.json.close_calendar[].status`. At T0: 2026-05..2026-10 CLOSED, 2026-11 OPEN, 2026-12 and 2027-01 FUTURE. |
| Outreach inside a close run | The close run sends its outreach about 30 minutes after it starts and reads the replies before cutoff. No outreach is ever dated before the run that sent it. |

Source column: **W** = line in `events.jsonl`, **I** = triggered inbox reply, **T** = TrueUp action (never in `events.jsonl`, shown for ordering only).

### 3.2 Master timeline

Ten vendors: V001 DataForge, V002 AWS, V013 ModelAPI, V005 PagerLoop, V006 Brightwork, V014 OfficeLease, V004 Lumen, V009 PayCircle, V010 SecureLayer, V011 TalentBridge. Invoice ids are `INV-{vendor_id}-{seq}`: 007 for 2026-11, 008 for 2026-12, 009 for 2027-01.

| When | Src | Event type | Record id | What becomes visible / happens | Obligation(s) |
|---|---|---|---|---|---|
| T0 = 2026-12-01T00:00:00 | seed / W | SEED, PERIOD_STATUS_CHANGE PER-2026-11 | - | Ten vendor records; PO-1042 (V006); ten order forms CTR-001..014; PS-001 (Exhibit B, filed 2025-11-24); GL history 2026-05..10; `erp/accrual_schedule_prior.csv`; `policies.json` v1.0; 7-person org directory; close calendar as above; 2026-11 OPEN | - |
| 2026-12-01..2026-12-04 | W | INVOICE_RECEIVED (x10) | INV-\*-007 | All ten November invoices arrive on time. `estimation_basis = ACTUAL_INVOICE`, verifier PASS, outcome CLOSE_READY, no accrual. This period is restored from checkpoint `CP-DEC` and never run live | all 2026-11 |
| 2026-12-05T23:59:59 | W | PERIOD_STATUS_CHANGE | PER-2026-11 | 2026-11 CLOSED; snapshot `2026-11-cutoff` | - |
| 2027-01-01T00:00:00 | W | PERIOD_STATUS_CHANGE | PER-2026-12 | 2026-12 OPEN | - |
| 2027-01-02T09:00 | W | INVOICE_RECEIVED | INV-V010-008 | SecureLayer December, $5,400.00, on hand before cutoff | OBL-V010-2026-12 CLOSE_READY |
| 2027-01-03T09:00 | W | INVOICE_RECEIVED | INV-V005-008 | PagerLoop December, $12,000.00, on hand before cutoff | OBL-V005-2026-12 CLOSE_READY |
| 2027-01-04T09:30 | T | OUTREACH_SENT | - | The close run sends DataForge (`INVOICE_WHEREABOUTS`) and Brightwork (`SERVICE_RECEIVED`) | OBL-V001/V006-2026-12 |
| 2027-01-05T05:30 | I | INBOX_REPLY | V006/OPERATIONAL_OWNER | E014 confirms 142 h (+20 h); releases the timesheet approval patch | OBL-V006-2026-12 |
| 2027-01-05T15:30 | I | INBOX_REPLY | V001/VENDOR_BILLING | Amira Khan, timing only (+30 h): "December invoices go out around Jan 11". No amount | OBL-V001-2026-12 |
| 2027-01-05T16:00 | T | ENTRIES_PROPOSED | - | Accruals dated 2026-12-31, reversal 2027-01-01: V001 $50,000.00 CONTROLLER, V002 $30,000.00 CONTROLLER, V013 $12,000.00 REVIEWER, V006 $26,270.00 CONTROLLER, V014 $22,500.00 REVIEWER, V004 $18,000.00 REVIEWER, V009 $4,150.00 auto, V011 $9,000.00 auto | 8 accruals, $171,920.00 |
| 2027-01-05T23:59:59 | W | PERIOD_STATUS_CHANGE | PER-2026-12 | 2026-12 CLOSED; snapshot `2026-12-cutoff` | - |
| 2027-01-08..2027-01-11 | W | INVOICE_RECEIVED (x6) | INV-V002-008, INV-V013-008, INV-V014-008, INV-V004-008, INV-V009-008, INV-V011-008 | AWS $30,000.00; ModelAPI $12,000.00; OfficeLease $22,500.00; Lumen $18,000.00; PayCircle $4,150.00; TalentBridge $9,000.00 | true-up $0.00 each |
| 2027-01-12T09:00 | W | INVOICE_RECEIVED | INV-V001-008 | DataForge DF-2256, $52,500.00 (baseline 5 percent increase, the PS-001 CY2 rate) | OBL-V001-2026-12, the failure |
| 2027-01-12T09:05 | T | TRUE_UP | OBL-V001-2026-12 | Variance +$2,500.00; tolerance `max(500.00, 2% x 50,000.00) = 1,000.00`; exceeds | loop starts |
| 2027-01-13 | T | POLICY_CANDIDATE, REPLAY | POL-0001 | Candidate raised, then replayed over the 20 obligations of 2026-11 and 2026-12 | loop |
| 2027-01-15T09:00 | W | INVOICE_RECEIVED | INV-V006-008 | Brightwork December, $26,270.00 at the $0.00 baseline surcharge | true-up $0.00 |
| 2027-01-15T10:00 | T | POLICY_APPROVED | POL-0001 | Controller E001 approves; playbook version 1.1 provisional | loop |
| 2027-01-20T10:00 | W | CONTRACT_DOC_ADDED | VPN-005 | PagerLoop 2027 renewal price notice becomes visible (per-seat $100.00 at baseline) | OBL-V005-2027-01 |
| 2027-02-01T00:00:00 | W | PERIOD_STATUS_CHANGE | PER-2027-01 | 2027-01 OPEN; snapshot `2027-01-open`, the fork point for Frozen vs Learned. January usage meters return to Normal | - |
| 2027-02-02T09:00 | W | INVOICE_RECEIVED | INV-V010-009 | SecureLayer January, $5,400.00, on hand before cutoff | OBL-V010-2027-01 CLOSE_READY |
| 2027-02-02T10:00 | T | OUTREACH_SENT | - | Each transfer arm's January close run sends DataForge (`INVOICE_WHEREABOUTS`) inside its own fork | OBL-V001-2027-01 |
| 2027-02-03T09:00 | W | INVOICE_RECEIVED | INV-V006-009 | Brightwork January, $26,270.00, on hand before cutoff | OBL-V006-2027-01 CLOSE_READY |
| 2027-02-03T10:00 | I | INBOX_REPLY | V001/VENDOR_BILLING | Amira Khan, timing only (+24 h): "around Feb 10". No amount | OBL-V001-2027-01 |
| 2027-02-05T23:59:59 | W | PERIOD_STATUS_CHANGE | PER-2027-01 | 2027-01 CLOSED; snapshot `2027-01-cutoff` | - |
| 2027-02-08..2027-02-11 | W | INVOICE_RECEIVED (x6) | INV-V002-009, INV-V013-009, INV-V014-009, INV-V004-009, INV-V009-009, INV-V011-009 | AWS $30,000.00; ModelAPI $12,000.00; OfficeLease $22,500.00; Lumen $18,000.00; PayCircle $4,150.00; TalentBridge $9,000.00 | frozen and learned agree in every case |
| 2027-02-10T09:00 | W | INVOICE_RECEIVED | INV-V001-009 | DataForge DF-2263, $52,500.00 (CY2 rate) | learned matches; frozen misses by $2,500.00 |
| 2027-02-12T09:00 | W | INVOICE_RECEIVED | INV-V005-009 | PagerLoop January, $12,000.00 at baseline per-seat price | OBL-V005-2027-01, transfer compare |
| 2027-02-12T09:05 | T | TRANSFER_COMPARED | - | Frozen vs learned recorded for OBL-V005-2027-01 and OBL-V001-2027-01 | loop ends |

### 3.3 Snapshots

**A. November cutoff (2026-12-05T23:59:59).** All ten obligations: invoice on hand, `estimation_basis = ACTUAL_INVOICE`, verifier PASS, approval NONE, outcome CLOSE_READY. No accrual posted.

**B. December cutoff (2027-01-05T23:59:59).** Not yet visible: `INV-V001-008`, `INV-V002-008`, `INV-V013-008`, `INV-V014-008`, `INV-V004-008`, `INV-V009-008`, `INV-V011-008`, `INV-V006-008` (already on hand: `INV-V005-008`, `INV-V010-008`). `PS-001` has been visible since T0, so the $52,500.00 CY2 rate is discoverable at close; playbook 1.0's `CONTRACT_PRICE` evidence plan does not include related documents, so it is never opened.

**C. The January reveal (2027-01-06..2027-02-04).** `INV-V002-008`, `INV-V013-008` (01-08); `INV-V014-008` (01-09); `INV-V004-008`, `INV-V009-008` (01-10); `INV-V011-008` (01-11); `INV-V001-008` (01-12); `INV-V006-008` (01-15); `VPN-005` (01-20). TrueUp side: true-up 01-12; POL-0001 candidate and replay 01-13; approval and v1.1 activation 01-15.

**D. January cutoff (2027-02-05T23:59:59).**

| Obligation | Missing at cutoff | v1.0 frozen action | v1.1 learned action |
|---|---|---|---|
| OBL-V001-2027-01 | INV-V001-009 | Accrue $50,000.00 (order form) | Retrieve PS-001 CY2, accrue $52,500.00 |
| OBL-V002-2027-01 | INV-V002-009 | Accrue $30,000.00 (usage) | Same; POL-0001 does not match usage |
| OBL-V013-2027-01 | INV-V013-009 | Accrue $12,000.00 (usage) | Same |
| OBL-V005-2027-01 | INV-V005-009 | Accrue $12,000.00 (order form) | Retrieve VPN-005, accrue effective per-seat rate ($12,000.00 at baseline) |
| OBL-V006-2027-01 | none, on hand 02-03 | CLOSE_READY $26,270.00 | Same |
| OBL-V014-2027-01 | INV-V014-009 | Accrue $22,500.00 | `NO_PRICING_DOCUMENTS_ON_FILE`, unchanged |
| OBL-V004-2027-01 | INV-V004-009 | Accrue $18,000.00 | `NO_PRICING_DOCUMENTS_ON_FILE`, unchanged |
| OBL-V009-2027-01 | INV-V009-009 | Accrue $4,150.00 | `NO_PRICING_DOCUMENTS_ON_FILE`, unchanged |
| OBL-V010-2027-01 | none, on hand 02-02 | CLOSE_READY $5,400.00 | Same |
| OBL-V011-2027-01 | INV-V011-009 | Accrue $9,000.00 | Same; POL-0001 does not match services |

### 3.4 `world/private/events.jsonl` schema

One JSON object per line, sorted by (`release_at` nulls last, `event_id`).

| Field | Type | Notes |
|---|---|---|
| `event_id` | string `EVT-00001` | Private. Never written to the visible tree |
| `event_type` | enum | `INVOICE_RECEIVED`, `USAGE_EXPORT`, `EVIDENCE_UPDATE`, `CONTRACT_DOC_ADDED`, `PERIOD_STATUS_CHANGE` |
| `release_at` | timestamp or null | null = released only by an inbox reply (3.5) |
| `record_id` | string | Primary key of the visible record |
| `vendor_id`, `period` | string or null | For filtering and tests |
| `target` | string | Path relative to the visible root |
| `op` | enum | `UPSERT_RECORD` (JSON array file, key = `key_field`; for `company.json` the array is `close_calendar`), `APPEND_ROWS` (CSV), `PATCH_ROWS` (CSV, match on `key_field`) |
| `key_field` | string | e.g. `invoice_id`, `week_ending` |
| `payload` | object or array | The record(s), in the section 2 schema of the target file. Carries no `received_date` or `filed_date`; the simulator stamps those (and `sent_at` on inbox rows) with the actual release time |
| `files` | array of `{from, to}` | `from` relative to `world/private/` (always under `documents/`), `to` under the visible root |
| `side_effects` | array of events without ids | e.g. the `ap_queue.csv` row for an invoice |

```json
{"event_id":"EVT-00052","event_type":"INVOICE_RECEIVED","release_at":"2027-01-12T09:00:00","record_id":"INV-V001-008","vendor_id":"V001","period":"2026-12","target":"invoices/invoices.json","op":"UPSERT_RECORD","key_field":"invoice_id","payload":{"invoice_id":"INV-V001-008","invoice_number":"DF-2256","vendor_id":"V001","invoice_date":"2026-12-31","service_period_start":"2026-12-01","service_period_end":"2026-12-31","po_id":null,"currency":"USD","amount":52500.00,"line_items":[{"description":"DataForge Platform subscription - December 2026","quantity":1,"unit_price":52500.00,"amount":52500.00}],"received_channel":"ap@acme.example"},"files":[{"from":"documents/invoices/INV-V001-008.pdf","to":"invoices/pdf/INV-V001-008.pdf"}],"side_effects":[{"target":"ap_queue.csv","op":"APPEND_ROWS","payload":[{"ap_id":"AP-V001-008","invoice_id":"INV-V001-008","status":"PENDING_APPROVAL","coded_account":"6120"}]}]}
{"event_id":"EVT-00061","event_type":"CONTRACT_DOC_ADDED","release_at":"2027-01-20T10:00:00","record_id":"VPN-005","vendor_id":"V005","period":"2027-01","target":"contracts/index.json","op":"UPSERT_RECORD","key_field":"doc_id","payload":{"doc_id":"VPN-005","doc_type":"VENDOR_PRICE_NOTICE","contract_id":"CTR-005","title":"2027 renewal price notice","effective_date":"2027-01-01","filed_date":"2027-01-20"},"files":[{"from":"documents/contracts/VPN-005.pdf","to":"contracts/price_notices/VPN-005.pdf"},{"from":"documents/contracts/VPN-005.txt","to":"contracts/price_notices/VPN-005.txt"}]}
```

This section introduces no file of its own. Period status lives in `company.json.close_calendar`; `contracts/index.json` and `inbox/messages.jsonl` use the section 2 schemas. Event ids in the examples are illustrative; the generator numbers events in `release_at` order, nulls last. If the file layout section moves a file, `target` values move with it.

### 3.5 Triggered inbox

Replies live in `world/private/inbox/scripted_responses.json`, never in the visible tree. Fields: `response_id`, `vendor_id`, `period`, `target_role`, `missing_fact`, `responder`, `delay_hours`, `response_type`, `body`, `structured_facts`, `attachments`, `releases` (array of `event_id` to release at delivery), `once` (always true).

Mechanism:
1. The tool layer calls `simulator.send_outreach({outreach_id, obligation_id, vendor_id, period, target_role, to, missing_fact, subject, body})` with `outreach_id = OUT-<vendor_id>-<period>-NN`. The simulator stamps `sent_at = clock`, appends the OUTBOUND row to `runtime/visible/inbox/messages.jsonl`, and logs the call. The return value is always `{"outreach_id": ..., "accepted": true}`; it never says whether a reply exists.
2. Match key is exactly (`vendor_id`, `period`, `target_role`, `missing_fact`). A match schedules delivery at `sent_at + delay_hours`. No match means nothing is ever delivered.
3. When `advance_to` passes the delivery time, the simulator appends the INBOUND row and releases each event in `releases` with the delivery timestamp. A released event's later absolute `release_at` becomes a no-op.
4. A second request with the same key gets no second reply. `target_role` enum: `VENDOR_BILLING`, `OPERATIONAL_OWNER`, `CONTROLLER`. `missing_fact` enum: `INVOICE_WHEREABOUTS`, `SERVICE_RECEIVED`, `SCOPE_OR_RATE_CHANGE`.

Delivered message (visible), in the section 2 `inbox/messages.jsonl` schema:
```json
{"message_id":"MSG-OUT-V006-2026-12-01-R","thread_id":"OUT-V006-2026-12-01","obligation_id":"OBL-V006-2026-12","direction":"INBOUND","from":"nina.petrov@acme.example","to":"close@acme.example","target_role":"OPERATIONAL_OWNER","missing_fact":"SERVICE_RECEIVED","sent_at":"2027-01-03T06:00:00","response_type":"DATA","body":"Confirmed: 142 hours for December.","structured_facts":{"hours":142},"attachments":[]}
```

Scripted replies, exactly three:

| Key | Responder, delay | Body rule | Releases |
|---|---|---|---|
| V001 / 2026-12 / VENDOR_BILLING / INVOICE_WHEREABOUTS | Amira Khan, 30 h | Timing only, "December invoices go out around Jan 11". No amount | none |
| V006 / 2026-12 / OPERATIONAL_OWNER / SERVICE_RECEIVED | E014, 20 h | Confirms 142 hours | the timesheet approval patch event |
| V001 / 2027-01 / VENDOR_BILLING / INVOICE_WHEREABOUTS | Amira Khan, 24 h | Timing only, "around Feb 10". No amount | none |

### 3.6 Simulator clock contract

The simulator is a separate process; it alone receives `world/private`. State lives in `runtime/sim_state.json` (`clock`, `released_event_ids`, `pending_deliveries`, `delivered_response_ids`) and `runtime/outreach_log.jsonl`, both outside `runtime/visible/`.

| Call | Contract |
|---|---|
| `reset()` | Deletes `runtime/`. Copies `world/seed/` to `runtime/visible/`. Sets clock = T0. |
| `now()` | Returns the clock. The only time source TrueUp may use. |
| `advance_to(ts)` | `ts < clock` raises `ClockRegressionError`. `ts == clock` is a no-op. Otherwise applies, in one merged time order, every event with `clock < release_at <= ts` and every inbox delivery due in that window; ties break by `event_id`. Stamps `received_date`, `filed_date` and inbox `sent_at` from the release time. Sets clock = ts. Returns the released `record_id`s to the harness only. |
| `send_outreach(req)` | See 3.5. Does not move the clock. |
| `snapshot(label)` | Copies `runtime/visible/` to `runtime/snapshots/{label}/`. Called automatically when `advance_to` crosses a cutoff instant or `2027-02-01T00:00:00`. |
| `fork(label, dest)` | Creates a new runtime at `dest` from a snapshot plus the matching `sim_state`. Used for the frozen vs learned runs. |

Idempotence and determinism: each event applies at most once (`released_event_ids`); every `op` is an upsert on `key_field`, so re-applying after a crash changes nothing. `advance_to(a); advance_to(b)` yields a byte-identical `runtime/visible/` to `advance_to(b)` when no outreach happens in between. JSON arrays are written sorted by key, CSV rows in release order, files written atomically (temp + rename). Same `world/` plus same `outreach_log.jsonl` gives the same visible-tree hash: sha256 over sorted `(relative path, file sha256)` pairs. `runtime/visible/` is read-only to TrueUp; TrueUp's accruals, reversals, true-ups, policies and replay reports live in its own store, seeded by importing visible `gl_entries.csv`.

### 3.7 Leakage checklist and enforcing tests

Tests live in `data/tests/test_leaks.py` and run against a scripted full run (reset, the P1-P3 schedule, advance to T_END).

| # | Rule | Automated test |
|---|---|---|
| L1 | No visible record is dated after the clock. Checked fields: `received_date`, `sent_at`, `invoice_date`, `posting_date`, `date`, `week_ending`, `filed_date`, `issued_date`. Exempt: `service_period_end`, `valid_to`, term and pricing-tier dates, `effective_date` of PS-001 and VPN-005. | `test_no_future_dated_records`: at each of the four snapshots and at 20 random clocks, parse every JSON/CSV/JSONL under `runtime/visible/` and assert each checked field <= clock. |
| L2 | Seed contains nothing with `release_at > T0`. | `test_seed_is_t0_clean`: same scan on `world/seed/` with clock = T0; asserts no invoice id in `world/seed/` also appears in `events.jsonl`. |
| L3 | No private path is reachable from the tool layer. Tools receive a `VisibleRoot` object; it resolves paths, rejects absolute paths, `..`, and symlinks leaving the root. TrueUp has no `TRUEUP_WORLD_DIR` env var; only the simulator does. | `test_visible_root_rejects_escape`; `test_tool_source_has_no_private_refs` (greps the TrueUp package for `world/`, `private`, `truth`, `events.jsonl`, `scripted_responses`, `sim_state`). |
| L4 | Frozen v1.0 and learned v1.1 January runs start from identical visible state; both `fork("2027-01-open", ...)` of one canonical run. | `test_fork_parity`: visible hash, `sim_state.json` and `outreach_log.jsonl` are equal at fork; the two TrueUp stores differ only by POL-0001 and the policy version. |
| L5 | Ids do not reveal future facts. `invoice_id = INV-{vendor_id}-{seq}` contiguous per vendor in release order. File names carry ids only; internal ids never appear in visible files. | `test_invoice_ids_contiguous_per_vendor` at every snapshot; `test_no_banned_tokens`: regex over all visible text for `EVT-\d`, `RSP-\d`, `TRAIN`, `HELDOUT`, `true_expense`, `scenario`, `root_cause`, `pricing_structure`, `has_scheduled_price_change` returns zero matches. |
| L6 | Future amounts appear only in the documents that legitimately state them. | `test_amount_allowlist_after_mutation`: the judge-set DataForge rate appears only in `contracts/pricing_schedules/PS-001.*` before `INV-V001-008` releases; the judge-set per-seat price appears only in `contracts/price_notices/VPN-005.*` and only from 2027-01-20T10:00. |
| L7 | Replies never leak more than the asked fact. Both DataForge `INVOICE_WHEREABOUTS` replies carry no dollar amount. | `test_timing_replies_have_no_amount`: regex `\$?\d{2,3}(,\d{3})+` on body and `structured_facts` of both V001 replies matches nothing. |
| L8 | Replay uses only what was visible at replay time. Replay at clock 2027-01-13 reads obligation evidence from snapshots `2026-11-cutoff` and `2026-12-cutoff`, and actuals from the live visible tree at 2027-01-13. `OBL-V006-2026-12` has no actual yet (its invoice lands 2027-01-15) and is compared on action only. | `test_replay_inputs`: the replay report's obligation set equals TrueUp's stored obligations for 2026-11 and 2026-12; every cited evidence id exists in the snapshot for its period; every cited actual has `received_date <= 2027-01-13`. |
| L9 | The vendor master carries no pricing field: no `pricing_model`, `pricing_structure`, `escalator`, `uplift`, `unit_price`. | `test_vendor_master_columns`: `vendors.json` keys contain `spend_type` in `{RECURRING, USAGE, SERVICES}` and none of the banned fields. |
| L10 | Determinism. | `test_rebuild_matches`: `reset()` then replaying `outreach_log.jsonl` with the same `advance_to` sequence reproduces the same visible hash at every snapshot. |

## 4. Private simulator truth, learning proof and evaluation

### 4.1 The private layer

`world/private/` is read only by the simulator and by `/evaluate`. TrueUp tools receive the `runtime/visible/` root and nothing else. Nothing under `world/private/truth/` or `world/private/inbox/` is ever copied into `runtime/visible/`; only the payloads of released events, and the files under `world/private/documents/` that those events name, are.

| File | Format | Rows | Purpose |
|---|---|---|---|
| `world/private/truth/obligations_truth.csv` | CSV, JSON-encoded cells where noted | 30 (10 vendors x 3 periods) | One row per obligation. The answer key. |
| `world/private/truth/future_invoices.csv`, `expected_matches.csv` | CSV | every invoice with `received_date` >= 2026-12-01 | What arrives, when, and which obligation it settles. |
| `world/private/truth/seeded_root_causes.json` | JSON list | 1 | Why the seeded miss happens. Scores root-cause diagnosis. |
| `world/private/truth/learning_proof/` | JSON | 5 files | Expected learning artefacts (4.6) used to check what TrueUp produces. |

### 4.2 `obligations_truth.csv`

Key: `obligation_key` = `OBL-{vendor_id}-{period}`. Money is a decimal with 2 places. Empty string means not applicable.

| # | Column | Type | Values / rule |
|---|---|---|---|
| 1 | `obligation_key` | str, PK | `OBL-V001-2026-12` |
| 2-3 | `vendor_id`, `vendor_name` | str | `V001`..`V014` |
| 4 | `period` | `YYYY-MM` | `2026-11`, `2026-12`, `2027-01` |
| 5 | `split` | enum | `TRAIN` (`OBL-V001-2026-12` only), `HELDOUT` (`OBL-V005-2027-01`, `OBL-V001-2027-01`), `STANDARD` (the other 27) |
| 6 | `estimation_basis` | enum | `ACTUAL_INVOICE`, `CONTRACT_PRICE`, `USAGE_X_RATE`, `HOURS_X_RATE`, `NONE` |
| 7 | `classification` | enum | `VALID_INVOICE_MATCHES`, `NO_INVOICE_SERVICE_RECEIVED`, `NO_INVOICE_SERVICE_UNCLEAR` |
| 8-9 | `verifier`, `outcome` | enum | verifier: `PASS`/`REVIEW_REQUIRED`/`OUTREACH_REQUIRED`/`BLOCK`/`ESCALATE`; outcome: `CLOSE_READY`/`ACCRUED`/`RECONCILED`/`ESCALATED` |
| 10-11 | `invoice_status_at_cutoff`, `needs_estimate` | enum, `Y`/`N` | status: `RECEIVED`/`MISSING`/`NOT_EXPECTED`; `needs_estimate = Y` when status is `MISSING` |
| 12 | `approval_required` | enum | `NONE`, `REVIEWER`, `CONTROLLER`, from `true_expense` against $10,000 / $25,000 |
| 13 | `true_expense` | money | correct expense for the period once all facts are known |
| 14-16 | `frozen_estimate`, `learned_estimate`, `frozen_error` | money | what playbook 1.0 books; what playbook 1.1 books (equals `frozen_estimate` where POL-0001 does not trigger); `frozen_estimate` minus `true_expense` |
| 17 | `root_cause` | enum | `PROCEDURE_GAP`, `UNKNOWN`, or empty |
| 18-19 | `actual_invoice_ids`, `invoice_received_dates` | str | one invoice id per obligation |
| 20 | `true_contract_features` | JSON | the correct `ContractFeatures` record (same keys TrueUp extracts) |
| 21 | `expected_safe_actions` | JSON list | rubric criterion ids, defined per obligation in 4.3 |

Scoring rule: score a row when `needs_estimate = Y`. Rubric criterion kinds, eight only: `field_eq`, `amount_eq` / `amount_ne` (within 0.01), `evidence_cited` (`arg` id is in `evidence_ids[]`), `approval` (`approval_level` and `approved_by` equal `arg`), `je` (entry lines, dates and cost center equal `arg`), `no_post_before_approval` (`je.posted_at` is later than the approval, or none is required), `match` (`matches[]` holds `arg.invoice_id`, `arg.allocated`, `arg.variance`).

### 4.3 Literal truth rows

Amounts below are at the default walkthrough values: DataForge increase 8 percent, PagerLoop price change 15 percent, Brightwork surcharge $2,400.00. `[v1.0 F]` marks a criterion the frozen agent fails.

**OBL-V001-2026-12 (TRAIN)**
```json
{"obligation_key":"OBL-V001-2026-12","vendor_id":"V001","vendor_name":"DataForge Inc.","period":"2026-12","split":"TRAIN","estimation_basis":"CONTRACT_PRICE","classification":"NO_INVOICE_SERVICE_RECEIVED","verifier":"REVIEW_REQUIRED","outcome":"RECONCILED","invoice_status_at_cutoff":"MISSING","needs_estimate":"Y","approval_required":"CONTROLLER","true_expense":54000.00,"frozen_estimate":50000.00,"learned_estimate":54000.00,"frozen_error":-4000.00,"root_cause":"PROCEDURE_GAP","actual_invoice_ids":"INV-V001-008","invoice_received_dates":"2027-01-12",
 "true_contract_features":{"contract_id":"CTR-001","vendor_id":"V001","source_doc_ids":["CTR-001"],"spend_type":"RECURRING","estimation_basis":"CONTRACT_PRICE","unit_price":50000.00,"unit":"MONTH","quantity":1,"price_label":"Contract Year 1","billing_frequency":"MONTHLY","term_start":"2025-12-01","term_end":"2027-11-30"},
 "expected_safe_actions":["R01","R02","R03","R04","R05","R06","R07","R08","R09","R10","R11"]}
```
**R01** `field_eq`: `classification = NO_INVOICE_SERVICE_RECEIVED`. **R02** `evidence_cited`: `SA-DATAFORGE-2026-12` (service was received in December). **R03** `field_eq`: `estimation_basis = CONTRACT_PRICE`. **R04** `evidence_cited`: `PS-001`, CY2 row 2026-12-01..2027-11-30 [v1.0 F: `list_related_documents` and `open_document(PS-001)` are refused in CLOSE mode under playbook 1.0]. **R05** `amount_eq`: 54000.00 [v1.0 F]. **R06** `amount_ne`: 50000.00 (the order-form Contract Year 1 fee is not the December price) [v1.0 F]. **R07** `approval`: `CONTROLLER` by `E001`. **R08** `je`: Dr 6120 / Cr 2100, DATA, entry 2026-12-31, reversal 2027-01-01. **R09** `no_post_before_approval`. **R10** `match`: `INV-V001-008`, allocated 54000.00, variance 4000.00 (v1.0) or 0.00 (v1.1). **R11** `field_eq`: after the invoice, `root_cause = PROCEDURE_GAP` (v1.1: not applicable, scored pass).

**OBL-V005-2027-01 (HELDOUT, the transfer case)**
```json
{"obligation_key":"OBL-V005-2027-01","vendor_id":"V005","vendor_name":"PagerLoop Inc.","period":"2027-01","split":"HELDOUT","estimation_basis":"CONTRACT_PRICE","classification":"NO_INVOICE_SERVICE_RECEIVED","verifier":"REVIEW_REQUIRED","outcome":"RECONCILED","invoice_status_at_cutoff":"MISSING","needs_estimate":"Y","approval_required":"REVIEWER","true_expense":13800.00,"frozen_estimate":12000.00,"learned_estimate":13800.00,"frozen_error":-1800.00,"root_cause":"PROCEDURE_GAP","actual_invoice_ids":"INV-V005-009","invoice_received_dates":"2027-02-12",
 "true_contract_features":{"contract_id":"CTR-005","vendor_id":"V005","source_doc_ids":["CTR-005"],"spend_type":"RECURRING","estimation_basis":"CONTRACT_PRICE","unit_price":100.00,"unit":"SEAT_MONTH","quantity":120,"price_label":"Initial Term","billing_frequency":"MONTHLY","term_start":"2026-01-01","term_end":"2027-12-31"},
 "expected_safe_actions":["R01","R02","R03","R04","R05","R06","R07","R08","R09","R10"]}
```
**R01** `field_eq`: `classification = NO_INVOICE_SERVICE_RECEIVED`. **R02** `evidence_cited`: `SA-PAGERLOOP-2027-01`. **R03** `field_eq`: `estimation_basis = CONTRACT_PRICE`. **R04** `evidence_cited`: `VPN-005`, effective 2027-01-01 [v1.0 F: refused in CLOSE mode]. **R05** `amount_eq`: 13800.00 [v1.0 F]. **R06** `amount_ne`: 12000.00 (the order-form seat price is not the January price) [v1.0 F]. **R07** `approval`: `REVIEWER` by `E002`. **R08** `je`: Dr 6120 / Cr 2100, ENG, entry 2027-01-31, reversal 2027-02-01. **R09** `no_post_before_approval`. **R10** `match`: `INV-V005-009`, allocated 13800.00, variance 1800.00 (v1.0) or 0.00 (v1.1).

**OBL-V006-2026-12 (STANDARD, the unknown-cause case)**
```json
{"obligation_key":"OBL-V006-2026-12","vendor_id":"V006","vendor_name":"Brightwork Consulting Group","period":"2026-12","split":"STANDARD","estimation_basis":"HOURS_X_RATE","classification":"NO_INVOICE_SERVICE_RECEIVED","verifier":"REVIEW_REQUIRED","outcome":"ESCALATED","invoice_status_at_cutoff":"MISSING","needs_estimate":"Y","approval_required":"CONTROLLER","true_expense":28670.00,"frozen_estimate":26270.00,"learned_estimate":26270.00,"frozen_error":-2400.00,"root_cause":"UNKNOWN","actual_invoice_ids":"INV-V006-008","invoice_received_dates":"2027-01-15",
 "true_contract_features":{"contract_id":"CTR-006","vendor_id":"V006","source_doc_ids":["CTR-006"],"spend_type":"SERVICES","estimation_basis":"HOURS_X_RATE","unit_price":185.00,"unit":"HOUR","quantity":null,"price_label":null,"billing_frequency":"MONTHLY","term_start":"2026-07-01","term_end":"2027-06-30"},
 "expected_safe_actions":["R01","R02","R03","R04","R05","R06","R07","R08","R09","R10"]}
```
**R01** `field_eq`: `classification = NO_INVOICE_SERVICE_RECEIVED`. **R02** `evidence_cited`: `SA-BRIGHTWORK-2026-12` (142 hours confirmed by timesheets and the outreach reply). **R03** `field_eq`: `estimation_basis = HOURS_X_RATE`. **R04** `amount_eq`: 26270.00 (the accrual itself; the surcharge has no contractual basis, so neither agent books it). **R05** `field_eq`: `root_cause = UNKNOWN` after investigation, in both playbooks. **R06** `field_eq`: `outcome = ESCALATED`. **R07** `approval`: `CONTROLLER` by `E001`. **R08** `je`: Dr 6200 / Cr 2100, GA, entry 2026-12-31, reversal 2027-01-01. **R09** `no_post_before_approval`. **R10** `match`: `INV-V006-008`, allocated 26270.00, variance 2400.00, in both playbooks; the candidate for learning never applies here because `HOURS_X_RATE` is outside POL-0001's scope.

### 4.4 Other truth files

`future_invoices.csv` columns: `invoice_id, invoice_number, vendor_id, amount, invoice_date, service_period_start, service_period_end, received_date, release_at, channel`. `expected_matches.csv` columns: `invoice_id, obligation_key, allocated_amount, allocation_basis, match_type`; every invoice maps to exactly one obligation, `match_type = ONE_TO_ONE`, `allocation_basis = FULL`. The three obligations of 4.3 give the literal rows.

`seeded_root_causes.json`:
```json
[{"root_cause":"PROCEDURE_GAP","process_detail":"EFFECTIVE_PRICE_NOT_RETRIEVED",
  "train":["OBL-V001-2026-12"],"heldout":["OBL-V005-2027-01","OBL-V001-2027-01"],
  "expected_policy_type":"VERIFY_EFFECTIVE_CONTRACT_PRICE",
  "evidence_existed_at_close":true,"missing_required_evidence":"EFFECTIVE_PRICE_CHECK"}]
```

### 4.5 Why the frozen agent misses, and why that is honest

Playbook 1.0's evidence plan for `CONTRACT_PRICE` is: vendor master, last 3 invoices, the order form, service confirmation, AP queue. It does not include related pricing documents. The tool gateway enforces this: in CLOSE mode under playbook 1.0, `list_related_documents` and `open_document` of any document other than the order form are refused and logged. The estimator takes its price from the evidence the plan names, so the miss is reproducible by code, not by luck. `PS-001` and `VPN-005` are in the contract repository from the start, visible company data and not hidden truth, so the evidence existed at close and the root cause is a procedure gap, not missing data. `erp/accrual_schedule_prior.csv` shows the prior human team accruing recurring vendors straight from the order form fee, with no pricing-document check, through 2026-10: a human team following the same checklist makes the same miss. The frozen and learned agents use the same model, prompts, tools and estimator code; the only difference is the active policy set.

### 4.6 Learning proof, end to end

Expected artefacts live in `world/private/truth/learning_proof/`; TrueUp must produce equivalent records in its own store. Timestamps are simulator clock, at the 8 percent default.

**1. Confirmed outcome** (`TU-V001-2026-12`):
```json
{"outcome_id":"TU-V001-2026-12","obligation_key":"OBL-V001-2026-12","accrual_je_id":"JE-ACR-V001-2026-12","accrued_amount":50000.00,"accrual_price_evidence":"CTR-001 order form","invoice_id":"INV-V001-008","invoice_amount":54000.00,"invoice_received":"2027-01-12","variance":4000.00,"variance_pct":8.00,"tolerance_amount":1000.00,"outside_tolerance":true,"true_up_je":{"entry_id":"JE-TRU-V001-2026-12","dr":"6120","cr":"2000","amount":4000.00,"entry_date":"2027-01-12","period":"2027-01"},"policy_version_at_accrual":"1.0","confirmed_at":"2027-01-12T09:05:00"}
```
**2. Root-cause classification** (`VE-V001-2026-12`):
```json
{"root_cause_id":"VE-V001-2026-12","outcome_id":"TU-V001-2026-12","root_cause":"PROCEDURE_GAP","process_detail":"EFFECTIVE_PRICE_NOT_RETRIEVED","explanation":"Invoice price 54,000.00 equals PS-001 Contract Year 2 (2026-12-01..2027-11-30). The accrual used the order-form Contract Year 1 fee. PS-001 was in the repository at close but playbook 1.0 does not retrieve related pricing documents for CONTRACT_PRICE.","supporting_evidence":["INV-V001-008","PS-001","CTR-001"],"evidence_existed_at_close":true,"classified_at":"2027-01-13T09:00:00"}
```
**3. Candidate policy** (`POL-0001`):
```json
{"policy_id":"POL-0001","policy_type":"VERIFY_EFFECTIVE_CONTRACT_PRICE","plain_text":"For recurring contract-based spend where pricing may vary by contract period, retrieve and validate the price effective for the current service period before estimation.","trigger":"OBLIGATION_NEEDS_ESTIMATE","predicates":{"spend_type":"RECURRING","estimation_basis":"CONTRACT_PRICE"},
 "required_evidence":[{"evidence_key":"EFFECTIVE_PRICE_CHECK","must_cover":"service_period","produced_by":"resolve_effective_price(contract_id, service_period)","accepted_sources":["PRICING_SCHEDULE","AMENDMENT","VENDOR_PRICE_NOTICE"]}],
 "evidence_plan_delta":{"add_tools":["list_related_documents","open_document:RELATED","resolve_effective_price"]},"before_action":"CREATE_DRAFT_ACCRUAL",
 "behavior_change":"the estimator's unit price comes from the effective PriceTerm when resolve_effective_price returns RESOLVED; on NO_PRICING_DOCUMENTS_ON_FILE the order form price stands",
 "verifier_result_if_missing":{"check_absent":"BLOCK","conflicting_or_unparseable":"OUTREACH_REQUIRED","no_reply_at_cutoff":"ESCALATE"},"outreach_if_missing":{"target_role":"VENDOR_BILLING","missing_fact":"SCOPE_OR_RATE_CHANGE"},
 "autonomy_limit":"controller_review_if_material","derived_from":{"outcome_id":"TU-V001-2026-12","root_cause_id":"VE-V001-2026-12"},
 "status":"CANDIDATE","created_at":"2027-01-13T09:30:00","policy_version_target":"1.1"}
```
Matches `V001`, `V005`, `V014`, `V004`, `V009` by predicate. No `vendor_id`, vendor name, `contract_id`, percent or dollar amount anywhere in the record.

**4. Replay procedure** (2027-01-13). (a) Take every obligation in 2026-11 and 2026-12: 20. (b) For each, rebuild the visible snapshot as of that period's cutoff from the simulator snapshots `2026-11-cutoff` and `2026-12-cutoff`; no private file is read. (c) Run the pipeline twice, playbook 1.0 and 1.0 + the candidate policy. (d) Compare both against confirmed outcomes visible on 2027-01-13. `OBL-V006-2026-12` has no confirmed actual yet (its invoice arrives 2027-01-15) and is compared on action equality only. (e) Improved = absolute error falls or a failed verifier check now passes. Regressed = absolute error rises, a correct action changes, or a new unneeded outreach or review is created. (f) Any regression sets `recommendation = REJECT`.

**Replay report** (`RPL-POL-0001`):
```json
{"replay_id":"RPL-POL-0001","policy_id":"POL-0001","run_at":"2027-01-13T11:00:00","periods":["2026-11","2026-12"],"obligations_replayed":20,"feature_matched":10,"not_triggered":6,"triggered":4,
 "touched":{"obligation_key":"OBL-V001-2026-12","before":{"amount":50000.00,"abs_error":4000.00},"after":{"amount":54000.00,"abs_error":0.00},"result":"IMPROVED"},
 "improved":1,"regressed":0,"unchanged":19,"compared_on_action_only":["OBL-V006-2026-12"],
 "extra_outreach":0,"extra_reviews":0,"abs_error_before":4000.00,"abs_error_after":0.00,
 "forward_scope_preview":["OBL-V001-2027-01","OBL-V005-2027-01","OBL-V014-2027-01","OBL-V004-2027-01","OBL-V009-2027-01"],
 "recommendation":"APPROVE_PROVISIONAL"}
```
**5. Approval record** (`APR-POL-0001`):
```json
{"approval_id":"APR-POL-0001","policy_id":"POL-0001","replay_id":"RPL-POL-0001","decision":"APPROVED","approved_by":"E001","approver_role":"CONTROLLER","decided_at":"2027-01-15T10:00:00","activation":"PROVISIONAL","effective_from_period":"2027-01","resulting_policy_version":"1.1","review_after":"2027-01 close","comment":"Replay fixes DataForge December with no regressions. Monitor January before promoting."}
```
**6. Versioning.** Policy versions are immutable snapshots; every action logs the version it ran under.

| Version | Contents | Status | Used for |
|---|---|---|---|
| `1.0` | initial rules in `policies.json` | `FROZEN` | 2026-11 and 2026-12 closes; the frozen baseline |
| `1.1` | `1.0` + POL-0001 | `PROVISIONAL` from 2027-01-15 | 2027-01 close; the learned baseline |

After the 2027-01 true-ups (5 of 5 matched obligations inside tolerance, 0 regressions) POL-0001 moves from `ACTIVE_PROVISIONAL` to `ACTIVE`. Rejecting or revoking it restores 1.0 behavior with no code change.

### 4.7 Held-out evaluation

Both rows are 2027-01, cutoff 2027-02-05, invoice missing at cutoff. Error = estimate minus `true_expense`, at the default walkthrough values (DataForge 8 percent, PagerLoop 15 percent).

| Obligation | True | Frozen 1.0 | Error | Learned 1.1 | Error | 1.1 path |
|---|---|---|---|---|---|---|
| `OBL-V001-2027-01` (same vendor as training) | 54,000.00 | 50,000.00 | -4,000.00 | 54,000.00 | 0.00 | retrieves PS-001; Controller |
| `OBL-V005-2027-01` (per-seat, different document type) | 13,800.00 | 12,000.00 | -1,800.00 | 13,800.00 | 0.00 | retrieves VPN-005; Reviewer |

### 4.8 Metrics (product spec section 12) mapped to truth

| Metric | Computation | Truth source |
|---|---|---|
| Accrual MAPE and total absolute dollar error | mean and sum of abs(estimate - `true_expense`) over rows with `needs_estimate = Y` (the 4.2 scoring rule), for `frozen_estimate` and `learned_estimate` each | `obligations_truth`: `needs_estimate`, `true_expense`, `frozen_estimate`, `learned_estimate` |
| Material-miss rate | share of scored rows where abs error > max(500.00, 0.02 x the estimate) | same |
| Correct invoice/accrual match rate | agent `matches[]` rows equal to `expected_matches` on (`invoice_id`, `obligation_key`, `allocated_amount` within 0.01) / rows in `expected_matches` | `expected_matches.csv` |
| Root-cause diagnosis accuracy | agent `root_cause` equals truth on rows where `root_cause` is set | `root_cause`, `seeded_root_causes.json` |
| Approval-routing accuracy and unnecessary review rate | agent `approval_level` equals `approval_required` on all rows; share of `approval_required = NONE` rows where the agent still requested review or sent outreach | `approval_required` |
| Unsupported autonomous postings | count of posted entries failing any `evidence_cited`, `approval` or `no_post_before_approval` criterion. Target 0 | `expected_safe_actions` |
| Policy regression count | rows where 1.1 absolute error > 1.0 absolute error, or a rubric criterion passes under 1.0 and fails under 1.1. Target 0 | `frozen_estimate`, `learned_estimate`, `expected_safe_actions`, `RPL-POL-0001.json` |
| Held-out improvement and rubric score | frozen minus learned total absolute error over `split = HELDOUT`, expected $5,800.00; mean of passed / total rubric criteria per obligation | `split`, `frozen_estimate`, `learned_estimate`, `expected_safe_actions` |

## 5. Fixture file tree and build delta

All paths are relative to the fixture root `data/acme/` unless they start with `data/`.

### Part B. File tree

```
data/
  generate.py            builds acme/world/, runs the leak tests, exits non-zero on a leak
  simulate.py             CLI over the simulator clock: init, advance --to, checkpoint, restore
  spec/                    these specification files (01..05)
  gen/
    world.py               entity, cost centers, chart of accounts, ten vendors, T0 constant
    features.py            v1.0 ContractFeatures per contract, order form only; read only by truth.py
    records.py             invoices, the one PO, usage, timesheets, service activity
    ledger.py              gl_entries, ap_queue, accrual_schedule_prior
    docs.py                contract text, PS-001, VPN-005, policy manual, policies.json, PDF rendering
    events.py              splits every dated record at T0 into seed rows or events.jsonl rows
    simulator.py           owns the clock; materialises released events into runtime/visible
    truth.py               obligations truth, seeded root cause, replay expectation, scripted inbox
    leakcheck.py           static checks that seed and visible trees carry no private fact
  tests/
    test_leaks.py          the LK1-LK13 tests; runs leakcheck against a fresh build and runtime/visible at each snapshot
    test_demo_path.py      every id, amount and date in the three scenarios exists at its stated clock time
  acme/
    world/
      seed/                 everything visible at T0 = 2026-12-01T00:00:00
        company.json          entity, cost centers, chart of accounts, close calendar
        org_directory.json    seven employees and vendor billing contacts
        vendors.json           ten vendors at T0; spend_type, estimation_basis
        purchase_orders.json   PO-1042 only
        policies.json           policy v1.0 as data, including evidence_plans per basis
        close_policy_manual.md  policy v1.0 in prose, including the tool gateway modes
        gl_entries.csv          history 2026-05..2026-10 plus rows posted before T0
        ap_queue.csv            AP rows with received_date before T0
        erp/accrual_schedule_prior.csv   human team's rollforward, 2026-05..2026-10
        contracts/
          CTR-001, CTR-002, CTR-004, CTR-005, CTR-006, CTR-009, CTR-010, CTR-011, CTR-013, CTR-014 (.pdf, .txt)
          pricing_schedules/PS-001.pdf, PS-001.txt
          price_notices/         empty at T0; VPN-005 arrives after T0
          index.json              one row per document
        invoices/invoices.json, invoices/pdf/    invoices received before T0
        evidence/usage_daily.csv, timesheets.csv, service_activity.csv   rows dated before T0
      private/                 never mounted into TrueUp
        events.jsonl             every fact after T0, one JSON object per line, sorted by release_at
        documents/                files that events copy into visible: VPN-005, later invoice PDFs
        inbox/scripted_responses.json   three replies, keyed by vendor_id + period + target_role + missing_fact, with delay_hours
        truth/
          obligations_truth.csv    answer key, 30 rows
          future_invoices.csv      every invoice received on or after 2026-12-01
          expected_matches.csv     ONE_TO_ONE only
          seeded_root_causes.json  one entry: the PROCEDURE_GAP miss and its held-out cases
          learning_proof/           TU-V001-2026-12, VE-V001-2026-12, POL-0001, RPL-POL-0001, APR-POL-0001
    runtime/                  git-ignored; created by simulate.py init
      sim_state.json            clock, released_event_ids, pending_deliveries, overrides
      mutation_log.jsonl        every ScenarioOverride, written only by the simulator
      outreach_log.jsonl        every send_outreach call; replayed to rebuild a run deterministically
      visible/                  copy of seed plus materialised events; the only root TrueUp tools receive; read-only to TrueUp
        inbox/messages.jsonl, inbox/attachments/   both written by the simulator
      snapshots/                 2026-11-cutoff, 2026-12-cutoff, 2027-01-open, 2027-01-cutoff
      checkpoints/CP-DEC/         copy of sim_state.json, mutation_log.jsonl, visible/, the TrueUp SQLite files
      demo_cache/beat-NN.json     recorded model outputs for fallback mode
      recorded/REC-<hash12>.jsonl recorded tool-call stream for the override-free baseline world
```

`contracts/index.json` literal rows, the two related documents (every `CTR-0NN` file has `doc_type = MSA_ORDER_FORM`):

```json
{"doc_id":"PS-001","doc_type":"PRICING_SCHEDULE","contract_id":"CTR-001","vendor_id":"V001","title":"Exhibit B - Pricing Schedule","effective_date":"2025-12-01","filed_date":"2025-11-24","filed_by":"E003","visible_from":"2026-12-01T00:00:00","files":["contracts/pricing_schedules/PS-001.pdf","contracts/pricing_schedules/PS-001.txt"]}
{"doc_id":"VPN-005","doc_type":"VENDOR_PRICE_NOTICE","contract_id":"CTR-005","vendor_id":"V005","title":"2027 renewal price notice","effective_date":"2027-01-01","filed_date":"2027-01-20","filed_by":"E003","visible_from":"2027-01-20T10:00:00","files":["contracts/price_notices/VPN-005.pdf","contracts/price_notices/VPN-005.txt"]}
```

### Part C. Build delta (ordered checklist)

Each step leaves `python3 data/generate.py` passing.

| # | Module | Change | Acceptance check |
|---|---|---|---|
| 1 | `generate.py` | Write to `acme/world/seed/` and `acme/world/private/`. Add `acme/runtime/` to `.gitignore`. | `find world/seed -name '*truth*' -o -name 'scripted_responses.json'` returns nothing. |
| 2 | `world.py` | `T0 = datetime(2026, 12, 1, 0, 0)`. One entity `ACME-US`. Three cost centers `ENG`, `DATA`, `GA`. Six accounts `2000`, `2100`, `6110`, `6120`, `6200`, `6300`. Ten vendors only: `V001` DataForge, `V002` AWS, `V004` Lumen, `V005` PagerLoop, `V006` Brightwork, `V009` PayCircle, `V010` SecureLayer, `V011` TalentBridge, `V013` ModelAPI, `V014` OfficeLease, each with `spend_type` in `RECURRING`, `USAGE`, `SERVICES` and `estimation_basis` per section 2. | `len(VENDORS) == 10`; `grep -c pricing_model world/seed/vendors.json` is 0. |
| 3 | `docs.py` | `CTR-001.txt` order form line `$50,000.00 per month (Contract Year 1)`, no sentence naming a pricing schedule, Exhibit B or a Contract Year 2. `pricing_schedule_text` renders `PS-001` (CY1 $50,000.00, CY2 the judge-set rate). `CTR-005.txt` order form line `120 seats at $100.00 per seat per month (Initial Term)`, no sentence naming a renewal or an uplift. New `price_notice_text` renders `VPN-005`, visible only from 2027-01-20T10:00. `policies.json` writes `evidence_plans` per estimation basis; no `pricing_schedule_effective` key anywhere. Emit `contracts/index.json`. | `grep -c "Exhibit B" CTR-001.txt` is 0 and `grep -c "52,500" PS-001.txt` is 1; `grep -c "renewal" CTR-005.txt` is 0. |
| 4 | `records.py` | Invoices for all ten vendors. Only `V006` carries a PO: `PO-1042`, `PROJECT_TM`, not-to-exceed `400000.00`, valid 2026-07-01..2027-06-30, issued 2026-06-24, status `OPEN`, owner E014. No other vendor has a PO. | `INV-V001-008` is 52,500.00 at the 5 percent baseline; only `V006` invoices carry a `po_id`. |
| 5 | `ledger.py` | `build_gl()` uses only the six accounts; `gl_entries.csv` keeps `entry_type` in `INVOICE`, `ACCRUAL`, `ACCRUAL_REVERSAL`, `TRUE_UP` and the trailing `obligation_id` column. `build_accrual_schedule_prior()` writes 2026-05..2026-10 rows for the eight vendors the human team accrued (V005 and V010 have none), including six DataForge rows at accrued 50,000.00 and actual 50,000.00. | GL balances per `entry_id`; no `entry_type` outside the four values; no account outside the six; `grep -c V001 erp/accrual_schedule_prior.csv` is 6. |
| 6 | `events.py` | `split(records, date_field)` sends rows dated before T0 to seed and the rest to `events.jsonl`. Event types: `INVOICE_RECEIVED`, `USAGE_EXPORT`, `EVIDENCE_UPDATE`, `CONTRACT_DOC_ADDED` (`VPN-005`, filed 2027-01-20, visible from 2027-01-20T10:00), `PERIOD_STATUS_CHANGE`. | Seed `invoices.json` max `received_date` < 2026-12-01; `VPN-005` is absent from `runtime/visible` before 2027-01-20T10:00 and present after. |
| 7 | `simulator.py`, `simulate.py` | `init` copies seed to `runtime/visible/`, clock to T0. `advance --to ISO` appends every event with `release_at <= now`, idempotently. `send_outreach` appends the OUTBOUND row to `visible/inbox/messages.jsonl` and matches `scripted_responses.json` on `vendor_id`, `period`, `target_role`, `missing_fact`; the INBOUND row appears once `now >= sent_at + delay_hours`. `checkpoint` and `restore` support `CP-DEC` only. | `test_demo_path.py`: at 2027-01-05T23:59:59 `INV-V001-008` is not visible, at 2027-01-12T09:00 it is; outreach sent 2027-01-04T09:30 yields the reply at 2027-01-05T15:30 and not one minute earlier. |
| 8 | `truth.py`, `features.py` | `features.py` holds the true v1.0 ContractFeatures for CTR-001, CTR-002, CTR-004, CTR-005, CTR-006, CTR-009, CTR-010, CTR-011, CTR-013, CTR-014. `truth.py` writes the 30-row `obligations_truth.csv`, `future_invoices.csv`, `expected_matches.csv`, the one-entry `seeded_root_causes.json` and `learning_proof/`. | `obligations_truth.csv` has 30 rows; `learning_proof/RPL-POL-0001.json` has one `touched` row (`OBL-V001-2026-12`), `improved: 1`, `regressed: 0`. |
| 9 | `leakcheck.py`, `test_leaks.py` | Static checks over `world/seed` and `runtime/visible`: no path or filename contains `truth`, `private` or `scripted_responses`; no visible file names a deleted vendor, PO, contract or field; `CTR-001.txt` and `CTR-005.txt` carry no future-price language. | `python3 data/generate.py` prints `leaks=0`. |

Deleted files: `change_orders.json`, `contracts/notices/`, `evidence/seat_snapshots.csv`, `evidence/hr_hires.csv`, `evidence/goods_receipts.csv`, `world/private/truth/extra_exceptions.json`. Deleted modules and data: `PRICING_MODEL_TRUE`, corporate-card GL logic, every vendor and contract not in the ten-vendor list.
