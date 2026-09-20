# Minimal Fee Classification Task

## Goal

Read the finance documents in [`output/pdf/startup_minimal_data`](../../output/pdf/startup_minimal_data) and classify each vendor fee into one of four categories:

- `RECURRING_FIXED`
- `RECURRING_VARIABLE`
- `ONE_TIME_FIXED`
- `ONE_TIME_VARIABLE`

The final result should follow the structure in [`expected_classifications.json`](expected_classifications.json).

## Data flow

```text
PDF documents
    |
    | read and extract facts
    v
classification_input.json     optional intermediate step
    |
    | classify and calculate the accrual
    v
expected_classifications.json final result
```

The PDFs are the original evidence and source of truth. [`classification_input.json`](classification_input.json) is a convenient normalized representation of the PDF content. A system may create or use this intermediate JSON to make classification easier, but it should be possible to complete the task directly from the PDFs.

[`document_manifest.json`](document_manifest.json) maps each document ID to its PDF path.

## What to extract from the PDFs

For each vendor, collect only the facts needed to answer two questions:

1. **Does the fee repeat?**
   - A contract term, monthly billing language, or consecutive monthly invoices indicates `RECURRING`.
   - A single purchase, project, or campaign with a defined end indicates `ONE_TIME`.

2. **Is the amount predetermined?**
   - A stated monthly fee or fixed order total indicates `FIXED`.
   - Usage, quantity, hours, delivery, or another measured activity indicates `VARIABLE`.

Also extract the facts needed to calculate the amount, such as the monthly fee, unit rate, usage quantity, delivered quantity, or delivered value.

## How to produce the result

Process the documents vendor by vendor:

1. Use [`document_manifest.json`](document_manifest.json) to locate the related PDFs.
2. Read the contract, invoice, purchase order, receipt, or delivery evidence.
3. Optionally write the extracted facts to [`classification_input.json`](classification_input.json).
4. Decide `recurrence` as `RECURRING` or `ONE_TIME`.
5. Decide `amount_type` as `FIXED` or `VARIABLE`.
6. Combine the two values into `category`.
7. Calculate `expected_amount` from the evidence.
8. Record the evidence that supports the decision.
9. Write the final records using the schema below.

## Final output schema

```json
{
  "expected_results": [
    {
      "case_id": "CASE-01",
      "vendor_id": "V001",
      "recurrence": "RECURRING",
      "amount_type": "FIXED",
      "category": "RECURRING_FIXED",
      "expected_amount": 1200.0,
      "calculation": "optional calculation when useful",
      "key_evidence": [
        "evidence from the source PDFs"
      ]
    }
  ]
}
```

`case_id` and `vendor_id` connect the result to the extracted case. `calculation` is optional when the amount appears directly in the evidence.

## Evaluation

Compare the generated result with [`expected_classifications.json`](expected_classifications.json). A correct result should match:

- the case and vendor IDs;
- recurrence and amount type;
- the combined category;
- the calculated amount; and
- the main evidence supporting the decision.

Do not classify a fee from the vendor name alone. Base every decision and amount on the contents of the PDFs.

## December 2026 and January 2027: a document lives in the month it arrives

A document is filed in the folder of the month it reached Orbit Labs, not the month it is
about. Everything about December that only turned up in January therefore sits in
`2027-01/`, which is exactly when the close sees it: December closes in the first days of
January on what `2026-12/` holds, and the January close - which runs in February - is where
December's true-ups happen. The one exception is a document that has to surface between the
two closes: `<month>/afterclose/` is read by that month's own settlement in the middle of the
next month (known on the 12th, settled on the 15th), and `<month>/afterclose/replies/` holds a
vendor's answer to a question settlement sent out (known on the 20th, read on the 25th). The
Mintlify invoice and the reply to it are filed that way, so December's price question is asked
and answered in January rather than waiting for the January close in February.

- **OpenAI usage (partial then final).** `2026-12/USG-OPENAI-DEC.pdf` is a *partial* usage
  report covering only December 1-25, 2026 (700,000 units, $14,000.00 at $0.02/unit),
  generated December 26, 2026. It states plainly that it is not an invoice and that usage
  after December 25 is not included. `2027-01/USG-OPENAI-DEC-FINAL.pdf` is the
  *final* report for the full month (December 1-31, 2026; 930,000 units, $18,600.00),
  generated January 8, 2027, and states that it replaces `USG-OPENAI-DEC`.
  `2027-01/USG-OPENAI-JAN.pdf` is January's own partial report (January 1-27, 2027;
  810,000 units, $16,200.00), generated January 28, 2027: January repeats December's problem
  one month on.
- **Mintlify invoice arrives late, at a higher price.** At the December close, only the
  $1,200/month `CTR-001` contract is known. The December invoice,
  `2026-12/afterclose/INV-MINTLIFY-DEC.pdf`, does not arrive until January 10, 2027 and bills
  the new amended amount of $1,400.00, so December's settlement sees it on January 15 and asks
  the vendor what changed. No amendment document is available in the December folder itself.
  `2026-12/afterclose/replies/REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED.txt` is
  Mintlify's reply, dated January 18, 2027, read on January 25, to that variance question: it
  explains that a signed contract amendment (`AMD-MINTLIFY-DEC`, signed December 15, 2026)
  raised the CTR-001 monthly fee from $1,200.00 to $1,400.00 effective December 1, 2026, and
  that all other terms are unchanged. The close reads that reply as the amendment it
  describes, which explains December's variance and reprices January.
- **Meta delivery report arrives after close.** Nobody answers before the December cutoff, so
  `2027-01/META-DELIVERY-DEC.pdf` (the $30,000 budget / $24,700 delivered campaign delivery
  report) is only seen by the January close. `2026-12/CAMPAIGN-004.pdf` (the campaign order
  itself) remains available during December, and its validity ends December 31, so January
  has no Meta case.

## The purchase orders carry the procurement facts

Nothing about a vendor, a purchase order or a PO line is seeded anywhere: the four order documents
(`2026-09/PO-001.pdf`, `2026-09/PO-002.pdf`, `2026-12/PO-003.pdf`, `2026-12/CAMPAIGN-004.pdf`) are the
only source of the purchase tables, and a vendor is created the first time a document names it. Each
order prints, as labelled fields, everything procurement would hand over: the order number, the vendor,
the order type (`FO - framework order` or `NB - standard order`), the validity window when the order has
one, the requester and the cost-center owner (whom the close asks when data is missing), the linked
contract id, and a line table with the line id, the item category (`P - service`, `B - limit`, or
`standard`), the description, the quantity ordered, the unit price, the overall limit for a limit line
and whether a goods receipt is required. A campaign order is rendered by the same maker as a purchase
order, so `CAMPAIGN-004` carries exactly the same fields. Adding a line to an order means adding an entry
to that document's `"lines"` array in `classification_input.json` and regenerating.

These placements are driven by an optional `"folder"` field on a document entry in
`classification_input.json` (e.g. `"folder": "2027-01"` on a document about December, or
`"folder": "2026-12/afterclose"` for an arrival between two closes), which
`generate_pdfs.py`'s `month_of()` honors ahead of the default month-of-service-period
placement.

## Notability (CASE-05): a subscription with no purchase order

Notability is the one vendor the corpus buys from without procurement in the middle: there is no
purchase order and no card statement, only an agreement and the single invoice that prepays it.
Both documents are filed in `2026-11`, the month they arrived, although the service they buy runs
from December 2026:

- `2026-11/CTR-003.pdf` is the team subscription agreement. It is effective December 1, 2026, runs
  twelve months to November 30, 2027, and is signed on November 24, 2026, the day the annual
  invoice was issued. The monthly fee is $1,800.00 and the twelve months are billed once, in
  advance, as $21,600.00.
- `2026-11/INV-NOTABILITY-ANNUAL.pdf` is that single invoice: dated 2026-11-24, service period
  `2026-12-01 to 2027-11-30`, 12 months at $1,800.00 = $21,600.00.

An agreement that does not start on the corpus's default date, or is not billed monthly in
arrears, says so through three optional fields on its entry in `classification_input.json` -
`"effective_date"`, `"signed_on"` and `"invoice_timing"`. Every earlier agreement omits all three
and keeps the defaults (January 1, 2026; signed December 15, 2025; invoiced monthly in arrears).
`expected_classifications.json` is unchanged: it holds the four cases that are backed by an order
line, and Notability has none.

## The pricing schedule carries the escalator

`2026-09/CTR-002-PRICING-SCHEDULE.pdf` is the pricing exhibit to the OpenAI agreement. The base
rate is $0.016 per API call and a 25 percent escalator lifts it to $0.020 per API call from
September 1, 2026 - which is why every OpenAI document in the corpus, from the September invoice
on, bills $0.02 per unit. `CTR-002` prints the escalated rate and calls the unit an "API usage
unit"; the schedule calls the same unit an "API call". The schedule is filed in `2026-09` with the
agreement it belongs to, and prints no issue date of its own, so it is known from the first day of
that month.

| Label | Meaning |
| --- | --- |
| SCHEDULE ID | the document id |
| LINKED CONTRACT | the agreement this schedule prices |
| VENDOR / CUSTOMER | the two parties, as on the agreement |
| BASE RATE | the rate before the escalator |
| ESCALATOR | the percentage the escalator adds |
| ESCALATOR EFFECTIVE DATE | the day the escalated rate starts |
| RATE AFTER ESCALATOR | the rate in force from that day; this is the rate `CTR-002` prints |
| PRICING TERMS | the two priced clauses, verbatim |

## Replies: `replies/` answers the close, `afterclose/replies/` answers the settlement

A reply is a plain-text file named `REPLY-<outreach key>.txt`, with the same four header lines as
the first reply in the corpus (`From`, `To`, `Date`, `Subject`) and the answer itself below a blank
line. The outreach key is `<vendor>-<period>-<topic>`, so the file name says which question it
answers. Which folder a reply belongs to is a question of when it arrived:

- `2026-12/replies/` is read a few days into January, while December is still being closed.
  `REPLY-OPENAI-2026-12-USAGE_CONFIRMATION.txt` (January 2, 2027, from the engineering service
  owner, confirming 930,000 API calls for the full month) and
  `REPLY-ASUS-2026-12-IN_SERVICE_DATE.txt` (January 4, 2027, from the operations owner, who cannot
  give in-service dates yet) both land there.
- `2026-12/afterclose/replies/` is read in the second half of January, after December has settled.
  It holds the Mintlify variance reply described above and
  `REPLY-META-2026-12-INVOICE_DISPUTE.txt`, in which Meta's ads billing accepts that the campaign
  ran $24,700.00 and voids the $30,000.00 invoice. That reply is dated February 2, 2027, which is
  later than the rest of this folder: the dispute it answers is raised after the December invoice
  arrives in January.

## The company documents: close policy and general ledger

Two documents belong to Orbit Labs itself rather than to a vendor, so their entries live in a
`"company_documents"` array in `classification_input.json` rather than inside a case. Each entry
names its own `"folder"`.

### `2026-09/POLICY-ORBIT-CLOSE.pdf` - the close policy

The rulebook a close reads about itself: the only accounts a journal entry may use, the amounts
above which a human has to look, the line between an expense and an asset, the rules a close is
checked against, and the two people it writes to. It is filed in `2026-09` and prints
`ISSUE DATE 2026-09-01`, the start of the first accounting period the corpus covers, so it is in
force for every month in it.

| Label | Meaning |
| --- | --- |
| POLICY ID | the document id |
| ISSUE DATE | the day the policy is in force from |
| CUSTOMER | the company the policy governs |
| REPORTING CURRENCY | the currency every amount in the corpus is stated in |
| ACCOUNTING BASIS | `ACCRUAL`: cost belongs to the month the service was received |
| CLOSE CYCLE | `CALENDAR_MONTH`: one close per calendar month |
| CHART OF ACCOUNTS (table) | `Account code`, `Account name`, `Account type` - the only accounts a journal entry may post to |
| APPROVAL AND MATERIALITY THRESHOLDS (table) | `Threshold`, `Threshold key`, `Amount` - above "Controller review above" a case needs the Controller, above "Mandatory review above" review cannot be waived, below "De minimis" a case is not worth an entry |
| CAPITALIZATION THRESHOLD | an order of like items at or above this amount is an asset, not an expense |
| USEFUL LIFE | the months a capitalized asset is depreciated over, straight-line, from the day it is placed in service |
| ACCRUAL POLICY (table) | `Rule ID`, `Rule` - the rules POL-01 to POL-08, which carry no parameters of their own |
| FINANCE ROLES | `CONTROLLER` and `DEFAULT AP OWNER`, each printed as person id, name with role, and e-mail |

### `<month>/GL-ACCRUALS-<month>.pdf` - the general ledger extract

The prior history a close is graded against: what was accrued at a month end, the entry that
reversed it, and the invoice that finally arrived. There is one extract per month in which the
ledger was posted to - `2026-10`, `2026-11` and `2026-12` - and each is filed in the folder of its
own posting month, because that is when it could have been run. `GENERATED AT` is the last posting
date the extract contains. The December extract holds only November's reversals and November's
invoices, so it tells a December close nothing about December.

| Label | Meaning |
| --- | --- |
| REPORT ID | the document id |
| REPORTING PERIOD | the posting month the extract covers |
| CUSTOMER | the company whose ledger it is |
| STATUS | `Final`: the month's postings are complete |
| PREPARED BY | the function that produced the extract |
| GENERATED AT | the last posting date in the extract |
| ENTRY ID | the ledger entry's id |
| POSTING DATE | the day the entry hit the ledger |
| PERIOD | the accounting period the entry is recorded in, which for an entry posted early in a month is the month that just opened |
| VENDOR | the vendor the entry is about |
| ENTRY TYPE | `AP_INVOICE`, `ACCRUAL`, `ACCRUAL_REVERSAL` or `MANUAL_ADJUSTMENT` |
| ENTRY STATUS | `POSTED`, or `REVERSED` for an accrual a later entry reversed |
| REVERSAL OF | the entry this one reverses; printed only when there is one |
| ENTRY DESCRIPTION | the entry's description, which each of its lines repeats |
| lines table | `Account`, `Debit`, `Credit` - one row per journal line, in the order the entry holds them |

## Regenerating

`python startup/minimal_data/generate_pdfs.py` rewrites the whole corpus in place. Every PDF
carries a generation timestamp, so a full run changes every file even when no content changed;
pass an output directory - `python startup/minimal_data/generate_pdfs.py /tmp/fixture_build` - to
render the corpus somewhere else and copy across only the documents you meant to change.
