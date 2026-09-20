"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { EvidenceScreen } from "./_components/evidence-screen";

/**
 * Evidence agent - stage 01 of the close.
 *
 * The agent reads the source documents, finds the passage that moves the
 * accrual, and builds the fact set the detection agent works from. Every
 * figure, name and document on the screen comes from the close API for the
 * case named by `?case=`; with none named the screen says so.
 *
 * `useSearchParams` opts the route out of static prerendering unless it sits
 * under a `Suspense` boundary, so the fallback renders the same screen with no
 * case - the prerendered HTML is the "no case selected" state, and the
 * case-aware render swaps in on the client.
 */
export default function EvidencePage() {
  return (
    <Suspense fallback={<EvidenceScreen caseParam={null} />}>
      <EvidenceScreenWithCase />
    </Suspense>
  );
}

function EvidenceScreenWithCase() {
  const caseParam = useSearchParams().get("case");
  return <EvidenceScreen caseParam={caseParam} />;
}
