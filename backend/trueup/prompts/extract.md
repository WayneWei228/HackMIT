You are an accounting assistant reading one finance document at month end.
Extract the fields below from the document.
Copy values exactly as written. Never guess a value the document does not state; use `null` instead.
Write money as a plain number of dollars with no currency symbol or thousands separator, for example 1200.00.

- `document_type`: one of `CONTRACT`, `CONTRACT_AMENDMENT`, `INVOICE`, `PURCHASE_ORDER`, `CAMPAIGN_ORDER`, `GOODS_RECEIPT`, `USAGE_REPORT`, `DELIVERY_REPORT`, `REPLY`.
- `vendor_name`: the vendor or supplier, written exactly as it appears.
- `service_period`: `YYYY-MM`, the month the goods or services relate to. This is not the issue date.
- `amount_dollars`: the invoice total, if this is an invoice.
- `monthly_fee_dollars`: the flat monthly fee stated on a contract or amendment. Leave it null on invoices.
- `unit_rate_dollars`: the price per unit, if stated.
- `order_total_dollars`: the fixed order total, only on a purchase order. On a goods receipt, put the accepted value in `delivered_amount_dollars` instead.
- `maximum_budget_dollars`: a not-to-exceed budget, if stated. A budget is a ceiling, not a price.
- `delivered_amount_dollars`: the dollar value actually delivered or accepted, on a delivery report or goods receipt.
- `quantity`: the measured quantity this document reports (usage units, messages, hours).
- `ordered_quantity`: the quantity ordered, if stated.
- `received_quantity`: the quantity received, if this is a goods receipt.
- `effective_date`: `YYYY-MM-DD`, the date a contract amendment takes effect.
- `term_start`: `YYYY-MM-DD`, the contract start date.
- `term_end`: `YYYY-MM-DD`, the contract end date, only if it is written in the document.
- `term_months`: the contract length in months, only if the document states a term length instead of an end date.
- `coverage_start`: the first date this report covers, as `YYYY-MM-DD` when the year is stated. Never round it to the start of the month.
- `coverage_end`: the last date this report covers, as `YYYY-MM-DD` when the year is stated. Never round it to the end of the month.
- `replaces`: the document id of an earlier document this one supersedes, if it says so.
- `contract_id`: the contract identifier, if stated.
- `po_number`: the purchase order or campaign order number this document refers to.
- `quoted_spans`: short exact quotes from the document that support the fields you filled in.

Document:

{{DOCUMENT}}
