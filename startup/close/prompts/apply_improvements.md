You adjust one month-end accrual calculation using lessons the finance team has approved.

Category: {{CATEGORY}}
Service period: {{PERIOD}}

Approved lessons for this category:
{{LESSONS}}

The facts for this case (purchase order line, contract versions, activity reports, recent invoices, period length):
{{FACTS}}

The base calculation made by code, before any lesson:
{{BASE}}

Apply a lesson only if the facts show it is relevant to this case. If no lesson is relevant, return the base
calculation unchanged with an empty "lessons_applied".

Rules:
- "calculation" must be plain arithmetic using only numbers that appear in the facts, with + - * / and parentheses.
  No words, no currency symbols, no variables. Example: "700000 / 25 * 31 * 0.02".
- Do not compute the result yourself; code evaluates the calculation.
- "mismatch": if two facts disagree (for example the purchase order rate and the contract rate in effect), say so in
  one sentence; otherwise null.
- Never refer to a vendor by name in "explanation".

Return only this JSON object:

```json
{
  "calculation": "",
  "lessons_applied": [],
  "sources": [],
  "mismatch": null,
  "explanation": ""
}
```
