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
