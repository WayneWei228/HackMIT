"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { ControlsScreen } from "../_controls/controls-screen";

/**
 * Outreach agent - stage 06 of the close chain.
 *
 * Where the estimate rests on something only a person knows, a ticket is\n * raised with a deadline and a recorded fallback to the PO budget; the reply\n * - or the expiry - is logged against the ticket.
 *
 * The screen itself is `_controls/controls-screen`, shared with the other
 * control agent. It holds no data of its own: what this agent found comes
 * from `GET /api/cases/{period}/{case_key}/screens/outreach`, and where it
 * sits in the chain comes from the route table.
 */
export default function OutreachPage() {
  /* `useSearchParams` suspends during the static prerender, so the boundary
     renders the screen's own loading state until the case is known. */
  return (
    <Suspense
      fallback={<ControlsScreen screen="outreach" agentId="outreach" caseParam={null} />}
    >
      <OutreachWithCase />
    </Suspense>
  );
}

function OutreachWithCase() {
  const caseParam = useSearchParams().get("case");
  return (
    <ControlsScreen screen="outreach" agentId="outreach" caseParam={caseParam} />
  );
}
