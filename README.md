# HackMIT - TrueUp
## Validation

### Two approaches

Before an accountant can book an accrual, someone has to pull the documents that
back up the number. We built a keyword baseline for that first: accept a
document if it mentions the vendor, a dollar amount and the period. Fast, free,
no model. Then we tried an LLM judge that actually reads each document and
decides whether it supports the accrual.

Both are scored against a relevance key we wrote by hand. Every case shows 10
files and only 3-4 of them matter, and the wrong ones aren't obvious --
superseded order forms, last quarter's invoice, a different company with a
similar name. All documents are synthetic and the upstream systems are
simulated.

    uv run python scripts/eval_ingestion.py --judge rule
    uv run python scripts/eval_ingestion.py --judge llm

| Vendor | Keyword rules F1 | LLM judge F1 |
|---|---:|---:|
| Mintlify | 0.67 | 0.67 |
| OpenAI | 0.33 | 1.00 |
| ASUS | 0.80 | 1.00 |
| Meta | 0.80 | 1.00 |
| Notability | 0.75 | 1.00 |
| **Mean F1** | **0.670** | **0.933** |

And on three vendors the pipeline had never seen:

| Vendor | Precision | Recall | F1 |
|---|---:|---:|---:|
| Terrastack Compute | 0.80 | 1.00 | 0.89 |
| Larkspur Design Studio | 1.00 | 1.00 | 1.00 |
| Corvid Security | 0.60 | 1.00 | 0.75 |
| **Mean F1** | | | **0.880** |

The LLM column uses `openai.gpt-oss-120b-1:0` on Bedrock and needs your own
credentials; the judge samples, so the numbers shift between runs. The keyword
column is deterministic and runs offline with no API key.

### Why this matters

**The number we care about most is recall, not F1.** If the agent misses a
document, the accrual gets booked on incomplete evidence and someone finds out
in the next close, or an auditor finds out later. If the agent grabs one extra
document, a human spends thirty seconds ignoring it. Those two mistakes are not
the same size.

Across the five demo vendors there are 17 documents that genuinely support the
accrual. **The keyword baseline found 10 of them. The LLM judge found all 17.**
On the OpenAI case the baseline was worst: 1 of 4 documents, so three quarters
of the evidence for that accrual just never showed up.

On the held-out vendors the LLM hit **recall 1.00 on all three** -- every
relevant document, on companies it had never seen, with fake lookalike vendors
sitting in the same folder. Precision dips to 0.60 on Corvid, which means it
over-pulled a couple of files. We'll take that trade: over-pulling costs review
time, under-pulling costs a wrong number in the ledger.

Running the whole close end to end, the held-out vendors pass **53 of 55
checks** (`scripts/run_holdout.py --judge llm --extractor llm`), covering
detection, classification, estimation method, the accrual itself and the
variance diagnosis once the real invoice lands.

The bigger point is maintenance. Keyword rules assume documents look the way you
expect. Every new vendor with a different invoice template is a new rule, and
nobody on a finance team wants to own a regex file. The LLM reads the document
instead, which is why it transfers to vendors it has never seen without anyone
touching the code.
