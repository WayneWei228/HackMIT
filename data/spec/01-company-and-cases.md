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
