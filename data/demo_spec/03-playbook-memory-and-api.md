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
