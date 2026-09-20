"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { ControlsScreen } from "../_controls/controls-screen";

/**
 * Settlement agent - stage 07 of the close chain.
 *
 * The late invoice or final report beside the accrual: the true-up, the\n * tolerance test, a re-check of what was knowable at close, the cause, and the\n * vendor's explanation where there is one.
 *
 * The screen itself is `_controls/controls-screen`, shared with the other
 * control agent. It holds no data of its own: what this agent found comes
 * from `GET /api/cases/{period}/{case_key}/screens/settlement`, and where it
 * sits in the chain comes from the route table.
 */
export default function SettlementPage() {
  /* `useSearchParams` suspends during the static prerender, so the boundary
     renders the screen's own loading state until the case is known. */
  return (
    <Suspense
      fallback={<ControlsScreen screen="settlement" agentId="settlement" caseParam={null} />}
    >
      <SettlementWithCase />
    </Suspense>
  );
}

function SettlementWithCase() {
  const caseParam = useSearchParams().get("case");
  return (
    <ControlsScreen screen="settlement" agentId="settlement" caseParam={caseParam} />
  );
}
