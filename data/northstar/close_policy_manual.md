# Northstar Analytics - Vendor Accrual and Close Policy (v1.0)

Owner: Controller (Dana Whitfield). Applies to all vendor spend for NS-US and NS-UK.

## 1. When to accrue
1.1 Accrue an expense when a service was received in the period and no valid invoice was received by the close cutoff (5th calendar day after month end).
1.2 Do not accrue when the service was not received, or when the cost was already invoiced in advance and sits in Prepaid Expenses (1300).
1.3 An invoice received by the cutoff for the period's service is booked at its actual amount, not estimated.
1.4 An invoice covering more than one period is allocated by calendar days of the stated service period.

## 2. Allowed estimation methods
| Method | Required evidence |
|---|---|
| FIXED_CONTRACT_FEE | Active contract with a stated fee; service period |
| USAGE_X_RATE | Usage, seat, hours or hire record for the period; valid contract rate |
| PRORATED_FEE | Contract fee; service start and end dates |
| PO_BASED | Approved PO; goods or service receipt |
| HISTORICAL_RUN_RATE | At least 3 prior invoices. Only when the estimate is under $10,000 and the last 3 invoices vary by under 10% |
No other method may be used. An owner's verbal estimate is not a method; it is evidence for a Controller decision.

## 3. Evidence of service received
At least one of: usage or seat record, approved timesheet, HR start record, goods receipt, or written confirmation from the operational owner. An unanswered request is not evidence.

## 4. Approval thresholds (per obligation)
| Amount | Requirement |
|---|---|
| Under $10,000, confidence at least 0.85 | May be prepared without individual review; batch review |
| $10,000 to $24,999.99 | Reviewer (Accounting Manager) approval |
| $25,000 and over | Controller approval |
Any amount with low confidence, conflicting evidence, or no allowed method: escalate; do not post.

## 5. Posting controls
5.1 Entries must balance and may only post to an OPEN period.
5.2 One active accrual per vendor obligation per period. Duplicate invoices (same vendor, PO, amount and service period) are held, not posted.
5.3 Vendor, entity, cost center, account, period and obligation ID are mandatory. The entity on the invoice must match the contracting entity.
5.4 Accruals auto-reverse on the first day of the next period. Costs still unbilled at the next close are re-accrued.

## 6. True-ups
A difference between accrual and invoice above the greater of $500 or 2% requires a documented root cause. An unaccrued prior-period invoice of $25,000 or more goes to the Controller.

## 7. Outreach
Ask the person or system most likely to know: operational owner (was it received), requester or PO owner (did scope or rate change), AP (is it already in the queue), vendor billing contact (where is the invoice, what is the price), Controller (which treatment). Allow 48 hours, then try the next-best source or escalate before the cutoff.

## 8. Changes to this policy
New or changed rules must be replay-tested against prior periods and approved by the Controller before activation. No rule may lower a threshold in section 4 or remove a control in section 5 without Controller approval.
