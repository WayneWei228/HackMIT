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
