# How the System Recognizes the Four Fee Types

The system classifies a purchase using two questions:

1. Does the expense repeat, or is it connected to one purchase, project, or event?
2. Is the amount predetermined, or does it depend on activity?

This produces four types:

| | Fixed amount | Variable amount |
|---|---|---|
| Repeats | Recurring fixed | Recurring variable |
| Happens once | One-time fixed | One-time variable |

## 1. Recurring fixed

### What the system sees

- A bill from the same vendor this month and in at least the previous three months.
- The bills arrive at a regular interval, such as monthly.
- The service descriptions and service periods are similar.
- The amount is the same or nearly the same each month.
- A contract may say “$1,200 per month,” “annual subscription,” or “automatically renews.”

### Example: Mintlify

| Service month | Amount | Description |
|---|---:|---|
| September | $1,200 | Documentation platform subscription |
| October | $1,200 | Documentation platform subscription |
| November | $1,200 | Documentation platform subscription |
| December | $1,200 | Documentation platform subscription |

The repeated monthly pattern and unchanged amount indicate a subscription.

```text
Repeats regularly: YES
Amount changes with activity: NO
Classification: RECURRING_FIXED
```

## 2. Recurring variable

### What the system sees

- A bill from the same vendor this month and in at least the previous three months.
- The bills arrive at a regular interval, such as monthly.
- The amount changes from month to month.
- The invoice contains usage, seats, transactions, minutes, tokens, or another measurable quantity.
- A usage report and rate card can explain the amount.

### Example: OpenAI

| Service month | Amount | Description |
|---|---:|---|
| September | $14,200 | API usage |
| October | $16,800 | API usage |
| November | $15,500 | API usage |
| December | $18,600 | API usage |

The bill repeats every month, but the amount changes with API usage.

```text
Repeats regularly: YES
Amount changes with activity: YES
Classification: RECURRING_VARIABLE
```

## 3. One-time fixed

### What the system sees

- No regular invoice pattern exists for the vendor or purchase.
- The invoice is connected to one purchase order, delivery, or project milestone.
- The total price was agreed before delivery.
- The amount does not depend on hours, usage, clicks, or another changing quantity after the order is placed.
- A goods receipt or completion record confirms that the purchase happened.

### Example: ASUS

| Record | Value |
|---|---|
| Purchase order | 25 laptop packages |
| Agreed total price | $40,000 |
| Previous monthly bills | None |
| Delivery | One shipment for the hiring expansion |

This is one purchase with a known total price.

```text
Repeats regularly: NO
Amount changes with activity: NO
Classification: ONE_TIME_FIXED
```

If only 20 laptops arrive by month-end, the system records only the received portion. That is a delivery issue; it does not change the original fee type.

## 4. One-time variable

### What the system sees

- No regular monthly or quarterly pattern exists.
- The cost is connected to one project, campaign, event, or engagement.
- The final amount depends on completed activity.
- The activity may be consulting hours, delivered advertising, units produced, or another measurable result.
- A budget or PO may set a maximum, but it does not determine the final expense.

### Example: Meta

| Record | Value |
|---|---|
| Project | Product-launch advertising campaign |
| Campaign budget | $30,000 |
| Advertising actually delivered | $24,700 |
| Previous matching campaigns | None |

The campaign happens once, and its final cost depends on the advertising delivered.

```text
Repeats regularly: NO
Amount changes with activity: YES
Classification: ONE_TIME_VARIABLE
```

## Simple decision process

```text
Did the same vendor charge for the same service on a regular schedule?

YES -> Recurring
  Is the periodic amount fixed by the agreement?
    YES -> RECURRING_FIXED
    NO  -> RECURRING_VARIABLE

NO -> One-time
  Was the total price agreed in advance?
    YES -> ONE_TIME_FIXED
    NO  -> ONE_TIME_VARIABLE
```

## Data the system needs

The minimum useful finance data is:

| Field | Why it helps |
|---|---|
| Vendor ID and name | Groups transactions from the same vendor |
| Invoice date | Shows whether bills arrive regularly |
| Service-period start and end | Shows which month or project the bill covers |
| Amount | Shows whether the charge stays fixed or changes |
| Line description | Distinguishes subscriptions, usage, hardware, campaigns, and other purchases |
| Contract or PO ID | Connects the bill to its commercial agreement |
| Quantity and unit rate, when present | Shows that the amount depends on activity |

Contract terms, usage reports, seat reports, timesheets, and goods receipts make the classification more reliable.

## Confidence rule

- **High confidence:** the contract or PO states the cadence and pricing method, and the transactions agree.
- **Medium confidence:** at least three prior periods show a clear pattern, but the agreement is unavailable.
- **Low confidence:** only one invoice exists or the records conflict. The system should ask for more information rather than make a permanent classification.

Three previous monthly bills are a strong signal of a subscription, but they are not absolute proof. An annual subscription may not have monthly invoices, and a variable service can accidentally produce the same amount for several months. Contract terms should win when they are available.
