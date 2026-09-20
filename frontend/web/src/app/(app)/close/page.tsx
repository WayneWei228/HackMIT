"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { CloseCaseScreen } from "./_components/close-case-screen";

/**
 * `/close` - the Evidence agent's intake view.
 *
 * Every document the agent read for this case this month, and which three of
 * them it kept; the reader at `/close/evidence` is what pulls the facts out
 * of them. The screen owns two columns of the desktop frame (the case itself
 * and the live execution rail), so it is rendered as one client component
 * rather than split here; `AppShell` in the route group layout supplies the
 * sidebar.
 *
 * All data is synthetic until a case is selected with `?case=`.
 */
export default function CloseCasePage() {
  /* `useSearchParams` suspends during the static prerender, so the boundary's
     fallback is what lands in the HTML: the same screen, on the mock. */
  return (
    <Suspense fallback={<CloseCaseScreen caseParam={null} />}>
      <CloseCaseWithCase />
    </Suspense>
  );
}

function CloseCaseWithCase() {
  const caseParam = useSearchParams().get("case");
  return <CloseCaseScreen caseParam={caseParam} />;
}
