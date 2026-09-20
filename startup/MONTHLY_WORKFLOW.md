# Monthly Close Workflow

Status: DRAFT for review. Nothing in this document is implemented yet.

## Purpose

Five agents run at month end, in a fixed order: they turn documents into databases, find what the company owes for the month, classify each obligation, estimate the accrual, and chase missing information. Two more agents run all the time: one finds the invoices that arrive later, the other learns from the difference between what was accrued and what was billed.

`MODEL` below means an LLM call through AWS Bedrock's OpenAI-compatible endpoint (`openai` SDK, model `openai.gpt-oss-120b`, overridable with `MODEL_ID`), made from one shared `call_model()` function. The key lives in a git-ignored `.env`. `CODE` means deterministic code. Only `CODE` writes state or produces a booked number.

## The agents

```text
MONTH END   run_month <period>                              ALWAYS ON   run_lookup

 PDFs, ERP, e-procurement, card issuer, contract platform    new invoice, AP entry, or
            |                                                complete report arrives
            v                                                          |
   EVIDENCE      documents -> JSON -> databases  <---------------------+
            |                                                          v
   DETECTION     what do we owe this period?   -> cases       INVOICE LOOKUP
            |    (asks Invoice Lookup what is already billed)  match it to a case
   CLASSIFIER    recurring/one-time x fixed/variable           -> INVOICED or SETTLED
            |                                                          |
   ESTIMATION    category + evidence + improvements.md -> amount       v
            |                                                  LEARNING
   OUTREACH      evidence missing or data wrong -> ask people   variance -> root cause
            |                                                   -> improvements.md
            v                                                          |
   close_packages/<period>/                        read by ESTIMATION next month
```

| Agent | Team notes | Runs |
|---|---|---|
| Evidence | (1) | month end, and whenever Invoice Lookup needs a new document read |
| Detection | (2) | month end |
| Classifier | (4) | month end |
| Estimation | (5) | month end |
| Outreach | (6) | month end, re-run until the cutoff |
| Invoice Lookup | constantly running; also the unfinished "Finding all of the invoices" | always on |
| Learning | constantly running | always on, after each settlement |

## Databases

The Evidence agent owns these. In production they are pulled from the source systems; in the demo they are built from the PDFs plus seed rows. All are JSON tables under `startup/db/`.

| Table | Source system | Key columns |
|---|---|---|
| `contracts` | contract lifecycle platform | `Contract_ID`, `Vendor_Name`, `Monthly_Rate` or `Unit_Rate`, `Effective_Start`, `Effective_End`, `Status`, `Version` |
| `po_headers` | e-procurement | `PO_Number`, `Vendor_ID`, `Order_Type` (`NB` standard, `FO` framework), `Validity_Start`, `Validity_End`, `Requester`, `Cost_Center_Owner`, `Created_Date`, `Status`, `Total_Amount` |
| `po_lines` | e-procurement | `PO_Line_ID`, `PO_Number`, `Item_Category` (`B`/`E` limit, `P` service, blank standard), `Contract_ID`, `GR_Based_IV` (invoice is verified against goods receipts), `GL_Account_Code`, `Quantity_Ordered`, `Unit_Price`, `Quantity_Received`, `Quantity_Billed`, `Line_Description` |
| `ap_invoices` | ERP | `Invoice_ID`, `Vendor_ID`, `PO_Line_ID`, `Service_Period`, `Amount`, `Received_Date` |
| `card_statements` | card issuer (Ramp, Brex, Amex) | `Program`, `Period`, `Settled_Balance`, `Pending_Balance` |
| `activity` | usage, delivery, and receipt reports | `Document_ID`, `PO_Line_ID`, `Service_Period`, `Coverage_Start`, `Coverage_End`, `Quantity`, `Value`, `Replaces` |

A contract amendment is a new `contracts` row with the next `Version` and its own effective dates; the earlier version becomes `Superseded`.

## The four situations

A **case** is one PO line in one month. Its category decides the evidence and the formula. The December fixtures plant one problem in each.

| Category | Base formula | Planted problem (December) | Correct result |
|---|---|---|---|
| `RECURRING_FIXED` | copy the flat rate from the PO line (`Unit_Price`) | Mintlify: contract V2 raises $1,200 to $1,400 from December 1; the PO still says $1,200 | $1,400, and tell procurement the PO is stale |
| `RECURRING_VARIABLE` | full-period usage x contract unit rate; `Unit_Price` is only the cap | OpenAI: the usage report covers December 1-25 only | estimate now, ask for the rest, fix later |
| `ONE_TIME_FIXED` | `Unit_Price` x (`Quantity_Received` - `Quantity_Billed`) | ASUS: 25 ordered, 20 received | $32,000, not $40,000 |
| `ONE_TIME_VARIABLE` | value delivered - value billed; `Total_Amount` is only a cap | Meta: $30,000 cap, $24,700 delivered | $24,700, not $30,000 |

"Dynamic" in the team notes is `VARIABLE` here, to match the existing fixtures.

**Non-PO spend** (cards, below the de minimis threshold) is a fifth, trivial situation: one case per card program per month, amount = `Settled_Balance` + `Pending_Balance`. The statement closes on the last day of the month and the bill arrives one to three days later, so it is always accrued and never classified. Direct AP invoices below the threshold are already in `ap_invoices`; nothing to accrue.

**Forced estimate.** When evidence for a recurring variable case is incomplete, Estimation does not wait: it books the average of the last three months in `ap_invoices`, never below what a partial report already shows. Outreach then tries to replace it before the cutoff. A one-time line with nothing received or delivered is not accrued, but Outreach asks the requester whether it arrived.

## State

| File | Holds |
|---|---|
| `db/*.json` | The six tables above |
| `ledger.json` | One record per case: state, category, amount, calculation, evidence |
| `outreach.json` | One ticket per question sent to a person |
| `classification_cache.json` | The model's reading of each PO line, keyed by a hash of the row |
| `improvements.md` | What the Learning agent has learned, grouped by category |

### Case states

```text
              invoice already in AP
   new case ---------------------------> INVOICED     (done)
      |
      |  no invoice, evidence complete
      +--------------------------------> ACCRUED   --+
      |                                              |  Invoice Lookup finds the invoice
      |  no invoice, forced estimate                 |  or a complete report
      +--------------------------------> ESTIMATED --+---------------------> SETTLED  (done)
                                             |
                                             +-- Outreach answered before cutoff --> ACCRUED
```

`SETTLED` adds `actual`, `variance`, `root_cause`.

### Outreach tickets

```text
OPEN (level 1: Requester) -> OPEN (level 2: Cost_Center_Owner) -> OPEN (level 3: procurement)
   any level --reply arrives--> ANSWERED            any level --cutoff passes--> EXPIRED
```

Bottom-up: the person closest to the purchase is asked first. Each level has a fixed reply window; when it passes, the next run escalates. At the cutoff the ticket expires and the forced estimate stands. A ticket never blocks a run.

| Reason | Raised by | First asked | Example |
|---|---|---|---|
| `MISSING_DATA` | Estimation | Requester | usage for December 26-31 |
| `NOT_RECEIVED` | Estimation | Requester | one-time PO due in the period, nothing logged as received |
| `DATA_MISMATCH` | Estimation | procurement (level 3 directly) | PO line says $1,200, contract in effect says $1,400 |
| `CLASSIFICATION_DISAGREEMENT` | Classifier | procurement (level 3 directly) | columns say fixed, description reads like usage; includes the suggested category |
| `UNMATCHED_INVOICE` | Invoice Lookup | Cost_Center_Owner | an invoice arrived with no PO line and no case |

### `improvements.md`

One heading per category; one bullet per lesson, tagged `[PROPOSED]` or `[ACTIVE]`. The Learning agent appends `[PROPOSED]` bullets. A person changes the tag to `[ACTIVE]`. Estimation reads only `[ACTIVE]` bullets for the case's category. A lesson never names a vendor.

```markdown
## RECURRING_FIXED
- [ACTIVE] I-001: Before copying the PO line rate, find the contract version in effect for the
  service period. If it differs, use the contract rate and raise DATA_MISMATCH.
```

## Month end: `run_month <period>`

Safe to run more than once before the cutoff; each run picks up new replies and documents.

| Agent | # | Actor | What it does | State written |
|---|---|---|---|---|
| **Evidence** | 1 | CODE | List new PDFs and Outreach replies in `<period>/` and `reference/`. Skip documents already in a table. Pull new rows from source systems (seed files in the demo). | |
| | 2 | MODEL | One call per document. Extract to JSON: document type, vendor, service period, amounts, quantities, rates, coverage dates, what it replaces. | |
| | 3 | CODE | Upsert into the tables. Contract or amendment -> `contracts` (new version). Invoice -> `ap_invoices`. Receipt -> `po_lines.Quantity_Received`. Usage or delivery report -> `activity`. A reply that answers a ticket closes it. | `db/`, ticket -> `ANSWERED` |
| **Detection** | 4 | CODE | Open a case for every `po_lines` row owed this period: recurring lines whose validity dates or contract cover the period, **even if no document arrived**; one-time lines with `Quantity_Received` > `Quantity_Billed` or activity in the period. One case per card program. | new case |
| | 5 | CODE | Ask Invoice Lookup which cases already have an invoice for the period. | case -> `INVOICED` |
| **Classifier** | 6 | CODE | Category from the columns, using the decision rule below. | |
| | 7 | MODEL | Read `Line_Description`; return category and confidence. Skipped when the row's hash is in the cache. | `classification_cache.json` |
| | 8 | CODE | Columns and model agree, no contradiction: accept. Otherwise keep the column result and hand Outreach a `CLASSIFICATION_DISAGREEMENT` with the model's suggestion. | case category |
| **Estimation** | 9 | CODE | Base formula for the category. Incomplete evidence: forced estimate. Card case: settled + pending. | |
| | 10 | MODEL | Only if `improvements.md` has `[ACTIVE]` lessons for the category: apply them to the case's rows and documents; return a corrected calculation, its sources, and any mismatch found. CODE re-evaluates the arithmetic. | case -> `ACCRUED` or `ESTIMATED` |
| **Outreach** | 11 | CODE | Open a ticket for each reason in the table above. Escalate open tickets whose reply window has passed. Expire tickets past the cutoff. | `outreach.json` |
| | 12 | CODE | Write `close_packages/<period>/`: `accruals.json`, `outreach.json`, `report.md`. Save state. | all |

### Classifier decision rule (step 6)

`limit` = `Item_Category` is `B` or `E`. `validity` = the header has validity dates. `service` = `Item_Category` is `P`, or the line has a `Contract_ID`. Branches are tested in order, so a limit line is variable even when it is also linked to a contract (OpenAI is both).

```text
1. FO and limit and validity                      -> RECURRING_VARIABLE
2. NB and limit and not validity                  -> ONE_TIME_VARIABLE
3. service and GR_Based_IV = FALSE  (NB or FO)    -> RECURRING_FIXED
4. NB and standard item and GR_Based_IV = TRUE
      and Quantity_Ordered, Unit_Price filled     -> ONE_TIME_FIXED
5. anything else                                  -> contradiction
```

Branches 1, 3, 4 are the team's logic tree. Branch 2 is added: the tree has a single one-time bucket, which would book Meta's campaign at its cap.

Four more checks run on every row. Any failure, or branch 5, is a contradiction:

1. `Contract_ID` is not in `contracts`, or no version covers the period.
2. A recurring line has neither validity dates nor a contract covering the period.
3. A limit line has `Quantity_Received` filled in.
4. Header `Total_Amount` differs from the sum of `Quantity_Ordered` x `Unit_Price` over its non-limit lines.

## Always on: `run_lookup`

Triggered whenever a document lands after a period's cutoff (in the demo: `<period>/afterclose/`), or on a schedule.

| Agent | # | Actor | What it does | State written |
|---|---|---|---|---|
| **Invoice Lookup** | 13 | CODE + MODEL | Have Evidence read the new documents (steps 1-3). | `db/` |
| | 14 | CODE | Match each new invoice or complete report to an `ACCRUED` or `ESTIMATED` case by PO line and service period. `variance = actual - booked`. A report that replaces another is used instead of it, never added to it. No match: `UNMATCHED_INVOICE` ticket. | case -> `SETTLED` |
| **Learning** | 15 | MODEL | For each variance above the threshold: given the case, its calculation, the new evidence, and `improvements.md`, return a one-sentence root cause and a lesson for that category. | |
| | 16 | CODE | Reject a lesson that names a vendor or repeats an existing one. Append the rest as `[PROPOSED]`. Write `close_packages/<period>/trueups.json`. | `improvements.md` |

Between runs, people do two things: answer Outreach tickets and change `[PROPOSED]` lessons to `[ACTIVE]`.

## Walkthrough with the current fixtures

Starting from empty state and an empty `improvements.md`.

| Run | Mintlify (branch 3) | OpenAI (branch 1) | ASUS (branch 4) | Meta (branch 2) |
|---|---|---|---|---|
| `run_month` `2026-09` to `2026-11` | `INVOICED` $1,200 each month | `INVOICED` $14,200, $16,800, $15,500 | | |
| `run_month 2026-12` | no invoice; copies the PO rate; `ACCRUED` **$1,200** | no invoice; partial report; `ESTIMATED` **$15,500**; `MISSING_DATA` ticket to the requester | `ACCRUED` $32,000 = 1,600 x 20 | `ACCRUED` $24,700 |
| cutoff, January 5 | | ticket `EXPIRED`; the estimate stands | | |
| `run_lookup`, January 10 | invoice $1,400; `SETTLED`, variance **+$200**; Learning proposes I-001 | final report 930,000 x $0.02 = $18,600; `SETTLED`, variance **+$3,100**; Learning proposes I-002 | still `ACCRUED` | still `ACCRUED` |

- **I-001** (`RECURRING_FIXED`): before copying the PO line rate, find the contract version in effect for the service period; if it differs, use the contract rate and raise `DATA_MISMATCH`.
- **I-002** (`RECURRING_VARIABLE`): when a usage report is partial, extend its daily rate to the full period instead of averaging prior months. (700,000 / 25 x 31 x $0.02 = $17,360; the variance would have been $1,240.)

Run December again with both lessons `[ACTIVE]`: Mintlify books $1,400 and procurement gets a `DATA_MISMATCH` ticket; OpenAI books $17,360.

## UI

A local web page for the demo. It shows the system working and is the place where people do their two jobs. It never computes anything: it reads the state files and calls the same two commands.

```text
browser (one static page, no build step)  <-->  server.py (FastAPI)  <-->  run_month / run_lookup, state/, db/
```

| Panel | Shows | Actions |
|---|---|---|
| **Timeline** | The months `2026-09` to `2027-01`, each with its status and accrual total | `Run month end`, `Run lookup`, `Reset demo` |
| **Agents** | The seven agents as a pipeline. While a run is in progress, the current agent and step light up and each step prints one line of what it did ("Classifier: PO-003-001 -> ONE_TIME_FIXED, model agrees 0.94") | |
| **Cases** | One row per case: vendor, category, state badge, amount. Expanding a row shows the calculation, the lessons applied, and the evidence, with links to the PDFs | |
| **Outreach** | Open tickets with their level, who is being asked, and time left before the cutoff | `Reply` (saved as a reply file in the period folder, picked up by Evidence on the next run) |
| **Learning** | Each settlement: booked, actual, variance, root cause, and the proposed lesson | `Approve` (changes `[PROPOSED]` to `[ACTIVE]` in `improvements.md`) |

Each agent step appends one line to `state/events.jsonl`; the Agents panel polls it. Nothing else is added to the agents for the UI.

Demo script: run September to December, show the four December cases and the OpenAI ticket, run lookup, show the two variances and lessons, approve both, reset December, run it again, and show Mintlify at $1,400 and OpenAI at $17,360.

## Files and fixtures

```text
startup/
  system/
    run_month.py   run_lookup.py   model.py (call_model via Bedrock)
    server.py      ui/index.html
    evidence.py  detection.py  classifier.py  estimation.py  outreach.py
    invoice_lookup.py  learning.py
    prompts/       extract.md  read_description.md  apply_improvements.md  root_cause.md
  db/              the six tables
  state/           ledger.json  outreach.json  classification_cache.json  improvements.md  events.jsonl
  close_packages/<period>/
```

Fixtures to add, because the current set has PDFs but no source-system rows:

- `po_headers` and `po_lines` seed rows. Mintlify: `FO`, `P` line, linked to CTR-001, `GR_Based_IV` false, `Unit_Price` 1,200. OpenAI: `FO`, limit line, linked to CTR-002, validity dates. PO-003 (ASUS): `NB`, standard line, `GR_Based_IV` true, 25 x $1,600. CAMPAIGN-004 (Meta): `NB`, limit line, no validity dates. Each header has a `Requester` and a `Cost_Center_Owner`.
- A card statement for at least one month, to exercise the non-PO path.
- One PO line whose columns and description disagree, to exercise `CLASSIFICATION_DISAGREEMENT`.
- One Outreach reply that arrives before the cutoff, to show `ESTIMATED` -> `ACCRUED`.

`minimal_data/run_classify.py` and `classify_prompt.md` are replaced. The two hints hard-coded in the current prompt are removed: averaging prior months is the forced estimate in code, and checking amendments is lesson I-001.

## Left out on purpose

Prepaid expenses, hybrid fees, multi-line POs spanning categories, vendor-name aliases, resuming a failed run, actually sending Outreach messages (tickets are written to `outreach.json`; replies are typed in the UI or dropped in the period folder), logins and multiple users in the UI, and document timestamps (the `afterclose/` folder stands in for "arrived after cutoff"). Add them when a fixture needs them.

## Open decisions

1. **Agent (3)** is missing from the team notes' numbering. Nothing in this document depends on it.
2. **Outreach reply window** per level. Draft: 24 hours, shortened to fit the days left before the cutoff.
3. **Variance threshold** for Learning. Draft: $100.
4. **Who approves lessons**, and whether any category is safe to auto-activate.
