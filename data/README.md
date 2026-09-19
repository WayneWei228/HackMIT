# Northstar Analytics fixture set

Synthetic data for TrueUp Close. Everything is invented; no real company or person.
Regenerate with `uv run --with reportlab python data/generate.py` (deterministic; wipes and rewrites `data/northstar/`).
Edit the world in `data/gen/world.py`, never the generated files.

## Timeline
- History (closed): 2026-05 to 2026-10. Already in the GL.
- Close periods (open): **2026-11, 2026-12, 2027-01**. Invoices keep arriving until 2027-02-11.
- Close cutoff: the 5th of the following month. An invoice with `received_date` after the cutoff is "missing at close".
- **The simulated clock is a filter.** At clock time T the agent may only see invoices, AP rows and inbox replies with a date on or before T. Nothing in the files enforces this; the tool layer must.

## Files the agent may read
| Path | What it is |
|---|---|
| `company.json` | Entities (NS-US, NS-UK), cost centers, chart of accounts, close calendar |
| `org_directory.json` | Employees with roles (CONTROLLER, AP_SPECIALIST, BUDGET_OWNER, REQUESTER...) and vendor billing contacts |
| `vendors.json` | 17 vendors: owner, requester, account, cost center, entity, contract and PO ids |
| `contracts/CTR-0NN.pdf` and `.txt` | Contract per vendor. Pricing traps live in the clauses (escalators, overage tiers, proration, billing cadence) |
| `purchase_orders.json`, `change_orders.json` | Blanket, project and one-time POs; CO-1 adds Helpline seats on Dec 10 |
| `invoices/invoices.json`, `invoices/pdf/` | 116 invoices with line items, service period, `received_date`, channel |
| `ap_queue.csv` | One row per invoice: coding, status, approver. Filter by `received_date` |
| `gl_entries.csv` | Balanced two-line journal entries for history: invoices, accruals, auto-reversals, carry-forwards, prepaid amortization |
| `evidence/usage_daily.csv` | Daily compute hours (CloudHarbor) and egress GB (StreamGrid) |
| `evidence/seat_snapshots.csv`, `timesheets.csv`, `hr_hires.csv`, `goods_receipts.csv` | Service-received evidence for seats, consulting hours, placements, print jobs |
| `close_policy_manual.md`, `policies.json` | Policy v1.0 in prose and as data: allowed methods, thresholds ($10k reviewer, $25k Controller), tolerances |
| `inbox/scripted_responses.json` | Replies to outreach. Match on `vendor_id + period + target_role + missing_fact`; deliver after `delay_hours`. No match, or `NO_RESPONSE`, means silence |

## Files the agent must never read
`ground_truth/` is the answer key for evaluation only.
- `obligations_truth.csv`: 50 obligations (vendor x period) with expected classification, method, verifier result, outreach target, outcome, approval level, `true_expense`, and two baselines (`static_rules_estimate`, `trailing_avg_estimate`). Score amounts only where `needs_estimate = Y`.
- `extra_exceptions.json`: two items that are not obligations: the PrintWorks duplicate invoice (hold) and the unaccrued October TalentBridge fee (prior period, Controller).

## Seeded cases
| Spec case | Where |
|---|---|
| Exact recurring match | OfficeNest, PayCircle, Lumen, PagerLoop, Thames (most months) |
| Missing invoice, supported accrual | CloudHarbor, StreamGrid, Atlas, Brightwork Nov/Jan, TalentBridge Nov/Jan |
| DataForge 5% escalator | V001 Dec: $50,000 estimate vs $52,500 invoice on Jan 12 |
| Missing service confirmation | Brightwork Dec: two timesheets unapproved; owner confirms 142 h |
| Vendor outreach changes the action | Northwind Nov: invoice sat in a retired mailbox; book actual, not an estimate |
| No response | Helpline Dec: vendor silent, PO requester answers |
| Duplicate invoice | PrintWorks 7731 vs 7731-R |
| Multi-period invoice | Quantive (Dec 15 to Jan 14), Atlas (one invoice for Nov to Jan) |
| Conflicting evidence | Meridian Dec: owner says $35-45k, vendor WIP says $58k; Controller decides |
| Mismatch / wrong entity | PayCircle Dec (unordered $830 module, later credit memo); Thames Dec (billed to NS-US) |
| Not an accrual | SecureLayer (annual prepaid), months with no hire or print job |

## Learning splits
Three root causes, each with a training miss in December and unseen cases in January.
| Root cause | TRAIN (Dec) | HELDOUT (Jan, different vendor) | Same vendor, next month |
|---|---|---|---|
| SCHEDULED_ESCALATOR | DataForge | Lumen CRM (4%, in a footnote); PagerLoop (rate only obtainable by asking the vendor) | DataForge Jan |
| TIERED_OVERAGE_RATE | CloudHarbor | StreamGrid | CloudHarbor Jan |
| CHANGE_ORDER_SEAT_EXPANSION | Helpline | none | none (Jan invoice arrives on time) |

Held-out static-rules error: Lumen -$720, PagerLoop -$352, StreamGrid -$1,200, DataForge Jan -$2,500, CloudHarbor Jan -$300.
