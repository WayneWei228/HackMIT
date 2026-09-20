# TrueUp

An auditable, agentic month-end accrual system for the Office of the CFO.

At month-end a company must record expenses for goods and services it has already
received but not yet been invoiced for. TrueUp executes that workflow — it detects
the obligations, gathers source-backed evidence, calculates the accrual
deterministically, enforces policy, posts a balanced simulated journal entry, and
then waits.

The waiting is the point. When the real invoice arrives weeks later, it grades the
estimate. TrueUp compares, diagnoses the difference against the evidence it used,
proposes a typed rule to stop the failure recurring, replay-tests that rule
against its own history, and asks a Controller to approve it. Only then does its
behaviour change.

---

## The four claims, and where to see each one

| Claim | Where |
|---|---|
| **Execute** — detect, calculate, post | `python scripts/run_demo.py`, or `POST /close/2026-12/run` |
| **Identify failure** — the later invoice exposes the variance | `app/services/agents/reconciliation.py` |
| **Diagnose why** — root cause from recorded evidence | `trueup_learning_rules.root_cause_summary` |
| **Improve** — replay-tested, Controller-approved rule | `out/improvements.md` |

---

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Run the full demonstration — twelve months, twice, baseline versus calibrated:

```bash
.venv/bin/python scripts/run_demo.py
```

Run the test suite:

```bash
.venv/bin/python -m pytest -q
```

Serve the API:

```bash
.venv/bin/python scripts/serve.py
```

**No API key is required.** With `GEMINI_API_KEY` unset, TrueUp uses a
deterministic stub that returns the same shapes the real model does, and the
entire simulation and test suite run unchanged. To use the real model:

```bash
export GEMINI_API_KEY=your-key-here   # never commit this
.venv/bin/python scripts/run_demo.py
```

The model is `gemini-2.5-flash`. (There is no "Gemini 3.5 Flash"; 2.5 Flash is the
current Flash model and is what the original `classify_documents.py` in the source
repo used.) Running the December close against the live model produces **the same
amounts to the cent** as the stub — which is the design working: the LLM reads
text, deterministic code owns every number.

---

## What the system actually does

```
Detection ─→ Invoice Lookup ─→ Evidence ─→ Classification ─→ Estimation
                    │                                            │
                    │ (invoice already in AP)                    ↓
                    └──→ NO ACCRUAL                        Policy Enforcer
                                                                 │
                              ┌──────────────┬───────────────────┼─────────────┐
                              ↓              ↓                   ↓             ↓
                          PERMIT      REQUIRE_OUTREACH   REQUIRE_CONTROLLER  BLOCK
                              │              │                   │
                              ↓          Outreach            Controller
                      Journal Entry       Agent              Workspace
                       (simulated)            └──────┬────────────┘
                              │                      ↓
                              └──────────────→  post or refuse
                                                     │
                                          … weeks pass, invoice arrives …
                                                     ↓
                              Reconciliation & True-Up ─→ Learning Agent
                                                              │
                                              propose typed rule → replay →
                                              Controller approves → ACTIVE
```

---

## The five design decisions that matter

### 1. The LLM never owns a number

Available to every reasoning agent, authoritative for none. It extracts fields
from contract prose, cross-checks classifications, drafts outreach, parses
replies, and writes explanations. Every amount, every variance, every policy
verdict and every rule activation is deterministic code.

When the model disagrees with the deterministic classifier, TrueUp does not
average them or defer to the model — it records a `CLASSIFICATION_CONFLICT`
evidence card and escalates material cases. Disagreement is information.

### 2. The estimator is a pure function

```python
estimate(ctx: EstimationContext, active_rules: list[ActiveRule]) -> EstimateResult
```

No database, no clock, no model. That is what makes replay possible: rebuild a
historical context, run the same function with and without a candidate rule, and
diff. An estimator that queries the database cannot be replayed without rewinding
the database.

### 3. One chokepoint for the as-of cutoff

Every read of AP invoices, service evidence and non-PO spend goes through
`app/repositories/asof.py`, which requires an explicit `as_of` and filters on
arrival time. No agent queries those tables directly.

All twelve months of invoices sit in the database the whole time. The backtest
does **not** delete future rows — it relies on the guard, which is a far stronger
test. `tests/test_leakage.py` runs the same historical close twice, once against
the full database and once against one with every post-cutoff row physically
deleted, and asserts the two are identical workpaper by workpaper.

### 4. Money is `Decimal`, end to end

`Numeric(18,2)`, quantized to cents at every boundary, with a `Decimal`-aware JSON
encoder. Floats would produce debit/credit imbalances of 1e-14 that break the
double-entry validator and off-by-a-cent variance comparisons.

### 5. A learned rule is a typed record, not code and not prose

```json
{
  "rule_key": "verify_escalator_effective_rate",
  "scope":  {"purchase_types": ["USAGE_BASED", "FIXED_RECURRING"],
             "conditions": ["CONTRACT_ESCALATOR_EFFECTIVE_ON_OR_BEFORE_SERVICE_START"]},
  "action": {"action_type": "REQUIRE_EVIDENCE", "evidence_type": "EFFECTIVE_RATE"}
}
```

Scope predicates come from a closed enumeration. Actions come from a closed set of
five verbs. A rule may require evidence, require outreach, require Controller
review, prohibit an estimator, or select an already-approved one.

It may **not** set a dollar amount, name a specific vendor, weaken an approval
threshold, auto-post, change accounting policy, or override a blocking control.
These are enforced in `app/schemas/rules.py` — on the raw payload before Pydantic
touches it, so the audit message says *which* prohibition was attempted — and
re-checked when rules are read, when they are activated, and by the Auditor.

---

## How learning actually changes an amount

This is the subtle part, and it is deliberately indirect.

A rule is forbidden from naming a number. So how does one fix an under-accrual?

1. The baseline estimator resolves the unit rate as `contract.base_rate`. That is
   the naive read, and it is wrong whenever an escalator clause is already in
   force.
2. The later invoice exposes the gap. Reconciliation attributes it to
   `MISSED_ESCALATOR` — deterministically, by checking that the variance equals
   the escalator applied to the accrued amount.
3. The Learning Agent proposes `REQUIRE_EVIDENCE[EFFECTIVE_RATE]`, scoped to
   periods where an escalator is already effective.
4. With that rule active, the **Evidence Agent** runs a derivation it would
   otherwise skip: it computes the in-force rate from the contract's own
   escalator fields and puts it on the record as an evidence card.
5. The estimator binds that card instead of `base_rate`.

The rule changed which *fact* was required. The arithmetic did the rest. And when
the clause is incomplete — a percentage with no effective date — the derivation
fails, the fact stays missing, and the item escalates instead of being estimated.

---

## Historical calibration

TrueUp does not enter the live close as a blank agent. `scripts/run_demo.py`
replays eleven prior closes (2026-01 … 2026-11) under a strict cutoff, lets the
later invoices grade them, diagnoses the repeatable failures, replay-tests the
candidate fixes, and starts December with a Controller-approved improvement set.

Replay scores a candidate across three populations:

- **positive** — the rule fires; it must reduce error
- **negative** — the rule must not fire; *any* change is a regression
- **held-out** — vendor `V008` (Confluent) is excluded from rule derivation
  entirely and reported separately, because improving on data you learned from
  proves nothing

A candidate passes only if it fires somewhere, causes zero regressions, and either
reduces MAE **or** converts a materially-wrong automatic posting into an
escalation. That second path matters: a control that trades false confidence for a
human decision is a real improvement even though no number moves.

### Measured results (deterministic stub, reproducible)

Every metric `metrics.compare` produces for the live period, 2026-12 — including
the ones that did not move:

| Metric | Frozen baseline | Calibrated | Change |
|---|---:|---:|---|
| Mean absolute accrual error | 378.23 | **30.86** | −92% |
| Median absolute percent error | 0.00 | 0.00 | — |
| Total absolute variance | 5,295.26 | **432.00** | −4,863.26 |
| Material variance rate | 7.14% | 7.14% | unchanged |
| Duplicate-accrual rate | 0.00% | 0.00% | unchanged |
| False-autonomy count | 1 | 1 | unchanged |
| Autonomous-action precision | 90.91% | 90.91% | unchanged |
| Escalation rate | 25.00% | 25.00% | unchanged |
| Active rules | 0 | 1 | |
| Replay regressions | — | **0** | |

**Why four of those are flat, and why that is the right answer.** All three
trace to one case: a card-spend group where $432 of transactions posted *after*
the December cutoff. It is the single material variance, the single
false-autonomy case, and therefore the reason precision and escalation rate do
not move.

TrueUp diagnoses it correctly as `TIMING_DIFFERENCE` and then deliberately
declines to propose a rule for it. Transactions that post after a cutoff cannot
be seen at the cutoff — that is a calendar fact, not an estimation defect, and no
estimator rule could fix it without inventing an amount. The learned rule
addresses missed escalators, so it correctly leaves this case alone. A system that
moved this number would be one that had learned to guess.

The held-out vendor, which contributed nothing to deriving the rule, goes from a
baseline MAE of 135.15 to **0.00**.

Across the full year, 148 obligations re-perform clean under the Auditor, with 13
informational restatements quantifying what the learning is worth.

## What TrueUp refuses to do

This matters as much as what it does.

- **It will not invent an amount.** If required evidence is absent, it gathers,
  then asks a specific person for a specific fact, then escalates. A
  `HISTORICAL_RUN_RATE` fallback is used only where policy allows and is flagged
  as a fallback on the workpaper.
- **Silence is not evidence.** An unanswered outreach is written to the record at
  confidence 0.00 and escalates with nothing posted. When someone *does* answer,
  the figure is promoted to a proper evidence card attributed to that person, at
  lower confidence than a meter reading — so a human-attested number never
  masquerades as a measured one. Both paths are tested.
- **It will not choose between contradictory sources.** When Dell's PO says
  $2,400 per unit and its contract says $2,100, TrueUp records the conflict and
  blocks, rather than picking the cheaper, the newer, or the one the model likes.
- **It will not propose a rule it cannot justify.** One variance is an anecdote;
  a rule needs at least two independent cases. Root causes with no typed remedy —
  `TIMING_DIFFERENCE`, `SCOPE_CHANGE`, `DUPLICATE_NON_PO_ACCRUAL`, `UNKNOWN` — are
  diagnosed and escalated with the reason stated, never automated.
- **It does not claim autonomous ERP posting.** Every entry is
  `POSTED_SIMULATED`.
- **It stores no chain-of-thought.** `trueup_agent_runs` records what was read,
  which facts were used, which rule fired, what was decided and what remains
  uncertain. A reviewer can reconstruct any decision without seeing a monologue.

The seeded company includes a deliberately unexplainable case: AWS bills a
$12,400 "reserved capacity commitment adjustment" in 2026-08. The metered usage
line reconciles to the meter *exactly*, so nothing on the record explains the
difference. TrueUp labels it `UNKNOWN`, states why, and escalates — it does not
fit a rule to a coincidence.

---

## Data model

Thirteen tables, no generic workflow/task/document/event tables. Extracted PDF
facts live in `trueup_evidence` with `source_table`, `source_id` and a quoted
`source_excerpt`.

**Company sources** (standing in for ERP, e-procurement, CLM, card issuer and
operational systems): `company_vendors`, `company_contracts` (one row per
*version*), `company_purchase_orders`, `company_service_evidence`,
`company_non_po_spend`, `company_ap_invoices`, `company_gl_entries`,
`company_config`.

**TrueUp internal**: `trueup_obligations` (the case), `trueup_evidence`,
`trueup_workpapers`, `trueup_agent_runs` (append-only audit), and
`trueup_learning_rules` (outcome + true-up + diagnosis + candidate + replay +
lifecycle in one row, so a rule can never be separated from the evidence that
produced it).

---

## Seed data: what came from a document, what did not

`app/services/simulator/profile.py` marks every vendor and contract `PDF` or
`SYNTH`, because a reviewer should never have to guess.

**From the 14 source PDFs** in `seed/pdf/` — these drive the December close and
the Evidence-Agent extraction demo. TrueUp reproduces all four documented cases to
the cent:

| Vendor | Case | TrueUp accrues |
|---|---|---:|
| Mintlify | Fixed monthly plan (CTR-001) | 1,200.00 |
| OpenAI | 930,000 units × $0.02 (USG-OPENAI-DEC) | 18,600.00 |
| ASUS | 20 of 25 accepted × $1,600 (GR-ASUS-DEC) | 32,000.00 |
| Meta | Delivered advertising, not the $30k budget | 24,700.00 |

**Generated**, because the PDFs contain none of it and the spec requires all of
it:

- eleven months of prior closes (2026-01 … 2026-11)
- non-PO card spend, including voided, disputed, refunded, already-invoiced and
  after-cutoff transactions
- contract escalators (Snowflake 5%, Datadog 8%, Confluent 6%) — the repeatable
  failure the backtest exists to find
- **V008 Confluent**, held out of rule derivation entirely
- **V006 Datadog**, whose meter is chronically late, forcing the run-rate fallback
- **V009 AWS**, the unexplainable $12,400 adjustment
- **V011 Dell**, whose PO ($2,400/unit) contradicts its contract ($2,100/unit),
  exercising the conflict → Controller route
- **V012 Vanta**, onboarded in December with no meter *and* no history — the only
  honest route to outreach, since there is nothing to fall back on

`trueup/seed/pdf/` holds a copy of the 14 fixtures that also live at
`output/pdf/startup_minimal_data/` in this repo. The duplication is deliberate:
it keeps `trueup/` self-contained, so cloning the branch and running `pytest`
works without depending on paths outside the project. Point `TRUEUP_PDF_DIR` at
the repo copy if you would prefer a single source of truth.

PDF text extraction is pure stdlib (ASCII85 + Flate) — no poppler, no wheel that
might not build on a laptop at 3am.

---

## Layout

```
app/
  money.py                    Decimal handling; the only place amounts are coerced
  models/                     the 13 tables
  repositories/
    asof.py                   THE leakage boundary
    contracts.py              version selection by date overlap, never by status
    rules.py                  ACTIVE rules only, re-validated on read
  schemas/rules.py            typed rules + every forbidden-action guard
  services/
    estimators/
      context.py              frozen snapshot + enumerated scope predicates
      engine.py               the pure estimator (six methods)
      derivations.py          shared by the Evidence Agent and replay
      builder.py              DB → context, the only place the halves meet
    agents/                   detection, invoice_lookup, evidence, classification,
                              estimation, outreach, reconciliation, learning, auditor
    policy/enforcer.py        deterministic routing, eleven checks
    learning/replay.py        the gate a rule passes before a human sees it
    simulator/                seed, clock, backtest
    journal.py, controller.py, orchestrator.py, metrics.py
  api/main.py                 HTTP surface
tests/                        44 tests: 18 acceptance criteria, workflow paths,
                              leakage, API
scripts/run_demo.py           baseline vs calibrated, end to end
```

---

## Test coverage

```
tests/test_acceptance.py     the 18 spec criteria, named for what they prove
tests/test_workflow_paths.py outreach (answered and unanswered), contract-vs-PO
                             conflict, terminal-state guarantee, held-out protection
tests/test_leakage.py        the as-of guard, determinism, and the guard's own alarm
tests/test_api.py            HTTP surface against a real seeded database
```

All 44 pass with no API key.
