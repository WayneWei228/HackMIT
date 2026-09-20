# TrueUp backend

Month-end accrual agents for a simulated 100-person startup.
Each close the agents detect what the company owes for vendors it has not been billed for, classify each purchase, estimate the accrual with deterministic models and book evidence-backed journal entries.
When the real invoice arrives, the learning agent grades the estimate and records why it missed.

All data is synthetic and every upstream system (ERP, e-procurement, contracts, card issuer) is simulated.

## Run

```
uv sync
cp .env.example .env
uv run pytest
uv run uvicorn trueup.api:app --reload
```

The suite and the server run with no API keys.
Without `TYPESAFE_API_KEY` the classifier runs on its rules only.
The LLM is OpenAI. Set `OPENAI_API_KEY`, or `AWS_BEARER_TOKEN_BEDROCK` to use OpenAI's gpt-oss on AWS Bedrock (region `AWS_REGION`, default us-east-2).
Set `MODEL_ID` to override the model. Never commit these values.

## Layout

| Path | Role |
|---|---|
| `trueup/gateway/` | `llm.py` (OpenAI), `jev.py` (Jev classifier), `tracing.py` |
| `trueup/db.py`, `schemas.py` | Source-system tables, agent output tables, shared types |
| `trueup/datagen/` | Seeded simulator and hidden future invoices (the answer key) |
| `trueup/agents/` | Evidence (PDF to typed fields, cached by text hash), detection, invoice lookup, classifier, outreach, learning |
| `trueup/estimators/` | The only place a dollar amount is computed |
| `trueup/agents/estimation.py` | Chooses the estimator for a classified obligation |
| `data/startup/` | Demo documents: 14 PDFs, their source JSON, and the expected answers (from the `startup-output` branch) |
| `trueup/orchestrator.py` | Runs the agents in order and persists results |
| `trueup/api.py` | HTTP routes for the UI |

## Demo loop over HTTP

1. `POST /simulate/reset`, then `POST /simulate/release` for each month up to 2026-11.
2. `POST /close/run {"period": "2026-11"}`. Four items are done and Mintlify is flagged because the PO price disagrees with the contract.
3. `POST /simulate/release {"period": "2026-12"}`. The invoices arrive and the learning agent records what each estimate missed.
4. `GET /learning`, `GET /improvements`.

## Not built yet

- LLM narration of each estimate and LLM diagnosis with quoted evidence (the deterministic diagnosis is a placeholder).
- Wiring Evidence into the close: `ingest_manifest` and `apply_contract` exist and are tested, but the orchestrator does not call them yet.
- Applying adopted lessons inside the estimators (the playbook is recorded and versioned but not yet read by them).
- Signed-bias guard in the replay gate, and the backtest over historical data.
- Prepaid amortization, the fixed asset register and reversing entries.
- Email invoice intake.
- The Jev call has been unit tested with fakes only; it has not been run against a live `TYPESAFE_API_KEY`.

Attribution for the adapted Ledger Sentinel modules is in `NOTICE.md`.
