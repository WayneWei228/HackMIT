# BenchRec vs. the Maximor cash reconciliation task

Dataset: [BenchRec: A Real-World Cash Reconciliation Dataset](https://www.kaggle.com/datasets/benchmarkteam/benchrec-real-world-cash-reconciliation-dataset) (CC BY 4.0, from the ICAIF 2023 competition).
Downloaded and profiled on 2026-09-19.

## Verdict

BenchRec is a good **benchmark** for one piece of the task: matching bank lines to the general ledger (GL) with a very high precision bar.
It is **not enough** for the task as written: it has no invoices, no Stripe or Adyen data, no labeled fees, almost no duplicates, and no text you can read.
Use it for evaluation and credibility, and pair it with a synthetic company dataset that covers the scenarios in the brief.

## What's in it

| File | Rows | Notes |
|---|---|---|
| `train.csv` | 149,854 (80,879 GL "A" + 68,975 bank "B") | Labeled: `matchId`, `matchRule`, `targetAllocation` |
| `eval.csv` | 69,171 (37,123 A + 32,048 B) | Unlabeled |
| `solution.csv` | 32,048 B | Ground truth for eval; 212 have no match, 1,779 map to more than one allocation |
| `MatcherByChatGPT_submission.csv` | 32,048 | Baseline with confidence and explanation columns |

- Source: an obfuscated production reconciliation from a Tier 1 bank.
- One account (`ACC#00001`), USD only; train dates are mostly 2022-2023, eval runs Dec 2022 to May 2023.
- Amounts are treasury-sized: the median bank line is about $1.28M.
- The task: for each bank line, predict the GL allocation key or keys, or leave it unmatched. An answer counts as correct if it equals the true set or is a subset of it.
- The bar: **99.8% precision**, then maximize match rate.
- Match shapes in train: 47,024 are 1:1, and about 9,000 involve more than one row on at least one side. The largest group has 134 A rows and 172 B rows, and some groups are A-only or B-only (internal offsets).
- About 44% of train rows were matched by hand (`MANUAL`), so the hard cases are in the data.

## Baseline to beat

I scored the bundled ChatGPT matcher (TF-IDF plus amount and date tolerance) against `solution.csv`:
- **precision 99.45%**, which is below the 99.8% bar
- **match rate 65.0%**

So there is clear room to beat it, and a result like "99.8%+ precision at X% match rate" is a concrete number to put on a demo slide.

## Coverage of the brief

| Scenario in the brief | In BenchRec? |
|---|---|
| One payment covering three invoices | Partly. It has many-to-one GL groupings, but no invoice or AR records. |
| Wire received net of bank fees | Weak. About 1,500 matches are off by $100 or less (many by $0.01), but no fee is labeled as a fee. |
| Refund posted twice | No. Only 2 bank rows share amount, date and reference. |
| $12.40 difference nobody can explain | Implicit. About 3,200 matched groups don't net to zero, with no explanation attached. |
| Stripe or Adyen payouts vs. orders and deposits, net of fees and chargebacks | **No.** There is no processor, order or chargeback data. |
| Readable descriptions for LLM reasoning or audit notes | **No.** Reference text is scrambled into dictionary words (`VOLERY 3235963666FP`, `TUP ...REAVOWED/WAMP/C`). |
| Multi-entity, multi-currency | **No.** One account, USD only. |

## What this means for a HackMIT entry

The Maximor judges said a cash-only point solution is "very meh" and to go for AP/AR and accruals.
Their criteria are ambition, autonomy, difficulty, frontier tools and a working demo.

Suggested approach:
1. **Simulate a company** (the judges suggested this). Generate a synthetic ledger with customers, invoices, Stripe payouts (with fees, refunds and chargebacks), bank feeds and vendor bills.
   Inject the brief's edge cases with ground-truth labels: a 3-invoice lump payment, a wire net of fees, a duplicate refund, and a $12.40 variance.
2. **Use BenchRec as the external benchmark.** Report precision and match rate against real bank data and beat the 99.45% / 65% baseline at 99.8% precision.
3. **Reach past cash.** Tie unmatched items into AR (chase the customer), AP (short-paid bills) and close (post the fee journal entry, write up the variance).
   Include human escalation, memory ("this customer always pays net of a $25 wire fee"), and a pause-and-resume flow while waiting on a human.

Other sources worth checking for synthetic scenarios: Stripe's test-mode balance transactions and payout reports.
