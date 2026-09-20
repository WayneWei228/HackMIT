The finance team ordered goods, no goods receipt is on file, and the receiving owner did not answer the request before the reporting deadline.
The books must still close, so the team estimates how many units arrived.
Choose the estimation method for the received quantity from the catalog below.

Rules:
- Choose only a method from the catalog. Do not invent one.
- Never state a quantity, a unit count or an amount. Code computes them from the records.
- `history_sources`: for TYPICAL_ORDER_AVERAGE, the ids of the earlier receipts you want averaged, copied exactly from the facts. Leave it empty to use all of them. For CONSERVATIVE_ESTIMATE leave it empty.
- Prefer TYPICAL_ORDER_AVERAGE when earlier receipts exist, because it rests on recorded facts. Use CONSERVATIVE_ESTIMATE only when it is the sole option or the earlier receipts are clearly not comparable, and say why.
- `rationale`: one or two sentences.
- `rejected`: every other catalog method with a short reason it was not chosen.
- `confidence`: LOW, MEDIUM or HIGH in how well the chosen method fits these facts.

Catalog:
{{CATALOG}}

Facts:
{{FACTS}}
