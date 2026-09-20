# Close Engine (Jev-first rebuild) - shared contract

A deterministic month-end close engine with Jev-powered decision nodes and specialized workers.
This file is the contract every worker is built against. If code and this file disagree, fix one of them in the same commit.

```text
CODE   state machine, querying, exact matching, accounting rules, cutoff logic, formulas, journals, true-ups
JEV    semantic classification, ambiguous matching, contradiction detection, estimator routing,
       evidence sufficiency, outreach routing, confidence gating, root-cause classification
LLM    document text -> structured JSON, outreach message text, human-readable rule text
```

Rules that never bend:

- Only code writes state or produces a booked number. Jev never returns an amount. LLM arithmetic is re-evaluated by `safe_math.evaluate`.
- Workers never talk to each other. A handoff is `case.status` changing on the `CloseCase`; the engine schedules the next worker.
- Workers never see the future: every read of world data goes through `store.visible(rows, as_of)`.
- Only Evidence reads the world and the documents. Every later worker takes the Evidence db (plus the cases) as its only input; `company.json` is copied into the db table `company` (one row).
- `jev` and `llm` are injected arguments. No worker imports `TypeSafeClient` or the OpenAI SDK. No test touches the network.
- No worker built so far calls Jev. Evidence and Classification call the LLM (Opus 4.6); Detection and Invoice Lookup are pure rules. `jev.py` stays in the package, unused, for later workers.
- Deterministic first. A worker calls Jev only when its rules leave more than one well-defined possibility, or as an independent verifier of a rule result. Independent questions over the same state go in ONE `jev.ask` call.
- Every Jev/LLM/rule decision that moves a case is appended to `case["decision_log"]`.

## Layout

```text
startup/close/
  DESIGN.md
  requirements.txt      typesafe-sdk openai python-dotenv pytest
  __init__.py
  workspace.py          Workspace, period helpers
  store.py              world tables (read-only, time-gated) + db tables + state files
  case.py               CloseCase constructor, statuses, transition(), log_decision()
  policy.py             thresholds and gate()
  jev.py                Jev protocol, TypeSafeJev (real), answer normalisation, call log
  llm.py                bedrock_llm(prompt_name, variables) -> dict
  safe_math.py          evaluate("700000 / 25 * 31 * 0.02")
  events.py             append/read state/events.jsonl
  prompts/              *.md for the LLM
  world/                synthetic world (seeded JSON + documents/ + ground_truth/)
  evidence.py  detection.py  invoice_lookup.py  classifier.py
  estimation.py  rules.py  outreach.py  journal.py  settlement.py  learning.py
  engine.py             state machine + CLI (python -m close.engine close 2026-12)
  tests/                __init__.py fakes.py test_*.py
```

Run tests from `startup/`: `../.venv/bin/python -m pytest close/tests -q`. `startup/` has no `__init__.py`; `close/` and `close/tests/` do.
Do not touch `startup/system/`, `startup/minimal_data/`, or `output/`.

## Workspace, time, store

```python
@dataclass
class Workspace:
    world_dir: Path      # read-only synthetic world
    db_dir: Path         # canonical tables written by Evidence (git-ignored: startup/close/_run/db)
    state_dir: Path      # cases.json, outreach.json, rules.json, caches, logs (startup/close/_run/state)
    out_dir: Path        # close packages (startup/close/_run/packages)
    as_of: str           # simulated clock, ISO "YYYY-MM-DDTHH:MM:SSZ"
    @classmethod
    def default(cls, as_of: str) -> "Workspace"

period_bounds("2026-12") -> ("2026-12-01", "2026-12-31")
days_in(period) -> int
prev_periods(period, n) -> list[str]            # oldest first, excludes period
covers(start, end, period) -> bool              # None bound = open-ended
overlap_days(start, end, period) -> int

# store.py
world(ws, name) -> list[dict]                   # world/<name>.json filtered by visible()
world_raw(ws, name) -> list[dict]               # unfiltered; ONLY tests and ground-truth scoring may call it
visible(rows, as_of) -> list[dict]              # keep rows with row.get("available_at") is None or <= as_of
load_table / save_table(ws, name, rows)         # db_dir/<name>.json
upsert(rows, row, key: tuple[str, ...])
load_state(ws, name, default) / save_state(ws, name, obj)
```

`available_at` compares as strings after normalising a bare date `YYYY-MM-DD` to `YYYY-MM-DDT00:00:00Z`.

## Jev

```python
# jev.py  - questions are the SDK's own classes: from typesafe_sdk import Choice, Noul, Score
class Jev(Protocol):
    def ask(self, state: dict, questions: dict[str, Choice | Noul | Score], *, tag: str) -> dict[str, dict]: ...

# normalised answers (plain dicts, JSON-serialisable)
{"type": "choice", "choice": "RECURRING_VARIABLE", "confidence": 0.86, "probabilities": {"RECURRING_VARIABLE": 0.86, ...}}
{"type": "noul",   "noul": 0.93}
{"type": "score",  "score": 0.43, "confidence": 0.71, "probabilities": {"0": 0.2, ...}}   # score normalised to 0..1

class TypeSafeJev:            # real client; TYPESAFE_API_KEY from repo-root .env; model jev-latest
    def __init__(self, ws, client=None)
    def ask(...)              # one client.system_one call; appends {at, tag, state_hash, questions, answers, ms} to state/jev_calls.jsonl
class JevUnavailable(Exception)   # raised on any TypeSafeError; callers gate to REVIEW, never guess
```

SDK facts (typesafe-sdk 0.7.0, verified from source): `TypeSafeClient().system_one(state=..., questions={...})` ->
`response.answers[id]` with `.choice/.confidence/.probabilities`, `.noul`, `.score/.confidence/.probabilities/.legend`.
`Choice(instructions=..., criteria={"OPTION": "definition or None", ...})`, `Noul(instructions=...)`, `Score(instructions=..., criteria=[level0, level1, ...])`.
Score returns a probability-weighted level index; divide by `len(criteria) - 1` to normalise. ~32k tokens per call. Questions in one call are independent.
Question ids are not sent to the model: put the full meaning in `instructions`, reference state with backticked paths (`` `po_line.Line_Description` ``), always include a no-match option ("OTHER" / "NONE") in a Choice.

`tests/fakes.py::FakeJev(answers)`: `answers` maps question id -> normalised answer dict, or -> `callable(state) -> answer`. Missing id raises `KeyError` (tests must script every question). Records `.calls = [(tag, state, questions)]`.

## Policy

```python
ACT = 0.90        # act automatically
CAUTION = 0.50    # below this: do not act
NOUL_YES = 0.80; NOUL_NO = 0.20
gate(confidence, amount=None, materiality=None) -> "ACT" | "VERIFY" | "REVIEW"
   # >= ACT -> ACT; >= CAUTION -> VERIFY; else REVIEW. If amount >= materiality, VERIFY is promoted to REVIEW.
```

Materiality comes from `world/company.json`.

## LLM

`llm: Callable[[str, dict], dict]` = `(prompt_name, variables) -> parsed JSON`. Real impl: OpenAI SDK against the Bedrock endpoint in `.env`
(`OPENAI_BASE_URL`, `OPENAI_API_KEY`, model `us.anthropic.claude-opus-4-6-v1` via the native Bedrock Converse API with the same key; env `MODEL_ID` overrides, non-Anthropic ids use the OpenAI-compatible endpoint), temperature 0, renders `prompts/<name>.md`
replacing `{{KEY}}`, extracts the first balanced JSON object, one retry, then `LLMError`.
`FakeLLM(**by_prompt)`: value is a dict, or `callable(variables) -> dict`. Records `.calls`.

## World (synthetic, deterministic, time-gated)

Company: Orbit Labs, Inc. (entity `ORBIT-US`). Periods 2026-09..2026-12 are in the world; 2026-12 is the demo close.
Close run `as_of = 2027-01-05T12:00:00Z`. Settlement run `as_of = 2027-01-25T12:00:00Z`.
Every row carries `available_at`. Economic dates are separate fields (`service_period`, `received_date`, `transaction_date`, ...).

| File | Row shape |
| --- | --- |
| `company.json` | object: `entity_id, name, materiality, de_minimis, close_calendar{period:{period_end, outreach_deadline, close_cutoff}}, gl_accounts{code:name}, accrual_liability_account` |
| `vendors.json` | `vendor_id, vendor_name, aliases[]` |
| `po_headers.json` | `po_number, vendor_id, entity_id, order_type(NB/FO), validity_start, validity_end, requester, cost_center_owner, status, total_amount, created_date` |
| `po_lines.json` | `po_line_id, po_number, item_category("", P, B, E), contract_id, pricing_model(FIXED/UNIT/USAGE/TM/LIMIT), billing_frequency(MONTHLY/QUARTERLY/MILESTONE/NONE), gr_required, service_entry_required, gl_account, quantity_ordered, unit_price, overall_limit, expected_value, service_start, service_end, delivery_date, line_description, modified_at` |
| `goods_receipts.json` | `gr_id, po_line_id, received_date, quantity` |
| `activity.json` | usage / timesheets / delivery reports: `activity_id, po_line_id, kind(USAGE/TIMESHEET/DELIVERY), service_period, coverage_start, coverage_end, quantity, value, replaces` |
| `invoices.json` | `invoice_id, vendor_id, entity_id, po_number, po_line_id (may be null), invoice_number, service_period, amount, currency, status(QUEUE/POSTED), received_date, posted_at` |
| `card_transactions.json` | `transaction_id, program, merchant, cardholder, entity_id, transaction_date, authorized_amount, settled_amount, status(PENDING/CLEARED/REVERSED), settled_at, gl_account, erp_exported_at` |
| `gl.json` | what is already booked: `entry_id, period, source_ref, gl_account, amount` |
| `prior_accruals.json` | accruals from earlier closes |
| `org_directory.json` | `person, role, manager, email`; escalation is requester -> cost_center_owner -> "Procurement" / "AP" / "Controller" |
| `outreach_responses.json` | scripted replies: `response_id, case_key (po_line_id), reason, responder, text, facts{...}` with `available_at` (some before cutoff, some after) |
| `documents/<DOC-ID>.txt` + `documents/index.json` | raw evidence text (contracts, amendments, termination notices, usage reports); index rows `doc_id, file, available_at`. Evidence turns these into db tables. |
| `ground_truth/expected.json` | per case: `case_key, scenario, expected_status, expected_amount, expected_estimator, expected_flags[], actual_amount (later invoice), expected_root_cause`. Workers never read it. |

Scenarios the world must contain for the 2026-12 close (one PO line or card group each; keep the Orbit Labs numbers where given):

| # | case_key | Scenario | Expected path |
| --- | --- | --- | --- |
| 1 | PO-001-001 Mintlify | Fixed SaaS, no Dec invoice, contract V1 $1,200 superseded by V2 $1,400 from Dec 1, PO line still 1,200 | contract schedule estimator -> 1,400, flag DATA_MISMATCH, outreach to Procurement; later invoice 1,400 |
| 2 | PO-002-001 OpenAI | Usage $0.02/unit; Sep 710k, Oct 840k, Nov 775k units invoiced; Dec usage report covers Dec 1-25 only (700,000 units) | sufficiency low -> outreach MISSING_USAGE; reply misses cutoff -> forced estimate; final report 930,000 units -> actual 18,600 -> learning |
| 3 | PO-003-001 ASUS | 25 laptops @ 1,600, 20 received Dec 28, no invoice | goods receipt estimator -> 32,000 |
| 4 | CAMPAIGN-004-001 Meta | Limit 30,000, delivery report 24,700 | delivery estimator -> 24,700 |
| 5 | PO-005-001 Twilio | NB standard line, qty 1 x 5,000, description "Monthly SMS usage charges billed per message sent" | rules ONE_TIME_FIXED vs Jev RECURRING_VARIABLE -> CONTRADICTION -> review |
| 6 | PO-006-001 rent | Fixed monthly 25,000, Dec invoice POSTED | invoice hit -> INVOICED, no accrual |
| 7 | PO-007-001 SaaS | Fixed monthly 3,000, Dec invoice in AP QUEUE (not posted) | accrue the known invoice amount, estimator INVOICE_IN_QUEUE |
| 8 | PO-008-001 monitors | 40 @ 450, 40 received, invoice POSTED for 24 units (10,800) | partial invoice -> accrue remaining 7,200 |
| 9 | PO-009-001 consulting | T&M $200/h, approved Dec timesheets 86h, no invoice | timesheet x rate -> 17,200 |
| 10 | PO-010-001 terminated | Fixed monthly 2,500, termination notice effective Nov 30 | NO_ACCRUAL |
| 11 | PO-011-001 cloud | Usage, NO Dec usage data at all; owner replies BEFORE cutoff with the figure | outreach -> answered -> re-estimate from reply |
| 12 | PO-012-001 duplicate | Two invoices same vendor/amount/period, different invoice numbers | lookup DUPLICATE_CANDIDATE -> review |
| 13 | PO-013-001 ambiguous | Vendor sends one invoice without PO reference; two open lines of that vendor plausible | Jev chooses candidate; low confidence -> AMBIGUOUS_MATCH |
| 14 | CARD/Ramp | Card transactions: cleared+exported (already in GL), cleared NOT exported, pending, pending whose later settled amount differs, one dated Jan | accrue cleared-unexported + pending at authorized amount; Jan excluded; pending delta becomes a true-up |

## CloseCase

`state/cases.json` is a list of cases. Helpers live in `case.py`.

```json
{"case_id": "2026-12/PO-002-001", "case_key": "PO-002-001", "period": "2026-12", "as_of": "2027-01-05T12:00:00Z",
 "kind": "PO_LINE", "entity_id": "ORBIT-US", "vendor_id": "V002", "vendor_name": "OpenAI", "po_line_id": "PO-002-001",
 "status": "DETECTED",
 "obligation": {"source_type": "PO", "source_id": "PO-002-001", "recognition_basis": "USAGE", "service_period_start": "2026-12-01", "service_period_end": "2026-12-31", "reasons": ["validity covers period"]},
 "invoice_match": null, "classification": null, "estimate": null, "outreach": null, "journal": null, "settlement": null,
 "flags": [], "evidence_refs": [], "decision_log": []}
```

`kind` is `PO_LINE`, `CARD` (`case_key` `CARD/<program>`) or `DIRECT_AP` (`case_key` `AP/<invoice_id>`: a non-PO invoice from a vendor with no open PO line).
Card obligations also carry `settled_unbooked`, `pending`, `already_booked`; non-PO spend at or above `company.de_minimis` is flagged `ABOVE_DE_MINIMIS`.
`recognition_basis`: `CONTRACT_SCHEDULE | GOODS_RECEIPT | SERVICE_ENTRY | TIMESHEET | USAGE | DELIVERY | CARD | INVOICE`.
Detection flags: `TERMINATED`, `TERMINATED_IN_PERIOD`, `EXPIRED_AUTHORIZATION`, `OBLIGATION_UNCERTAIN`, `ABOVE_DE_MINIMIS`.

Statuses and legal transitions (`case.transition(case, new_status, worker, why)` raises `IllegalTransition` otherwise):

```text
DETECTED          -> ENRICHED
ENRICHED          -> INVOICED | ESTIMATE_REQUIRED | NO_ACCRUAL | REVIEW
ESTIMATE_REQUIRED -> ESTIMATED | OUTREACH_PENDING | REVIEW
OUTREACH_PENDING  -> ESTIMATE_REQUIRED (reply arrived) | FORCED_ESTIMATE (cutoff passed)
FORCED_ESTIMATE   -> ESTIMATED
ESTIMATED         -> JOURNALED | REVIEW
REVIEW            -> ESTIMATE_REQUIRED | JOURNALED | NO_ACCRUAL      (human resolution; demo auto-resolves with columns-win)
INVOICED, NO_ACCRUAL, JOURNALED -> CLOSED
CLOSED            -> SETTLED            (only cases that carried an accrual)
SETTLED           -> LEARNED
```

Sub-objects (each owned by exactly one worker):

```json
"invoice_match": {"result": "NO_INVOICE|INVOICE_IN_QUEUE|PARTIAL_INVOICE|FULL_INVOICE|DUPLICATE_CANDIDATE|AMBIGUOUS_MATCH", "invoice_ids": [], "invoiced_amount": 0.0, "candidates": [], "jev": null}
"classification": {"rules": "ONE_TIME_FIXED", "rules_why": "...", "model": "RECURRING_VARIABLE", "model_confidence": 0.86, "agree": false, "contradictions": [], "final": "ONE_TIME_FIXED", "suggested": "RECURRING_VARIABLE", "cache_hit": false}
"estimate": {"estimator": "TRAILING_AVERAGE", "routed_by": "RULE|JEV", "amount": 15500.0, "calculation": "(14200 + 16800 + 15500) / 3", "inputs": {}, "sufficiency": 0.43, "plausibility": 0.9, "rules_applied": [], "forced": true, "missing": "usage for 2026-12-26..31"}
"outreach": {"tickets": ["T-0001"]}
"journal": {"entry_id": "JE-2026-12-0007", "lines": [{"account": "610200", "debit": 15500.0, "credit": 0.0}, {"account": "210500", "debit": 0.0, "credit": 15500.0}], "reverses_on": "2027-01-01"}
"settlement": {"actual": 18600.0, "accrued": 15500.0, "true_up": 3100.0, "settled_by": ["INV-..."], "root_cause": null, "rule_id": null}
```

Categories: `RECURRING_FIXED | RECURRING_VARIABLE | ONE_TIME_FIXED | ONE_TIME_VARIABLE | NON_PO`.
Estimators: `CONTRACT_SCHEDULE | GOODS_RECEIPT | SERVICE_ENTRY | TIMESHEET_X_RATE | USAGE_X_RATE | DELIVERY_REPORT | TRAILING_AVERAGE | INVOICE_IN_QUEUE | CARD_TRANSACTIONS | NO_ACCRUAL`.
Decision log entry: `{"at": ws.as_of, "worker": "classifier", "kind": "RULE|JEV|LLM", "question": "...", "answer": ..., "confidence": 0.86, "action": "flag CONTRADICTION"}`.
Money is rounded to 2 decimals when stored.

## Workers (built one by one, each `run(ws, ..., period) -> list[case]`, idempotent)

1. `evidence.run(ws, llm, period)` - canonicalisation. Copies the visible feeds into the db and, for each document in the period's folder: LLM `extract` -> record; code checks (known vendor, resolvable PO line, required fields) -> `documents` row with `quality: OK|NEEDS_REVIEW`; OK records go to `contracts`, `terminations`, `activity`, `goods_receipts`, `invoices`, stamped with `available_at`. Hash-cached per document. No Jev.
2. `detection.run(ws, period)` - pure rules, and its ONLY input is the two purchase tables Evidence wrote (`po_headers`, `po_lines`; `po_lines` carries `quantity_received`, kept in step with goods receipts by Evidence, and `quantity_billed`). Open/Approved PO; goods lines owed when `quantity_received > quantity_billed`; every other line owed when the PO validity or the line service window covers the period. Creates `DETECTED` cases; keeps CLOSED+ cases untouched. No Jev, no card or direct-AP detection.
3. `invoice_lookup.run(ws, period)` - input: the period's DETECTED cases + the Evidence tables `invoices` (status `POSTED` = on the AP, `QUEUE` = received, not booked) and `po_lines`. Exact match on PO line + service period (goods lines: every invoice of the line up to the period). Results `NO_INVOICE | INVOICE_IN_QUEUE | FULL_INVOICE | PARTIAL_INVOICE (goods: invoiced < received x unit price) | DUPLICATE_CANDIDATE | AMBIGUOUS_MATCH`. Pure rules, no Jev: an invoice with no PO line whose vendor has several detected lines -> `AMBIGUOUS_MATCH`, never guessed. Never rewrites the invoices table. No email intake.
4. `classifier.run(ws, llm, period)` - input: the period's DETECTED cases + `po_headers` + `po_lines`. Rule tree: FO + limit item (B/E) + validity -> RECURRING_VARIABLE; NB + limit item -> ONE_TIME_VARIABLE; service item (P) or contract, not goods-receipt based -> RECURRING_FIXED; NB + standard item with quantity and unit price -> ONE_TIME_FIXED; else no rule fits. Separate column contradiction checks. The LLM (prompt `read_description`) reads `line_description` alone and returns `{category, confidence}`, cached by sha256 of the description text. Columns win; confident disagreement -> `CLASSIFICATION_MISMATCH` with the model's category as `suggested`; no rule fits -> the model decides only at ACT confidence, else `CLASSIFICATION_UNKNOWN`. After 3 and 4 the engine sets `ENRICHED` and resolves.
5. `estimation.run(ws, llm, period)` - input: the period's cases (with `invoice_match` + `classification`), the Evidence tables, and `state/improvements.md`. Resolves each DETECTED case: invoice in queue / on AP -> `INVOICED` (not estimated); duplicate / ambiguous / no category -> `REVIEW`; otherwise `ESTIMATE_REQUIRED`. CODE base formula by category (per `startup/MONTHLY_WORKFLOW.md`): RECURRING_FIXED copy PO `unit_price`; RECURRING_VARIABLE full-period usage x contract unit rate, else forced estimate = average of the last three invoices, never below the partial report; ONE_TIME_FIXED `unit_price x (received - billed)`; ONE_TIME_VARIABLE delivered value - billed, never the cap. MODEL (prompt `apply_improvements`) only when `improvements.md` has `[ACTIVE]` lessons for the category; CODE re-evaluates the arithmetic with `safe_math`, rejects numbers not present in the facts and lessons that are not active; a reported mismatch flags `DATA_MISMATCH`. Amount -> `ESTIMATED` (flag `FORCED_ESTIMATE` when incomplete); no amount -> `OUTREACH_PENDING` (flag `MISSING_DATA`). No Jev.
6. `outreach.run(ws, jev, llm, period)` - tickets in `state/outreach.json`; Jev: missing-information type, contact role, urgency; LLM writes the message; reads scripted replies visible at `as_of`; reply -> `ESTIMATE_REQUIRED`; past `outreach_deadline` -> `FORCED_ESTIMATE`.
7. `journal.run(ws, period)` - pure code: balanced accrual entries with auto-reversal, close package, `CLOSED`.
8. `settlement.run(ws, jev, period)` - at a later `as_of`: match newly visible invoices / final reports to CLOSED accrued cases, compute true-up, `SETTLED`.
9. `learning.run(ws, jev, llm, period)` - Jev root-cause Choice; LLM drafts rule text; code backtests on prior periods; rule saved `DRAFT` in `state/rules.json` (+ rendered `improvements.md`); only `approve(rule_id)` makes it `ACTIVE`. `LEARNED`.
10. `engine.py` - the state machine: `run_close(ws, jev, llm, period)`, `run_settlement(...)`, CLI, and a demo printer that surfaces the Jev moments.
