You read a colleague's free-text reply to a finance team's request for missing information at month end.
Extract only what the reply states. Never guess, infer or compute a value the reply does not contain.

- `resolved`: true only when the reply supplies the information the request asked for. A reply that says the information is not available yet, or is vague, is not resolved.
- `service_received`: true if the reply says the goods or services were received or delivered, false if it says they were not, null if it does not say.
- `quantity`: the quantity exactly as written in the reply, as a plain number without commas, or null. Do not add, sum or convert numbers. For goods received, this is the number of units the reply says arrived, never the number ordered or still outstanding.
- `unit`: the unit the quantity is measured in. Use one of the known units when the reply matches it, otherwise null.
- `in_service_date`: `YYYY-MM-DD`, only when the reply states a specific date, otherwise null.
- `corrected_amount`: for an invoice dispute only, the amount of the corrected invoice or credit memo the sender commits to, exactly as written in the reply and as a plain number without commas, otherwise null. Never use an amount the reply only mentions as wrong or as the original bill.
- `reason`: one short sentence saying why the reply is or is not enough.

Request topic: {{TOPIC}}
What was asked: {{QUESTION}}
Known units: {{UNITS}}

Reply:

{{REPLY}}
