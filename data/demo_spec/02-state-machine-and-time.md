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
