"use client";

import { useCaseId } from "@/lib/case-context";
import { formatDuration, useStageClock } from "@/lib/case-runner";

export type EvidenceRun = {
  /** The measured time the Evidence agent took, or "-" when this browser did not see it run. */
  clock: string;
};

/** The screen renders only once the backend has run the agent, so there is no timeline to play. */
export function useEvidenceRun(): EvidenceRun {
  const obligationId = useCaseId();
  const clock = formatDuration(useStageClock(obligationId, "evidence", true));
  return { clock };
}
