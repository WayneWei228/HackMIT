# Project workflow: an AI finance team for one simulated month

Track: Maximor, "build an agentic system that runs the office of the CFO" (HackMIT 2026).
This document is written for people who are not finance experts.
Finance terms are explained in the vocabulary section, and used sparingly after that.

## What we are building

We build a fake company, let AI agents run its money for a month, and check every decision against an answer key.
A real bank dataset (BenchRec) proves that the core matching works on real data, not only on data we made ourselves.

Most teams will build "AI matches two spreadsheets".
We show an AI that does the finance team's month: it collects money from customers, pays suppliers, checks the bank against the books, asks a person only when it is unsure, remembers the answer, and closes the month.

## Vocabulary

| Finance word | Plain meaning |
|---|---|
| Ledger (or GL) | The company's own record book of every dollar in and out |
| Bank feed | The list of transactions the bank says happened |
| Reconciliation | Checking that the record book and the bank agree, line by line |
| Invoice | A bill we send to a customer ("you owe us $4,000") |
| Bill | A bill a supplier sends to us ("you owe us $2,000") |
| AR (accounts receivable) | Money customers still owe us |
| AP (accounts payable) | Money we still owe suppliers |
| Aging | A list of unpaid invoices sorted by how late they are |
| Cash application | Working out which invoices a payment was for |
| Purchase order (PO) | "We agreed to buy 100 chairs at $50 each" |
| Goods receipt | "The warehouse received 100 chairs" |
| Three-way match | The PO, the goods receipt and the bill all agree, so it is safe to pay |
| Journal entry | A correction or new line written into the record book |
| Accrual | Recording a cost we know we owe, before the bill has arrived |
| Prepaid | Something paid up front that covers several months (such as a yearly subscription) |
| Month-end close | The end of the month: everything is checked and the books are final |
| Controller | The finance manager who approves things |
| Audit trail | A saved log of every decision and the reason for it |

## Two datasets, and why

We use two datasets because neither one is enough alone.

**BenchRec is the proof.**
It is real, disguised data from a large bank: about 69,000 bank lines and 118,000 ledger lines, with correct answers for scoring.
It only covers one job (matching bank lines to ledger lines), its text is scrambled, and it has no customers, invoices, suppliers or Stripe data.
We use it for one thing: a trustworthy score for our matcher.
The bar is 99.8% precision; the ChatGPT-built matcher bundled with the dataset reaches 99.45% precision and matches 65% of lines, so that is the number to beat.
Details are in [benchrec-cash-rec.md](benchrec-cash-rec.md).

**The fake company is the world the demo runs in.**
We generate it ourselves, so it can contain everything the brief asks for: customers, invoices, suppliers, orders, deliveries, Stripe payouts, a bank feed, payroll and a ledger.
We plant tricky situations on purpose and record the right answer for each, so the agents can be scored.
The Maximor speakers suggested this approach themselves ("simulate an entire company").

We do not invent invoices to fit BenchRec's bank lines.
If we did, the right answers would be built into the data and the demo would prove nothing.

## The workflow

```
   BenchRec (real bank data)            Fake company (we generate it)
   only used to score the matcher       customers · invoices · suppliers · orders
              │                         deliveries · Stripe · bank · payroll
              │                                     │
              │                        events arrive day by day
              │                  ┌──────────────────┼──────────────────┐
              │                  ↓                  ↓                  ↓
              │              AR Agent           AP Agent      Reconciliation Agent
              │             (money in)         (money out)      (bank vs. books)
              │                  └──────────────────┼──────────────────┘
              │                                     ↓
              └───────────────────────────►  Matching Engine
                                                    ↓
                                    ┌───────────────┴───────────────┐
                                    ↓                               ↓
                                 matched                        exception
                                    ↓                               ↓
                           Verification Agent               Resolution Agent
                                    │                               ↓
                                    │          ┌──────────┬─────────┼─────────┬──────────┐
                                    │          ↓          ↓         ↓         ↓          ↓
                                    │         Fee     Duplicate   Timing   Mismatch   Unknown
                                    │          ↓          ↓         ↓         ↓          ↓
                                    │       Journal    Hold /     Wait &   Route to    Human
                                    │        Entry     Reverse    retry    approver    Review
                                    │          └──────────┴─────────┼─────────┘          │
                                    │                               ↓                    │
                                    │                         Policy Memory ◄────────────┘
                                    │                               │      (the person's answer
                                    └───────────────┬───────────────┘       is saved as a rule)
                                                    ↓
                                     RECORD BOOK (ledger) + decision log
                                                    ↓
                                 ┌──────────────────┼──────────────────┐
                                 ↓                  ↓                  ↓
                            Close Agent        Audit Agent      Reporting Agent
```

The workflow has two halves.
The top half takes in events, matches them, and **writes** to the record book.
The bottom half only **reads** the record book.
That is why one workflow can cover all five problem areas in the brief: the bottom three agents need no new data, so they are cheap to add once the top half is correct.

## What each part does

### Matching Engine

The shared core. Every agent in the top half asks it the same question: "which things belong together?"

| Used by | It matches |
|---|---|
| Reconciliation Agent | bank line ↔ record-book line |
| AR Agent | one payment ↔ one or more invoices |
| AP Agent | bill ↔ purchase order ↔ goods receipt |
| Reconciliation Agent (Stripe) | payout ↔ charges − fees − refunds − chargebacks |

It works in three steps:
1. Find candidates by amount, date, reference and customer or supplier.
2. Score the possible matches, including one-to-many groups and amounts that differ by a fee.
3. Check hard rules: the amounts add up, nothing is used twice, and dates are within range. The result is a match with a confidence score.

### The three front-door agents

- **AR Agent (money in).** Applies customer payments to invoices, keeps the aging list current, emails late customers, waits for a reply (possibly for days) and picks up where it left off.
- **AP Agent (money out).** Runs the three-way match on every supplier bill, holds duplicates, sends mismatches to the right approver, and once a week proposes who gets paid, based on cash in the bank, due dates and early-payment discounts. A person approves the payment run.
- **Reconciliation Agent (bank vs. books).** Checks every bank line against the record book and breaks each Stripe payout into its charges, fees, refunds and chargebacks.

### Verification Agent

A second look at every match before it is written down.
It re-checks that the amounts add up, that no item was used in two matches, and that the match follows the saved policies.

### Resolution Agent

Handles everything that did not match cleanly. It first decides what kind of problem it is:

| Kind | Example | What happens |
|---|---|---|
| Fee | Customer paid $9,970 on a $10,000 invoice; the bank kept $30 | Journal entry for the fee; invoice marked as paid |
| Duplicate | A refund sent twice; the same bill received twice | Reverse the extra entry, or hold the second bill |
| Timing | Payment recorded on the 30th, reaches the bank on the 2nd | Wait and retry when the next day's data arrives |
| Mismatch | Bill says 120 chairs, delivery says 100 | Send to the person who approved the order |
| Unknown | A $12.40 gap with no explanation | Ask a person; never guess |

The rule for acting:

```
high confidence            → act, and write it in the record book
a saved policy covers it   → act as the policy says, and cite the policy
low confidence / unknown   → ask a person
```

### Policy Memory

When a person resolves something, the answer is saved as a rule with conditions, an action and an approval limit.
The next time the same situation appears, the agent handles it alone and cites the rule it used.

```yaml
policy: international_wire_fee
conditions:
  payment_type: wire
  difference_max: 50
action:
  classify_difference_as: bank_fee
approval:
  auto_post_below: 25
  review_above: 25
```

With this policy, a $20 gap is fixed automatically, and a $43 gap is fixed but sent for approval.

### Record book and decision log

The single source of truth.
Every action, by an agent or a person, is logged with its reason, the evidence it used and the policy it followed.
This log is the audit trail.

### The three reader agents

- **Close Agent.** Keeps the month-end checklist: what is done and what is stuck.
  It books accruals (a delivery arrived but the bill has not, so record the expected cost), spreads prepaid costs over the months they cover ($12,000 for a year becomes $1,000 a month), and links every balance to its evidence.
- **Audit Agent.** Plays the outside checker.
  It runs four checks over the record book (duplicate suppliers, round-number payments, entries posted after the month was closed, requests approved by the person who made them), picks random transactions, re-runs the matching on its own, and writes up what it found.
- **Reporting Agent.** Keeps a 13-week cash forecast: expected customer payments, minus supplier payments due, minus payroll.
  When real numbers arrive, it compares them to the forecast and names the transactions behind the gap.
  As a stretch goal it explains changes in the results (such as "margin dropped three points") and drafts the board report.

## One simulated month, step by step

0. **Setup.** The generator builds the company and its month, plants the tricky cases and writes the answer key. The matcher is scored on BenchRec.
1. **The clock starts.** Each simulated day brings new payments, bills, deliveries and Stripe payouts. The agents react as events arrive.
2. **Money comes in.** A customer sends $9,500 with no note; the AR Agent works out it covers invoices of $4,000, $3,000 and $2,500. A late customer gets a reminder, and the agent waits for the reply.
3. **Money goes out.** Bills are three-way matched. A duplicate is held. On Friday the AP Agent proposes the payment run and a person approves it.
4. **Bank vs. books.** The double refund is caught and reversed. The $12.40 gap has no explanation, so the agent asks the controller.
5. **The agent learns.** The controller says "that is a Stripe fee adjustment". The answer becomes a policy, and the next such gap is handled without asking.
6. **The month closes.** Accruals and prepaid entries are booked, the checklist reaches 100%, and the Audit Agent checks the work.
7. **The score.** The final screen shows how many transactions were processed, how many were handled without a person, how many policies were learned, how many cases went to a person, and how many decisions matched the answer key.

## Where each problem from the brief is handled

| Problem from the brief | Handled by | How |
|---|---|---|
| Three-way match | AP Agent → Matching Engine | Match bill ↔ order ↔ delivery |
| Hold duplicates | Resolution → Duplicate | The same bill shows up twice, so the second is held |
| Route approvals | Resolution → Mismatch | Price or quantity is off, so it goes to the right person |
| Decide what gets paid this week | AP Agent | Weekly: cash in the bank vs. due dates vs. early-payment discounts |
| Work the aging, chase | AR Agent | Sort unpaid invoices by lateness, email, wait, resume |
| Apply cash to the right invoices | AR Agent → Matching Engine | One payment ↔ several invoices |
| One payment for three invoices, wire fee, double refund, $12.40 gap | Reconciliation → Resolution | Classified as fee, duplicate or unknown, then handled as in the table above |
| Stripe or Adyen payouts | Reconciliation → Matching Engine | Payout = charges − fees − refunds − chargebacks |
| Accruals for bills not yet received | Close Agent | A delivery with no bill yet; the AP data already holds the delivery record |
| Spread prepaid and asset costs | Close Agent | A simple monthly schedule |
| Tie balances to evidence, track done and stuck | Close Agent | A checklist with a link to proof for each item |
| Duplicate vendors, round-number payments, late entries, self-approval | Audit Agent | Four checks over the record book; each case is planted in the fake company |
| Sample, re-perform, write findings | Audit Agent | Random sample, independent re-run of the matcher, written report |
| 13-week cash forecast, explain the miss | Reporting Agent | Forecast from AR, AP and payroll; compare with actuals and name the cause |
| Explain a variance, draft the board pack | Reporting Agent | Drill from the total to the transactions responsible; draft the text (stretch goal) |

## The fake company

One month of activity for a small company. Each planted case has an entry in the answer key.

| Area | What we generate | Tricky cases we plant |
|---|---|---|
| Customers and invoices | About 30 customers, each with a payment habit | One payment covering three invoices; payment short by a wire fee; a customer who pays 12 days late in Singapore dollars; a payment with no reference |
| Suppliers | Suppliers, purchase orders, goods receipts, bills | A bill sent twice; a price or quantity mismatch; the same supplier entered under two names; a request approved by its own requester; a delivery with no bill yet |
| Stripe | Charges, fees, refunds, chargebacks, payouts | A payout that includes a chargeback; a refund posted twice |
| Bank and ledger | Every event above lands here | A $12.40 gap with no cause; timing gaps across the month end; an entry posted after the close; round-number payments |
| Other | Payroll schedule, a yearly prepaid subscription | Needed for the forecast and the prepaid schedule |

## How we keep score

- **On BenchRec:** precision and match rate of the Matching Engine. Target: at least 99.8% precision, with a match rate above the 65% baseline.
- **On the fake company:** each agent decision is compared with the answer key and counted as correct, wrong, or passed to a person. A wrong action counts against us more than a question to a person, which mirrors BenchRec's rule that a missed match is better than a false one.
- **Learning:** run the same kind of case before and after a policy is saved, and show that the second one needs no person.

## Scope for two days

| Level | What | Why |
|---|---|---|
| Build properly | Matching Engine, Reconciliation, AR, AP, Resolution, Policy Memory | The core. The judges said AP and AR are where the value is. |
| Build simply | Close checklist, accruals, prepaid schedule, the Audit Agent's four checks | Queries and schedules over data we already have; a few hours each |
| Build last, keep small | 13-week forecast and explaining the miss | Needs payroll in the fake company |
| Only if time is left | Variance explanation, board report | Mostly LLM writing; impressive but not core |

Build order:

```
Matching Engine ─► BenchRec score
       │
generator + answer key ─► AR Agent ─► Reconciliation Agent ─► Policy Memory ─► Close ─► Audit ─► Reporting
                              └──► AP Agent ──────┘
```

- **Day 1:** one person builds the Matching Engine and scores it on BenchRec; another builds the generator and the answer key.
- **Day 2:** the agents, in the order above, then the dashboard.

Top half first, bottom half second: if the record book is wrong, everything that reads it is wrong too.
If time runs out, stop after the "build simply" level.
That is still one connected system covering cash, AP, AR, close and audit, which is a stronger entry than five separate demos.
