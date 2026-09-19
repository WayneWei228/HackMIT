# Startup Sponsor Vendors

Assume we are a 100-person AI startup and the HackMIT sponsors are companies we buy products or services from.

These are four simple, realistic examples. The amounts are fictional demo values, not the vendors' actual prices.

| Fee category | Vendor | What we buy | Example cost | One issue | How the system handles it |
|---|---|---|---:|---|---|
| Recurring fixed | Mintlify | Documentation website for our developers | $1,200 per month | The contract price increased to $1,400 | Check the effective contract price and accrue $1,400. |
| Recurring variable | OpenAI | API usage for features inside our product | $18,600 for December | The December usage report is incomplete | Request the missing usage data and wait before finalizing the accrual. |
| One-time fixed | ASUS | 25 laptops for new engineers | $40,000 once | Only 20 laptops arrived by year-end | Record only the 20 received laptops: 20 x $1,600 = $32,000. |
| One-time variable | Meta | Advertising for a product-launch campaign | $24,700 for the campaign | The budget is $30,000, but only $24,700 of ads were delivered | Record the $24,700 delivered amount rather than the full budget. |

The four main patterns are:

1. **Recurring fixed:** happens repeatedly and normally costs the same amount.
2. **Recurring variable:** happens repeatedly, but the amount changes with usage or quantity.
3. **One-time fixed:** happens once and has a known agreed price.
4. **One-time variable:** happens once, but the final amount depends on completed activity.

For the demo, invoice timing can be changed separately. Any of these invoices can arrive on time, arrive late, be missing, or contain the wrong amount without changing the underlying fee category.

## Prepaid example

**Notability:** We pay $21,600 in advance for a 12-month team subscription.

- The payment is recorded as a prepaid asset.
- The system spreads the cost across the 12 service months.
- Monthly expense: $21,600 / 12 = **$1,800**.
- The issue: someone tries to expense the full $21,600 in the first month.
- The system uses the contract service dates to keep $19,800 in prepaid expense after the first month and record only $1,800 as expense.

## Asset example

The ASUS purchase also tests asset accounting when the company's capitalization policy applies.

- Only 20 laptops were received by year-end, so the recorded asset cost is **$32,000**.
- The other five laptops are not recorded until they arrive.
- The system adds the received laptops to the fixed-asset schedule.
- Their cost is spread over their useful life beginning when they are placed in service.
- The purchase order and goods receipt support the asset balance; the asset schedule supports monthly depreciation.

## Vendor-related balance-sheet evidence

| Balance-sheet account | Example | Evidence |
|---|---|---|
| Accrued expenses | Mintlify, OpenAI, or Meta bill not yet received | Contract, usage or delivery report, calculation, and approval |
| Prepaid expenses | Notability annual subscription | Invoice, payment record, contract dates, and monthly prepaid schedule |
| Fixed assets | ASUS laptops | Purchase order, goods receipt, asset register, and depreciation schedule |
| Accounts payable | Vendor invoices received but not yet paid | Invoice, AP record, approval, and vendor balance |

## Close status

Each item receives a simple status:

- **Done:** evidence is complete and the amount is recorded.
- **Waiting:** the system requested missing information.
- **Blocked:** the invoice or evidence does not agree.
- **Needs review:** a human must approve the amount or treatment.

The scope of this demo is vendor-related close work: book supported accruals, spread prepaid and asset costs, connect vendor-related balances to evidence, and show what is done or stuck.
