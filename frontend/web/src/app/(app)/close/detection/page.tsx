"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { AnalysisScreen } from "../_analysis/analysis-screen";

/**
 * Detection agent - stage 02 of the close chain.
 *
 * Which lines of the purchase order are owed for this period: the PO\n * must still be valid or its service window cover the month, and a goods line\n * counts only where more has been received than billed.
 *
 * The screen itself is `_analysis/analysis-screen`, shared with the other two
 * analysis agents. It holds no data of its own: what this agent found comes
 * from `GET /api/cases/{period}/{case_key}/screens/detection`, and where it
 * sits in the chain comes from the route table.
 */
export default function DetectionPage() {
  /* `useSearchParams` suspends during the static prerender, so the boundary
     renders the screen's own loading state until the case is known. */
  return (
    <Suspense
      fallback={<AnalysisScreen screen="detection" agentId="detection" caseParam={null} />}
    >
      <DetectionWithCase />
    </Suspense>
  );
}

function DetectionWithCase() {
  const caseParam = useSearchParams().get("case");
  return (
    <AnalysisScreen screen="detection" agentId="detection" caseParam={caseParam} />
  );
}
