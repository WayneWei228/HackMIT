# 04 Scenarios and demo flow

Deliverables 7 and 8. Binding on this file: `00-decisions.md` (ids, states, buttons, endpoints, tables) and `WORLD_SPEC.md` (amounts, evidence text, ids). All amounts below are recomputed here, not copied blind; each matches `00-decisions.md` section 4 where that section already gives the row.
Shared notation: `CONTROLLER` = E001 Dana Whitfield, `REVIEWER` = E002 Marcus Oyelaran. Tolerance = `max($500.00, 0.02 x accrued amount)`. Accrual is `Dr <expense> / Cr 2100`, dated the last day of the service month, reversed day 1 of next month. Invoice posts `Dr <expense> / Cr 2000` for the accrued amount; true-up posts `Dr <expense> / Cr 2000` for the variance only. Guard G1 blocks a candidate whose predicates leave the section 1.7 whitelist or cite a post-cutoff fact. Guard G2 blocks a candidate with `regressed > 0` or no drop in absolute error.

## 1. SCN-A: learnable failure (DataForge, V001)

**Judge action and diff.** Scenario Lab, vendor V001, control `CTL-DATAFORGE-INCREASE`. Options 0 / 5 / 8 / 12 percent; 5 is the untouched baseline (`PS-001` CY2 is already $52,500.00, no visible diff); this walkthrough uses **8**, a genuine judge edit. `btn-apply-mutation` rewrites `contracts/pricing_schedules/PS-001.txt` CY2 row `$52,500.00 -> $54,000.00`, re-derives hidden `INV-V001-008` to $54,000.00, and changes `world_hash` (budget under 2s).

**What TrueUp sees at close** (`btn-run-close`, period 2026-12, clock 2027-01-04T09:00 to 2027-01-05T15:30). Playbook 1.0's evidence plan for `CONTRACT_PRICE` is `get_vendor`, `list_invoices(limit=3)`, `open_document(primary)`, `get_service_confirmation`, `read_ap_queue`: vendor master, the last 3 invoices (all $50,000.00), the CTR-001 order form ("$50,000.00 per month (Contract Year 1)"), service confirmation, the AP queue. It does not include related documents: `PS-001` is never opened, and a `list_related_documents(CTR-001)` call, if attempted, is refused with `OUTSIDE_EVIDENCE_PLAN`.

**ActionProposal and JE.** `PRP-V001-2026-12-01`, amount $50,000.00, Dr 6120 / Cr 2100, `calculation_method CONTRACT_PRICE`, evidence `[CTR-001, SA-DATAFORGE-2026-12]`, `policy_version 1.0`. Verifier `PE-V001-2026-12-01`: `REVIEW_REQUIRED`, `required_approval_level CONTROLLER` (`MATERIALITY_APPROVAL` fails: 50000.00 >= 25000.00; `EVIDENCE_PLAN_COMPLETE` passes). `JE-ACR-V001-2026-12` Dr 6120 / Cr 2100 $50,000.00, CC DATA, dated 2026-12-31; `JE-REV-V001-2026-12` reversal 2027-01-01. Presenter clicks `btn-approve-accrual` (E001) -> `CLOSE_POSTED`.

**Advance Time and variance.** `btn-advance-time` to 2027-01-12T09:00 releases the six invoices dated 2027-01-08 to 2027-01-11, each matching its accrual to $0.00, then `INV-V001-008`, **$54,000.00**. $54,000.00 - $50,000.00 = **$4,000.00**. Tolerance `max(500.00, 0.02 x 50000.00) = $1,000.00`. Outside tolerance -> `TRUEUP_COMPUTED`, `btn-investigate` enabled. `JE-INV-V001-008` Dr 6120 / Cr 2000 $50,000.00; `JE-TRU-V001-2026-12` Dr 6120 / Cr 2000 $4,000.00, dated 2027-01-12.

**Investigation trail** (`btn-investigate`, clock 2027-01-13T09:00, run `RUN-0002`), in order: `open_invoice(INV-V001-008)` -> `list_related_documents(CTR-001)` returns `["CTR-001","PS-001"]` -> `open_document(PS-001)` quoting the CY2 row, $54,000.00 -> `open_document(CTR-001)` quoting "$50,000.00 per month (Contract Year 1)" -> `compute_variance` (deterministic, 4,000.00) -> `classify_root_cause`. Root cause `PROCEDURE_GAP`, `process_detail = EFFECTIVE_PRICE_NOT_RETRIEVED`, `evidence_existed_at_close = true` because `PS-001.filed_date = 2025-11-24`, before the period cutoff -> `ROOT_CAUSE_FOUND`.

**Candidate policy and replay.** `POL-0001`, `policy_type VERIFY_EFFECTIVE_CONTRACT_PRICE`, predicates `{spend_type: RECURRING, estimation_basis: CONTRACT_PRICE}`. No `vendor_id`, vendor name, or `contract_id` anywhere in the record; Guard G1 passes (both fields are on the section 1.7 whitelist). Replay (`btn-run-replay`, `RPL-POL-0001`, 20 obligations across 2026-11 and 2026-12): `feature_matched = 10`, triggered 4, touched `OBL-V001-2026-12` only, before $50,000.00 / abs_error $4,000.00, after $54,000.00 / abs_error $0.00, `improved = 1, regressed = 0, unchanged = 19`. Guard G2 passes; recommendation `APPROVE_PROVISIONAL`.

**Approve vs Reject.** `btn-approve-policy` (judge's second real choice, actor E001): `POLICY_APPROVED`, playbook badge 1.0 -> 1.1, `POL-0001.status = ACTIVE_PROVISIONAL`, persisted in `trueup_playbook.db` (survives Reset World); SCN-B's learned arm uses this. `btn-reject-policy`: `POLICY_REJECTED`, playbook stays 1.0, `policy_events` row `REJECTED` by E001; SCN-B's learned arm then behaves identically to the frozen arm.

## 2. SCN-B: prove transfer (PagerLoop, V005)

Runs after SCN-A's decision; this walkthrough assumes approve. Frozen and learned arms fork snapshot `2027-01-open` at 2027-02-01T00:00, so both see one byte-identical visible state.

**Judge action and diff.** Lab, vendor V005, control `CTL-PAGERLOOP-PRICE`. Options 0 / 10 / 15 / 25 percent; 0 is baseline. This walkthrough uses **15**, the judge's own number: `contracts/price_notices/VPN-005.txt` per-seat line `$100.00 -> $115.00`, hidden `INV-V005-009` amount $12,000.00 -> $13,800.00 (`120 x 115.00`). `CTR-005.txt` and the 120 seat count are untouched.

**What each arm sees at close** (period 2027-01, clock at or after 2027-02-01):
- Frozen (1.0): reads only `CTR-005` order form ("120 seats at $100.00 per seat per month (Initial Term)"); accrues $12,000.00.
- Learned (1.1): `POL-0001` matches (`spend_type = RECURRING`, `estimation_basis = CONTRACT_PRICE`); draft $12,000.00; verifier `BLOCK` (`EFFECTIVE_PRICE_CHECK` missing); `list_related_documents(CTR-005)` returns `["CTR-005","VPN-005"]`; `open_document(VPN-005)` quotes the per-seat line; `PriceTerm {PER_SEAT_MONTH, 115.00, 2027-01-01, VPN-005}`; re-propose `120 x 115.00 = $13,800.00`. It books the right number; it does not merely block.

| | Frozen (1.0) | Learned (1.1) |
|---|---|---|
| Accrual amount | $12,000.00 | $13,800.00 |
| Price evidence | CTR-005 order form only | VPN-005 per-seat line |
| Verifier result / approval | REVIEW_REQUIRED / REVIEWER (E002) | BLOCK -> REVIEW_REQUIRED / REVIEWER (E002) |
| JE | Dr 6120 / Cr 2100 $12,000.00, CC ENG, 2027-01-31 | Dr 6120 / Cr 2100 $13,800.00, CC ENG, 2027-01-31 |
| Hidden `INV-V005-009` | $13,800.00 | $13,800.00 |
| True-up | $1,800.00 (tolerance $500.00; outside) | $0.00 |

`#transfer-panel` carries a second row, the training vendor one period later: `OBL-V001-2027-01`, frozen $50,000.00 against the CY2 rate. At the default walkthrough the frozen January error is `4,000.00 + 1,800.00 = $5,800.00` and the learned error is $0.00.

**Rejected path.** If the Controller rejected in SCN-A, `playbook_versions` never gains row 1.1, both arms load 1.0, and `GET /api/transfer/compare` returns identical amount, approval level, estimation basis and tool-call sequence for both columns. The panel prints `Learned == Frozen (policy rejected 2027-01-15, reason: "<reason>")`.

## 3. SCN-C: know when not to learn (Brightwork, V006)

**Judge action and diff.** Lab, vendor V006, control `CTL-BRIGHTWORK-SURCHARGE`. Options $0.00 / $900.00 / $2,400.00 / $6,000.00. This walkthrough uses **$2,400.00**. None of the visible repository changes: the Lab shows "This control changes only the hidden invoice." Hidden `INV-V006-008` total becomes $28,670.00.

**What TrueUp sees at close** (`OBL-V006-2026-12`): timesheets show 68 hours `APPROVED`, 74 hours `PENDING`. Verifier returns `OUTREACH_REQUIRED`, fact `SERVICE_RECEIVED`, target E014. Reply after 20h confirms 142 hours. `HOURS_X_RATE`: `142 x $185.00 = $26,270.00`. `PRP-V006-2026-12-01`, Dr 6200 / Cr 2100, `REVIEW_REQUIRED`, `required_approval_level CONTROLLER`. `JE-ACR-V006-2026-12` dated 2026-12-31, reversal 2027-01-01, approved by E001.

**Advance Time and variance.** SCN-C runs on an otherwise untouched baseline world, so advancing to 2027-01-15T09:00 also releases `INV-V001-008` at $52,500.00, which misses by $2,500.00; `#trueup-panel` shows both rows outside tolerance and the presenter investigates `OBL-V006-2026-12`. That release materializes `INV-V006-008`, total **$28,670.00** (two line items: $26,270.00 services, $2,400.00 "Year end expedite premium"). $28,670.00 - $26,270.00 = **$2,400.00**. Tolerance `max(500.00, 0.02 x 26270.00 = 525.40) = $525.40`. Outside tolerance -> `btn-investigate` enabled.

**Investigation trail.** SCN-C runs from a fresh `btn-reset-world`, so ids restart: close is `RUN-0001`, investigation is `RUN-0002`. `list_related_documents(CTR-006)` returns `["CTR-006"]`, no pricing document; `open_document(CTR-006)` quotes "Consultant shall bill actual hours worked at $185.00 per hour. No additional fees apply absent a signed change order."; `search_inbox` for `SCOPE_OR_RATE_CHANGE` finds no thread; `classify_root_cause` finds no clause or correspondence supporting $2,400.00. Root cause `UNKNOWN`, `process_detail = NO_CONTRACTUAL_BASIS` -> `ROOT_CAUSE_UNKNOWN` -> automatic -> `ESCALATED`. The state machine only reaches `CANDIDATE_READY` from `ROOT_CAUSE_FOUND`, so `UNKNOWN` never scopes a predicate: nothing is proposed.

**EscalationNote:**
```json
{"escalation_id":"ESC-V006-2026-12-01","obligation_id":"OBL-V006-2026-12","raised_at":"2027-01-15T12:00:00","raised_by":"TRUEUP",
 "reason_code":"NO_CONTRACTUAL_BASIS","variance_amount":2400.00,"tolerance_amount":525.40,
 "evidence_ids":["INV-V006-008","CTR-006"],"routed_to":"E001","routed_role":"CONTROLLER",
 "summary":"Invoice carries a $2,400.00 line, 'Year end expedite premium', with no supporting clause or correspondence.",
 "status":"OPEN","controller_decision":null}
```
No scripted inbox reply exists for this note, so it stays `OPEN` until Reset World / Reset Demo. No candidate policy, no replay, no Approve/Reject: `btn-approve-policy` and `btn-reject-policy` are never rendered; `ESCALATED`'s only enabled buttons are Reset World and Reset Demo. This absence is the deliverable: TrueUp declines to generalize from one unexplained dollar.

## 4. The three-minute judge-facing flow

Backbone is SCN-A end to end, closing with the SCN-B transfer proof. SCN-C is not in the timed path (its payoff is silence, not a state change) but is a 20-30 second closing beat or Q&A backup.

**GPF (Golden Path Fallback).** A mutated world never gets a cached answer. If any live call in a beat below stalls past 5 seconds or errors, the presenter says the fallback line, clicks `btn-reset-world`, and reruns `Run Close` on the override-free baseline world, the one whose `fixture_hash == BASELINE_FIXTURE_HASH` (DataForge increase 5 percent = baseline, still misses by $2,500.00). That world has a recording at `runtime/recorded/REC-<hash12>.jsonl`, keyed by the first 12 hex of its `world_hash`; the beat continues under the `RECORDED` badge instead of `LIVE`.

| # | Sec | Actor | Click | Screen shows | Spoken line | Fallback |
|---|---|---|---|---|---|---|
| 1 | 0-8 | presenter | none | `#clock-bar`: clock 2027-01-04T09:00, `fixture_hash` matches `BASELINE_FIXTURE_HASH`, playbook 1.0 | "Acme AI, reset to a pinned hash. Nothing here is scripted." | none |
| 2 | 8-14 | presenter | hands over laptop | `#lab-panel` open | "Pick a vendor, change one real fact about their contract." | none |
| 3 | 14-26 | judge | select V001, `CTL-DATAFORGE-INCREASE`, pick a percent | staged diff | "Your number changes the contract, not the invoice." | preset chips for 5/8/12 |
| 4 | 26-34 | (auto) | none | What Changed: `PS-001` and only `PS-001` on the visible side | "That's the only visible file that moves." | none |
| 5 | 34-40 | judge | `btn-apply-mutation` | new `world_hash` | "That just rebuilt a real PDF and the hidden invoice behind it." | GPF |
| 6 | 40-56 | presenter | `btn-run-close` | `#evidence-trail` shows the v1.0 plan and the refused related-document call; no pricing document opened | "Watch it pull the contract, the recent invoices, the AP queue, live. It never opens the pricing schedule." | GPF |
| 7 | 56-66 | presenter | none | workpaper: $50,000.00, `REVIEW_REQUIRED`, CONTROLLER | "Fifty thousand, straight off the Year One line." | none |
| 8 | 66-72 | presenter | `btn-approve-accrual` | `JE-ACR-V001-2026-12` posted | "A human signs off because fifty thousand clears the threshold." | none |
| 9 | 72-82 | presenter | `btn-advance-time` | real invoice lands, amount in red vs accrual | "One click forward, and the real bill lands. Not fifty thousand." | none |
| 10 | 82-88 | (auto) | none | miss highlighted, variance against tolerance | "That gap is math, not a guess." | none |
| 11 | 88-104 | presenter | `btn-investigate` | evidence trail: invoice -> contract -> related documents -> PS-001 with the quoted row | "It opens the pricing schedule that was sitting there the whole time." | GPF |
| 12 | 104-110 | (auto) | none | `PROCEDURE_GAP`, `EFFECTIVE_PRICE_NOT_RETRIEVED` | "It names exactly what it skipped." | GPF |
| 13 | 110-118 | (auto) | none | candidate `POL-0001`, no vendor id in the record | "Its fix names a contract feature. It never says DataForge." | GPF |
| 14 | 118-128 | presenter | `btn-run-replay` | replay: 20 obligations, changed 1, regressed 0, bias to zero | "Twenty past obligations, replayed live, right now. Nothing else moved." | none |
| 15 | 128-138 | judge | `btn-approve-policy` or `btn-reject-policy` | playbook badge 1.0 -> 1.1 | "Your call: approve it, or reject it and it forgets this happened." | none |
| 16 | 138-146 | judge | select V005, `CTL-PAGERLOOP-PRICE`, pick a percent, `btn-apply-mutation` | staged `VPN-005` diff | "Different vendor, different pricing shape: per seat, not flat." | none |
| 17 | 146-164 | presenter | `btn-run-transfer` | `#transfer-panel` split table, Frozen vs Learned side by side | "Same rule, new vendor: it blocks the guess and gets the right number." | GPF (learned arm only) |
| 18 | 164-176 | presenter | `btn-advance-time`; open `#audit-panel` | result and the audit line | "Every dollar traces to evidence, a policy version, a name." | none |
| 19 | 176-180 | presenter | none | (wrap) | "Reject instead, and it misses the same way, every time." | none |

Real judge choices: beats 3, 15 and 16 (the mutation value, Approve/Reject, and the PagerLoop price).

## 5. Sixty-second expo variant

SCN-A only, compressed, preset buttons instead of free entry, results revealed rather than narrated step by step. Same GPF rule; pre-armed at a 3 second timeout since there is no slack to wait.

| # | Sec | Actor | Click | Screen shows | Spoken line |
|---|---|---|---|---|---|
| 1 | 0-6 | presenter | none | clock-bar, hash pinned | "Live agent, real contract data, one pinned hash." |
| 2 | 6-16 | judge | preset chip "8 percent" then `btn-apply-mutation` | diff + new hash | "Pick the miss size." |
| 3 | 16-28 | presenter | `btn-run-close` then `btn-approve-accrual` | accrual $50,000.00, CONTROLLER | "It accrues fifty thousand off the order form." |
| 4 | 28-38 | presenter | `btn-advance-time` | invoice $54,000.00, variance card | "Real bill: fifty-four. A four-thousand-dollar miss." |
| 5 | 38-48 | presenter | `btn-investigate` (result pre-warmed) | root cause card, `POL-0001` scope | "It finds the missed pricing schedule and drafts a fix, no vendor name." |
| 6 | 48-58 | judge | `btn-approve-policy` | badge 1.0 -> 1.1 | "You approve it; it becomes company memory." |
| 7 | 58-60 | presenter | none | (wrap) | "Next vendor, same rule, no retraining." |

## 6. Pre-demo checklist

1. `POST /sim/reset/demo`; confirm response `fixture_hash == BASELINE_FIXTURE_HASH`.
2. `GET /sim/hash` and `GET /api/state`: confirm `world_hash` matches, playbook version `1.0`, badge `LIVE`.
3. Warm the LLM path once: run SCN-A live at baseline (DataForge increase 5 percent, no Apply Change needed) end to end through `Run Transfer Compare`, so `runtime/recorded/REC-<hash12>.jsonl` exists for `BASELINE_FIXTURE_HASH`. This file is the GPF safety net and is not cleared by Reset World or Reset Demo.
4. `POST /sim/reset/demo` again to return to `IDLE_BASELINE` with a clean `trueup_state.db` (the recording from step 3 survives; the run itself does not).
5. Stage a dry-run override for each of the three demo-path controls (`CTL-DATAFORGE-INCREASE`, `CTL-PAGERLOOP-PRICE`, `CTL-BRIGHTWORK-SURCHARGE`) with `POST /sim/overrides/stage`, confirm the diff preview renders in under 2s, then `DELETE /sim/overrides` to clear them unapplied.
6. One throwaway live model call (any beat-6-style evidence citation) to confirm API reachability before judges arrive.
7. Open `GET /` once, confirm `#clock-bar` shows the 12-hex `world_hash` / `BASELINE_FIXTURE_HASH` pair and the `LIVE`/`RECORDED` badge toggles correctly.
8. Confirm all twelve buttons in `00-decisions.md` section 1.3 render with the correct enabled/disabled state for `IDLE_BASELINE` per the state table in `02-state-machine-and-time.md`.
9. Leave live mode for the judge session; only switch to recorded/cached deliberately if GPF is invoked.
