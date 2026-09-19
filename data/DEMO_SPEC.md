# TrueUp Close: interactive judge demo specification

Status: specification only, no code changed. Built on `data/WORLD_SPEC.md` (frozen world) and the TrueUp product spec. Source request: `data/demo_spec/BRIEF.md`. Sections are also kept separately under `data/demo_spec/`.
v2: simplified to Acme AI, six judge-facing vendors, causality fix.

# 00 Decisions: shared contract for the interactive judge demo

Scope: names, the five controls, the ScenarioOverride shape, the state machine, the three scenario number tables, endpoint and table lists, id formats, section ownership.
Binding on sections 01 to 05. `data/WORLD_SPEC.md` is the frozen world and this file never departs from it. Every id, amount and date below comes from WORLD_SPEC or from the arithmetic shown. All data is synthetic; the company is Acme AI, Inc., a fictional company.

## 1. Glossary

### 1.1 Services and roots

| Name | Process | Owns | Never sees |
|---|---|---|---|
| Simulator (`sim`) | FastAPI, port 8100 | `world/seed`, `world/private`, the clock, the Scenario Lab, ScenarioOverrides, regeneration, `runtime/mutation_log.jsonl` | TrueUp state and the playbook database |
| TrueUp (`trueup`) | FastAPI, port 8000 | agents, deterministic estimator, verifier, tool gateway, `trueup_state.db`, `trueup_playbook.db`, the web page | `world/`, `sim_state.json`, `mutation_log.jsonl`, any event whose `release_at` is later than the clock |

The Lab belongs to `sim`. TrueUp tools receive `runtime/visible/` only. `trueup` exposes `/api/lab/*` as a byte passthrough proxy to `sim`, so the browser has one origin. The proxy module imports nothing from `data/gen`.

### 1.2 UI panels (one web page, `GET /`)

`#clock-bar` "Clock and World" (simulated clock, period statuses, playbook version badge, 12 hex world hash, `LIVE` or `RECORDED`); `#lab-panel` "Scenario Lab"; `#diff-panel` "What Changed"; `#close-board` "Close Command Center"; `#workpaper` "Vendor Obligation Workpaper"; `#outreach-queue` "Outreach and Resolution"; `#trueup-panel` "Invoice and True-Up"; `#evidence-trail` "Evidence Trail" (live tool-call stream, refused calls included); `#learning-panel` "Learning and Controls"; `#transfer-panel` "Frozen vs Learned"; `#audit-panel` "Audit Packet".

### 1.3 Buttons

`btn-apply-mutation` "Apply Change"; `btn-undo-mutation` "Undo Change"; `btn-run-close` "Run Close"; `btn-approve-accrual` "Approve Accrual"; `btn-advance-time` "Advance Time"; `btn-investigate` "Investigate Variance"; `btn-run-replay` "Run Replay"; `btn-approve-policy` "Approve Policy"; `btn-reject-policy` "Reject Policy"; `btn-run-transfer` "Run Transfer Compare"; `btn-reset-world` "Reset World"; `btn-reset-demo` "Reset Demo". Twelve buttons, each specified exactly once across sections 01 to 03.

### 1.4 Tool gateway modes

Every tool call passes a gateway. `CLOSE` mode allows exactly the active playbook's evidence plan for that obligation's `estimation_basis`, plus `get_vendor`, `read_ap_queue`, `send_outreach`, `search_inbox`, plus anything an ACTIVE policy adds through `evidence_plan_delta`. `INVESTIGATE` mode allows every read tool, including `list_related_documents`, `open_document` of any doc_id and `resolve_effective_price`, and may write nothing but the `VarianceExplanation`.

Under playbook 1.0 in CLOSE mode, `list_related_documents`, `resolve_effective_price` and `open_document` of any non-primary document are refused. A refused call returns `{"refused": true, "reason": "OUTSIDE_EVIDENCE_PLAN", "playbook_version": "1.0"}`, is written to `tool_calls` with `refused = true`, and is streamed to `#evidence-trail`. This is what makes Frozen and Learned differ, and what gives Reject a real consequence. Section 03 owns the gateway; section 02 owns its leakage tests.

### 1.5 Hashes

`world_hash` = sha256 over the newline-joined sorted list of `"<relative path> <sha256 of file bytes>"` for every file under `runtime/visible/`. `fixture_hash` = the same function over `world/seed/`, `world/private/events.jsonl` and `world/private/truth/`. `BASELINE_FIXTURE_HASH` = the `fixture_hash` of an override-free build, pinned in `data/demo_spec/BASELINE_HASH.txt`, printed in `#clock-bar`, re-verified by Reset Demo. The UI shows the first 12 hex characters of each.

### 1.6 Additive deltas to frozen schemas

Only these. `tool_calls` gains `mode`, `refused` and `refusal_reason`. The policy status enum is `CANDIDATE`, `BLOCKED`, `ACTIVE_PROVISIONAL`, `ACTIVE`, `REJECTED`, `REVOKED`. New record types: ScenarioOverride, AgentRun, ToolCall, EscalationNote.

### 1.7 Policy scope whitelist (guard G1)

A candidate policy predicate may reference only `estimation_basis` and these ContractFeatures fields: `spend_type`, `unit`, `billing_frequency`, `price_label`, `term_start`, `term_end`.
Banned anywhere in a policy record: `vendor_id`, vendor name, `contract_id`, `cost_center`, `gl_account`, `po_id`, `unit_price`, `quantity`, any dollar amount, any percent, and any post-cutoff fact (`invoice_id`, `true_up_amount`, `actual_invoice_total`, `root_cause`). An unrecognised key is a G1 failure, not a pass-through.

## 2. Control catalogue

Five controls, one per vendor card, each a dropdown. The baseline option is labelled `(current)` and `Apply Change` is disabled while it is selected. There are no free-form fields, no eligible-vendor matrix and no cut order.

| control_id | Vendor | Target obligation | Options (baseline marked) | Resulting world value | Validator |
|---|---|---|---|---|---|
| `CTL-DATAFORGE-INCREASE` | V001 DataForge | `OBL-V001-2026-12` | 0 / **5 (current)** / 8 / 12 percent | PS-001 CY2 monthly fee 50,000.00 / 52,500.00 / 54,000.00 / 56,000.00 | `VAL-DATAFORGE-INCREASE` |
| `CTL-AWS-USAGE` | V002 AWS | `OBL-V002-2026-12` | Low 0.7x / **Normal 1.0x (current)** / High 1.3x / Spike 1.6x | December `compute_hours` 84,000 / 120,000 / 156,000 / 192,000 at $0.25 | `VAL-AWS-USAGE` |
| `CTL-MODELAPI-USAGE` | V013 ModelAPI | `OBL-V013-2026-12` | Low 0.7x / **Normal 1.0x (current)** / High 1.3x / Spike 1.6x | December input and output token meters at $3.00 and $15.00 per million | `VAL-MODELAPI-USAGE` |
| `CTL-PAGERLOOP-PRICE` | V005 PagerLoop | `OBL-V005-2027-01` | **0 (current)** / 10 / 15 / 25 percent | VPN-005 per-seat price 100.00 / 110.00 / 115.00 / 125.00 | `VAL-PAGERLOOP-PRICE` |
| `CTL-BRIGHTWORK-SURCHARGE` | V006 Brightwork | `OBL-V006-2026-12` | **$0.00 (current)** / $900.00 / $2,400.00 / $6,000.00 | one extra line item on the hidden `INV-V006-008` | `VAL-BRIGHTWORK-SURCHARGE` |

Default walkthrough values: DataForge 8 percent, PagerLoop 15 percent, Brightwork $2,400.00.

Usage amounts, computed exactly. AWS: `84,000 x 0.25 = 21,000.00`, `120,000 x 0.25 = 30,000.00`, `156,000 x 0.25 = 39,000.00`, `192,000 x 0.25 = 48,000.00`. ModelAPI: `1,400 x 3 + 280 x 15 = 8,400.00`, `2,000 x 3 + 400 x 15 = 12,000.00`, `2,600 x 3 + 520 x 15 = 15,600.00`, `3,200 x 3 + 640 x 15 = 19,200.00`. Both vendors always accrue correctly and always true up to $0.00: their job is to show that a judge input flows through deterministic code and that usage-based spend does not match POL-0001.

**Validators.** `VAL-DATAFORGE-INCREASE`: percent in the offered set; `rate = 50000.00 x (1 + pct/100)`; the CY1 row, both date ranges and `CTR-001.txt` untouched; every invoice with a service period starting on or after 2026-12-01 re-derived from the same pricing function. `VAL-AWS-USAGE` and `VAL-MODELAPI-USAGE`: multiplier in the offered set; daily rows sum exactly to the monthly total; the hidden invoice equals total times rate to the cent; the contract rates and the November and January meters untouched. `VAL-PAGERLOOP-PRICE`: percent in the offered set; `per_seat = 100.00 x (1 + pct/100)`; seat count stays 120; `CTR-005.txt` untouched; no proration; VPN-005 still releases 2027-01-20T10:00. `VAL-BRIGHTWORK-SURCHARGE`: amount in the offered set; no contract, purchase order, timesheet or other pre-cutoff visible file changes.

**Locking.** A control locks once a close run has written an `ActionProposal` for its target obligation, with the tooltip `Locked: the close has already used this obligation. Reset World to change it.` `CTL-PAGERLOOP-PRICE` targets a 2027-01 obligation, so it stays editable through `POLICY_APPROVED` and `POLICY_REJECTED` and locks when `btn-run-transfer` is pressed. One applied override per control; a second on the same control returns `423 WORLD_LOCKED`. Overrides on different controls stack. Reset World unlocks everything.

### 2.1 ScenarioOverride

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

`apply_mode` is `COLD` (full regeneration, runtime reset, fast-forward to `start_clock`) or `HOT` (every affected record is still unreleased and the target obligation is unconsumed, so only unreleased events are rewritten and the clock is untouched). `CTL-PAGERLOOP-PRICE` is the only control that may apply `HOT`; the other four are always `COLD`.

A control parameter never edits a truth file. The simulator re-runs the pricing functions with the override applied and rebuilds `world/seed`, `world/private/events.jsonl` and `world/private/truth/`, so a document and its hidden invoice can never disagree. The judge never sets an expected error, a variance or an invoice amount. Budget: stage under 300 ms, apply under 2 seconds.

## 3. Demo state machine

Nineteen states, UPPER_SNAKE, stored in `demo_state.state`. The clock column is the simulator clock on entry.

| State | Clock on entry | Enabled buttons |
|---|---|---|
| `IDLE_BASELINE` | 2027-01-04T09:00:00 | Apply Change (after staging), Run Close, Reset World, Reset Demo |
| `MUTATION_STAGED` | 2027-01-04T09:00:00 | Apply Change, Undo Change |
| `MUTATION_APPLIED` | 2027-01-04T09:00:00 | Run Close, Undo Change |
| `CLOSE_RUNNING` | 2027-01-04T09:00:00 to 2027-01-05T15:30:00 | none |
| `CLOSE_AWAITING_APPROVAL` | 2027-01-05T16:00:00 | Approve Accrual |
| `CLOSE_POSTED` | 2027-01-05T23:59:59 | Advance Time |
| `TRUEUP_COMPUTED` | 2027-01-12T09:00:00 (SCN-A), 2027-01-15T09:00:00 (SCN-C) | Investigate Variance |
| `NO_MISS` | same | Advance Time, Reset World, Reset Demo |
| `INVESTIGATING` | 2027-01-13T09:00:00 (SCN-A), 2027-01-15T11:00:00 (SCN-C) | none |
| `ROOT_CAUSE_FOUND` | 2027-01-13T09:00:00 | Run Replay |
| `ROOT_CAUSE_UNKNOWN` | 2027-01-15T11:00:00 | none |
| `ESCALATED` | 2027-01-15T12:00:00 | Reset World, Reset Demo |
| `CANDIDATE_READY` | 2027-01-13T09:30:00 | Run Replay |
| `CANDIDATE_BLOCKED` | 2027-01-13T09:30:00 (G1) or 2027-01-13T11:00:00 (G2) | Reject Policy, Reset World |
| `REPLAY_REPORT_READY` | 2027-01-13T11:00:00 | Approve Policy, Reject Policy |
| `POLICY_APPROVED` | 2027-01-15T10:00:00 | Advance Time, Run Transfer Compare, Apply Change (PagerLoop only) |
| `POLICY_REJECTED` | 2027-01-15T10:00:00 | Advance Time, Run Transfer Compare, Apply Change (PagerLoop only) |
| `TRANSFER_RUNNING` | 2027-02-05T09:00:00 | none |
| `TRANSFER_COMPARED` | 2027-02-12T09:00:00 | Reset World, Reset Demo |

Transitions.

| From | Event | Guard | To |
|---|---|---|---|
| `IDLE_BASELINE` | Lab selection changed | control and option both set | `MUTATION_STAGED` |
| `MUTATION_STAGED` | `btn-apply-mutation` | validator passes | `MUTATION_APPLIED` |
| `MUTATION_STAGED` / `MUTATION_APPLIED` | `btn-undo-mutation` | - | `IDLE_BASELINE` |
| `MUTATION_APPLIED` / `POLICY_APPROVED` / `POLICY_REJECTED` | a second, unlocked control is selected | different `control_id`, target obligation unconsumed | `MUTATION_STAGED` |
| `IDLE_BASELINE` / `MUTATION_APPLIED` | `btn-run-close` | period 2026-12 status is OPEN | `CLOSE_RUNNING` |
| `CLOSE_RUNNING` | agent emits a `POST_ACCRUAL` proposal | `required_approval_level != NONE` | `CLOSE_AWAITING_APPROVAL` |
| `CLOSE_RUNNING` | verifier result `ESCALATE` | conflicting or absent evidence | `ESCALATED` |
| `CLOSE_AWAITING_APPROVAL` | `btn-approve-accrual` | actor E001 for CONTROLLER, E002 for REVIEWER | `CLOSE_POSTED` |
| `CLOSE_POSTED` | `btn-advance-time` | target clock greater than current | `TRUEUP_COMPUTED` |
| `TRUEUP_COMPUTED` | automatic | `abs(variance) <= tolerance` | `NO_MISS` |
| `TRUEUP_COMPUTED` | `btn-investigate` | `abs(variance) > tolerance` | `INVESTIGATING` |
| `INVESTIGATING` | classifier returns `PROCEDURE_GAP` | the cited document's `filed_date` is on or before the period cutoff | `ROOT_CAUSE_FOUND` |
| `INVESTIGATING` | classifier returns `UNKNOWN` | no contractual basis and no supporting document | `ROOT_CAUSE_UNKNOWN` |
| `ROOT_CAUSE_UNKNOWN` | automatic | - | `ESCALATED` (EscalationNote to E001, no candidate policy) |
| `ROOT_CAUSE_FOUND` | `POST /api/policy/candidate`, guard G1 | every predicate is on the 1.7 whitelist | `CANDIDATE_READY` |
| `ROOT_CAUSE_FOUND` | `POST /api/policy/candidate`, guard G1 | any predicate outside the whitelist or any post-cutoff field | `CANDIDATE_BLOCKED` |
| `CANDIDATE_READY` | `btn-run-replay` | G1 passed | `REPLAY_REPORT_READY` |
| `REPLAY_REPORT_READY` | guard G2 | `regressed > 0`, `abs_error_after >= abs_error_before`, or any approval level falls | `CANDIDATE_BLOCKED` |
| `REPLAY_REPORT_READY` | `btn-approve-policy` | G1 and G2 passed, actor E001 | `POLICY_APPROVED` |
| `REPLAY_REPORT_READY` / `CANDIDATE_BLOCKED` | `btn-reject-policy` | reason of at least 10 characters | `POLICY_REJECTED` |
| `POLICY_APPROVED` / `POLICY_REJECTED` / `NO_MISS` | `btn-run-transfer` | clock at or after 2027-02-01T00:00:00 | `TRANSFER_RUNNING` |
| `TRANSFER_RUNNING` | both arms finish | - | `TRANSFER_COMPARED` |
| any | `btn-reset-world` | - | `IDLE_BASELINE` |
| any | `btn-reset-demo` | `fixture_hash == BASELINE_FIXTURE_HASH` after rebuild | `IDLE_BASELINE` |

`btn-approve-policy` is rendered disabled in `CANDIDATE_BLOCKED`, with the failing guard named on the button.
Reset World clears overrides, rebuilds the baseline world, resets the runtime to T0, fast-forwards to 2027-01-04T09:00:00, wipes `trueup_state.db` and keeps `trueup_playbook.db`, so the playbook badge still reads 1.1 after a Reset World that follows an approval.
Reset Demo does all of that and also drops and re-seeds `trueup_playbook.db` at version 1.0, then prints `BASELINE_FIXTURE_HASH`.

## 4. The three judge scenarios

Accrual is `Dr <expense> / Cr 2100`, dated the last day of the service month, reversed on day 1 of the next month. The invoice posts `Dr <expense> / Cr 2000` for the accrued amount and the true-up posts `Dr <expense> / Cr 2000` for the variance. A zero variance produces no `JE-TRU-` row. Tolerance is `max(500.00, 0.02 x accrued amount)`. Every true-up outside tolerance routes to the approver of its own accrual.

### SCN-A learnable failure, DataForge V001

`OBL-V001-2026-12`, control `CTL-DATAFORGE-INCREASE`, Dr 6120 / Cr 2100 and Cr 2000, cost center DATA, entry 2026-12-31, reversal 2027-01-01, true-up dated 2027-01-12. The v1.0 accrual is always the CTR-001 order form Contract Year 1 fee of $50,000.00. Tolerance `max(500.00, 0.02 x 50000.00) = 1000.00`.

| increase | PS-001 CY2 rate | accrual | hidden INV-V001-008 | variance | vs 1,000.00 | JE-TRU | approval | branch |
|---|---|---|---|---|---|---|---|---|
| 0 percent | 50,000.00 | 50,000.00 | 50,000.00 | 0.00 | inside | none | CONTROLLER E001 | `NO_MISS`, no candidate |
| 5 percent (current) | 52,500.00 | 50,000.00 | 52,500.00 | +2,500.00 | outside | 2,500.00 | CONTROLLER E001 | POL-0001 candidate |
| 8 percent (default) | 54,000.00 | 50,000.00 | 54,000.00 | +4,000.00 | outside | 4,000.00 | CONTROLLER E001 | POL-0001 candidate |
| 12 percent | 56,000.00 | 50,000.00 | 56,000.00 | +6,000.00 | outside | 6,000.00 | CONTROLLER E001 | POL-0001 candidate |

Under the learned playbook the same obligation accrues the CY2 rate and the variance is 0.00 in every row. Replay at 2027-01-13 covers the 20 obligations of 2026-11 and 2026-12: 10 feature-matched, 4 triggered, 1 touched (`OBL-V001-2026-12`), improved 1, regressed 0, unchanged 19, extra outreach 0, extra reviews 0, 1 compared on action only (`OBL-V006-2026-12`). `abs_error_before` equals the variance above, `abs_error_after` is 0.00, and the signed bias (accrued minus actual) goes from the negative of that variance to 0.00.

### SCN-B prove transfer, PagerLoop V005

`OBL-V005-2027-01`, control `CTL-PAGERLOOP-PRICE`, Dr 6120 / Cr 2100 and Cr 2000, cost center ENG, entry 2027-01-31, reversal 2027-02-01, true-up dated 2027-02-12. TrueUp has never accrued PagerLoop: its invoices always arrived before cutoff. Frozen and learned arms fork snapshot `2027-01-open` at 2027-02-01T00:00:00, so the visible state is byte identical. Tolerance `max(500.00, 0.02 x 12000.00 = 240.00) = 500.00`.

| price change | VPN-005 per seat | frozen accrual | hidden INV-V005-009 | frozen variance | vs 500.00 | frozen JE-TRU | learned accrual | learned variance |
|---|---|---|---|---|---|---|---|---|
| 0 percent (current) | 100.00 | 12,000.00 | 12,000.00 | 0.00 | inside | none | 12,000.00 | 0.00 |
| 10 percent | 110.00 | 12,000.00 | 13,200.00 | +1,200.00 | outside | 1,200.00 | 13,200.00 | 0.00 |
| 15 percent (default) | 115.00 | 12,000.00 | 13,800.00 | +1,800.00 | outside | 1,800.00 | 13,800.00 | 0.00 |
| 25 percent | 125.00 | 12,000.00 | 15,000.00 | +3,000.00 | outside | 3,000.00 | 15,000.00 | 0.00 |

`120 x 100.00 = 12,000.00`; `120 x 110.00 = 13,200.00`; `120 x 115.00 = 13,800.00`; `120 x 125.00 = 15,000.00`. Approval is REVIEWER E002 in both arms at every option.

The structure differs from DataForge on purpose: per-seat rather than flat, and the authoritative rate is in a `VENDOR_PRICE_NOTICE` (`VPN-005`, a related document of CTR-005, filed 2027-01-20, effective for service from 2027-01-01) rather than a pricing schedule. The seat count of 120 comes from the CTR-005 order form in both arms. The learned arm blocks, lists related documents, reads the notice, extracts a typed `PriceTerm` and books the effective amount: it gets the right number, it does not merely block.

`#transfer-panel` carries a second row, `OBL-V001-2027-01`, the training vendor one period later: frozen 50,000.00 against the CY2 rate. At the default walkthrough the frozen January error is `4,000.00 + 1,800.00 = 5,800.00` and the learned error is 0.00.

**Rejected path.** If the Controller rejected, `playbook_versions` never gains row 1.1, both arms load 1.0, and `GET /api/transfer/compare` returns identical amount, approval level, estimation basis and tool-call sequence for both columns. The panel prints `Learned == Frozen (policy rejected 2027-01-15, reason: "<reason>")`.

### SCN-C know when not to learn, Brightwork V006

`OBL-V006-2026-12`, control `CTL-BRIGHTWORK-SURCHARGE`, Dr 6200 / Cr 2100 and Cr 2000, cost center GA, entry 2026-12-31, reversal 2027-01-01, true-up dated 2027-01-15. The accrual is `142 x 185.00 = 26,270.00` by `HOURS_X_RATE`, approval CONTROLLER. Tolerance `max(500.00, 0.02 x 26270.00 = 525.40) = 525.40`.

| surcharge | accrual | hidden INV-V006-008 | variance | vs 525.40 | JE-TRU | outcome |
|---|---|---|---|---|---|---|
| $0.00 (current) | 26,270.00 | 26,270.00 | 0.00 | inside | none | `NO_MISS`, no review |
| $900.00 | 26,270.00 | 27,170.00 | +900.00 | outside | 900.00 | `UNKNOWN`, ESCALATED, no candidate |
| $2,400.00 (default) | 26,270.00 | 28,670.00 | +2,400.00 | outside | 2,400.00 | same |
| $6,000.00 | 26,270.00 | 32,270.00 | +6,000.00 | outside | 6,000.00 | same |

The surcharge arrives as one invoice line with no basis in the contract, the purchase order or the timesheets. The investigation finds no supporting document, so `root_cause = UNKNOWN`, `process_detail = NO_CONTRACTUAL_BASIS`, `EscalationNote` `ESC-V006-2026-12-01` to E001, and no candidate policy. The root-cause taxonomy for the whole demo is `PROCEDURE_GAP` and `UNKNOWN`; a variance inside tolerance sets `root_cause = null` and runs no investigation.

Guard G1 blocks any candidate whose predicates leave the 1.7 whitelist or cite a post-cutoff fact. Guard G2 blocks any candidate with a regression, no reduction in absolute error, or a falling approval level. A blocked candidate never reaches `btn-approve-policy`.

## 5. Endpoints, tables and id formats

Simulator, base `/sim`: `GET /sim/health`, `GET /sim/controls`, `POST /sim/overrides/stage`, `POST /sim/overrides/apply`, `GET /sim/overrides`, `DELETE /sim/overrides`, `GET /sim/clock`, `POST /sim/advance`, `POST /sim/outreach`, `POST /sim/snapshot`, `POST /sim/fork`, `GET /sim/hash`, `POST /sim/reset/world`, `POST /sim/reset/demo`.

TrueUp, base `/api`: `GET /api/state`, `GET /api/obligations`, `GET /api/obligations/{obligation_id}`, `POST /api/close/run`, `POST /api/accrual/approve`, `POST /api/trueup/run`, `POST /api/investigate`, `POST /api/policy/candidate`, `POST /api/policy/replay`, `POST /api/policy/approve`, `POST /api/policy/reject`, `GET /api/playbook`, `POST /api/transfer/run`, `GET /api/transfer/compare`, `GET /api/audit/{obligation_id}`, `GET /api/evidence-trail`, `POST /api/reset/world`, `POST /api/reset/demo`, `ANY /api/lab/{path}`.

No endpoint is added or removed for v2. Three payload changes: `GET /sim/controls` returns the five controls of section 2; `POST /sim/overrides/apply` carries `apply_mode` and reports `runtime_reset: false` on a hot apply; `GET /api/obligations/{obligation_id}` gains `evidence_plan` and `refused_tool_calls[]`. `POST /api/investigate` switches the gateway to `INVESTIGATE` for that run. `allow_multi` is removed from `POST /sim/overrides/stage`.

`trueup_playbook.db`, survives Reset World:

| Table | Columns |
|---|---|
| `playbook_versions` | `version` PK, `parent_version`, `status`, `created_at`, `activated_at`, `policies_json`, `fixture_hash` |
| `policies` | `policy_id` PK, `policy_type`, `plain_text`, `trigger`, `predicates_json`, `required_evidence_json`, `evidence_plan_delta_json`, `before_action`, `verifier_result_if_missing_json`, `outreach_if_missing_json`, `behavior_change`, `autonomy_limit`, `derived_from_json`, `status`, `created_at`, `policy_version_target` |
| `policy_events` | `event_id` PK, `policy_id`, `event_type`, `actor`, `decided_at`, `from_status`, `to_status`, `comment`, `replay_id` |
| `replay_reports` | `replay_id` PK, `policy_id`, `run_at`, `periods_json`, `obligations_replayed`, `improved`, `regressed`, `unchanged`, `extra_outreach`, `extra_reviews`, `abs_error_before`, `abs_error_after`, `touched_json`, `feature_matched_json`, `not_triggered_json`, `compared_on_action_only_json`, `forward_scope_preview_json`, `recommendation` |

`trueup_state.db`, wiped by both resets: `obligations`, `contract_features`, `evidence_facts`, `proposals`, `evaluations`, `workpapers`, `approvals`, `outreach_tasks`, `journal_entries`, `invoice_matches`, `trueups`, `variance_explanations`, `escalation_notes`, `agent_runs`, `tool_calls`, `demo_state`.

Id formats for new records: `OVR-0001` ScenarioOverride, `MUT-0001` mutation log line, `RUN-0001` AgentRun, `TC-0001-007` ToolCall, `ESC-V006-2026-12-01` EscalationNote, `PEV-0001` policy event, `REC-<first 12 of world_hash>` recorded run, `SCN-A` to `SCN-C` scenarios, `CTL-<SLUG>` controls, `VAL-<SLUG>` validators. Existing formats (`OBL-`, `PRP-`, `PE-`, `WP-`, `APR-`, `OUT-`, `JE-`, `IM-`, `TU-`, `VE-`, `POL-`, `RPL-`) are unchanged.

Live-model risk. Every agent run streams its tool calls, refusals included, to `#evidence-trail` over `GET /api/evidence-trail`. A recorded run exists only for the override-free baseline world, identified by `fixture_hash == BASELINE_FIXTURE_HASH`, stored at `runtime/recorded/REC-<hash12>.jsonl`; `#clock-bar` shows the `RECORDED` badge while it plays. Any mutated world runs live only. If a live model call fails, the state machine goes to `ESCALATED` with the error shown; it never substitutes a recorded answer.

## 6. Section ownership

| Section | File | Owns |
|---|---|---|
| 01 | `01-scenario-lab-and-mutations.md` | Scenario Lab layout, the five control widgets, the per-control data mutation detail, diff rendering, consistency invariants, regeneration budget; `btn-apply-mutation` and `btn-undo-mutation` |
| 02 | `02-state-machine-and-time.md` | state machine detail, clock handling, hidden-data protection, the leakage tests; `btn-run-close`, `btn-advance-time`, `btn-reset-world`, `btn-reset-demo` |
| 03 | `03-playbook-memory-and-api.md` | playbook memory, the tool gateway and evidence plans, policy lifecycle, replay, Frozen and Learned arms, the API surface; `btn-approve-accrual`, `btn-investigate`, `btn-run-replay`, `btn-approve-policy`, `btn-reject-policy`, `btn-run-transfer` |
| 04 | `04-scenarios-and-demo-flow.md` | the three scenarios end to end and the three-minute judge flow |
| 05 | `05-weaknesses-and-fixes.md` | attacks a judge could make and the smallest fixes |

---

# 01: Judge Scenario Lab UI and mutations

Scope: deliverables 1 and 2 of BRIEF.md. Binding on this file: `00-decisions.md`. Every id, amount and date below is reused from `WORLD_SPEC.md` or derived from it by the arithmetic shown once. All data is synthetic; the company is Acme AI, Inc.

## 1. Judge Scenario Lab UI (deliverable 1)

### 1.1 Page layout

```
+-----------------------------------------------------------------------+
| #clock-bar  Clock 2027-01-04T09:00 | 2026-12 OPEN | Playbook v1.0     |
|   World hash 9f2c41ab77d0 | Fixture hash a10efc9b2d31       [LIVE]   |
+-----------------------------------------------------------------------+
| #lab-panel  SCENARIO LAB            | #diff-panel  WHAT CHANGED       |
|  DataForge   [ 5% (current)   v ]   | PS-001.txt: - $52,500.00        |
|  AWS         [ Normal 1.0x    v ]   |              + $54,000.00       |
|  ModelAPI    [ Normal 1.0x    v ]   | Hidden re-derived: 2 ids,       |
|  PagerLoop   [ 0% (current)   v ]   |   rel. 2027-01-12 / 2027-02-10  |
|  Brightwork  [ $0.00 (current) v ]  |                                  |
|  [ Apply Change ] [ Undo Change ]   | #evidence-trail: tool-call log  |
+-----------------------------------------------------------------------+
| #close-board #workpaper #outreach-queue #trueup-panel                 |
|   [ Run Close ] [ Advance Time ]                                      |
| #learning-panel [Investigate][Run Replay][Approve Policy][Reject]     |
| #transfer-panel [ Run Transfer Compare ]                              |
| #audit-panel   [ Reset World ] [ Reset Demo ]                         |
+-----------------------------------------------------------------------+
```

### 1.2 Five controls, one per vendor card

Each control is one dropdown on one vendor card. Choosing a new option auto-calls `POST /sim/overrides/stage` (debounced 300ms) and repaints `#diff-panel`; nothing under `runtime/visible/` changes until `btn-apply-mutation`. The baseline option is labelled `(current)` and Apply Change is disabled while it is selected. There are no free-form fields.

| control_id | vendor | target obligation | options (baseline marked) | resulting world value | validator |
|---|---|---|---|---|---|
| `CTL-DATAFORGE-INCREASE` | V001 DataForge | `OBL-V001-2026-12` | 0 / 5 (current) / 8 / 12 percent | PS-001 CY2 fee 50,000.00 / 52,500.00 / 54,000.00 / 56,000.00 | `VAL-DATAFORGE-INCREASE` |
| `CTL-AWS-USAGE` | V002 AWS | `OBL-V002-2026-12` | Low 0.7x / Normal 1.0x (current) / High 1.3x / Spike 1.6x | December `compute_hours` 84,000 / 120,000 / 156,000 / 192,000 at $0.25 | `VAL-AWS-USAGE` |
| `CTL-MODELAPI-USAGE` | V013 ModelAPI | `OBL-V013-2026-12` | Low 0.7x / Normal 1.0x (current) / High 1.3x / Spike 1.6x | December input and output token meters at $3.00 and $15.00 per million | `VAL-MODELAPI-USAGE` |
| `CTL-PAGERLOOP-PRICE` | V005 PagerLoop | `OBL-V005-2027-01` | 0 (current) / 10 / 15 / 25 percent | VPN-005 per-seat price 100.00 / 110.00 / 115.00 / 125.00 | `VAL-PAGERLOOP-PRICE` |
| `CTL-BRIGHTWORK-SURCHARGE` | V006 Brightwork | `OBL-V006-2026-12` | $0.00 (current) / $900.00 / $2,400.00 / $6,000.00 | one extra line item on the hidden `INV-V006-008` | `VAL-BRIGHTWORK-SURCHARGE` |

Default walkthrough values: DataForge 8 percent, PagerLoop 15 percent, Brightwork $2,400.00.

**Locking.** A control locks once a close run has written an `ActionProposal` for its target obligation, with the tooltip "Locked: the close has already used this obligation. Reset World to change it." `CTL-PAGERLOOP-PRICE` targets a 2027-01 obligation, so it stays editable through `POLICY_APPROVED` and `POLICY_REJECTED` and locks only when `btn-run-transfer` is pressed; the other four lock when the December close runs. One applied override per control; a second on the same control returns `423 WORLD_LOCKED`. Overrides on different controls stack. Reset World unlocks everything.

### 1.3 What Changed panel

Two blocks, always both present after a stage call. **Visible document diff:** a unified text diff of the one file the staged control touches, old lines prefixed `-`, new lines `+`. `CTL-BRIGHTWORK-SURCHARGE` has no visible diff by design; the panel reads "No visible document changes. The surcharge only appears on the invoice that has not been released yet." **Hidden records that will be re-derived:** a count and a list of evidence ids only, taken from `hidden_records_rederived`, each annotated with its `release_at` and the text "not visible to the agent until <timestamp>", no amount, no content. For `CTL-PAGERLOOP-PRICE` this list also names `VPN-005` itself, labelled "not visible to the agent until 2027-01-20T10:00:00" until that time passes, since the notice is filed after the demo start.

### 1.4 What the judge can and cannot see

Can see: every file currently under `runtime/visible/`, `world_hash`, `fixture_hash`, `BASELINE_FIXTURE_HASH`, the simulated clock, the staged override's before/after of the one visible document it touches, the list (not content) of hidden records it will touch, and the full `#evidence-trail`.
Cannot see, ever: `world/private/events.jsonl`, `world/private/truth/`, `runtime/mutation_log.jsonl`, `runtime/sim_state.json`, or any file's content dated after the current clock. The hidden invoice for the active mutation (for example `INV-V001-008` at $54,000.00) is invisible until `btn-advance-time` releases it; the Lab shows only its id and release timestamp, never its `amount` or `line_items`.

## 2. Control mutation specifications (deliverable 2)

Every row calls `POST /sim/overrides/apply` with the `ScenarioOverride` shape of `00-decisions.md` section 2.1; `override_id` and `world_hash` are illustrative placeholders. Regeneration re-runs the pricing functions and rebuilds `world/seed`, `world/private/events.jsonl` and `world/private/truth/`; a control parameter never writes a truth file directly, and the judge never sets an expected error, a variance or an invoice amount.

### 2.1 `CTL-DATAFORGE-INCREASE`

```json
{"override_id":"OVR-0001","control_id":"CTL-DATAFORGE-INCREASE","validator":"VAL-DATAFORGE-INCREASE","vendor_id":"V001","target_obligation_id":"OBL-V001-2026-12","param":{"price_increase_pct":8},"baseline_param":{"price_increase_pct":5},"visible_docs_changed":["contracts/pricing_schedules/PS-001.txt"],"hidden_records_rederived":["INV-V001-008","INV-V001-009"],"apply_mode":"COLD","staged_at":"2027-01-04T09:00:00","applied_by":"JUDGE","start_clock":"2027-01-04T09:00:00","world_hash":"9f2c41ab77d0"}
```

Worked example, verbatim: The judge sets the DataForge increase to 8 percent. The contract pricing schedule effective rate becomes $54,000.00. The hidden future invoice becomes $54,000.00. The baseline accrual is still $50,000.00. The true-up is +$4,000.00.

Arithmetic, `rate = 50,000.00 x (1 + pct/100)`: 0 percent gives 50,000.00, 5 percent (current) gives 52,500.00, 8 percent gives 54,000.00, 12 percent gives 56,000.00. Only the PS-001 CY2 row changes; the CY1 row, both date ranges and `CTR-001.txt` stay untouched, and every invoice with a service period on or after 2026-12-01 is re-derived from the same pricing function. Accrual under playbook 1.0 stays 50,000.00 in every case, so the true-up against tolerance 1,000.00 is 0.00 / 2,500.00 / 4,000.00 / 6,000.00.

### 2.2 `CTL-AWS-USAGE`

```json
{"override_id":"OVR-0002","control_id":"CTL-AWS-USAGE","validator":"VAL-AWS-USAGE","vendor_id":"V002","target_obligation_id":"OBL-V002-2026-12","param":{"usage_multiplier":1.3},"baseline_param":{"usage_multiplier":1.0},"visible_docs_changed":["evidence/usage_daily.csv"],"hidden_records_rederived":["INV-V002-008"],"apply_mode":"COLD","staged_at":"2027-01-04T09:00:00","applied_by":"JUDGE","start_clock":"2027-01-04T09:00:00","world_hash":"a4c0f7e2b615"}
```

`evidence/usage_daily.csv` December rows for V002 are re-derived by `floor(monthly_total / days_in_month)` per day, the final day carrying the remainder so the month sums exactly to the pinned total; `INV-V002-008 = monthly compute_hours x $0.25`. Amounts: Low 0.7x, 84,000 h, $21,000.00; Normal 1.0x (current), 120,000 h, $30,000.00; High 1.3x, 156,000 h, $39,000.00; Spike 1.6x, 192,000 h, $48,000.00. `CTR-002.txt`'s rate and the November and January meters are untouched. Accrual is `USAGE_X_RATE`, always correct, so every level true-ups to $0.00: the control shows a judge input flowing through deterministic code, and that usage-based spend does not match POL-0001.

### 2.3 `CTL-MODELAPI-USAGE`

```json
{"override_id":"OVR-0003","control_id":"CTL-MODELAPI-USAGE","validator":"VAL-MODELAPI-USAGE","vendor_id":"V013","target_obligation_id":"OBL-V013-2026-12","param":{"usage_multiplier":1.3},"baseline_param":{"usage_multiplier":1.0},"visible_docs_changed":["evidence/usage_daily.csv"],"hidden_records_rederived":["INV-V013-008"],"apply_mode":"COLD","staged_at":"2027-01-04T09:00:00","applied_by":"JUDGE","start_clock":"2027-01-04T09:00:00","world_hash":"5b9a0e73dc1f"}
```

`INV-V013-008 = input_M x $3.00 + output_M x $15.00`, both meters scaled by the same multiplier and re-derived the same way as `usage_daily.csv`. Amounts: Low 0.7x, 1,400M / 280M, $8,400.00; Normal 1.0x (current), 2,000M / 400M, $12,000.00; High 1.3x, 2,600M / 520M, $15,600.00; Spike 1.6x, 3,200M / 640M, $19,200.00. `CTR-013.txt`'s two rates are untouched. Accrual is `USAGE_X_RATE`, always correct, so every level true-ups to $0.00.

### 2.4 `CTL-PAGERLOOP-PRICE`

```json
{"override_id":"OVR-0004","control_id":"CTL-PAGERLOOP-PRICE","validator":"VAL-PAGERLOOP-PRICE","vendor_id":"V005","target_obligation_id":"OBL-V005-2027-01","param":{"per_seat_increase_pct":15},"baseline_param":{"per_seat_increase_pct":0},"visible_docs_changed":["contracts/price_notices/VPN-005.txt"],"hidden_records_rederived":["INV-V005-009"],"apply_mode":"HOT","staged_at":"2027-01-15T10:00:00","applied_by":"JUDGE","start_clock":"2027-01-04T09:00:00","world_hash":"3f80b6c1a9de"}
```

`CTL-PAGERLOOP-PRICE` is the only control that may apply `HOT`: `VPN-005` is filed 2027-01-20 and `INV-V005-009` releases 2027-02-12, both still unreleased at any point before the transfer run, so the simulator rewrites only these unreleased records and the clock stays where it is. Arithmetic, `per_seat = 100.00 x (1 + pct/100)`, seat count stays 120, no proration: 0 percent (current) gives 100.00, accrual 12,000.00, invoice 12,000.00, variance 0.00; 10 percent gives 110.00, invoice 13,200.00, variance +1,200.00; 15 percent (default) gives 115.00, invoice 13,800.00, variance +1,800.00; 25 percent gives 125.00, invoice 15,000.00, variance +3,000.00. Tolerance is `max(500.00, 0.02 x 12,000.00) = 500.00`. `CTR-005.txt` is untouched; `VPN-005` still releases at 2027-01-20T10:00.

### 2.5 `CTL-BRIGHTWORK-SURCHARGE`

```json
{"override_id":"OVR-0005","control_id":"CTL-BRIGHTWORK-SURCHARGE","validator":"VAL-BRIGHTWORK-SURCHARGE","vendor_id":"V006","target_obligation_id":"OBL-V006-2026-12","param":{"surcharge_amount":2400.00},"baseline_param":{"surcharge_amount":0.00},"visible_docs_changed":[],"hidden_records_rederived":["INV-V006-008"],"apply_mode":"COLD","staged_at":"2027-01-04T09:00:00","applied_by":"JUDGE","start_clock":"2027-01-04T09:00:00","world_hash":"c2d5f19e0a77"}
```

The surcharge is added as one invoice line item on `INV-V006-008`: `{"description":"Year end expedite premium","quantity":1,"unit_price":X,"amount":X}`. No contract text, no purchase order, no timesheet and no other pre-cutoff visible file changes, so nothing the agent can inspect before the invoice lands hints at the surcharge. Accrual stays `142 x 185.00 = 26,270.00` (`HOURS_X_RATE`, unaffected). Tolerance is `max(500.00, 0.02 x 26,270.00) = 525.40`. Invoice totals: $0.00 (current) gives 26,270.00, variance 0.00; $900.00 gives 27,170.00, variance +900.00; $2,400.00 (default) gives 28,670.00, variance +2,400.00; $6,000.00 gives 32,270.00, variance +6,000.00.

## 3. Consistency invariants checked after every mutation

`POST /sim/overrides/apply` runs these, in order, against the rebuilt world before it is written to `runtime/visible/`. Any failure rejects the apply and leaves the world unchanged.

| # | Invariant |
|---|---|
| INV-1 | GL balanced: debits equal credits per `entry_id` and in total. |
| INV-2 | Every hidden invoice tied to a mutated contract or meter equals the pricing function evaluated for its own service period, to the cent. |
| INV-3 | No closed period is edited: no re-derived record has a service period or posting date inside 2026-05..2026-11. |
| INV-4 | No leaked future fact: no visible date field exceeds the clock, and the mutated amount appears in no visible file before its own `release_at`. |
| INV-5 | Truth re-derived, never edited: `obligations_truth.csv`, `future_invoices.csv` and `expected_matches.csv` are fully regenerated, and the diff touches only rows for the mutated vendor. |
| INV-6 | Policy scope untouched: the mutation never writes `policies.json`, `trueup_playbook.db` or any `POL-` record. |
| INV-7 | One override, one log line: exactly one `MUT-000N` row per apply. |
| INV-8 | Budget: stage under 300ms, apply under 2 seconds. |

---

# 02 State machine, clock control and hidden-data protection

Scope: the state machine and the four buttons owned here (`btn-run-close`, `btn-advance-time`, `btn-reset-world`, `btn-reset-demo`), plus hidden-data protection. States, clocks and transition guards follow `00-decisions.md` section 3 verbatim. `btn-approve-accrual`, `btn-investigate`, `btn-run-replay`, `btn-approve-policy`, `btn-reject-policy` and `btn-run-transfer` belong to `03-playbook-memory-and-api.md`; `btn-apply-mutation` and `btn-undo-mutation` belong to `01-scenario-lab-and-mutations.md`.

## 1. State table: clock, buttons, visibility

| State | Clock on entry | Enabled buttons | What is on screen |
|---|---|---|---|
| `IDLE_BASELINE` | 2027-01-04T09:00:00 | Apply Change (disabled until staged), Run Close, Reset World, Reset Demo | `#clock-bar` clock, playbook badge, 12-hex `world_hash`; `#lab-panel` pickers empty; `#close-board` December inventory under the active playbook, `OBL-V001-2026-12` `invoice_status=MISSING` |
| `MUTATION_STAGED` | 2027-01-04T09:00:00 | Apply Change, Undo Change | `#diff-panel` shows the staged document diff from `POST /sim/overrides/stage` (before/after text, no world change yet); `#lab-panel` highlights the chosen control |
| `MUTATION_APPLIED` | 2027-01-04T09:00:00 | Run Close, Undo Change | `#diff-panel` shows the applied diff; `#clock-bar` `world_hash` changed from baseline; `#close-board` still shows December, now built from the mutated world |
| `CLOSE_RUNNING` | 2027-01-04T09:00:00 to 2027-01-05T15:30:00 | none | `#evidence-trail` streams `ToolCall` rows live (`GET /api/evidence-trail`), refused calls included; `#close-board` and `#workpaper` are read-only |
| `CLOSE_AWAITING_APPROVAL` | 2027-01-05T16:00:00 | Approve Accrual (03) | `#workpaper` S2: calculation trace, draft `JE-ACR-*`, verifier checklist, `required_approval_level` |
| `CLOSE_POSTED` | 2027-01-05T23:59:59 | Advance Time | `#workpaper` shows the posted entry and the 2027-01-01 reversal; `#clock-bar` period 2026-12 status `CLOSED` |
| `TRUEUP_COMPUTED` | 2027-01-12T09:00:00 (SCN-A), 2027-01-15T09:00:00 (SCN-C) | Investigate Variance | `#trueup-panel` S4: matched invoice, variance, tolerance test, row highlighted red because `abs(variance) > tolerance` |
| `NO_MISS` | same as above | Advance Time, Reset World, Reset Demo | `#trueup-panel` shows variance 0.00, row highlighted green, no `Investigate Variance` button |
| `INVESTIGATING` | 2027-01-13T09:00:00 (SCN-A), 2027-01-15T11:00:00 (SCN-C) | none | `#evidence-trail` streams the classifier's tool calls: SCN-A opens `list_related_documents(CTR-001)` then `open_document(PS-001)`; SCN-C opens `list_related_documents(CTR-006)`, finds only `CTR-006`, and calls `search_inbox` |
| `ROOT_CAUSE_FOUND` | 2027-01-13T09:00:00 | Run Replay | `#trueup-panel` adds `root_cause`, `process_detail`, cited evidence ids and quotes |
| `ROOT_CAUSE_UNKNOWN` | 2027-01-15T11:00:00 | none | `#trueup-panel` shows `root_cause=UNKNOWN`, `process_detail=NO_CONTRACTUAL_BASIS`; no policy panel content |
| `ESCALATED` | 2027-01-15T12:00:00 | Reset World, Reset Demo | `#audit-panel` shows the `EscalationNote` to E001 with both source figures where applicable; no candidate policy anywhere |
| `CANDIDATE_READY` | 2027-01-13T09:30:00 | Run Replay | `#learning-panel` S5: candidate `POL-0001` JSON, scope, required evidence; no vendor id visible in the record |
| `CANDIDATE_BLOCKED` | 2027-01-13T09:30:00 (G1) or 2027-01-13T11:00:00 (G2) | Reject Policy (03), Reset World | `#learning-panel` names the failing guard (G1 or G2) next to a disabled `Approve Policy` |
| `REPLAY_REPORT_READY` | 2027-01-13T11:00:00 | Approve Policy (03), Reject Policy (03) | `#learning-panel` replay report: improved/regressed/unchanged counts, `touched[]` list, `abs_error_before/after` |
| `POLICY_APPROVED` | 2027-01-15T10:00:00 | Advance Time, Run Transfer Compare, Apply Change (PagerLoop only, 01) | playbook badge reads 1.1; `#learning-panel` shows the approval record |
| `POLICY_REJECTED` | 2027-01-15T10:00:00 | Advance Time, Run Transfer Compare, Apply Change (PagerLoop only, 01) | playbook badge stays 1.0; `#learning-panel` shows the rejection event, POL-0001 status `REJECTED` |
| `TRANSFER_RUNNING` | 2027-02-05T09:00:00 | none | `#evidence-trail` streams two labeled tool-call streams, `frozen` and `learned` |
| `TRANSFER_COMPARED` | 2027-02-12T09:00:00 | Reset World, Reset Demo | `#transfer-panel` split view and predicate match line; `#audit-panel` packet for `OBL-V005-2027-01` |

## 2. State flow

Undo Change returns `MUTATION_STAGED`/`MUTATION_APPLIED` to `IDLE_BASELINE`; a second, different, unlocked control re-enters `MUTATION_STAGED` from `MUTATION_APPLIED`, `POLICY_APPROVED` or `POLICY_REJECTED`. With the two-value root-cause taxonomy, `PROCEDURE_GAP` always has `evidence_existed_at_close = true`, so there is no `ROOT_CAUSE_FOUND -> ESCALATED` edge. The clocks in section 1 that no `Advance Time` reaches are stamped by the call that enters the state: `POST /api/investigate`, `POST /api/policy/candidate`, `POST /api/policy/replay` and `POST /api/policy/approve|reject` each set `demo_state.clock` to the value pinned for the state they enter.

```
IDLE_BASELINE -(lab selection)-> MUTATION_STAGED -(Apply Change)-> MUTATION_APPLIED
IDLE_BASELINE / MUTATION_APPLIED -(Run Close, 2026-12 OPEN)-> CLOSE_RUNNING
CLOSE_RUNNING -(proposal, approval required)-> CLOSE_AWAITING_APPROVAL -(Approve Accrual, 03)-> CLOSE_POSTED
CLOSE_RUNNING -(verifier ESCALATE)-> ESCALATED
CLOSE_POSTED -(Advance Time)-> TRUEUP_COMPUTED -(<=tolerance, automatic)-> NO_MISS
TRUEUP_COMPUTED -(>tolerance, Investigate Variance)-> INVESTIGATING
INVESTIGATING -(PROCEDURE_GAP, filed_date <= cutoff)-> ROOT_CAUSE_FOUND
INVESTIGATING -(UNKNOWN, no contractual basis)-> ROOT_CAUSE_UNKNOWN -(automatic)-> ESCALATED
ROOT_CAUSE_FOUND -(guard G1 passes)-> CANDIDATE_READY -(Run Replay)-> REPLAY_REPORT_READY
ROOT_CAUSE_FOUND -(guard G1 fails)-> CANDIDATE_BLOCKED
REPLAY_REPORT_READY -(guard G2 fails)-> CANDIDATE_BLOCKED
REPLAY_REPORT_READY -(Approve Policy, 03)-> POLICY_APPROVED
REPLAY_REPORT_READY / CANDIDATE_BLOCKED -(Reject Policy, 03, reason >= 10 chars)-> POLICY_REJECTED
POLICY_APPROVED / POLICY_REJECTED / NO_MISS -(Run Transfer Compare, clock >= 2027-02-01)-> TRANSFER_RUNNING
TRANSFER_RUNNING -(both arms finish)-> TRANSFER_COMPARED
any state -(Reset World / Reset Demo, fixture_hash check)-> IDLE_BASELINE
```

## 3. Button semantics

### 3.1 `btn-run-close` -> `POST /api/close/run`

**Precondition.** State is `IDLE_BASELINE` or `MUTATION_APPLIED`, and `company.json.close_calendar` period `2026-12` has `status = OPEN`. The button is not rendered in any other state, so the precondition is also enforced client side.

**Side effects.** Creates `AgentRun` `RUN-000N` and opens the tool gateway in `CLOSE` mode, built from the active playbook's evidence plan for each obligation's `estimation_basis` (03, Tool gateway). Under playbook 1.0 that plan never includes `list_related_documents`, `resolve_effective_price`, or `open_document` of any non-primary document; a call outside the plan is refused and logged, never executed. Runs Discover, Gather, Classify, Estimate, Verify, Outreach (if the verifier's `next_action` names one), Work product, in that order, against `runtime/visible/` only. The deterministic estimator computes `estimated_amount` from `calculation_trace.formula`, taken from the contract on file; the LLM only classifies evidence, drafts outreach text, and reads the verifier checklist to decide `next_action`. It never computes an amount. Writes `ActionProposal` `PRP-V001-2026-12-01` and `PolicyEvaluation` `PE-V001-2026-12-01`. Transitions to `CLOSE_AWAITING_APPROVAL` when `required_approval_level != NONE`, or to `ESCALATED` when the verifier result is `ESCALATE`.

**Idempotency.** While `demo_state.state == CLOSE_RUNNING` the endpoint returns `409 {"state": "CLOSE_RUNNING"}` and starts no second `AgentRun`. Once posted, the button is absent in `CLOSE_AWAITING_APPROVAL` and later states; a direct API call still returns `409` naming the current state.

**Failure handling.** A live model-call failure or a deterministic-code exception moves the state to `ESCALATED` with the raw error text shown in `#evidence-trail` and an `EscalationNote`, `target_role = CONTROLLER`, `reason = "AGENT_RUN_FAILED"`. The run never falls back to a cached answer once it has started live.

### 3.2 `btn-advance-time` -> `POST /api/lab/sim/advance` then, when the target crosses a true-up point, `POST /api/trueup/run`

**Precondition.** State is `CLOSE_POSTED` (target `TRUEUP_COMPUTED`), or `NO_MISS` / `POLICY_APPROVED` / `POLICY_REJECTED` with the target clock at or after `2027-02-01T00:00:00` (state unchanged; the advance is what enables `btn-run-transfer`). The button carries a fixed `target_ts` per source state and scenario; it is never a free-text field, so a judge cannot jump the clock past the next release point and see a future fact early. `target_ts` values: `CLOSE_POSTED` -> `2027-01-12T09:00:00` (SCN-A) or `2027-01-15T09:00:00` (SCN-C); `NO_MISS`/`POLICY_APPROVED`/`POLICY_REJECTED` -> `2027-02-05T09:00:00`.

**Side effects.** Calls `sim.advance_to(target_ts)`, which applies every `events.jsonl` row with `clock < release_at <= target_ts` and every inbox delivery due in that window, in one merged time order (ties break by `event_id`). `#diff-panel` lists the released `record_id`s. When the target crosses `2026-12-05`, `2027-01-05`, `2027-02-05` or `2027-02-01T00:00:00`, the simulator snapshots `runtime/visible/` automatically. Once the clock lands, and only from `CLOSE_POSTED`, the backend runs deterministic matching and the tolerance test (section 4) and sets state to `TRUEUP_COMPUTED` (falling straight through to `NO_MISS` inside the same request when the variance is inside tolerance). From `NO_MISS`, `POLICY_APPROVED` or `POLICY_REJECTED` the state is unchanged and `btn-run-transfer` becomes enabled; `TRANSFER_RUNNING` is entered only by `btn-run-transfer`.

**Idempotency.** `ts == clock` is a no-op; the endpoint returns the current state unchanged. `ts < clock` raises `ClockRegressionError`, returns `400`, state unchanged. The button is disabled once its `target_ts` has been reached.

**Failure handling.** If `sim.advance_to` succeeds but the matching/tolerance step throws, the clock has still moved, but `demo_state.state` stays `CLOSE_POSTED` and an error banner names the obligation; retrying `Advance Time` is a no-op on the clock and only retries the matching step.

### 3.3 `btn-reset-world` -> `POST /api/reset/world` -> `POST /sim/reset/world`

**Precondition.** None; enabled in every state.

**Side effects.** Clears all `ScenarioOverride`s, regenerates `world/seed/` and `world/private/` with no override applied, deletes and rebuilds `runtime/visible/` from that seed, resets `sim_state.json` (`clock`, `released_event_ids`, `pending_deliveries`) and fast-forwards the clock to `2027-01-04T09:00:00`. Wipes every table in `trueup_state.db` (`obligations`, `proposals`, `evaluations`, `journal_entries`, `trueups`, `agent_runs`, `tool_calls`, `demo_state`, ...). Does **not** touch `trueup_playbook.db`: if `POL-0001` was already approved, the playbook badge still reads 1.1 after this reset. Sets `demo_state.state = IDLE_BASELINE`.

**Idempotency.** Safe to call from any state, any number of times; the result is always the same baseline `world_hash` (no override survives) and `IDLE_BASELINE`. Calling it twice in a row is a no-op the second time except for the wall-clock cost of rebuilding. **Failure handling.** The rebuild writes to a temporary runtime directory and renames it into place atomically, so a failure mid-rebuild (regeneration exceeds the under-2-second budget, or throws) leaves the previous `runtime/` untouched; the endpoint returns `500` and the UI keeps the pre-reset state with an error banner. `demo_state.state` only changes to `IDLE_BASELINE` after the rename succeeds.

### 3.4 `btn-reset-demo` -> `POST /api/reset/demo` -> `POST /sim/reset/demo`

**Precondition.** None; enabled in every state.

**Side effects.** Everything `Reset World` does, plus: drops and re-seeds `trueup_playbook.db` at version 1.0 (`POL-0001`, if it existed, is gone; `playbook_versions` has one row, `1.0`, `FROZEN`, in the schema of `03-playbook-memory-and-api.md` section 1). Computes `fixture_hash` over the fresh `world/seed/`, `world/private/events.jsonl` and `world/private/truth/`, and asserts it equals `BASELINE_FIXTURE_HASH` from `data/demo_spec/BASELINE_HASH.txt`. `#clock-bar` prints both hashes' 12-hex prefixes.

**Idempotency.** Always returns to the identical starting point: `world_hash` = baseline, playbook 1.0, no overrides, `demo_state.state = IDLE_BASELINE`. **Failure handling.** The `any -> IDLE_BASELINE` transition guard requires `fixture_hash == BASELINE_FIXTURE_HASH` after rebuild. If it fails (generator drift, not a runtime condition), the state machine does **not** transition; the button surfaces "baseline drift" with both hashes side by side and the run is not recoverable live. The presenter restarts the `sim` process from a clean checkout rather than retrying the button.

## 4. Advance Time: matching, variance, true-up, failure highlight

**Release.** `Advance Time` releases every `events.jsonl` row with `release_at` in `(old_clock, target_ts]` plus any inbox reply whose `sent_at + delay_hours` falls in that window. For SCN-A at `target_ts = 2027-01-12T09:00:00` this releases the six invoices dated 2027-01-08 to 2027-01-11 (V002, V013, V014, V004, V009, V011), each matching its accrual to $0.00, and then `INV-V001-008`, the only row outside tolerance.

**Match keys.** Deterministic, no LLM call. `(invoice.vendor_id == obligation.vendor_id) AND (invoice.service_period_start == obligation.service_period_start) AND (invoice.service_period_end == obligation.service_period_end)` gives `ONE_TO_ONE`, `allocated_amount = invoice.amount`. Every invoice in this world matches exactly one obligation this way (`expected_matches.csv` uses only `ONE_TO_ONE`, `allocation_basis = FULL`). A second invoice repeating an already-matched key fails the `NO_DUPLICATE_ACCRUAL` verifier invariant; the verifier returns `ESCALATE` and nothing posts.

**Variance and tolerance.** `variance = allocated_amount - accrued_amount` (sign: actual minus accrued). `tolerance = max(500.00, 0.02 * accrued_amount)`. `outside_tolerance = abs(variance) > tolerance`. SCN-A at the 8 percent default: `variance = 54000.00 - 50000.00 = 4000.00`; `tolerance = max(500.00, 0.02*50000.00) = 1000.00`; `4000.00 > 1000.00`, outside.

**True-up JE.** When `variance != 0.00`: `JE-TRU-<vendor_id>-<period>`, `Dr <expense account> / Cr 2000`, amount `abs(variance)` (sign flips the debit/credit pair if `variance < 0`), dated the invoice's `received_date`, `entry_type = TRUE_UP`, `obligation_id` set. When `variance == 0.00` no `JE-TRU-` row is created. SCN-A: `JE-TRU-V001-2026-12`, Dr 6120 / Cr 2000, $4,000.00, dated `2027-01-12`.

**Failure highlight.** `/api/trueup/run` writes `TrueUpAdjustment.within_tolerance = false` when outside tolerance. `#trueup-panel` renders that obligation's row with a red background, the variance figure in red with a `+`/`-` sign, and shows the `Investigate Variance` button only on that row. The state machine stays at `TRUEUP_COMPUTED` (does not auto-advance to `NO_MISS`) exactly when `within_tolerance = false`.

## 5. Hidden-data protection

**Process and directory boundary.** `sim` (port 8100) and `trueup` (port 8000) are separate OS processes. `sim` alone opens `world/seed/`, `world/private/`, `runtime/sim_state.json`, `runtime/mutation_log.jsonl` and `runtime/outreach_log.jsonl`. `trueup` has no `TRUEUP_WORLD_DIR` (or any) environment variable pointing at `world/`; its only channel to `sim` is HTTP, through `ANY /api/lab/{path}`, a byte passthrough proxy that imports nothing from `data/gen`. `trueup` owns `trueup_state.db` and `trueup_playbook.db`; `sim` never opens either.

**Tool-layer visibility filter.** Every TrueUp tool (`read_file`, `list_dir`, `send_outreach`) is bound to a `VisibleRoot` object rooted at `runtime/visible/`. It resolves relative paths, rejects absolute paths, `..` segments, and symlinks that leave the root. Each call is logged as `ToolCall` `TC-0001-007` and streamed to `#evidence-trail`; the log itself lives in `trueup_state.db`, not under `runtime/visible/`.

**Excluded from the LLM context, always:** `runtime/mutation_log.jsonl`; `sim_state.json` (clock internals, `released_event_ids`, `pending_deliveries`); every file under `world/private/` (`events.jsonl`, `truth/`, `inbox/scripted_responses.json`, `documents/` staging area); the Lab's staged/active `ScenarioOverride` list (`OVR-000N` records) and `overrides.baseline_param` values; any visible record whose `release_at` (or `sent_at`, `received_date`) is later than the current simulated clock; the full 64-hex `world_hash` (only its 12-hex UI prefix is shown, and that prefix is UI-only, never passed to a tool call or a prompt).

**Pinned snapshot for Frozen vs Learned.** The fork point is snapshot `2027-01-open`, taken automatically when `advance_to` crosses `2027-02-01T00:00:00`. `btn-run-transfer` calls `sim.fork("2027-01-open", "frozen")` and `sim.fork("2027-01-open", "learned")`, producing two runtimes with byte-identical `runtime/visible/` and `sim_state.json` (asserted by leakage test LK5 below). The frozen TrueUp instance is pinned to playbook version `1.0`; the learned instance to `1.1`. Model, prompts, tool set and estimator code are identical between the two; `agent_run.agent_build_hash` is logged and compared equal for both arms.

**Automated leakage tests, run after every judge mutation (`Apply Change`), every `Advance Time`, and at demo start.**

| # | Assertion |
|---|---|
| LK1 | `test_no_future_dated_records`: for every JSON/CSV/JSONL under `runtime/visible/`, every date-typed field in WORLD_SPEC L1's checked-field list is `<= demo_state.clock`. Run at every snapshot and after every `Advance Time`. |
| LK2 | `test_visible_root_rejects_escape`: a tool call with path `../sim_state.json`, `../../world/private/events.jsonl`, an absolute path, or a planted symlink leaving `runtime/visible/` raises `PathEscapeError` and is never opened. |
| LK3 | `test_tool_source_has_no_private_refs`: `grep -rE "world/private|sim_state|mutation_log|scripted_responses|outreach_log" trueup/` returns zero matches outside the `/api/lab/*` proxy module. |
| LK4 | `test_mutation_log_never_visible`: after every `Apply Change`, `runtime/mutation_log.jsonl` is not present under `runtime/visible/`, and no `ToolCall.result` field contains `OVR-` or `override_id`. |
| LK5 | `test_fork_parity`: after `Run Transfer Compare`, the `frozen` and `learned` runtimes have equal `world_hash` and equal `sim_state.json`; their `trueup_state.db` differ only in `policy_version_used` and the rows attributable to `POL-0001`. |
| LK6 | `test_no_banned_tokens`: a regex scan of every file under `runtime/visible/` for `EVT-\d`, `RSP-\d`, `OVR-\d`, `MUT-\d`, `TRAIN`, `HELDOUT`, `true_expense`, `scenario`, `root_cause`, `pricing_structure`, `has_scheduled_price_change` returns zero matches. |
| LK7 | `test_amount_allowlist_after_mutation`: the judge-set DataForge rate appears only in `contracts/pricing_schedules/PS-001.*` before `INV-V001-008` releases; the judge-set per-seat price appears only in `contracts/price_notices/VPN-005.*` and only from `2027-01-20T10:00`. |
| LK8 | `test_timing_replies_have_no_amount`: the regex `\$?\d{2,3}(,\d{3})+` matches nothing in the `body` or `structured_facts` of any `INVOICE_WHEREABOUTS` reply for V001 or V005. |
| LK9 | `test_replay_inputs_bounded`: every obligation cited in a replay report belongs to period `2026-11` or `2026-12`; every cited evidence id exists in that period's cutoff snapshot; every cited actual has `received_date <= run_at`. |
| LK10 | `test_advance_time_no_overshoot`: `POST /sim/advance` rejects (`400`) any `ts` beyond the `target_ts` set named in section 3.2 for the current `demo_state.state` and active scenario; the UI never sends a free-text target. |
| LK11 | `test_no_back_solve`: for every obligation whose estimate depends on a price the agent must retrieve, that price appears in exactly one visible document, and no other visible number (purchase order amount, prior invoice, GL row, ledger total, or that number divided by 12) falls within the obligation's tolerance of it. |
| LK12 | `test_evidence_plan_enforced`: during a CLOSE run under playbook 1.0, every `ToolCall` for `list_related_documents`, `resolve_effective_price` or `open_document` of a non-primary document has `refused = true` and returned no content. |
| LK13 | `test_v1_0_knows_no_pricing`: `CTR-001.txt` and `CTR-005.txt` contain none of `Exhibit B`, `Pricing Schedule`, `PS-001`, `VPN-005`, `Contract Year 2`, `escalator`, `uplift`, `renewal price`; no v1.0 `ContractFeatures` record cites a doc_id other than its own `CTR-0NN`; `policies.json` at version 1.0 names no pricing document and no related-document tool. |

---

# 03 Playbook Memory and API

Scope: playbook memory, the tool gateway and evidence plans, policy lifecycle, replay, Approve and Reject, the Frozen vs Learned runner, the full API surface, the evidence-trail stream. This file owns the tool gateway; `02-state-machine-and-time.md` owns the leakage tests (`00-decisions.md` section 6).

## 1. Playbook memory tables

`trueup_playbook.db` survives Reset World. Reset Demo drops and re-seeds it at version 1.0.

- `playbook_versions`: `version` PK (`'1.0'`, `'1.1'`), `parent_version` FK, `status` (`FROZEN|PROVISIONAL|ACTIVE`), `created_at`, `activated_at`, `policies_json` (policy ids active at this version), `fixture_hash`.
- `policies`: `policy_id` PK (`'POL-0001'`), `policy_type`, `plain_text`, `trigger`, `predicates_json` (G1 whitelist fields only, section 5), `required_evidence_json`, `evidence_plan_delta_json`, `before_action`, `verifier_result_if_missing_json`, `outreach_if_missing_json`, `behavior_change`, `autonomy_limit`, `derived_from_json` (`{outcome_id, root_cause_id}`), `status` (`CANDIDATE|BLOCKED|ACTIVE_PROVISIONAL|ACTIVE|REJECTED|REVOKED`), `created_at`, `policy_version_target` FK.
- `policy_events`: `event_id` PK (`'PEV-0001'`), `policy_id` FK, `event_type` (`CANDIDATE_CREATED|GUARD_G1_BLOCKED|REPLAY_RUN|GUARD_G2_BLOCKED|POLICY_APPROVED|POLICY_REJECTED|POLICY_PROMOTED|POLICY_REVOKED`), `actor` (employee id or `'SYSTEM'`), `decided_at`, `from_status`, `to_status`, `comment`, `replay_id` FK.
- `replay_reports`: `replay_id` PK (`'RPL-POL-0001'`), `policy_id` FK, `run_at`, `periods_json`, `obligations_replayed`, `improved`, `regressed`, `unchanged`, `extra_outreach`, `extra_reviews`, `abs_error_before`, `abs_error_after`, `touched_json`, `feature_matched_json`, `not_triggered_json`, `compared_on_action_only_json`, `forward_scope_preview_json`, `recommendation` (`APPROVE_PROVISIONAL|REJECT`).

`trueup_state.db` is wiped by both resets and holds `demo_state`, a single row (id=1), upserted, never appended: `state` (one of the 19 states in `00-decisions.md` section 3), `scenario_id` (`SCN-A|SCN-B|SCN-C|NULL`), `clock`, `world_hash`, `fixture_hash`, `playbook_version_loaded`, `run_mode` (`LIVE|RECORDED`), `active_override_id`, `updated_at`. `playbook_version_loaded` is written by the close-run loader in section 3, not by the UI.

## 2. Typed policy record, in full

`POL-0001`, literal:

```json
{"policy_id":"POL-0001","policy_type":"VERIFY_EFFECTIVE_CONTRACT_PRICE",
 "plain_text":"For recurring contract-based spend where pricing may vary by contract period, retrieve and validate the price effective for the current service period before estimation.",
 "trigger":"OBLIGATION_NEEDS_ESTIMATE","predicates":{"spend_type":"RECURRING","estimation_basis":"CONTRACT_PRICE"},
 "required_evidence":[{"evidence_key":"EFFECTIVE_PRICE_CHECK","must_cover":"service_period","produced_by":"resolve_effective_price(contract_id, service_period)","accepted_sources":["PRICING_SCHEDULE","AMENDMENT","VENDOR_PRICE_NOTICE"]}],
 "evidence_plan_delta":{"add_tools":["list_related_documents","open_document:RELATED","resolve_effective_price"]},
 "before_action":"CREATE_DRAFT_ACCRUAL",
 "behavior_change":"the estimator's unit price comes from the effective PriceTerm when resolve_effective_price returns RESOLVED; on NO_PRICING_DOCUMENTS_ON_FILE the order form price stands",
 "verifier_result_if_missing":{"check_absent":"BLOCK","conflicting_or_unparseable":"OUTREACH_REQUIRED","no_reply_at_cutoff":"ESCALATE"},
 "outreach_if_missing":{"target_role":"VENDOR_BILLING","missing_fact":"SCOPE_OR_RATE_CHANGE"},
 "autonomy_limit":"controller_review_if_material","derived_from":{"outcome_id":"TU-V001-2026-12","root_cause_id":"VE-V001-2026-12"},
 "status":"CANDIDATE","created_at":"2027-01-13T09:30:00","policy_version_target":"1.1"}
```

`predicates` may reference only `estimation_basis` and the ContractFeatures fields on the G1 whitelist (section 5). No `vendor_id`, vendor name or `contract_id` appears anywhere in the record. Matches V001, V005, V014, V004, V009. Does not match V002, V013, V010 (usage) or V006, V011 (services).

## 3. Loading and enforcing the active playbook

Every `POST /api/close/run` starts with a loader, run before any LLM call:

1. It picks the highest-priority row of `playbook_versions` with `status IN ('ACTIVE','PROVISIONAL')` (falls back to `'1.0'` FROZEN if no row), loads the typed policy records for that version's `policies_json` with `status IN ('ACTIVE','ACTIVE_PROVISIONAL')`, and writes `demo_state.playbook_version_loaded`. Together these form a `PolicySet`: the base `policies.json` rules plus zero or more typed policy records.
2. The loader also builds the tool gateway's allowed set for this run: the active playbook's evidence plan for the obligation's `estimation_basis` (section 4), plus every loaded ACTIVE policy's `evidence_plan_delta.add_tools`.
3. The `PolicySet` goes only to the deterministic verifier, never into an LLM message. The LLM sees only `ContractFeatures`, the obligation's evidence records and the tool catalogue the gateway allows. It proposes an `ActionProposal` with `estimation_basis`, `amount`, `evidence_ids`; it never sees a policy predicate, cannot special-case a vendor, and never computes a dollar amount itself.
4. The verifier evaluates the proposal against the `PolicySet` in code. Each `checks[]` row's `source` is `"BASE"` or a `policy_id`, so the workpaper shows exactly which rule fired.

The same loader and gateway code runs for every vendor of a given `estimation_basis`; nothing in the pipeline is keyed on `vendor_id`.

## 4. Tool gateway

Every tool call passes the gateway. A call outside the active mode's allowed set is refused, never executed.

| mode | entered by | allowed |
|---|---|---|
| `CLOSE` | `POST /api/close/run` | the active playbook's evidence plan for the obligation's `estimation_basis`, plus `get_vendor`, `read_ap_queue`, `send_outreach`, `search_inbox`, plus any tool an ACTIVE policy adds via `evidence_plan_delta` |
| `INVESTIGATE` | `POST /api/investigate` | every read tool, including `list_related_documents`, `open_document` for any doc_id, and `resolve_effective_price`; no proposal, no posting, no write other than the `VarianceExplanation` |

Evidence plan per basis, playbook 1.0, CLOSE mode:

| estimation_basis | allowed tool calls |
|---|---|
| `ACTUAL_INVOICE` | `get_vendor`, `read_ap_queue`, `open_invoice`, `open_document(primary)`, `get_service_confirmation` |
| `CONTRACT_PRICE` | `get_vendor`, `list_invoices(limit=3)`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue` |
| `USAGE_X_RATE` | `get_vendor`, `read_usage_meter`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue` |
| `HOURS_X_RATE` | `get_vendor`, `read_timesheets`, `open_document(primary)`, `get_purchase_order`, `read_ap_queue` |
| `NONE` | none; escalate |

`open_document(primary)` means the contract's own order form and nothing else. The `CONTRACT_PRICE` plan does not include related documents. Under playbook 1.0 in CLOSE mode, `list_related_documents`, `resolve_effective_price` and `open_document` of any non-primary document are always refused. A refused call returns `{"refused": true, "reason": "OUTSIDE_EVIDENCE_PLAN", "playbook_version": "1.0"}`, is written to `tool_calls` (`mode`, `refused`, `refusal_reason` columns), and streams to `#evidence-trail`. This is what makes Frozen and Learned differ, and what gives Reject a real consequence.

## 5. Candidate gate

`POST /api/policy/candidate` runs guard **G1** synchronously:

- Every `predicates` key must be on the whitelist: `estimation_basis`, `spend_type`, `unit`, `billing_frequency`, `price_label`, `term_start`, `term_end`.
- Reject any value that is a post-cutoff fact (`invoice_id`, `true_up_amount`, `actual_invoice_total`, `root_cause`) or a banned identifier (`vendor_id`, vendor name, `contract_id`, `cost_center`, `gl_account`, `po_id`, `unit_price`, `quantity`, a dollar amount, a percent).
- An unrecognized key is a G1 failure, not a pass-through.

G1 fail: `policies.status = 'BLOCKED'`, `demo_state.state = 'CANDIDATE_BLOCKED'`, a `policy_events` row `GUARD_G1_BLOCKED` naming the offending field; only Reject or Reset are reachable. G1 pass: status stays `'CANDIDATE'`, `demo_state.state = 'CANDIDATE_READY'`, a `CANDIDATE_CREATED` row.

`POST /api/policy/replay` rebuilds each obligation of 2026-11 and 2026-12 from its own cutoff snapshot, runs the pipeline under 1.0 and under 1.0 plus the candidate, and compares both to the confirmed outcome. Guard **G2** fails if `regressed > 0`, if `abs_error_after >= abs_error_before`, or if any touched row's approval level falls. Pass sets `recommendation = 'APPROVE_PROVISIONAL'` and `demo_state.state = 'REPLAY_REPORT_READY'`; fail sets `recommendation = 'REJECT'` and `demo_state.state = 'CANDIDATE_BLOCKED'`.

Replay report shown in `#learning-panel`, POL-0001 at the default 8 percent DataForge increase: `obligations_replayed` 20, `feature_matched` 10, `not_triggered` 6, `touched` 1 (`OBL-V001-2026-12`, before 50,000.00, after 54,000.00), `improved` 1, `regressed` 0, `unchanged` 19, `compared_on_action_only` 1 (`OBL-V006-2026-12`), `extra_outreach` 0, `extra_reviews` 0, `abs_error_before` 4,000.00, `abs_error_after` 0.00, `forward_scope_preview` 5 ids with no amounts. Signed bias (sum of `accrued - actual` over triggered obligations) goes from -4,000.00 to 0.00. At 5 percent the same two fields read 2,500.00 / 0.00; at 12 percent, 6,000.00 / 0.00. The other three triggered obligations (`OBL-V014-2026-12`, `OBL-V004-2026-12`, `OBL-V009-2026-12`) resolve to `NO_PRICING_DOCUMENTS_ON_FILE`, so their amount and approval level are byte-identical before and after: the regression evidence.

## 6. Approve / Reject

`POST /api/policy/approve`. Precondition: `demo_state.state = 'REPLAY_REPORT_READY'`, actor E001, `policies.status = 'CANDIDATE'`, `replay_reports.recommendation = 'APPROVE_PROVISIONAL'`. It sets `policies.status = 'ACTIVE_PROVISIONAL'`; inserts `playbook_versions(version='1.1', parent_version='1.0', status='PROVISIONAL', policies_json='["POL-0001"]', fixture_hash)`; inserts a `policy_events` row `POLICY_APPROVED` by E001; and sets `demo_state.state = 'POLICY_APPROVED'`. `playbook_version_loaded` refreshes to `'1.1'` on the next close-run loader call.

`POST /api/policy/reject`. Precondition: `demo_state.state IN ('REPLAY_REPORT_READY','CANDIDATE_BLOCKED')`. Body `{"reason": "..."}`, required, at least 10 characters. It sets `policies.status = 'REJECTED'`, inserts a `policy_events` row `POLICY_REJECTED`, writes no row to `playbook_versions` (the active playbook stays `'1.0'` FROZEN), and sets `demo_state.state = 'POLICY_REJECTED'`.

**Rejected path proof.** Because reject never creates version 1.1, the loader in section 3 keeps returning `'1.0'` for every later run, for both the Frozen and Learned labels. `POST /api/transfer/run` after a reject pins both arms to `'1.0'`; `GET /api/transfer/compare` returns identical amount, approval level, `estimation_basis` and tool-call sequence for both columns, and the panel prints `Learned == Frozen (policy rejected 2027-01-15, reason: "<reason>")`. This is the same code path as an approved-then-unused policy, not a special case: the diff is empty because both arms loaded the same `playbook_versions` row.

## 7. Frozen vs Learned runner

`POST /api/transfer/run`. Precondition: `demo_state.state IN ('POLICY_APPROVED','POLICY_REJECTED','NO_MISS')` and sim clock at or after 2027-02-01T00:00:00. Both arms fork the `2027-01-open` snapshot (identical `runtime/visible/` bytes and `sim_state.json`). Arm `FROZEN` pins `playbook_version = '1.0'` for the whole run regardless of what is active in `trueup_playbook.db`. Arm `LEARNED` pins `playbook_version` to whatever row of `playbook_versions` has `status IN ('ACTIVE','PROVISIONAL')` at call time: `'1.1'` if approved, `'1.0'` if rejected. Each arm runs `POST /api/close/run` internally against its own fork and its pinned version, then advances its own fork to 2027-02-12T09:00:00, which releases `INV-V005-009` and `INV-V001-009` in that fork only; the shared demo clock is unaffected, and `demo_state.clock` on entry to `TRANSFER_COMPARED` is 2027-02-12T09:00:00. A `TransferResult` row is written per obligation: `{"obligation_id","frozen":{"amount","approval_level","estimation_basis"},"learned":{...},"delta":"IDENTICAL"|"DIFFERENT","predicate_match":{"spend_type":"RECURRING","estimation_basis":"CONTRACT_PRICE","matched_policy_id":"POL-0001"}}`.

`GET /api/transfer/compare` returns the array of `TransferResult` rows plus the literal POL-0001 record, so the panel can show "no vendor identifier anywhere in this record" next to the diff. At the default walkthrough (DataForge 8 percent, PagerLoop 15 percent): `OBL-V005-2027-01` frozen 12,000.00, learned 13,800.00; `OBL-V001-2027-01` frozen 50,000.00, learned 54,000.00.

## 8. API

Error codes: `400 VALIDATION_ERROR` malformed body or unknown enum; `404 NOT_FOUND` unknown id; `409 STATE_CONFLICT` `demo_state.state` does not allow this call; `422 GUARD_FAILED` G1 or G2 rejected; `423 WORLD_LOCKED` the control's target obligation is already locked (`00-decisions.md` section 2); `502 SIM_UNREACHABLE` the proxy call to `sim` failed; `500 LIVE_MODEL_ERROR` the agent call failed, `demo_state.state -> 'ESCALATED'`, no recorded fallback is substituted.

No endpoint is added or removed from `WORLD_SPEC.md`. `sim` paths start `/sim`, `trueup` paths start `/api`.

| Endpoint | Precondition | Request | Response (key fields) | Errors |
|---|---|---|---|---|
| `GET /sim/health` | none | - | `{"status":"ok","build":"..."}` | - |
| `GET /sim/controls` | none | - | the five controls of `00-decisions.md` section 2 | - |
| `POST /sim/overrides/stage` | target control unlocked | `{"control_id":"CTL-DATAFORGE-INCREASE","param":{"price_increase_pct":8}}` | `{"override_id":"OVR-0001","validator":"VAL-DATAFORGE-INCREASE","valid":true}` | 400, 423 |
| `POST /sim/overrides/apply` | one staged override exists | `{"override_id":"OVR-0001"}` | `{"world_hash":"...","runtime_reset":true,"clock":"...","apply_mode":"COLD"}`; on `HOT`, `runtime_reset:false`, clock unchanged | 404, 400 |
| `GET /sim/overrides` | none | - | `[ScenarioOverride, ...]` | - |
| `DELETE /sim/overrides` | none | - | `{"cleared":1}` | - |
| `GET /sim/clock` | none | - | `{"clock":"...","periods":[{"period":"2026-12","status":"OPEN"}]}` | - |
| `POST /sim/advance` | target `> clock` | `{"to":"2027-01-12T09:00:00"}` | `{"clock":"...","released":["INV-V001-008"]}` | 400 |
| `POST /sim/outreach` | obligation exists | `{"obligation_id":"OBL-V001-2026-12","target_role":"VENDOR_BILLING","missing_fact":"INVOICE_WHEREABOUTS"}` | `{"outreach_id":"OUT-V001-2026-12-01","accepted":true}` | 404 |
| `POST /sim/snapshot` | none | `{"label":"2026-12-cutoff"}` | `{"label":"2026-12-cutoff","stored":true}` | - |
| `POST /sim/fork` | snapshot exists | `{"label":"2027-01-open","dest":"learned-run-1"}` | `{"dest":"learned-run-1","world_hash":"..."}` | 404 |
| `GET /sim/hash` | none | - | `{"world_hash":"...","fixture_hash":"...","baseline_fixture_hash":"..."}` | - |
| `POST /sim/reset/world` | none | - | `{"clock":"...","world_hash":"..."}` | - |
| `POST /sim/reset/demo` | none | - | `{"clock":"...","fixture_hash_matches_baseline":true}` | 500 |
| `GET /api/state` | none | - | `{"state":"...","clock":"...","playbook_version":"1.0","world_hash":"...","mode":"LIVE"}` | - |
| `GET /api/obligations` | none | `?period=2026-12` | `[VendorObligation summary, ...]` | 400 |
| `GET /api/obligations/{obligation_id}` | obligation exists | - | full VendorObligation, evidence, verifier checklist, `evidence_plan`, `refused_tool_calls[]` | 404 |
| `POST /api/close/run` | `state IN ('IDLE_BASELINE','MUTATION_APPLIED')`, period OPEN | `{"period":"2026-12"}` | `{"run_id":"RUN-0001","state":"CLOSE_RUNNING"}` (async; poll `/api/state`) | 409, 500 |
| `POST /api/accrual/approve` | `state = 'CLOSE_AWAITING_APPROVAL'`, actor matches required level | `{"obligation_id":"OBL-V001-2026-12","actor":"E001"}` | `{"accrual_entry_id":"JE-ACR-V001-2026-12","state":"CLOSE_POSTED"}` | 409, 403 |
| `POST /api/trueup/run` | `state = 'CLOSE_POSTED'`, invoice now visible | `{"obligation_id":"OBL-V001-2026-12"}` | `{"true_up_amount":4000.00,"within_tolerance":false,"state":"TRUEUP_COMPUTED"}` | 409, 404 |
| `POST /api/investigate` | `state = 'TRUEUP_COMPUTED'`, outside tolerance | `{"obligation_id":"OBL-V001-2026-12"}` | `VarianceExplanation` (`root_cause`, `process_detail`, `evidence_existed_at_close`); switches the gateway to `INVESTIGATE` for this run, back to `CLOSE` after | 409 |
| `POST /api/policy/candidate` | `state = 'ROOT_CAUSE_FOUND'` | `{"root_cause_id":"VE-V001-2026-12"}` | POL-0001 record, `state` `CANDIDATE_READY` or `CANDIDATE_BLOCKED` | 409, 422 |
| `POST /api/policy/replay` | `state = 'CANDIDATE_READY'` | `{"policy_id":"POL-0001"}` | `replay_reports` row, `state` `REPLAY_REPORT_READY` or `CANDIDATE_BLOCKED` | 409, 422 |
| `POST /api/policy/approve` | section 6 | `{"policy_id":"POL-0001","actor":"E001"}` | `{"policy_version":"1.1","status":"ACTIVE_PROVISIONAL","state":"POLICY_APPROVED"}` | 409, 403 |
| `POST /api/policy/reject` | section 6 | `{"policy_id":"POL-0001","actor":"E001","reason":"..."}` | `{"status":"REJECTED","playbook_version_unchanged":"1.0","state":"POLICY_REJECTED"}` | 409, 400 |
| `GET /api/playbook` | none | - | `{"versions":[...],"policies":[...],"events":[...]}` | - |
| `POST /api/transfer/run` | section 7 | `{}` | `{"run_id":"RUN-0003","state":"TRANSFER_RUNNING"}` (learned arm; frozen arm is `RUN-0004`) | 409 |
| `GET /api/transfer/compare` | `state = 'TRANSFER_COMPARED'` | - | `[TransferResult, ...]` plus POL-0001 | 409 |
| `GET /api/audit/{obligation_id}` | obligation exists | - | proposal, evaluation, approval, JEs, true-up, policy trace | 404 |
| `GET /api/evidence-trail` | run exists | `?run_id=RUN-0001` | SSE stream, section 9 | 404 |
| `POST /api/reset/world` | none | - | proxies `/sim/reset/world`, wipes `trueup_state.db`, keeps `trueup_playbook.db` | 502 |
| `POST /api/reset/demo` | none | - | proxies `/sim/reset/demo`, wipes `trueup_state.db`, re-seeds `trueup_playbook.db` at `'1.0'` | 502, 500 |
| `ANY /api/lab/{path}` | none | byte passthrough | byte passthrough to `sim` | 502 |

## 9. Evidence-trail SSE stream

`GET /api/evidence-trail?run_id=RUN-0001`, `text/event-stream`, ids `TC-<run suffix>-<seq>`. Six event types, in order: `tool_call_start` (`tool_call_id`, `run_id`, `obligation_id`, `tool`, `args`, `at`; example `{"tool_call_id":"TC-0001-007","tool":"open_document","args":{"doc_id":"CTR-001"}}`); `tool_call_result` (`tool_call_id`, `result_summary`, `evidence_id`); `tool_call_refused`, the added type, one per gateway refusal (`tool_call_id`, `tool`, `reason` always `OUTSIDE_EVIDENCE_PLAN`, `playbook_version`); `proposal_created` (`proposal_id`, `amount`, `estimation_basis`); `verifier_result` (`evaluation_id`, `result`, `required_approval_level`); `done` (`run_id`, `state`).

Every event is also written to `trueup_state.db.tool_calls`, so the trail survives a page reload; the stream replays from that table on reconnect.

## 10. Backend delta and build checklist

Delta against the generator (`data/gen/`): pricing functions, invoice and PO builders and `release_at` values accept `ScenarioOverride` parameters. `truth.py` and `features.py` keep their logic and are re-run, never hand-edited.

Build order and hours: `sim` skeleton plus outreach/snapshot/fork (4h); ScenarioOverride validators, stage/apply, pricing re-run (4h); `trueup_state.db` and `trueup_playbook.db` schemas, seed data, `/api/lab/*` proxy (4h); close pipeline loader, tool gateway, estimator, verifier (5h); `POST /api/close/run`, accrual approve, obligations, SSE trail (4h); `POST /api/trueup/run`, `POST /api/investigate` (3h); guard G1 candidate, replay engine, guard G2 (6h); approve, reject, playbook read, Frozen/Learned runner (5h); audit endpoint, reset endpoints, recorded-run capture, live-model fallback (4h); web page and leakage tests against the live API (11h). Total 50 hours; four people in parallel fits a 24-hour build with roughly 12 hours of slack.

---

# 04 Scenarios and demo flow

Deliverables 7 and 8. Binding on this file: `00-decisions.md` (ids, states, buttons, endpoints, tables) and `WORLD_SPEC.md` (amounts, evidence text, ids). All amounts below are recomputed here, not copied blind; each matches `00-decisions.md` section 4 where that section already gives the row.
Shared notation: `CONTROLLER` = E001 Dana Whitfield, `REVIEWER` = E002 Marcus Oyelaran. Tolerance = `max($500.00, 0.02 x accrued amount)`. Accrual is `Dr <expense> / Cr 2100`, dated the last day of the service month, reversed day 1 of next month. Invoice posts `Dr <expense> / Cr 2000` for the accrued amount; true-up posts `Dr <expense> / Cr 2000` for the variance only. Guard G1 blocks a candidate whose predicates leave the section 1.7 whitelist or cite a post-cutoff fact. Guard G2 blocks a candidate with `regressed > 0` or no drop in absolute error.

## 1. SCN-A: learnable failure (DataForge, V001)

**Judge action and diff.** Scenario Lab, vendor V001, control `CTL-DATAFORGE-INCREASE`. Options 0 / 5 / 8 / 12 percent; 5 is the untouched baseline (`PS-001` CY2 is already $52,500.00, no visible diff); this walkthrough uses **8**, a genuine judge edit. `btn-apply-mutation` rewrites `contracts/pricing_schedules/PS-001.txt` CY2 row `$52,500.00 -> $54,000.00`, re-derives hidden `INV-V001-008` to $54,000.00, and changes `world_hash` (budget under 2s).

**What TrueUp sees at close** (`btn-run-close`, period 2026-12, clock 2027-01-04T09:00 to 2027-01-05T15:30). Playbook 1.0's evidence plan for `CONTRACT_PRICE` is `get_vendor`, `list_invoices(limit=3)`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue`: vendor master, the last 3 invoices (all $50,000.00), the CTR-001 order form ("$50,000.00 per month (Contract Year 1)"), service confirmation, the AP queue. It does not include related documents: `PS-001` is never opened, and a `list_related_documents(CTR-001)` call, if attempted, is refused with `OUTSIDE_EVIDENCE_PLAN`.

**ActionProposal and JE.** `PRP-V001-2026-12-01`, amount $50,000.00, Dr 6120 / Cr 2100, `calculation_method CONTRACT_PRICE`, evidence `[CTR-001, SA-DATAFORGE-2026-12]`, `policy_version 1.0`. Verifier `PE-V001-2026-12-01`: `REVIEW_REQUIRED`, `required_approval_level CONTROLLER` (`MATERIALITY_APPROVAL` fails: 50000.00 >= 25000.00; `EVIDENCE_PLAN_COMPLETE` passes). `JE-ACR-V001-2026-12` Dr 6120 / Cr 2100 $50,000.00, CC DATA, dated 2026-12-31; `JE-REV-V001-2026-12` reversal 2027-01-01. Presenter clicks `btn-approve-accrual` (E001) -> `CLOSE_POSTED`.

**Advance Time and variance.** `btn-advance-time` to 2027-01-12T09:00 releases the six invoices dated 2027-01-08 to 2027-01-11, each matching its accrual to $0.00, then `INV-V001-008`, **$54,000.00**. $54,000.00 - $50,000.00 = **$4,000.00**. Tolerance `max(500.00, 0.02 x 50000.00) = $1,000.00`. Outside tolerance -> `TRUEUP_COMPUTED`, `btn-investigate` enabled. `JE-INV-V001-008` Dr 6120 / Cr 2000 $50,000.00; `JE-TRU-V001-2026-12` Dr 6120 / Cr 2000 $4,000.00, dated 2027-01-12.

**Investigation trail** (`btn-investigate`, clock 2027-01-13T09:00, run `RUN-0002`), in order: `open_invoice(INV-V001-008)` -> `list_related_documents(CTR-001)` returns `["CTR-001","PS-001"]` -> `open_document(PS-001)` quoting the CY2 row, $54,000.00 -> `open_document(CTR-001)` quoting "$50,000.00 per month (Contract Year 1)" -> `compute_variance` (deterministic, 4,000.00) -> `classify_root_cause`. Root cause `PROCEDURE_GAP`, `process_detail = EFFECTIVE_PRICE_NOT_RETRIEVED`, `evidence_existed_at_close = true` because `PS-001.filed_date = 2025-11-24`, before the period cutoff -> `ROOT_CAUSE_FOUND`.

**Candidate policy and replay.** `POL-0001`, `policy_type VERIFY_EFFECTIVE_CONTRACT_PRICE`, predicates `{spend_type: RECURRING, estimation_basis: CONTRACT_PRICE}`. No `vendor_id`, vendor name, or `contract_id` anywhere in the record; Guard G1 passes (both fields are on the section 1.7 whitelist). Replay (`btn-run-replay`, `RPL-POL-0001`, 20 obligations across 2026-11 and 2026-12): `feature_matched = 10`, triggered 4, touched `OBL-V001-2026-12` only, before $50,000.00 / abs_error $4,000.00, after $54,000.00 / abs_error $0.00, `improved = 1, regressed = 0, unchanged = 19`. Guard G2 passes; recommendation `APPROVE_PROVISIONAL`.

**Approve vs Reject.** `btn-approve-policy` (judge's second real choice, actor E001): `POLICY_APPROVED`, playbook badge 1.0 -> 1.1, `POL-0001.status = ACTIVE_PROVISIONAL`, persisted in `trueup_playbook.db` (survives Reset World); SCN-B's learned arm uses this. `btn-reject-policy`: `POLICY_REJECTED`, playbook stays 1.0, `policy_events` row `REJECTED` by E001; SCN-B's learned arm then behaves identically to the frozen arm.

## 2. SCN-B: prove transfer (PagerLoop, V005)

Runs after SCN-A's decision; this walkthrough assumes approve. Frozen and learned arms fork snapshot `2027-01-open` at 2027-02-01T00:00, so both see one byte-identical visible state.

**Judge action and diff.** Lab, vendor V005, control `CTL-PAGERLOOP-PRICE`. Options 0 / 10 / 15 / 25 percent; 0 is baseline. This walkthrough uses **15**, the judge's own number: `contracts/price_notices/VPN-005.txt` per-seat line `$100.00 -> $115.00`, hidden `INV-V005-009` amount $12,000.00 -> $13,800.00 (`120 x 115.00`). `CTR-005.txt` and the 120 seat count are untouched.

**What each arm sees at close** (period 2027-01, clock at or after 2027-02-01):
- Frozen (1.0): reads only `CTR-005` order form ("120 seats at $100.00 per seat per month (Initial Term)"); accrues $12,000.00.
- Learned (1.1): `POL-0001` matches (`spend_type = RECURRING`, `estimation_basis = CONTRACT_PRICE`); draft $12,000.00; verifier `BLOCK` (`EFFECTIVE_PRICE_CHECK` missing); `list_related_documents(CTR-005)` returns `["CTR-005","VPN-005"]`; `open_document(VPN-005)` quotes the per-seat line; `PriceTerm {PER_SEAT_MONTH, 115.00, 2027-01-01, VPN-005}`; re-propose `120 x 115.00 = $13,800.00`. It books the right number; it does not merely block.

| | Frozen (1.0) | Learned (1.1) |
|---|---|---|
| Accrual amount | $12,000.00 | $13,800.00 |
| Price evidence | CTR-005 order form only | VPN-005 per-seat line |
| Verifier result / approval | REVIEW_REQUIRED / REVIEWER (E002) | BLOCK -> REVIEW_REQUIRED / REVIEWER (E002) |
| JE | Dr 6120 / Cr 2100 $12,000.00, CC ENG, 2027-01-31 | Dr 6120 / Cr 2100 $13,800.00, CC ENG, 2027-01-31 |
| Hidden `INV-V005-009` | $13,800.00 | $13,800.00 |
| True-up | $1,800.00 (tolerance $500.00; outside) | $0.00 |

`#transfer-panel` carries a second row, the training vendor one period later: `OBL-V001-2027-01`, frozen $50,000.00 against the CY2 rate. At the default walkthrough the frozen January error is `4,000.00 + 1,800.00 = $5,800.00` and the learned error is $0.00.

**Rejected path.** If the Controller rejected in SCN-A, `playbook_versions` never gains row 1.1, both arms load 1.0, and `GET /api/transfer/compare` returns identical amount, approval level, estimation basis and tool-call sequence for both columns. The panel prints `Learned == Frozen (policy rejected 2027-01-15, reason: "<reason>")`.

## 3. SCN-C: know when not to learn (Brightwork, V006)

**Judge action and diff.** Lab, vendor V006, control `CTL-BRIGHTWORK-SURCHARGE`. Options $0.00 / $900.00 / $2,400.00 / $6,000.00. This walkthrough uses **$2,400.00**. None of the visible repository changes: the Lab shows "This control changes only the hidden invoice." Hidden `INV-V006-008` total becomes $28,670.00.

**What TrueUp sees at close** (`OBL-V006-2026-12`): timesheets show 68 hours `APPROVED`, 74 hours `PENDING`. Verifier returns `OUTREACH_REQUIRED`, fact `SERVICE_RECEIVED`, target E014. Reply after 20h confirms 142 hours. `HOURS_X_RATE`: `142 x $185.00 = $26,270.00`. `PRP-V006-2026-12-01`, Dr 6200 / Cr 2100, `REVIEW_REQUIRED`, `required_approval_level CONTROLLER`. `JE-ACR-V006-2026-12` dated 2026-12-31, reversal 2027-01-01, approved by E001.

**Advance Time and variance.** SCN-C runs on an otherwise untouched baseline world, so advancing to 2027-01-15T09:00 also releases `INV-V001-008` at $52,500.00, which misses by $2,500.00; `#trueup-panel` shows both rows outside tolerance and the presenter investigates `OBL-V006-2026-12`. That release materializes `INV-V006-008`, total **$28,670.00** (two line items: $26,270.00 services, $2,400.00 "Year end expedite premium"). $28,670.00 - $26,270.00 = **$2,400.00**. Tolerance `max(500.00, 0.02 x 26270.00 = 525.40) = $525.40`. Outside tolerance -> `btn-investigate` enabled.

**Investigation trail.** SCN-C runs from a fresh `btn-reset-world`, so ids restart: close is `RUN-0001`, investigation is `RUN-0002`. `list_related_documents(CTR-006)` returns `["CTR-006"]`, no pricing document; `open_document(CTR-006)` quotes "Consultant shall bill actual hours worked at $185.00 per hour. No additional fees apply absent a signed change order."; `search_inbox` for `SCOPE_OR_RATE_CHANGE` finds no thread; `classify_root_cause` finds no clause or correspondence supporting $2,400.00. Root cause `UNKNOWN`, `process_detail = NO_CONTRACTUAL_BASIS` -> `ROOT_CAUSE_UNKNOWN` -> automatic -> `ESCALATED`. The state machine only reaches `CANDIDATE_READY` from `ROOT_CAUSE_FOUND`, so `UNKNOWN` never scopes a predicate: nothing is proposed.

**EscalationNote:**
```json
{"escalation_id":"ESC-V006-2026-12-01","obligation_id":"OBL-V006-2026-12","raised_at":"2027-01-15T12:00:00","raised_by":"TRUEUP",
 "reason_code":"NO_CONTRACTUAL_BASIS","variance_amount":2400.00,"tolerance_amount":525.40,
 "evidence_ids":["INV-V006-008","CTR-006"],"routed_to":"E001","routed_role":"CONTROLLER",
 "summary":"Invoice carries a $2,400.00 line, 'Year end expedite premium', with no supporting clause or correspondence.",
 "status":"OPEN","controller_decision":null}
```
No scripted inbox reply exists for this note, so it stays `OPEN` until Reset World / Reset Demo. No candidate policy, no replay, no Approve/Reject: `btn-approve-policy` and `btn-reject-policy` are never rendered; `ESCALATED`'s only enabled buttons are Reset World and Reset Demo. This absence is the deliverable: TrueUp declines to generalize from one unexplained dollar.

## 4. The three-minute judge-facing flow

Backbone is SCN-A end to end, closing with the SCN-B transfer proof. SCN-C is not in the timed path (its payoff is silence, not a state change) but is a 20-30 second closing beat or Q&A backup.

**GPF (Golden Path Fallback).** A mutated world never gets a cached answer. If any live call in a beat below stalls past 5 seconds or errors, the presenter says the fallback line, clicks `btn-reset-world`, and reruns `Run Close` on the override-free baseline world, the one whose `fixture_hash == BASELINE_FIXTURE_HASH` (DataForge increase 5 percent = baseline, still misses by $2,500.00). That world has a recording at `runtime/recorded/REC-<hash12>.jsonl`, keyed by the first 12 hex of its `world_hash`; the beat continues under the `RECORDED` badge instead of `LIVE`.

| # | Sec | Actor | Click | Screen shows | Spoken line | Fallback |
|---|---|---|---|---|---|---|
| 1 | 0-8 | presenter | none | `#clock-bar`: clock 2027-01-04T09:00, `fixture_hash` matches `BASELINE_FIXTURE_HASH`, playbook 1.0 | "Acme AI, reset to a pinned hash. Nothing here is scripted." | none |
| 2 | 8-14 | presenter | hands over laptop | `#lab-panel` open | "Pick a vendor, change one real fact about their contract." | none |
| 3 | 14-26 | judge | select V001, `CTL-DATAFORGE-INCREASE`, pick a percent | staged diff | "Your number changes the contract, not the invoice." | preset chips for 5/8/12 |
| 4 | 26-34 | (auto) | none | What Changed: `PS-001` and only `PS-001` on the visible side | "That's the only visible file that moves." | none |
| 5 | 34-40 | judge | `btn-apply-mutation` | new `world_hash` | "That just rebuilt a real PDF and the hidden invoice behind it." | GPF |
| 6 | 40-56 | presenter | `btn-run-close` | `#evidence-trail` shows the v1.0 plan and the refused related-document call; no pricing document opened | "Watch it pull the contract, the recent invoices, the AP queue, live. It never opens the pricing schedule." | GPF |
| 7 | 56-66 | presenter | none | workpaper: $50,000.00, `REVIEW_REQUIRED`, CONTROLLER | "Fifty thousand, straight off the Year One line." | none |
| 8 | 66-72 | presenter | `btn-approve-accrual` | `JE-ACR-V001-2026-12` posted | "A human signs off because fifty thousand clears the threshold." | none |
| 9 | 72-82 | presenter | `btn-advance-time` | real invoice lands, amount in red vs accrual | "One click forward, and the real bill lands. Not fifty thousand." | none |
| 10 | 82-88 | (auto) | none | miss highlighted, variance against tolerance | "That gap is math, not a guess." | none |
| 11 | 88-104 | presenter | `btn-investigate` | evidence trail: invoice -> contract -> related documents -> PS-001 with the quoted row | "It opens the pricing schedule that was sitting there the whole time." | GPF |
| 12 | 104-110 | (auto) | none | `PROCEDURE_GAP`, `EFFECTIVE_PRICE_NOT_RETRIEVED` | "It names exactly what it skipped." | GPF |
| 13 | 110-118 | (auto) | none | candidate `POL-0001`, no vendor id in the record | "Its fix names a contract feature. It never says DataForge." | GPF |
| 14 | 118-128 | presenter | `btn-run-replay` | replay: 20 obligations, changed 1, regressed 0, bias to zero | "Twenty past obligations, replayed live, right now. Nothing else moved." | none |
| 15 | 128-138 | judge | `btn-approve-policy` or `btn-reject-policy` | playbook badge 1.0 -> 1.1 | "Your call: approve it, or reject it and it forgets this happened." | none |
| 16 | 138-146 | judge | select V005, `CTL-PAGERLOOP-PRICE`, pick a percent, `btn-apply-mutation` | staged `VPN-005` diff | "Different vendor, different pricing shape: per seat, not flat." | none |
| 17 | 146-164 | presenter | `btn-run-transfer` | `#transfer-panel` split table, Frozen vs Learned side by side | "Same rule, new vendor: it blocks the guess and gets the right number." | GPF (learned arm only) |
| 18 | 164-176 | presenter | `btn-advance-time`; open `#audit-panel` | result and the audit line | "Every dollar traces to evidence, a policy version, a name." | none |
| 19 | 176-180 | presenter | none | (wrap) | "Reject instead, and it misses the same way, every time." | none |

Real judge choices: beats 3, 15 and 16 (the mutation value, Approve/Reject, and the PagerLoop price).

## 5. Sixty-second expo variant

SCN-A only, compressed, preset buttons instead of free entry, results revealed rather than narrated step by step. Same GPF rule; pre-armed at a 3 second timeout since there is no slack to wait.

| # | Sec | Actor | Click | Screen shows | Spoken line |
|---|---|---|---|---|---|
| 1 | 0-6 | presenter | none | clock-bar, hash pinned | "Live agent, real contract data, one pinned hash." |
| 2 | 6-16 | judge | preset chip "8 percent" then `btn-apply-mutation` | diff + new hash | "Pick the miss size." |
| 3 | 16-28 | presenter | `btn-run-close` then `btn-approve-accrual` | accrual $50,000.00, CONTROLLER | "It accrues fifty thousand off the order form." |
| 4 | 28-38 | presenter | `btn-advance-time` | invoice $54,000.00, variance card | "Real bill: fifty-four. A four-thousand-dollar miss." |
| 5 | 38-48 | presenter | `btn-investigate` (result pre-warmed) | root cause card, `POL-0001` scope | "It finds the missed pricing schedule and drafts a fix, no vendor name." |
| 6 | 48-58 | judge | `btn-approve-policy` | badge 1.0 -> 1.1 | "You approve it; it becomes company memory." |
| 7 | 58-60 | presenter | none | (wrap) | "Next vendor, same rule, no retraining." |

## 6. Pre-demo checklist

1. `POST /sim/reset/demo`; confirm response `fixture_hash == BASELINE_FIXTURE_HASH`.
2. `GET /sim/hash` and `GET /api/state`: confirm `world_hash` matches, playbook version `1.0`, badge `LIVE`.
3. Warm the LLM path once: run SCN-A live at baseline (DataForge increase 5 percent, no Apply Change needed) end to end through `Run Transfer Compare`, so `runtime/recorded/REC-<hash12>.jsonl` exists for `BASELINE_FIXTURE_HASH`. This file is the GPF safety net and is not cleared by Reset World or Reset Demo.
4. `POST /sim/reset/demo` again to return to `IDLE_BASELINE` with a clean `trueup_state.db` (the recording from step 3 survives; the run itself does not).
5. Stage a dry-run override for each of the three demo-path controls (`CTL-DATAFORGE-INCREASE`, `CTL-PAGERLOOP-PRICE`, `CTL-BRIGHTWORK-SURCHARGE`) with `POST /sim/overrides/stage`, confirm the diff preview renders in under 2s, then `DELETE /sim/overrides` to clear them unapplied.
6. One throwaway live model call (any beat-6-style evidence citation) to confirm API reachability before judges arrive.
7. Open `GET /` once, confirm `#clock-bar` shows the 12-hex `world_hash` / `BASELINE_FIXTURE_HASH` pair and the `LIVE`/`RECORDED` badge toggles correctly.
8. Confirm all twelve buttons in `00-decisions.md` section 1.3 render with the correct enabled/disabled state for `IDLE_BASELINE` per the state table in `02-state-machine-and-time.md`.
9. Leave live mode for the judge session; only switch to recorded/cached deliberately if GPF is invoked.

---

# 05 Weaknesses a Maximor judge will attack, and the smallest fixes

Deliverable 10. Written from the seat of a finance-automation engineer who has watched many "AI accountant" demos and called a cash-only point solution "very meh".
Every attack is aimed at a named part of the simplified design. Every fix is under 2 hours of build on top of the plan in `03-playbook-memory-and-api.md`. Nothing here changes the product spec. All data is synthetic; the company is Acme AI, Inc.

## 0. Arithmetic, computed once

| Quantity | Working | Result |
|---|---|---|
| SCN-A tolerance | `max(500.00, 0.02 x 50,000.00 = 1,000.00)` | 1,000.00 |
| SCN-A 8 percent variance | `50,000.00 x 1.08 = 54,000.00`; `54,000.00 - 50,000.00` | 4,000.00 |
| SCN-A 12 percent variance | `50,000.00 x 1.12 = 56,000.00`; `56,000.00 - 50,000.00` | 6,000.00 |
| SCN-B tolerance | `max(500.00, 0.02 x 12,000.00 = 240.00)` | 500.00 |
| SCN-B 15 percent frozen variance | `120 x 115.00 = 13,800.00`; `13,800.00 - 12,000.00` | 1,800.00 |
| Frozen January error, both `#transfer-panel` rows | `4,000.00 + 1,800.00` | 5,800.00 |
| Replay coverage | 1 touched / 20 replayed | 5 percent |
| POL-0001 breadth | 5 of 10 vendors match the predicates; 3 of the 4 triggered resolve `NO_PRICING_DOCUMENTS_ON_FILE` | 1 amount changed |
| True-up approver today | every true-up outside tolerance routes to the approver of its own accrual (`00` section 4), so 4,000.00 goes to E001 | already pinned, no fix needed |

## 1. Ranked attacks

| # | Attack, as the judge says it | Hits | Smallest fix | Cost |
|---|---|---|---|---|
| W01 | "Your v1.0 is a strawman you built so you could fix it." | `03` tool gateway, `CONTRACT_PRICE` evidence plan | Print the human rollforward the plan came from, next to the plan | 1 h |
| W02 | "The gateway learned, not the model. That is a feature flag." | `03` `evidence_plan_delta`, `00` 1.4 | Provenance card: model wrote / code checked, two columns | 1.5 h |
| W03 | "POL-0001 is just open-every-document, always." | `03` 2 predicates, `00` 1.7 | Print the cost of the breadth from the replay report | 1.5 h |
| W04 | "PagerLoop and DataForge are the same case." | `04` SCN-B, `00` 4 | Three more `#transfer-panel` rows: two matched and unchanged, one not matched | 1 h |
| W05 | "The LLM is decorative." | `03` 3 | Ablation card over the 20 replay obligations | 1.5 h |
| W06 | "One touched obligation out of twenty proves nothing." | `03` 8 replay report | Replay also over `erp/accrual_schedule_prior.csv` | 2 h |
| W07 | "Approval is a JSON field. I can be your Controller with curl." | `03` 5, `00` 1.6 | Role check with 403, approver name on the event, promotion rule printed | 1 h |
| W08 | "Your true-up lands in a closed period and no schedule shows it." | `02` 4 | `out_of_period` flag, rendered disclosure line, unadjusted-differences table | 1 h |

Ten and a half hours across the four existing tracks. If time runs out, cut in the order W06, W05, W08. W01 to W04 are never cut.

## 2. The attacks in full

### W01. The v1.0 baseline is a strawman

- **Attack.** "No close accountant accrues a December subscription without checking the pricing schedule. PS-001 has sat in the same contract folder since 2025-11-24. You wrote a baseline that refuses to open the next document so you would have a failure to fix."
- **Why it lands.** The `CONTRACT_PRICE` evidence plan in playbook 1.0 names the order form and nothing else, and the gateway refuses `list_related_documents` in CLOSE mode. The miss is a design choice written into `policies.json` before any model runs.
- **Smallest fix.** Render the provenance of the plan, not just the plan. `erp/accrual_schedule_prior.csv` holds the 2026-05 to 2026-10 rollforward that E004 prepared and E002 reviewed, and it accrues DataForge at the order form price of $50,000.00 every month. Print two lines in `#workpaper` beside the v1.0 evidence plan: the six human accruals and their source, and the sentence "this is the procedure the agent inherited". Add the same two lines to the audit packet.
- **Answer.** "That plan is the one this close team actually ran for six months, printed from their own rollforward. It was right six times and wrong on the seventh, which is exactly how procedure gaps reach production."

### W02. The tool gateway did the learning, not the model

- **Attack.** "Approve flips `list_related_documents` from refused to allowed. That is a feature flag with a signature page on it. Nothing in your model changed."
- **Why it lands.** The only mechanical difference between playbook 1.0 and 1.1 is `evidence_plan_delta.add_tools`, and the estimator, the verifier and the arithmetic are identical in both arms.
- **Smallest fix.** A provenance card in `#learning-panel`, two columns. Model wrote: the `PriceTerm` extracted from PS-001 with its verbatim quote, the root-cause label, the predicate set of the candidate, each with its `RUN-` id and the tool call that produced it. Code checked: the quote is a substring of the document text, the effective date covers the service period, the variance, the replay, the final amount.
- **Answer.** "The model reads the document and names the failure, code checks every claim and computes every dollar, and what the Controller signs is a retrieval step that a deterministic gateway then enforces on every vendor. That is the only shape of learning an auditor can sign."

### W03. POL-0001 is "open every document, always"

- **Attack.** "Two predicates, `spend_type = RECURRING` and `estimation_basis = CONTRACT_PRICE`. That is five of your ten vendors. The required evidence is: list the related documents. You did not learn a rule, you turned retrieval on for half the company."
- **Why it lands.** It is true by design. Of the 4 obligations the replay triggers, 3 return `NO_PRICING_DOCUMENTS_ON_FILE` and change nothing, so most of the matched population pays a tool call for no benefit.
- **Smallest fix.** Price the breadth instead of hiding it. `#learning-panel` prints, straight from the replay report: 10 feature matched, 4 triggered, 1 amount changed, 3 `NO_PRICING_DOCUMENTS_ON_FILE`, extra reviews 0, extra outreach 0, and the extra document calls per triggered obligation. Beneath it, one line naming the narrower candidate the replay rejects: a predicate on `price_label = "Contract Year 1"` matches DataForge and drops `OBL-V005-2027-01`, whose label is "Initial Term", so it wins December and loses January.
- **Answer.** "Broad on purpose. It costs one extra document call on five vendors, zero extra reviews and zero regressions, and the narrow version that names the vendor's own wording fails the very next month."

### W04. PagerLoop and DataForge are the same case

- **Attack.** "Both recurring, both contract price, both hide the new price one document away, both fixed by the same extra call. Transferring to a case you built to match your policy is not transfer."
- **Why it lands.** Both vendors match the same two predicates by construction. The differences that are real, `PER_SEAT_MONTH` against `PER_MONTH` and a `VENDOR_PRICE_NOTICE` filed 2027-01-20 against a `PRICING_SCHEDULE` filed 2025-11-24, are easy to miss on screen.
- **Smallest fix.** Show what the policy touched and did not touch, on the same panel. Three rows below PagerLoop: `OBL-V014-2027-01` and `OBL-V004-2027-01` match the predicates, resolve `NO_PRICING_DOCUMENTS_ON_FILE`, and book 22,500.00 and 18,000.00 in both arms; `OBL-V002-2027-01` does not match at all and books 30,000.00 in both arms. Print the learned arm's arithmetic on the PagerLoop row, `120 x 115.00 = 13,800.00`, with the seat count sourced from CTR-005 and the price from VPN-005.
- **Answer.** "One rule, a different document type, a different unit, and two vendors it matched and correctly left alone. A rule that only knew DataForge would have moved DataForge and nothing else."

### W05. The LLM is decorative

- **Attack.** "Estimator is code, verifier is code, replay is code, the amount is code. Delete the model, hard-code 'go read the pricing schedule', and this demo is identical."
- **Why it lands.** The policy set goes only to the deterministic verifier. The model's whole output is a `PriceTerm` extraction, a root-cause label chosen from two values, and a predicate set drawn from a six-field whitelist.
- **Smallest fix.** Pre-compute an ablation card for `#audit-panel` over the 20 replay obligations: model extraction against a regex on the pricing document against always taking the last table row. Report `PriceTerm` accuracy, verbatim-quote pass rate and document calls per obligation, frozen 1 against learned 3. Run once before the demo, store the JSON, render it.
- **Answer.** "The model reads documents and names the failure, code does every dollar, and the card shows both cheap substitutes pulling the wrong line out of PagerLoop's price notice."

### W06. Replay over twenty obligations proves nothing

- **Attack.** "Twenty replayed, one touched, nineteen unchanged. Your regression test is n equals one against a world your own generator produced. Of course it improves."
- **Why it lands.** The replay report says improved 1, regressed 0, unchanged 19, which is 5 percent of the set moving, and every row in it came from the same simulator.
- **Smallest fix.** Add the second denominator that already exists in the fixtures. Replay the candidate over `erp/accrual_schedule_prior.csv`, the 2026-05 to 2026-10 accruals E004 prepared and E002 reviewed, which carry accrued, actual and variance per vendor-month. No new fixture. The report prints both denominators with feature-matched, would-have-changed and regressed counts. DataForge sits inside Contract Year 1 for all six months, so the honest headline is no change and no regression against accruals a human team signed.
- **Answer.** "One changed number is the point. It also replayed over every accrual this team posted in the last six months and touched none of them."

### W07. Approval is a JSON field

- **Attack.** "Your approve call takes `actor: E001` in a request body. I can be your Controller with curl. And the policy sits at ACTIVE_PROVISIONAL forever, with ACTIVE and REVOKED in the enum and nothing driving them."
- **Why it lands.** `POST /api/policy/approve` checks that a string equals E001. The status enum in `00` 1.6 carries ACTIVE and REVOKED, and no beat in the demo reaches either.
- **Smallest fix.** No new endpoint and no new button. `#learning-panel` renders an approver picker seeded from `org_directory.json`; the server returns 403 for any actor whose role is not CONTROLLER and writes the approver name onto the `policy_events` row. After the transfer run, print the promotion rule with its evidence: the in-scope 2027-01 obligations and whether each landed inside tolerance, with the stated consequence that all inside promotes 1.1 to ACTIVE and any regression returns the active pointer to 1.0.
- **Answer.** "Only a Controller can sign it, the name is on the policy event, it stays provisional until January's invoices agree with it, and Reject puts the company back on 1.0 with no code change."

### W08. The true-up lands in a closed period and no schedule shows it

- **Attack.** "December closed at 2027-01-05T23:59:59. On 2027-01-12 you post 4,000.00 of December expense into January. Where is the out-of-period disclosure, and where is the summary of unadjusted differences my auditor asks for?"
- **Why it lands.** `JE-TRU-V001-2026-12` is dated at the invoice received date and nothing on the entry says it belongs to a closed period. Routing is already correct, the true-up goes to E001 who signed the accrual, but no schedule aggregates these adjustments.
- **Smallest fix.** Two workpaper additions. First, `TrueUpAdjustment` gains `out_of_period: true` and a rendered line: "prior-period adjustment; 2026-12 expense understated 4,000.00; recorded in 2027-01 because 2026-12 closed 2027-01-05T23:59:59". Second, `#audit-panel` gains a Summary of Unadjusted Differences table listing every out-of-period true-up in the period, signed, with a total. The reversal `JE-REV-V001-2026-12` dated 2027-01-01 is already correct and unchanged.
- **Answer.** "The miss lands in January as a labelled prior-period adjustment, signed by the same Controller who signed the accrual, and it sits on the unadjusted-differences schedule with everything else."
