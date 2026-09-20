"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import {
  EstimationLoading,
  EstimationScreen,
} from "./_components/estimation-screen";

/**
 * `/close/estimation`, optionally for a case: `?case=<period>/<case_key>`.
 *
 * `useSearchParams` opts a client component out of the prerender, so the call
 * lives below a `Suspense` boundary. The prerendered HTML is the screen's own
 * skeleton - the product holds no content of its own to show there - and the
 * case's real figures arrive on hydration.
 */
export default function EstimationPage() {
  return (
    <Suspense fallback={<EstimationLoading />}>
      <EstimationScreenWithCase />
    </Suspense>
  );
}

function EstimationScreenWithCase() {
  const caseParam = useSearchParams().get("case");
  return <EstimationScreen caseParam={caseParam} />;
}
