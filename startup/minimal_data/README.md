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
