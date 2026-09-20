You are choosing how to estimate one vendor's usage for a month-end accrual when the data for the period is incomplete.
We asked the service owner for the full-period usage and got no reply before the deadline, and the reporting period cannot wait longer.
Pick the projection method that best fits the facts below. A separate program will do all the arithmetic and check every parameter you give against the source records.

Rules:
- Choose exactly one method from the catalog. Do not invent a method.
- Never write a money amount, a unit count or a projected total. Give only the method, the day counts and the period names listed in the facts.
- `covered_days` and `period_days` must be copied from the facts.
- `history_periods` lists the prior periods the method uses, copied from the facts. Leave it empty for LINEAR_SCALE_TO_PERIOD. PRIOR_PERIOD_RUN_RATE uses only the latest prior period.
- Say why you chose the method in one or two plain sentences, and for every method you did not choose give one short reason.
- `confidence` is LOW, MEDIUM or HIGH: how far this projection can be trusted given how much of the period the data covers.

Catalog:
{{CATALOG}}

Facts:
{{FACTS}}
