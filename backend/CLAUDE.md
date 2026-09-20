# TrueUp backend: conventions for every agent session

## Stack
- Python 3.12+, managed with `uv` (`uv sync`, `uv run pytest`). `pyproject.toml` is the single dependency list.
- FastAPI + SQLite (SQLAlchemy 2.x) + pydantic v2. The frontend lives in `../frontend/web`.
- Lint with `ruff`, test with `pytest`. Run both before every commit. CI runs them on every PR.

## Rules
- All money is integer cents. Never use floats for currency.
- Every model call goes through `trueup/gateway/llm.py` (Claude). Every Jev call goes through `trueup/gateway/jev.py`. Never call either anywhere else.
- A language model never outputs a dollar amount. Amounts come only from `trueup/estimators`.
- Every proposed journal entry must carry `evidence[]` and balance exactly. `ProposedJE` enforces both.
- Agents must never read `future_invoices`. It is the simulator's answer key.
- `improvements.md` is generated from `learning_entries`, never edited by hand.
- A learning entry becomes part of the playbook only after `learning.replay_gate` passes.
- Deterministic code needs unit tests with fixtures. Keep the test suite runnable with no API keys.
- Label all data as synthetic and all upstream systems as simulated.
- Prefer small, readable modules over clever abstractions.
