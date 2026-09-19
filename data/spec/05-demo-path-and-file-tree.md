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
