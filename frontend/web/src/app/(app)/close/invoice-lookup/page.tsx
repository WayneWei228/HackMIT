"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { AnalysisScreen } from "../_analysis/analysis-screen";

/**
 * Invoice Lookup agent - stage 03 of the close chain.
 *
 * Whether an invoice already exists for this line and period - on the\n * posted AP ledger or still in the AP queue - and which of none, in queue,\n * posted, partial, duplicate or ambiguous that amounts to.
 *
 * The screen itself is `_analysis/analysis-screen`, shared with the other two
 * analysis agents. It holds no data of its own: what this agent found comes
 * from `GET /api/cases/{period}/{case_key}/screens/invoice-lookup`, and where it
 * sits in the chain comes from the route table.
 */
export default function InvoiceLookupPage() {
  /* `useSearchParams` suspends during the static prerender, so the boundary
     renders the screen's own loading state until the case is known. */
  return (
    <Suspense
      fallback={<AnalysisScreen screen="invoice-lookup" agentId="invoice-lookup" caseParam={null} />}
    >
      <InvoiceLookupWithCase />
    </Suspense>
  );
}

function InvoiceLookupWithCase() {
  const caseParam = useSearchParams().get("case");
  return (
    <AnalysisScreen screen="invoice-lookup" agentId="invoice-lookup" caseParam={caseParam} />
  );
}
