# estimation-agent

Classifies vendor fees from finance PDFs using the Gemini API.

## What it does

Reads the 14 synthetic finance PDFs in `output/pdf/startup_minimal_data/`,
groups them by vendor, and classifies each fee as:

- `RECURRING_FIXED` / `RECURRING_VARIABLE`
- `ONE_TIME_FIXED` / `ONE_TIME_VARIABLE`

Output is written to `out/classifications.json`.

## Usage

```bash
python3 classify_documents.py \
  --repo-root <path-to-this-repo> \
  --api-key   <your-gemini-api-key> \
  --output    out/classifications.json
```

## Input PDFs

Located in `output/pdf/startup_minimal_data/`:

| Document | Vendor | Type |
|---|---|---|
| CTR-001.pdf | Mintlify | Contract |
| INV-MINTLIFY-SEP/OCT/NOV/DEC.pdf | Mintlify | Invoices |
| CTR-002.pdf | OpenAI | Contract |
| INV-OPENAI-SEP/OCT/NOV.pdf | OpenAI | Invoices |
| USG-OPENAI-DEC.pdf | OpenAI | Usage report |
| PO-003.pdf | ASUS | Purchase order |
| GR-ASUS-DEC.pdf | ASUS | Goods receipt |
| CAMPAIGN-004.pdf | Meta | Campaign order |
| META-DELIVERY-DEC.pdf | Meta | Delivery report |

## Output

`out/classifications.json` — one record per vendor case with category,
expected amount, and key evidence quoted from the PDFs.

---

## TrueUp backend (`trueup/`)

The `trueup/` directory on this branch contains the full agentic month-end
accrual backend: FastAPI + SQLAlchemy, 13 tables, 12 agent services, a seeded
company simulator, an 11-month historical backtest, and the replay-gated
learning loop that produces `trueup/out/improvements.md`.

The classifier above (`classify_documents.py`) established the four vendor cases
from the source PDFs. TrueUp reproduces all four to the cent as part of its
December 2026 close, then goes further: it posts balanced simulated journal
entries, waits for the later invoices to grade those estimates, diagnoses the
variances against recorded evidence, and replay-tests candidate rules before a
Controller may activate them.

```bash
cd trueup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q        # 44 tests, no API key needed
.venv/bin/python scripts/run_demo.py # baseline vs calibrated, 12 months
```

See `trueup/README.md` for the design decisions and measured results.
