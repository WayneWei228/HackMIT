# Monthly Close System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Work test-first. This plan fixes file boundaries, exact interfaces, data shapes, and the assertions each test must make; the implementer writes the code.

**Goal:** Build the seven-agent month-end accrual system described in the spec, runnable per month from the CLI and from a local web UI.

**Architecture:** A Python package `startup/system/`. Every agent is a module with a `run(ws, model, period)`-style function that reads and writes JSON tables through `store.py`. The LLM is injected as a callable, so every test runs with a fake model and no network. A FastAPI server wraps the same functions for a single static HTML page.

**Tech Stack:** Python 3.11+, `openai` SDK against the Bedrock OpenAI-compatible endpoint, FastAPI + uvicorn, pytest, `pdftotext` (already installed), vanilla HTML/CSS/JS.

**Spec:** `startup/MONTHLY_WORKFLOW.md`. Read it before any task.

## Global Constraints

- Only `CODE` writes state or produces a booked number. Model output is parsed, validated, and any arithmetic is re-evaluated by `safe_math.evaluate`.
- Agents never import `model.bedrock_model` directly; they receive `model: Callable[[str, dict], dict]` as an argument.
- No test may touch the network or the real `startup/db`, `startup/state`, `startup/close_packages`. Tests build a `Workspace` on `tmp_path`.
- Categories are exactly `RECURRING_FIXED`, `RECURRING_VARIABLE`, `ONE_TIME_FIXED`, `ONE_TIME_VARIABLE`. Case states are exactly `OPEN` (inside a run only), `INVOICED`, `ACCRUED`, `ESTIMATED`, `SETTLED`. Ticket states are `OPEN`, `ANSWERED`, `EXPIRED`.
- Money is rounded to 2 decimals when stored. Dates are ISO strings (`YYYY-MM-DD`); periods are `YYYY-MM`.
- The Bedrock key is read from the git-ignored `.env` at the repo root. Never print it, never commit it.
- Do not modify anything under `startup/minimal_data/` or `output/`. Those hold uncommitted fixture work that belongs to the user.
- Python env: `uv venv .venv && uv pip install --python .venv/bin/python -r startup/system/requirements.txt`. Run tests with `cd startup && ../.venv/bin/python -m pytest system/tests -q`. `startup/` must not contain an `__init__.py`; `startup/system/` and `startup/system/tests/` must.
- Do not run `git commit`. The coordinator commits after each wave.

## File structure

```text
startup/system/
  requirements.txt        openai fastapi uvicorn pytest httpx python-dotenv
  __init__.py
  workspace.py            Workspace dataclass, period helpers
  store.py                JSON tables and state files
  events.py               append/read state/events.jsonl
  safe_math.py            evaluate("700000 / 25 * 31 * 0.02") safely
  model.py                bedrock_model(prompt_name, variables) -> dict
  prompts/                extract.md read_description.md apply_improvements.md root_cause.md
  seed/                   vendors.json po_headers.json po_lines.json card_statements.json
  evidence.py             Evidence agent
  invoice_lookup.py       find_invoice, settle (Invoice Lookup agent)
  detection.py            Detection agent
  classifier.py           Classifier agent
  improvements.py         parse / append / approve improvements.md
  estimation.py           Estimation agent
  outreach.py             Outreach agent
  learning.py             Learning agent
  report.py               close package writer
  run_month.py            month-end orchestration, snapshots, resets, CLI
  run_lookup.py           always-on orchestration, CLI
  server.py               FastAPI app
  ui/index.html           the single page
  tests/                  __init__.py, fakes.py, test_*.py
```

## Shared shapes (every task relies on these)

```python
# workspace.py
@dataclass
class Workspace:
    pdf_root: Path        # default <repo>/output/pdf/startup_minimal_data
    seed_dir: Path        # default startup/system/seed
    db_dir: Path          # default startup/db
    state_dir: Path       # default startup/state
    packages_dir: Path    # default startup/close_packages
    @classmethod
    def default(cls) -> "Workspace": ...
def period_bounds(period: str) -> tuple[str, str]      # ("2026-12-01", "2026-12-31")
def days_in(period: str) -> int
def prev_periods(period: str, n: int) -> list[str]     # oldest first, excludes `period`
def covers(start: str | None, end: str | None, period: str) -> bool   # None = open-ended; any overlap with the month

# store.py
TABLES = ["vendors", "contracts", "po_headers", "po_lines", "ap_invoices", "card_statements", "activity", "documents"]
def load_table(ws, name: str) -> list[dict]            # [] when the file is missing
def save_table(ws, name: str, rows: list[dict]) -> None
def upsert(rows: list[dict], row: dict, key: tuple[str, ...]) -> None   # in place
def load_state(ws, name: str, default)                 # name like "ledger.json"
def save_state(ws, name: str, obj) -> None

# events.py
def log(ws, agent: str, step: int, message: str, period: str | None = None) -> None
def read(ws, since: int = 0) -> list[dict]             # each: {"n", "ts", "agent", "step", "period", "message"}

# safe_math.py
def evaluate(expr: str) -> float    # numbers, + - * / ( ) only; commas and $ stripped; raises ValueError otherwise

Model = Callable[[str, dict], dict]   # (prompt_name, variables) -> parsed JSON
```

Table row keys: `vendors` `Vendor_ID`; `contracts` (`Contract_ID`, `Version`); `po_headers` `PO_Number`; `po_lines` `PO_Line_ID`; `ap_invoices` `Invoice_ID`; `card_statements` (`Program`, `Period`); `activity` `Document_ID`; `documents` `Document_ID`. Column names are exactly those in the spec's Databases table, plus: `vendors` = `{Vendor_ID, Vendor_Name}`; `documents` = `{Document_ID, File, Hash, Type, Vendor_ID, Service_Period, Facts}`; `activity` adds `Replaced_By` (null until superseded) and `Vendor_ID`.

Case (one element of `state/ledger.json`):

```json
{"case_id": "2026-12/PO-002-001", "period": "2026-12", "kind": "PO_LINE",
 "po_line_id": "PO-002-001", "po_number": "PO-002", "vendor_id": "V002", "vendor_name": "OpenAI",
 "state": "ESTIMATED", "category": "RECURRING_VARIABLE",
 "classification": {"columns": "RECURRING_VARIABLE", "model": "RECURRING_VARIABLE", "confidence": 0.93, "contradictions": []},
 "amount": 15500.0, "calculation": "(14200 + 16800 + 15500) / 3", "complete": false,
 "missing": "usage for 2026-12-26 to 2026-12-31",
 "evidence": ["USG-OPENAI-DEC"], "lessons_applied": [], "explanation": "",
 "settlement": null}
```

Card cases use `"kind": "CARD"`, `case_id` `"<period>/CARD/<Program>"`, `category` `"NON_PO"`. `settlement` when set: `{"actual", "variance", "settled_by", "root_cause", "lesson_id"}`.

Ticket (one element of `state/outreach.json`):

```json
{"ticket_id": "T-0001", "case_id": "2026-12/PO-002-001", "period": "2026-12", "reason": "MISSING_DATA",
 "level": 1, "to": "dana.kim", "chain": ["dana.kim", "raj.patel", "Procurement"],
 "question": "...", "suggested": null, "state": "OPEN", "runs_seen": 1}
```

Extraction record (what the `extract` prompt returns; all keys present, unknown = null):

```json
{"document_type": "CONTRACT|CONTRACT_AMENDMENT|INVOICE|PURCHASE_ORDER|CAMPAIGN_ORDER|GOODS_RECEIPT|USAGE_REPORT|DELIVERY_REPORT|REPLY",
 "vendor_name": "", "service_period": "YYYY-MM", "amount": 0, "quantity": 0, "unit_rate": 0, "monthly_fee": 0,
 "effective_date": "", "term_start": "", "term_end": "", "coverage_start": "", "coverage_end": "",
 "received_quantity": 0, "delivered_amount": 0, "replaces": "", "contract_id": "", "po_number": ""}
```

`Document_ID` is never taken from the model: it is the file stem with a leading `ISSUE-` removed (`ISSUE-USG-OPENAI-DEC.pdf` -> `USG-OPENAI-DEC`).

## Seed rows (Task 1 writes these files verbatim)

`vendors.json`: V001 Mintlify, V002 OpenAI, V003 ASUS, V004 Meta, V005 Twilio.

`po_headers.json`:

| PO_Number | Vendor_ID | Order_Type | Validity_Start | Validity_End | Requester | Cost_Center_Owner | Created_Date | Status | Total_Amount |
|---|---|---|---|---|---|---|---|---|---|
| PO-001 | V001 | FO | 2026-09-01 | 2027-08-31 | sam.lee | priya.shah | 2026-08-25 | Open | 14400 |
| PO-002 | V002 | FO | 2026-09-01 | 2027-08-31 | dana.kim | raj.patel | 2026-08-25 | Open | 300000 |
| PO-003 | V003 | NB | null | null | alex.chen | priya.shah | 2026-12-10 | Open | 40000 |
| CAMPAIGN-004 | V004 | NB | null | null | maria.gomez | tom.baker | 2026-12-01 | Open | 30000 |
| PO-005 | V005 | NB | null | null | dana.kim | raj.patel | 2026-12-03 | Open | 5000 |

`po_lines.json` (`PO_Line_ID` = `<PO_Number>-001`; `Quantity_Billed` 0 everywhere):

| PO | Item_Category | Contract_ID | GR_Based_IV | GL | Quantity_Ordered | Unit_Price | Quantity_Received | Line_Description |
|---|---|---|---|---|---|---|---|---|
| PO-001 | P | CTR-001 | false | 610200 | null | 1200 | null | Team documentation platform subscription, billed monthly |
| PO-002 | B | CTR-002 | false | 610300 | null | 25000 | null | API usage, billed monthly on measured units, monthly limit |
| PO-003 | "" | null | true | 150100 | 25 | 1600 | 0 | Laptop packages for new engineers, one shipment |
| CAMPAIGN-004 | B | null | false | 620100 | null | 30000 | null | Product-launch advertising campaign, charged on delivery up to budget |
| PO-005 | "" | null | true | 610400 | 1 | 5000 | 1 | Monthly SMS usage charges billed per message sent |

PO-005 is the planted classification disagreement: its columns say `ONE_TIME_FIXED`, its description reads as recurring variable.

`card_statements.json`: `{"Program": "Ramp", "Period": "2026-12", "Settled_Balance": 8450.25, "Pending_Balance": 1210.00}`.

---

## Wave A

### Task 1: Foundations

**Files:** Create `requirements.txt`, `__init__.py`, `workspace.py`, `store.py`, `events.py`, `safe_math.py`, `seed/*.json`, `tests/__init__.py`, `tests/test_foundations.py`. Append `startup/db/`, `startup/state/`, `startup/close_packages/` to the repo `.gitignore`. Create the venv.

**Produces:** everything under "Shared shapes" for `workspace`, `store`, `events`, `safe_math`, and the seed files.

Tests must assert:
- `period_bounds("2026-12") == ("2026-12-01", "2026-12-31")`; `period_bounds("2027-02")[1] == "2027-02-28"`; `days_in("2026-12") == 31`.
- `prev_periods("2027-01", 3) == ["2026-10", "2026-11", "2026-12"]`.
- `covers("2026-09-01", "2027-08-31", "2026-12")` true; `covers("2026-12-01", None, "2026-11")` false; `covers(None, "2026-11-30", "2026-12")` false; `covers("2026-12-15", "2026-12-20", "2026-12")` true.
- `load_table` on a missing file returns `[]`; save then load round-trips; `upsert` replaces a row with the same key and appends a new one; composite keys work.
- `events.log` twice then `events.read(ws, since=1)` returns only the second, with `n == 2`.
- `evaluate("700000 / 25 * 31 * 0.02") == 17360.0`; `evaluate("(14200 + 16800 + 15500) / 3") == 15500.0`; `evaluate("$1,600 * 20") == 32000.0`; `evaluate("__import__('os')")` and `evaluate("2 ** 8")` raise `ValueError`.
- The seed files load as JSON and contain 5 headers, 5 lines, 5 vendors, 1 card statement, with the values in the tables above.

---

## Wave B (four tasks, disjoint files, may run in parallel after Task 1)

### Task 2: Model client and Evidence agent

**Files:** Create `model.py`, `prompts/extract.md`, `evidence.py`, `tests/fakes.py`, `tests/test_evidence.py`.

**Produces:**

```python
# model.py
def bedrock_model(prompt_name: str, variables: dict) -> dict
    # loads .env from the repo root (python-dotenv), reads prompts/<prompt_name>.md, replaces each {{KEY}} with
    # variables[KEY] (dicts/lists are json.dumps'ed), calls OpenAI().chat.completions.create(model=os.getenv("MODEL_ID",
    # "openai.gpt-oss-120b"), temperature=0), extracts the first {...} JSON object from the reply, retries once on
    # a parse failure, then raises ModelError.
def extract_json(text: str) -> dict        # pure; tested

# evidence.py
def document_id(path: Path) -> str
def pull_seed(ws, period: str) -> None
    # vendors: all. po_headers with Created_Date[:7] <= period, and their lines. card_statements with Period == period.
    # Insert only when the key is absent, so receipts already applied to po_lines survive a re-run.
def ingest(ws, model, period: str, files: list[Path]) -> list[dict]
    # For each file whose sha256 is not in `documents`: text = pdftotext -layout (or read_text for .txt);
    # facts = cached extraction from state/extract_cache.json keyed by hash, else model("extract", {"DOCUMENT": text});
    # apply(facts); add the documents row; events.log one line per document. Returns the new documents rows.
def run(ws, model, period: str) -> list[dict]
    # pull_seed, then ingest sorted(pdf_root/reference/*.pdf) + sorted(pdf_root/<period>/*.pdf) + sorted(pdf_root/<period>/replies/*.txt)
def ingest_afterclose(ws, model, period: str) -> list[dict]     # pdf_root/<period>/afterclose/*.pdf
```

How `apply` maps a record (vendor resolved by case-insensitive `vendor_name` against `vendors`; PO line resolved by `po_number` if it names a header, else the vendor's only line; unresolved -> documents row only, `events.log` a warning):

| document_type | Effect |
|---|---|
| CONTRACT | `contracts` row: `Contract_ID` = `contract_id` or the Document_ID, `Version` 1, `Monthly_Rate` = `monthly_fee`, `Unit_Rate` = `unit_rate`, `Effective_Start` = `term_start` or first day of `period`, `Effective_End` = `term_end`, `Status` "Active" |
| CONTRACT_AMENDMENT | Find the vendor's latest contract version. Set its `Effective_End` to the day before `effective_date` and `Status` "Superseded". Add `Version`+1 with the new `Monthly_Rate`/`Unit_Rate` (fall back to the old value when null), `Effective_Start` = `effective_date`, `Effective_End` = the old end, `Status` "Active" |
| INVOICE | `ap_invoices` row: `Invoice_ID` = Document_ID, `Vendor_ID`, `PO_Line_ID`, `Service_Period`, `Amount`, `Received_Date` = today |
| GOODS_RECEIPT | set that line's `Quantity_Received` = `received_quantity` |
| USAGE_REPORT, DELIVERY_REPORT | `activity` row with `Quantity` = `quantity`, `Value` = `delivered_amount`, coverage dates (DELIVERY_REPORT with null coverage -> the whole `service_period`), `Replaces`. When `replaces` names an existing activity row, set that row's `Replaced_By` |
| REPLY | file stem is the ticket id. If `quantity` and coverage dates are present -> `activity` row as above. If `received_quantity` is present -> update the line. Set that ticket's state to `ANSWERED` in `outreach.json` |
| PURCHASE_ORDER, CAMPAIGN_ORDER | documents row only |

`tests/fakes.py` provides `make_ws(tmp_path) -> Workspace` (pdf_root under tmp, seed_dir = the real seed dir), `touch_pdf(ws, rel_path, content)` (writes a unique-content file; tests monkeypatch `evidence.pdf_text` to return the file's text), and `FakeModel(extractions: dict[str, dict], **other)` whose `"extract"` branch finds the Document_ID marker `DOC:<id>` in the text and returns `extractions[id]` with every missing key filled with null. `FakeModel.calls` records `(prompt_name, variables)`.

`prompts/extract.md`: instructs the model to return only the JSON record above, defines each field in one line, says `service_period` is the month the goods or services relate to (not the issue date), says a usage report's coverage dates must be copied exactly, and ends with `Document:\n\n{{DOCUMENT}}`.

Tests must assert: `extract_json` pulls JSON out of prose and fenced blocks; `document_id(Path("ISSUE-USG-OPENAI-DEC.pdf")) == "USG-OPENAI-DEC"`; `pull_seed("2026-09")` loads PO-001 and PO-002 only and no card statement, `pull_seed("2026-12")` adds the other three and the card row, and does not reset a `Quantity_Received` changed in between; contract then amendment yields V1 (`Effective_End` 2026-11-30, Superseded) and V2 (1400, from 2026-12-01, Active); an invoice lands in `ap_invoices` with `PO_Line_ID` "PO-001-001"; a goods receipt sets `Quantity_Received` 20 on PO-003-001; a final usage report with `replaces` marks the partial row's `Replaced_By`; ingesting the same file twice calls the model once and adds one documents row; a second workspace run reuses `extract_cache.json` (model not called).

### Task 3: Invoice matching and Detection agent

**Files:** Create `invoice_lookup.py` (only `find_invoice` in this task), `detection.py`, `tests/test_detection.py`.

**Consumes:** `store`, `workspace.covers`, `events`.

**Produces:**

```python
# invoice_lookup.py
def find_invoice(ws, po_line_id: str, period: str) -> dict | None     # ap_invoices row for that line and Service_Period

# detection.py
def detect(ws, period: str) -> list[dict]
```

`detect` rules: consider `po_lines` whose header `Status` is "Open" or "Approved". A line is owed this period when (a) its header validity covers the period, or (b) it has a `Contract_ID` with any `contracts` version covering the period, or (c) `(Quantity_Received or 0) > (Quantity_Billed or 0)`, or (d) a non-replaced `activity` row exists for the line with `Service_Period == period`. One `CARD` case per `card_statements` row for the period. Existing `SETTLED` cases for the period are kept untouched; every other case for the period is rebuilt from scratch with state `OPEN`, then set to `INVOICED` (amount = invoice amount, evidence = [Invoice_ID]) when `find_invoice` hits. Saves the ledger and returns the period's cases. One `events.log` line per case.

Tests must assert (tables written directly with `store`, no model): for `2026-09` with invoices for both FO lines -> two cases, both `INVOICED` with 1200 and 14200; for `2026-12` with no December invoices, PO-003 received 20, a Meta delivery activity row, PO-005 received 1, the Ramp statement -> six cases (`PO-001-001`, `PO-002-001`, `PO-003-001`, `CAMPAIGN-004-001`, `PO-005-001`, `CARD/Ramp`), all `OPEN`; PO-003 with `Quantity_Received` 0 produces no case; a `Closed` header produces no case; running `detect` twice yields the same six case ids once each; a pre-existing `SETTLED` case is unchanged after `detect`.

### Task 4: Classifier agent

**Files:** Create `classifier.py`, `prompts/read_description.md`, `tests/test_classifier.py`.

**Consumes:** `store`, `events`, `workspace.covers`; `outreach.open_ticket(ws, case, reason, detail, suggested=None)` (Task 6; in this task call it through a module-level `_open_ticket` hook that tests replace).

**Produces:**

```python
def classify_columns(header: dict, line: dict) -> tuple[str | None, list[str]]
def extra_checks(ws, header: dict, line: dict, period: str) -> list[str]
def read_description(ws, model, header: dict, line: dict) -> dict     # {"category", "confidence"}; cached
def run(ws, model, period: str) -> None
```

`classify_columns` is the spec's five-branch rule, in order: `limit` = `Item_Category in ("B", "E")`; `validity` = both validity dates set; `service` = `Item_Category == "P"` or `Contract_ID` set. (1) FO, limit, validity -> RV. (2) NB, limit, not validity -> OTV. (3) not limit, service, `GR_Based_IV` false -> RF. (4) NB, not limit, not service, `GR_Based_IV` true, `Quantity_Ordered` and `Unit_Price` set -> OTF. (5) else `(None, ["no branch matches: ..."])`. `extra_checks` returns the spec's four contradiction messages. `read_description` cache key = sha256 of the JSON of the header's `Order_Type`/validity and the full line; stored in `state/classification_cache.json`. `run` handles every `OPEN` `PO_LINE` case of the period: sets `category` = columns result (or the model's when columns give None) and the `classification` block; opens a `CLASSIFICATION_DISAGREEMENT` ticket (suggested = model category) when columns != model or any contradiction exists. `CARD` cases get `category` "NON_PO" and no model call.

`prompts/read_description.md`: defines the four categories in one line each (from `startup/FEE_CLASSIFICATION.md`), gives `{{LINE_DESCRIPTION}}`, asks for `{"category": "...", "confidence": 0.0-1.0}` only, and says to judge from the description alone.

Tests must assert: the five seed lines classify as PO-001 RF, PO-002 RV, PO-003 OTF, CAMPAIGN-004 OTV, PO-005 OTF; OpenAI's line (limit and contract-linked) is RV, proving branch order; an FO line with no validity dates -> None; a limit line with `Quantity_Received` 3 -> contradiction; a `Contract_ID` missing from `contracts` -> contradiction; header total 99 vs 25 x 1600 -> contradiction; with a fake model answering `RECURRING_VARIABLE` for PO-005, `run` keeps `category == "ONE_TIME_FIXED"`, records `classification.model`, and the ticket hook is called once with reason `CLASSIFICATION_DISAGREEMENT` and suggested `RECURRING_VARIABLE`; a second `run` makes zero model calls (cache).

### Task 5: Improvements file and Estimation agent

**Files:** Create `improvements.py`, `estimation.py`, `prompts/apply_improvements.md`, `tests/test_improvements.py`, `tests/test_estimation.py`.

**Consumes:** `store`, `events`, `safe_math.evaluate`, workspace helpers; `outreach.open_ticket` via a `_open_ticket` hook as in Task 4.

**Produces:**

```python
# improvements.py   (file: state/improvements.md, format in the spec)
def load(ws) -> list[dict]                       # {"lesson_id", "category", "status", "text"}
def active_for(ws, category: str) -> list[dict]
def propose(ws, category: str, text: str) -> dict    # next id I-001, I-002, ...; status PROPOSED
def approve(ws, lesson_id: str) -> dict              # raises KeyError when unknown

# estimation.py
def base_estimate(ws, case: dict) -> dict        # {"amount", "calculation", "complete", "missing", "evidence"}
def usage_for(ws, po_line_id: str, period: str) -> dict   # {"quantity", "value", "complete", "missing", "documents"}
def rate_in_effect(ws, contract_id: str, period: str) -> dict | None   # contracts version covering the period (latest Version wins)
def run(ws, model, period: str) -> None
```

`usage_for`: take non-replaced activity rows for the line and period. If one row alone covers the first through last day, use the latest such row alone. Otherwise merge all rows' coverage intervals; `complete` when the union covers the whole month; quantity and value are sums. `missing` lists the uncovered date ranges as `"usage for 2026-12-26 to 2026-12-31"`.

`base_estimate` by category:
- RF: `Unit_Price`; calculation `"1200"`; complete.
- RV: complete -> `quantity x Unit_Rate` of `rate_in_effect`, calculation `"930000 * 0.02"`. Incomplete -> average of the `ap_invoices` amounts for the line over `prev_periods(period, 3)` (those that exist), never below the partial cost; calculation `"(14200 + 16800 + 15500) / 3"`; `complete` false.
- OTF: `Unit_Price x (Quantity_Received - Quantity_Billed)`; calculation `"1600 * (20 - 0)"`.
- OTV: activity `value` minus the sum of that line's invoices; complete only when `usage_for` is complete; nothing delivered -> amount 0, incomplete.
- NON_PO: `Settled_Balance + Pending_Balance`.

`run` for each `OPEN` case of the period: `base_estimate`; then, only when `improvements.active_for(category)` is non-empty, call `model("apply_improvements", {"LESSONS", "CASE", "PO_HEADER", "PO_LINE", "CONTRACTS", "ACTIVITY", "INVOICE_HISTORY", "BASE"})`, expecting `{"calculation": str | null, "applied": [ids], "mismatch": {"field", "po_value", "contract_value"} | null, "explanation": str}`. When `calculation` evaluates (via `safe_math`) to a number >= 0, it replaces the base amount and calculation and `lessons_applied` = `applied`; an invalid calculation keeps the base and logs an event. A `mismatch` opens a `DATA_MISMATCH` ticket. An incomplete case opens a `MISSING_DATA` ticket with `missing` as the detail (OTF/OTV with nothing received: `NOT_RECEIVED`). Final state: `ACCRUED` when complete, else `ESTIMATED`. One `events.log` line per case with the amount and calculation.

`prompts/apply_improvements.md`: gives the lessons, the case data, and the base calculation; says to apply only lessons whose condition actually holds for this data; the calculation must be plain arithmetic on numbers found in the data (no words, no variables); includes two worked examples of the output JSON (a rate mismatch, and a daily-rate extension of a partial report); JSON only.

Tests must assert: `propose` twice yields I-001 and I-002 under their category headings and `load` round-trips; `approve("I-001")` flips only that tag; `active_for` ignores PROPOSED. Estimation with seed rows plus hand-written tables: Mintlify 1200 ACCRUED; OpenAI partial 1-25 (700000) with Sep-Nov invoices -> 15500 ESTIMATED, `missing == "usage for 2026-12-26 to 2026-12-31"`, MISSING_DATA hook called; partial + a second row for 26-31 (230000) -> 18600 ACCRUED; a full-month row that replaces the partial -> 18600, not 32600; ASUS 32000 ACCRUED; Meta 24700 ACCRUED (not 30000); Ramp 9660.25 ACCRUED; with no active lessons the model is never called; with I-001 active and a fake model returning `{"calculation": "1400", "applied": ["I-001"], "mismatch": {...}}` -> Mintlify 1400, `lessons_applied == ["I-001"]`, DATA_MISMATCH hook called; with a fake returning `"calculation": "700000 / 25 * 31 * 0.02"` -> OpenAI 17360 and still ESTIMATED; a fake returning `"calculation": "os.system('x')"` keeps 15500.

---

## Wave C

### Task 6: Outreach, report, and month-end orchestration

**Files:** Create `outreach.py`, `report.py`, `run_month.py`, `tests/test_outreach.py`, `tests/test_run_month.py`, `tests/fixtures.py`. Modify `classifier.py` and `estimation.py` so their `_open_ticket` hook defaults to `outreach.open_ticket`.

**Produces:**

```python
# outreach.py
START_LEVEL = {"MISSING_DATA": 1, "NOT_RECEIVED": 1, "UNMATCHED_INVOICE": 2, "DATA_MISMATCH": 3, "CLASSIFICATION_DISAGREEMENT": 3}
def open_ticket(ws, case: dict, reason: str, detail: str, suggested: str | None = None) -> dict
    # idempotent per (case_id, reason); chain = [Requester, Cost_Center_Owner, "Procurement"] from the case's PO header
    # (CARD or unknown -> ["Finance", "Finance", "Procurement"]); question is a one-sentence template per reason.
def advance(ws, period: str) -> None     # every OPEN ticket of the period: runs_seen += 1; when runs_seen > 1 and level < 3, level += 1 and `to` moves up the chain
def expire(ws, period: str) -> None      # OPEN -> EXPIRED
def save_reply(ws, ticket_id: str, text: str) -> Path   # pdf_root/<period>/replies/<ticket_id>.txt

# report.py
def write(ws, period: str) -> None       # close_packages/<period>/accruals.json, outreach.json, report.md
def write_trueups(ws, period: str) -> None   # close_packages/<period>/trueups.json (SETTLED cases of the period)

# run_month.py
def run_month(ws, model, period: str) -> dict    # {"period", "cases": n, "total": sum of ACCRUED + ESTIMATED amounts}
def reset_period(ws, period: str) -> None
def reset_all(ws) -> None
# CLI: python -m system.run_month 2026-12
```

The demo has no real clock: a ticket's reply window is "one run". `run_month` order: on the first run of a period, snapshot `db_dir`, `ledger.json`, `outreach.json` into `state_dir/snapshots/<period>/`; then `evidence.run`, `detection.detect`, `classifier.run`, `estimation.run`, `outreach.advance`, `report.write`; each stage wrapped in `events.log` start lines naming the agent. Tickets whose case no longer needs them (case now `ACCRUED` with no `missing`) are set `ANSWERED`. `reset_period` restores that snapshot, deletes snapshots and close packages for that and later periods, and leaves `improvements.md` and both caches alone. `reset_all` deletes `db_dir`, the ledger, outreach, snapshots, events, `improvements.md`, and close packages, keeping the two caches. `report.md` has a totals line, one table row per case (vendor, category, state, amount, calculation), an Outreach section, and a Lessons applied section.

`tests/fixtures.py` builds the full fixture workspace for end-to-end tests: `build_fixture_ws(tmp_path) -> tuple[Workspace, FakeModel]` creates marker files (content `DOC:<id>`) mirroring the real layout (`reference/CTR-001`, `CTR-002`; `2026-09`..`2026-11` two invoices each; `2026-12/` `ISSUE-AMD-MINTLIFY-DEC`, `ISSUE-USG-OPENAI-DEC`, `PO-003`, `ISSUE-GR-ASUS-DEC`, `CAMPAIGN-004`, `ISSUE-META-DELIVERY-DEC`; `2026-12/afterclose/` `INV-MINTLIFY-DEC`, `USG-OPENAI-DEC-FINAL`) with extraction records transcribed from `startup/minimal_data/classification_input.json` and `afterclose_evidence.json` (CTR-001 `term_start` 2026-09-01, `monthly_fee` 1200; CTR-002 `unit_rate` 0.02; the final usage report `replaces` "USG-OPENAI-DEC"). Its `read_description` branch answers each seed line with the category its columns give, except PO-005 -> `RECURRING_VARIABLE`.

Tests must assert: `open_ticket` twice -> one ticket; MISSING_DATA for OpenAI starts at level 1 to `dana.kim`; DATA_MISMATCH starts at level 3 to "Procurement"; `advance` on the second run moves level 1 -> 2 (`raj.patel`), third -> 3, then stays; `expire` sets EXPIRED. End to end with `build_fixture_ws`: `run_month` for 2026-09, -10, -11 -> every case `INVOICED`, amounts 1200 and 14200/16800/15500; `run_month("2026-12")` -> `PO-001-001` ACCRUED 1200, `PO-002-001` ESTIMATED 15500, `PO-003-001` ACCRUED 32000, `CAMPAIGN-004-001` ACCRUED 24700, `PO-005-001` ACCRUED 5000, `CARD/Ramp` ACCRUED 9660.25, summary total 88060.25; open tickets are exactly one MISSING_DATA (OpenAI) and one CLASSIFICATION_DISAGREEMENT (PO-005); the afterclose files were not ingested; `close_packages/2026-12/report.md` and `accruals.json` exist; running December again produces the same cases and amounts, no duplicate tickets, and the OpenAI ticket at level 2; after `save_reply` of a reply whose fake extraction is a usage row for 12-26..12-31 with 230000 units, the next `run_month("2026-12")` gives OpenAI ACCRUED 18600 and that ticket `ANSWERED`; `reset_period("2026-12")` leaves only the Sep-Nov cases and no December invoice rows.

### Task 7: Invoice Lookup, Learning, and always-on orchestration

**Files:** Modify `invoice_lookup.py`. Create `learning.py`, `run_lookup.py`, `prompts/root_cause.md`, `tests/test_lookup_learning.py`.

**Produces:**

```python
# invoice_lookup.py
def settle(ws, model, period: str) -> list[dict]
    # evidence.ingest_afterclose; for each ACCRUED/ESTIMATED PO_LINE case of the period: actual = invoice amount when
    # find_invoice hits; else, for RECURRING_VARIABLE / ONE_TIME_VARIABLE, the base formula when usage_for is now
    # complete AND draws on a document the case did not have; else skip. Sets state SETTLED and settlement
    # {actual, variance = round(actual - amount, 2), settled_by, root_cause: None, lesson_id: None}.
    # An afterclose invoice that matches no case -> UNMATCHED_INVOICE ticket. Then outreach.expire(ws, period).
    # Returns the newly settled cases.

# learning.py
VARIANCE_THRESHOLD = 100.0
def learn(ws, model, case: dict) -> dict | None
    # skipped when abs(variance) <= threshold. model("root_cause", {"CASE", "ACTUAL_EVIDENCE", "PO_LINE", "CONTRACTS",
    # "ACTIVITY", "LESSONS"}) -> {"root_cause": str, "covered_by": lesson_id | null, "lesson": {"category", "text"} | null}.
    # Stores root_cause on the case. Rejects a lesson whose text contains any vendors.Vendor_Name (case-insensitive),
    # whose category is not the case's category, or whose normalized text equals an existing lesson's. Otherwise
    # improvements.propose(...) and records lesson_id on the settlement.

# run_lookup.py
def run_lookup(ws, model) -> dict    # for every period with ACCRUED/ESTIMATED cases, oldest first: settle, learn each, report.write_trueups
# CLI: python -m system.run_lookup
```

`prompts/root_cause.md`: gives the case (calculation, evidence, lessons applied), the actual evidence, and existing lessons; asks why the booked amount differed, in one sentence; asks for a lesson that would have prevented it, tied to the fee category, phrased as an instruction to the estimator, with no vendor or product names; if an existing lesson already covers it, return its id in `covered_by` and `lesson: null`; JSON only, with one worked example.

Tests must assert, continuing from the December end-to-end state with a fake `root_cause` branch: `run_lookup` settles Mintlify (actual 1400, variance 200.0, settled_by "INV-MINTLIFY-DEC") and OpenAI (actual 18600, variance 3100.0, settled_by "USG-OPENAI-DEC-FINAL"); ASUS, Meta, PO-005, Ramp stay ACCRUED; the partial usage row has `Replaced_By`; the OpenAI MISSING_DATA ticket is EXPIRED; two lessons are PROPOSED (I-001 under RECURRING_FIXED, I-002 under RECURRING_VARIABLE); `trueups.json` lists both; a fake lesson containing "Mintlify" is rejected and nothing is proposed; a variance of 50 calls no model; a second `run_lookup` changes nothing. Full learning loop: approve both, `reset_period("2026-12")`, `run_month("2026-12")` with the fake `apply_improvements` branch returning "1400" + mismatch for RF and "700000 / 25 * 31 * 0.02" for RV -> Mintlify ACCRUED 1400 with a DATA_MISMATCH ticket at level 3, OpenAI ESTIMATED 17360; then `run_lookup` -> Mintlify variance 0.0, OpenAI variance 1240.0.

---

## Wave D (two tasks, may run in parallel)

### Task 8: API server

**Files:** Create `server.py`, `tests/test_server.py`.

**Produces** (FastAPI app factory `create_app(ws: Workspace, model: Model) -> FastAPI`; module-level `app = create_app(Workspace.default(), bedrock_model)`; start with `cd startup && ../.venv/bin/python -m uvicorn system.server:app --port 8000`):

| Route | Behavior |
|---|---|
| `GET /` | serves `ui/index.html` |
| `GET /api/state` | `{"periods": [{"period", "status": "NOT_RUN"/"CLOSED"/"SETTLED", "total", "cases": n}] for 2026-09..2027-01, "cases": [...ledger], "tickets": [...], "lessons": [...], "running": bool, "last_error": str/null}`. A period is `NOT_RUN` with no cases, `SETTLED` when at least one of its cases is SETTLED, otherwise `CLOSED` |
| `GET /api/events?since=N` | `events.read` |
| `POST /api/run_month` `{"period"}` | starts `run_month` in a background thread; `409` when a run is in progress |
| `POST /api/run_lookup` | same, for `run_lookup` |
| `POST /api/reset` `{"period": str or null}` | `reset_period` or `reset_all`; `409` while running |
| `POST /api/tickets/{ticket_id}/reply` `{"text"}` | `outreach.save_reply`; `404` for an unknown ticket |
| `POST /api/lessons/{lesson_id}/approve` | `improvements.approve`; `404` when unknown |
| `GET /pdf/{path}` | file under `ws.pdf_root`; `404` outside it (no path traversal) |

Each case in `/api/state` gains `"evidence_links": [{"document_id", "url"}]` built from the `documents` table. An exception inside a background run is caught, stored in `last_error`, logged as an event, and clears `running`.

Tests (FastAPI `TestClient`, fixture workspace, fake model; background runs are joined through a `app.state.join()` helper): state before any run shows five periods `NOT_RUN`; `run_month` 2026-12 then state shows six cases and total 88060.25; a second `run_month` while `running` is forced true -> 409; reply to the OpenAI ticket writes the reply file; approve flips a lesson; unknown ids -> 404; `/pdf/../../.env` -> 404; reset with null empties the ledger.

### Task 9: Web page

**Files:** Create `ui/index.html` (single file, inline CSS and JS, no CDN dependencies, no build).

**Consumes:** the Task 8 routes exactly as specified.

Five panels per the spec's UI section. Behavior: poll `/api/state` every 2 s and `/api/events?since=` every 1 s while `running`. Timeline: a card per period with status, total, a `Run month end` button (disabled while running); global `Run lookup` and `Reset demo` buttons, and a per-period `Reset` on closed periods. Agents: the seven agents in two groups (Month end, Always on); the agent named by the latest event is highlighted; the event log scrolls beneath, newest last. Cases: grouped by period, newest period first; category and state as colored badges (INVOICED grey, ACCRUED green, ESTIMATED amber, SETTLED blue); amounts right-aligned with thousands separators; clicking a row expands calculation, explanation, lessons applied, missing, and evidence links that open the PDF in a new tab; SETTLED rows also show actual and variance (variance red when non-zero). Outreach: open tickets first, showing reason, level, who is asked, the question, suggested value; a `Reply` box that posts and clears. Learning: one card per SETTLED case with a non-null root cause (booked, actual, variance, root cause) and the lessons list with `Approve` on PROPOSED ones. Show `last_error` in a dismissible banner. Layout: two columns on wide screens (left: Timeline + Agents; right: tabs for Cases, Outreach, Learning), single column under 900 px. Light and dark via `prefers-color-scheme`. A finance tool: dense, calm, legible; no gradients, no emoji.

Verify by starting the server on the fixture-free default workspace is NOT required in this task; instead load the page against the running server in Task 10.

---

## Wave E

### Task 10: Live run against Bedrock and the real PDFs

**Files:** Modify prompts and, only if a real bug appears, the agent modules (with a regression test). Create `startup/system/README.md` (setup, the two CLI commands, starting the UI, the demo script from the spec, how to refresh the Bedrock key in `.env`). Update the "Status" line of `startup/MONTHLY_WORKFLOW.md` to say it is implemented and point at `startup/system/README.md`.

Steps: `reset_all`; run 2026-09 through 2026-12 with the real model and compare every case with the walkthrough table (Sep-Nov INVOICED at the listed amounts; December 1200 / 15500 / 32000 / 24700 / 5000 / 9660.25); fix extraction-prompt problems until they match; `run_lookup` and check the variances (200 and 3100) and that both proposed lessons are vendor-free and sensible; approve both; `reset_period("2026-12")`; rerun December and check 1400 and 17360; start the server, load the page, click through the demo script, and screenshot each panel. Report every mismatch found and how it was fixed.
