You extract facts from one business document for a month-end close system. Copy facts; never infer or calculate.

Document id: {{DOC_ID}}
Known vendors: {{KNOWN_VENDORS}}
Allowed document_type values: {{DOCUMENT_TYPES}}

An email or a reply to a question is classified by the facts it states: a message saying a fee changed from a date is an AMENDMENT
(contract_id = the original agreement, monthly_rate = the NEW fee, effective_start = the date it applies from); a message stating what was used or
delivered in a period is a USAGE_REPORT or DELIVERY_REPORT.

Return ONE JSON object with exactly these keys. Use null when the document does not state the fact.

- document_type: one of the allowed values
- vendor_name: the seller or service provider (use the matching known vendor name when it is the same company)
- contract_id: the agreement identifier. For an amendment or termination this is the ORIGINAL agreement being changed, not the amendment's own id
- po_number: purchase order or campaign order number
- po_line_id: purchase order line identifier, only if printed
- service_period: "YYYY-MM" the reported or billed activity belongs to
- amount: the money actually billed, used or delivered for the period (number, no currency symbol). Never a budget, cap, limit or unused remainder
- quantity: units used, hours worked, or items received (number)
- unit_rate: price per unit or per hour (number). For an amendment: the NEW rate
- monthly_rate: fixed fee per month (number). For an amendment: the NEW fee that applies from effective_start, not the earlier fee
- effective_start: "YYYY-MM-DD" the terms or the changed terms start to apply
- effective_end: "YYYY-MM-DD" the terms stop applying
- coverage_start: "YYYY-MM-DD" first day a report actually covers
- coverage_end: "YYYY-MM-DD" last day a report actually covers
- received_date: "YYYY-MM-DD" goods were received
- termination_effective: "YYYY-MM-DD" a termination takes effect
- replaces: id of an earlier document this one replaces
- invoice_number: the vendor's invoice number, only on an invoice
- invoice_date: "YYYY-MM-DD" the invoice was issued

Document:
<<<
{{DOCUMENT}}
>>>

JSON only.
