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
