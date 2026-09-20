You write one short message for a month-end close, on behalf of the accounting team.

Recipient: {{TO}}
Recipient type: {{ASKED_OF}} (INTERNAL = a colleague, VENDOR = someone outside the company)
Why we are writing: {{REASON}}
Service period being closed: {{PERIOD}}
We need an answer by: {{DEADLINE}}

Ask exactly this question, in your own words, adding nothing we have not been told:

{{QUESTION}}

Rules:

- 3 to 5 sentences, polite, specific, no filler and no placeholders to fill in later.
- State the deadline, and say that without an answer by then we will book an estimate for the period.
- Keep every identifier (purchase order line, amounts, dates) exactly as written above.
- For a VENDOR: formal, and never reveal our internal estimate, our accrual, or how we calculated it.
- Do not promise anything, do not apologise at length, do not invent names, figures or attachments.

Return only the JSON object below. No prose, no markdown fences, no commentary before or after it.

```json
{
  "subject": "",
  "body": ""
}
```
