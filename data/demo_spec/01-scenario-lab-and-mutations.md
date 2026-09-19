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
