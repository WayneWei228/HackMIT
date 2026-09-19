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
