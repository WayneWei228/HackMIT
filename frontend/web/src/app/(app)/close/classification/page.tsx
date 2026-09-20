"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { AnalysisScreen } from "../_analysis/analysis-screen";

/**
 * Classification agent - stage 04 of the close chain.
 *
 * Recurring or one-time, fixed or variable: a rule tree over the PO\n * columns decides, and the model's reading of the line description is\n * cross-checked against it.
 *
 * The screen itself is `_analysis/analysis-screen`, shared with the other two
 * analysis agents. It holds no data of its own: what this agent found comes
 * from `GET /api/cases/{period}/{case_key}/screens/classification`, and where it
 * sits in the chain comes from the route table.
 */
export default function ClassificationPage() {
  /* `useSearchParams` suspends during the static prerender, so the boundary
     renders the screen's own loading state until the case is known. */
  return (
    <Suspense
      fallback={<AnalysisScreen screen="classification" agentId="classification" caseParam={null} />}
    >
      <ClassificationWithCase />
    </Suspense>
  );
}

function ClassificationWithCase() {
  const caseParam = useSearchParams().get("case");
  return (
    <AnalysisScreen screen="classification" agentId="classification" caseParam={caseParam} />
  );
}
