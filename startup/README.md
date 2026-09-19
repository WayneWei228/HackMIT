# Startup Accrual Demo Data

This sample represents a roughly 100-person B2B software startup. It uses expenses that founders, finance teams, and judges can recognize immediately.

## When to record an accrual

Record an accrual when:

1. The company received the service or goods during the period.
2. A valid invoice was not available by the close cutoff.
3. The amount can be reasonably estimated from a contract, usage record, timesheet, purchase order, or other evidence.

If the invoice has already arrived, record the invoice. If service was not received, do not accrue. If the company paid in advance, record or amortize a prepaid expense instead.

## Main fee categories

Use two dimensions to classify a fee:

- **Timing:** recurring or event/project-based.
- **Amount:** fixed or variable.

| Category | Familiar startup expense | How the fee works | Example month-end treatment |
|---|---|---|---|
| Recurring fixed | Office rent | Same contractual amount every month | December service received, invoice missing: accrue $25,000 |
| Recurring fixed | SaaS or data platform | Fixed monthly subscription | Monthly contract fee is $18,000: accrue $18,000 |
| Recurring variable | Cloud infrastructure | Amount changes with measured usage | Usage report shows $72,400: accrue $72,400 |
| Recurring variable | Per-seat support software | Active seats multiplied by the contracted rate | 120 seats x $85: accrue $10,200 |
| Recurring hybrid | Cloud or data provider | Fixed commitment plus usage overage | $40,000 commitment plus $7,500 overage: accrue $47,500 |
| One-time fixed | Security audit | Fixed fee earned when a milestone is completed | Audit phase completed, invoice missing: accrue $30,000 |
| One-time fixed | Conference sponsorship | Fixed fee for a delivered event | December event completed: accrue $20,000 |
| One-time variable | Consulting project | Approved hours multiplied by the contract rate | 140 hours x $185: accrue $25,900 |
| One-time variable | Outside legal counsel | Hours and attorney rates vary | Evidence supports a range rather than an exact amount: request support or escalate |
| Event-based | Recruiting agency | Fee becomes due when a candidate starts | 20% x $150,000 salary: accrue $30,000 |
| Event-based | Printing or marketing production | Fee becomes due when goods are delivered | Materials received under an $8,000 PO: accrue $8,000 |
| Prepaid comparison | Annual security software | Paid before the service period | $96,000 paid upfront: amortize $8,000 per month; do not create a new accrual |

Proration, scheduled price increases, tiered rates, and contract termination are modifiers to these categories. Invoice conditions such as late, missing, duplicate, or incorrectly billed are also separate from the fee category.

## Recommended demo vendors

| Vendor | Expense | Fee pattern | Normal amount | Evidence used for an accrual |
|---|---|---|---:|---|
| CityCenter Offices | Office rent | Recurring fixed | $25,000/month | Lease and proof the office remained occupied |
| DataStream | Market data platform | Recurring fixed with an annual increase | $50,000, then $52,500/month | Contract, effective pricing schedule, and service activity |
| CloudCore | Cloud hosting | Recurring hybrid | $60,000-$80,000/month | Usage report and contract rate card |
| SupportFlow | Customer-support software | Recurring variable per seat | About $10,000/month | Active-seat report and price per seat |
| BrightPath Consulting | Implementation consulting | One-time variable | About $25,000/month during the project | Approved timesheets and hourly rate |
| TalentBridge Recruiting | Recruiting fee | Event-based variable | About $30,000 per hire | Employee start record and fee percentage |
| ExpoWorks | Event materials | One-time fixed | $8,000 | Purchase order and goods receipt |
| SecureShield | Security software | Annual prepaid | $96,000/year | Invoice, payment record, and service term |

## Primary learning scenario

DataStream historically charges $50,000 per month. Its pricing schedule raises the fee by 5% on December 1, making the effective monthly price $52,500.

At the December close, the invoice is missing. The initial process reads the old order-form price and accrues $50,000. The invoice later arrives for $52,500, creating a $2,500 true-up. The system identifies that it failed to check pricing effective for the service period and proposes a reusable rule:

> For a recurring fixed fee with a scheduled price change, retrieve and verify the price effective during the service period before calculating the accrual.

The rule can then transfer to another vendor with a pilot-to-production price change without depending on the DataStream vendor name.
