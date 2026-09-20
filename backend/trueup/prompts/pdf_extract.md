You extract facts from one business document for a month-end close. Copy facts; never infer or calculate.

Document id: {{DOC_ID}}
Allowed document_type values: {{DOCUMENT_TYPES}}

An email or a reply to a question is classified by the facts it states: a message saying a fee changed from a date is an AMENDMENT
(contract_id = the original agreement, amendment_id = the amendment's own id, monthly_rate = the NEW fee, effective_start = the date it applies from);
a message stating what was used or delivered in a period is a USAGE_REPORT or DELIVERY_REPORT.

Use null when the document does not state the fact. Never substitute a default, a zero or a guess: a missing fact is null.

- document_type: one of the allowed values
- vendor_name: the seller or service provider. Never the buyer: the customer named on the document is never the vendor
- customer: the buyer the document is addressed to, as printed
- contract_id: the agreement identifier. For an amendment or termination this is the ORIGINAL agreement being changed, not the amendment's own id
- contract_text: the commercial clause that sets the price or rate, copied word for word
- po_number: purchase order or campaign order number
- po_line_id: purchase order line identifier, only if printed
- service_period: "YYYY-MM" the reported or billed activity belongs to
- description: the line or service description, copied word for word
- unit: the unit the quantity is counted in, as printed (e.g. "API usage units", "monthly service")
- status: the document's own status word, e.g. "PARTIAL", "FINAL", or a goods receipt's inspection note
- amount: the money actually billed, used or delivered for the period (number, no currency symbol). Never a budget, cap, limit or unused remainder
- quantity: units used, hours worked, or items received (number)
- unit_rate: price per unit or per hour (number). For an amendment: the NEW rate
- monthly_rate: fixed fee per month (number). For an amendment: the NEW fee that applies from effective_start, not the earlier fee
- accepted_value: the value a goods receipt states was accepted (number)
- effective_start: "YYYY-MM-DD" the terms or the changed terms start to apply
- effective_end: "YYYY-MM-DD" the terms stop applying
- coverage_start: "YYYY-MM-DD" first day a report actually covers
- coverage_end: "YYYY-MM-DD" last day a report actually covers
- received_date: "YYYY-MM-DD" goods were received
- termination_effective: "YYYY-MM-DD" a termination takes effect
- invoice_number: the vendor's invoice number, only on an invoice
- invoice_date: "YYYY-MM-DD" the invoice was issued
- issue_date: "YYYY-MM-DD" a buyer-issued order was issued
- generated_at: "YYYY-MM-DD" a report was generated
- replaces: id of an earlier document this one replaces
- amendment_id: an amendment's own printed id, which is never the agreement it changes

On a PURCHASE_ORDER (a purchase order or a campaign order: a buyer-issued order) also fill these, copying the
printed labels. Leave them null on every other document.

- order_type: "FO" when the order is a framework order, "NB" when it is a standard order
- validity_start / validity_end: "YYYY-MM-DD" the order's validity window, null when the order states none
- requester: the person who requested the order, as printed (e.g. "sam.lee")
- cost_center_owner: the cost-center owner, as printed
- approved_by / approval_date: the approver and the date of approval, as printed
- received_by: the person who signed for goods, as printed on a goods receipt
- lines: the order's line table, one object per printed line, each with exactly these keys:
  - po_line_id: the line identifier as printed (e.g. "PO-001-001"); a wrapped id is still one id
  - item_category: "P" for a service line, "B" or "E" for a limit line, "" for a standard line
  - contract_id: the contract linked to this line, else null
  - gr_required: true when the line says a goods receipt is required, false when it says it is not
  - quantity_ordered: the quantity ordered on the line (number), null when the line states none
  - unit_price: the price per unit or the fixed fee per period on the line (number), null when none
  - overall_limit: the line's overall limit / spending cap / maximum budget (number), null when none
  - line_description: the line's description, copied word for word

A narrow column can wrap a printed number across two lines: "$300,000.0" followed by "0" is one amount, 300000.00.

Document:
<<<
{{DOCUMENT}}
>>>

JSON only.
