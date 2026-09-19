# Brief: interactive judge demo for TrueUp Close (source request, verbatim in substance)

The synthetic Northstar Analytics world is designed (`data/WORLD_SPEC.md`). Design the interactive demo system around it.

The goal is NOT a pre-scripted animation. Judges must be able to interact with the synthetic company, change realistic facts, run the close, create a real failure, and watch TrueUp diagnose and learn from that failure.

Treat the TrueUp product spec and the synthetic-company design as frozen. Do not redesign the product. Focus only on demoability, interaction design, state transitions, and the minimum backend changes required to support this live.

## Core learning model
- TrueUp begins with a limited company playbook.
- A recurring SaaS vendor historically bills $50,000/month. TrueUp initially estimates from invoice history/run rate.
- The contract contains a scheduled price escalation, but the initial playbook does not require checking effective contract pricing for this type of accrual. TrueUp accrues $50,000.
- The later invoice arrives at $52,500. The deterministic true-up engine detects a $2,500 miss.
- Only after the miss does TrueUp investigate the contract, discover the 5% escalator, and diagnose the cause.
- It proposes a generalized policy: IF recurring vendor accrual AND contract has scheduled pricing terms -> retrieve and validate effective pricing before estimation. NOT vendor-name-specific.
- A human Controller reviews evidence, replay/regression result and the proposed policy, then explicitly approves or rejects.
- Once approved, the policy becomes persistent company memory/playbook state, not text left in the LLM context.
- A later unseen vendor with the same relevant feature triggers the learned behavior.

## Judge Scenario Lab
A UI where we turn the laptop around and a judge modifies the synthetic company before running a close. A small number of understandable controls such as:
- change contract annual escalator: 0% / 5% / 8% / 12%
- change effective date
- switch billing cadence: monthly / quarterly / in arrears
- introduce a usage spike
- terminate a contract
- delay an invoice
- mark service confirmation missing
- create a duplicate invoice
- introduce an unusual surcharge / unknown case

No arbitrary raw database editing. Safe, finance-realistic scenario controls only. Every mutation must modify the underlying synthetic records consistently (escalator 5% -> 8% changes both the contract pricing schedule and the future hidden invoice). The agent must never receive hidden future truth before it would naturally become available.

## Required live flow
Phase 1, judge creates the failure: reset to deterministic baseline; judge picks vendor/scenario and changes one realistic fact; show exactly which company document changed; run month-end close; TrueUp uses only its current active playbook and currently available evidence; show accrual/workpaper and simulated journal entry.

Phase 2, reveal ground truth: click Advance Time; release the later invoice that was hidden; deterministically match invoice -> prior accrual; compute variance; highlight the failure visually.

Phase 3, investigation: TrueUp investigates using available tools; visibly show which evidence it opens (contract, invoice history, usage, PO...); it identifies the seeded root cause or says UNKNOWN - ESCALATE; show quoted/source-linked evidence.

Phase 4, human-in-the-loop learning: TrueUp creates a candidate typed policy/playbook change; run historical replay/regression checks; show prior cases replayed, regressions, signed bias impact, scope of proposed policy. Two visible buttons: APPROVE POLICY / REJECT POLICY. Approved -> persisted as a new version of the Northstar playbook. Rejected -> the agent does NOT learn it.

Phase 5, prove transfer: present a different vendor the agent has never handled; judge may configure a similar condition on it; run another close; show side by side Frozen Agent vs Learned TrueUp; show that the learned agent behaves differently because the approved policy's predicates match observable features of the new case, NOT because it memorized the original vendor.

## Product constraints
- Judge mutations operate on synthetic company state, not on hidden expected-answer values directly.
- Future invoices remain hidden until time advances.
- LLM never directly calculates financial amounts. Deterministic code computes accruals, variance, journal entries, replay results and metrics.
- The LLM may inspect evidence, classify root cause, choose allowed tools, and propose structured policies.
- Policies must have explicit: trigger, scope/predicates, required evidence, behavior change, approval status, version.
- Company policies persist across later runs.
- A Reset Demo function restores the exact baseline fixture.
- Every scenario remains internally consistent after mutation.
- The hidden simulator retains seeded ground truth for evaluation.
- Preserve the MVP causal chain exactly: missing vendor bill -> evidence gathering -> deterministic accrual -> verification -> human interaction -> simulated ledger entry -> later invoice -> true-up -> candidate policy -> replay -> Controller approval -> held-out improvement.

## Deliverables (implementation-ready specification, no code)
1. The exact Judge Scenario Lab UI and controls.
2. The underlying data mutations each control causes.
3. The demo state machine.
4. How hidden future data is protected from the agent.
5. How playbook/policy memory persists after approval.
6. How Approve, Reject, Advance Time, Run Close, and Reset Demo work.
7. Three judge-driven scenarios: one that creates a learnable failure, one that proves transfer to an unseen vendor, one where TrueUp should refuse to learn and escalate.
8. The exact 3-minute judge-facing demo flow.
9. The minimum API endpoints/state changes needed.
10. Weaknesses a Maximor judge could attack, and the smallest fixes.

Keep it demo-first and hackathon-feasible. Do not expand scope, add unrelated features, redesign the architecture, or brainstorm generically. Make concrete decisions.
