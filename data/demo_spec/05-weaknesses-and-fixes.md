# 05 Weaknesses a Maximor judge will attack, and the smallest fixes

Deliverable 10. Written from the seat of a finance-automation engineer who has watched many "AI accountant" demos and called a cash-only point solution "very meh".
Every attack is aimed at a named part of the simplified design. Every fix is under 2 hours of build on top of the plan in `03-playbook-memory-and-api.md`. Nothing here changes the product spec. All data is synthetic; the company is Acme AI, Inc.

## 0. Arithmetic, computed once

| Quantity | Working | Result |
|---|---|---|
| SCN-A tolerance | `max(500.00, 0.02 x 50,000.00 = 1,000.00)` | 1,000.00 |
| SCN-A 8 percent variance | `50,000.00 x 1.08 = 54,000.00`; `54,000.00 - 50,000.00` | 4,000.00 |
| SCN-A 12 percent variance | `50,000.00 x 1.12 = 56,000.00`; `56,000.00 - 50,000.00` | 6,000.00 |
| SCN-B tolerance | `max(500.00, 0.02 x 12,000.00 = 240.00)` | 500.00 |
| SCN-B 15 percent frozen variance | `120 x 115.00 = 13,800.00`; `13,800.00 - 12,000.00` | 1,800.00 |
| Frozen January error, both `#transfer-panel` rows | `4,000.00 + 1,800.00` | 5,800.00 |
| Replay coverage | 1 touched / 20 replayed | 5 percent |
| POL-0001 breadth | 5 of 10 vendors match the predicates; 3 of the 4 triggered resolve `NO_PRICING_DOCUMENTS_ON_FILE` | 1 amount changed |
| True-up approver today | every true-up outside tolerance routes to the approver of its own accrual (`00` section 4), so 4,000.00 goes to E001 | already pinned, no fix needed |

## 1. Ranked attacks

| # | Attack, as the judge says it | Hits | Smallest fix | Cost |
|---|---|---|---|---|
| W01 | "Your v1.0 is a strawman you built so you could fix it." | `03` tool gateway, `CONTRACT_PRICE` evidence plan | Print the human rollforward the plan came from, next to the plan | 1 h |
| W02 | "The gateway learned, not the model. That is a feature flag." | `03` `evidence_plan_delta`, `00` 1.4 | Provenance card: model wrote / code checked, two columns | 1.5 h |
| W03 | "POL-0001 is just open-every-document, always." | `03` 2 predicates, `00` 1.7 | Print the cost of the breadth from the replay report | 1.5 h |
| W04 | "PagerLoop and DataForge are the same case." | `04` SCN-B, `00` 4 | Three more `#transfer-panel` rows: two matched and unchanged, one not matched | 1 h |
| W05 | "The LLM is decorative." | `03` 3 | Ablation card over the 20 replay obligations | 1.5 h |
| W06 | "One touched obligation out of twenty proves nothing." | `03` 8 replay report | Replay also over `erp/accrual_schedule_prior.csv` | 2 h |
| W07 | "Approval is a JSON field. I can be your Controller with curl." | `03` 5, `00` 1.6 | Role check with 403, approver name on the event, promotion rule printed | 1 h |
| W08 | "Your true-up lands in a closed period and no schedule shows it." | `02` 4 | `out_of_period` flag, rendered disclosure line, unadjusted-differences table | 1 h |

Ten and a half hours across the four existing tracks. If time runs out, cut in the order W06, W05, W08. W01 to W04 are never cut.

## 2. The attacks in full

### W01. The v1.0 baseline is a strawman

- **Attack.** "No close accountant accrues a December subscription without checking the pricing schedule. PS-001 has sat in the same contract folder since 2025-11-24. You wrote a baseline that refuses to open the next document so you would have a failure to fix."
- **Why it lands.** The `CONTRACT_PRICE` evidence plan in playbook 1.0 names the order form and nothing else, and the gateway refuses `list_related_documents` in CLOSE mode. The miss is a design choice written into `policies.json` before any model runs.
- **Smallest fix.** Render the provenance of the plan, not just the plan. `erp/accrual_schedule_prior.csv` holds the 2026-05 to 2026-10 rollforward that E004 prepared and E002 reviewed, and it accrues DataForge at the order form price of $50,000.00 every month. Print two lines in `#workpaper` beside the v1.0 evidence plan: the six human accruals and their source, and the sentence "this is the procedure the agent inherited". Add the same two lines to the audit packet.
- **Answer.** "That plan is the one this close team actually ran for six months, printed from their own rollforward. It was right six times and wrong on the seventh, which is exactly how procedure gaps reach production."

### W02. The tool gateway did the learning, not the model

- **Attack.** "Approve flips `list_related_documents` from refused to allowed. That is a feature flag with a signature page on it. Nothing in your model changed."
- **Why it lands.** The only mechanical difference between playbook 1.0 and 1.1 is `evidence_plan_delta.add_tools`, and the estimator, the verifier and the arithmetic are identical in both arms.
- **Smallest fix.** A provenance card in `#learning-panel`, two columns. Model wrote: the `PriceTerm` extracted from PS-001 with its verbatim quote, the root-cause label, the predicate set of the candidate, each with its `RUN-` id and the tool call that produced it. Code checked: the quote is a substring of the document text, the effective date covers the service period, the variance, the replay, the final amount.
- **Answer.** "The model reads the document and names the failure, code checks every claim and computes every dollar, and what the Controller signs is a retrieval step that a deterministic gateway then enforces on every vendor. That is the only shape of learning an auditor can sign."

### W03. POL-0001 is "open every document, always"

- **Attack.** "Two predicates, `spend_type = RECURRING` and `estimation_basis = CONTRACT_PRICE`. That is five of your ten vendors. The required evidence is: list the related documents. You did not learn a rule, you turned retrieval on for half the company."
- **Why it lands.** It is true by design. Of the 4 obligations the replay triggers, 3 return `NO_PRICING_DOCUMENTS_ON_FILE` and change nothing, so most of the matched population pays a tool call for no benefit.
- **Smallest fix.** Price the breadth instead of hiding it. `#learning-panel` prints, straight from the replay report: 10 feature matched, 4 triggered, 1 amount changed, 3 `NO_PRICING_DOCUMENTS_ON_FILE`, extra reviews 0, extra outreach 0, and the extra document calls per triggered obligation. Beneath it, one line naming the narrower candidate the replay rejects: a predicate on `price_label = "Contract Year 1"` matches DataForge and drops `OBL-V005-2027-01`, whose label is "Initial Term", so it wins December and loses January.
- **Answer.** "Broad on purpose. It costs one extra document call on five vendors, zero extra reviews and zero regressions, and the narrow version that names the vendor's own wording fails the very next month."

### W04. PagerLoop and DataForge are the same case

- **Attack.** "Both recurring, both contract price, both hide the new price one document away, both fixed by the same extra call. Transferring to a case you built to match your policy is not transfer."
- **Why it lands.** Both vendors match the same two predicates by construction. The differences that are real, `PER_SEAT_MONTH` against `PER_MONTH` and a `VENDOR_PRICE_NOTICE` filed 2027-01-20 against a `PRICING_SCHEDULE` filed 2025-11-24, are easy to miss on screen.
- **Smallest fix.** Show what the policy touched and did not touch, on the same panel. Three rows below PagerLoop: `OBL-V014-2027-01` and `OBL-V004-2027-01` match the predicates, resolve `NO_PRICING_DOCUMENTS_ON_FILE`, and book 22,500.00 and 18,000.00 in both arms; `OBL-V002-2027-01` does not match at all and books 30,000.00 in both arms. Print the learned arm's arithmetic on the PagerLoop row, `120 x 115.00 = 13,800.00`, with the seat count sourced from CTR-005 and the price from VPN-005.
- **Answer.** "One rule, a different document type, a different unit, and two vendors it matched and correctly left alone. A rule that only knew DataForge would have moved DataForge and nothing else."

### W05. The LLM is decorative

- **Attack.** "Estimator is code, verifier is code, replay is code, the amount is code. Delete the model, hard-code 'go read the pricing schedule', and this demo is identical."
- **Why it lands.** The policy set goes only to the deterministic verifier. The model's whole output is a `PriceTerm` extraction, a root-cause label chosen from two values, and a predicate set drawn from a six-field whitelist.
- **Smallest fix.** Pre-compute an ablation card for `#audit-panel` over the 20 replay obligations: model extraction against a regex on the pricing document against always taking the last table row. Report `PriceTerm` accuracy, verbatim-quote pass rate and document calls per obligation, frozen 1 against learned 3. Run once before the demo, store the JSON, render it.
- **Answer.** "The model reads documents and names the failure, code does every dollar, and the card shows both cheap substitutes pulling the wrong line out of PagerLoop's price notice."

### W06. Replay over twenty obligations proves nothing

- **Attack.** "Twenty replayed, one touched, nineteen unchanged. Your regression test is n equals one against a world your own generator produced. Of course it improves."
- **Why it lands.** The replay report says improved 1, regressed 0, unchanged 19, which is 5 percent of the set moving, and every row in it came from the same simulator.
- **Smallest fix.** Add the second denominator that already exists in the fixtures. Replay the candidate over `erp/accrual_schedule_prior.csv`, the 2026-05 to 2026-10 accruals E004 prepared and E002 reviewed, which carry accrued, actual and variance per vendor-month. No new fixture. The report prints both denominators with feature-matched, would-have-changed and regressed counts. DataForge sits inside Contract Year 1 for all six months, so the honest headline is no change and no regression against accruals a human team signed.
- **Answer.** "One changed number is the point. It also replayed over every accrual this team posted in the last six months and touched none of them."

### W07. Approval is a JSON field

- **Attack.** "Your approve call takes `actor: E001` in a request body. I can be your Controller with curl. And the policy sits at ACTIVE_PROVISIONAL forever, with ACTIVE and REVOKED in the enum and nothing driving them."
- **Why it lands.** `POST /api/policy/approve` checks that a string equals E001. The status enum in `00` 1.6 carries ACTIVE and REVOKED, and no beat in the demo reaches either.
- **Smallest fix.** No new endpoint and no new button. `#learning-panel` renders an approver picker seeded from `org_directory.json`; the server returns 403 for any actor whose role is not CONTROLLER and writes the approver name onto the `policy_events` row. After the transfer run, print the promotion rule with its evidence: the in-scope 2027-01 obligations and whether each landed inside tolerance, with the stated consequence that all inside promotes 1.1 to ACTIVE and any regression returns the active pointer to 1.0.
- **Answer.** "Only a Controller can sign it, the name is on the policy event, it stays provisional until January's invoices agree with it, and Reject puts the company back on 1.0 with no code change."

### W08. The true-up lands in a closed period and no schedule shows it

- **Attack.** "December closed at 2027-01-05T23:59:59. On 2027-01-12 you post 4,000.00 of December expense into January. Where is the out-of-period disclosure, and where is the summary of unadjusted differences my auditor asks for?"
- **Why it lands.** `JE-TRU-V001-2026-12` is dated at the invoice received date and nothing on the entry says it belongs to a closed period. Routing is already correct, the true-up goes to E001 who signed the accrual, but no schedule aggregates these adjustments.
- **Smallest fix.** Two workpaper additions. First, `TrueUpAdjustment` gains `out_of_period: true` and a rendered line: "prior-period adjustment; 2026-12 expense understated 4,000.00; recorded in 2027-01 because 2026-12 closed 2027-01-05T23:59:59". Second, `#audit-panel` gains a Summary of Unadjusted Differences table listing every out-of-period true-up in the period, signed, with a total. The reversal `JE-REV-V001-2026-12` dated 2027-01-01 is already correct and unchanged.
- **Answer.** "The miss lands in January as a labelled prior-period adjustment, signed by the same Controller who signed the accrual, and it sits on the unadjusted-differences schedule with everything else."
