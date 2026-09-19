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
