"use client";

import type { FrontStage, Header } from "./api-types";
import { useCaseId } from "./case-context";
import { useCaseRun } from "./case-runner";
import type { StageKey } from "./case-store";
import { useRevealingStage } from "./stage-reveal";
import { shownStatus } from "./status-styles";
import { STAGES, stageDone } from "./trail";

export type StageStatus = "Complete" | "Running" | "Queued" | "Waiting";

type HeaderLike = {
  started: boolean;
  stages_completed?: readonly FrontStage[];
  current_agent?: string | null;
};

/**
 * Where a stage stands right now, from the backend's completed list and the
 * runner: complete once every agent of it has run, running while its call is in
 * flight, queued when it is next in line, and waiting otherwise.
 */
export function useStageStatuses(header: HeaderLike): Record<StageKey, StageStatus> {
  const run = useCaseRun(useCaseId());
  const result = {} as Record<StageKey, StageStatus>;
  /* A case with no agent left to run is at rest: what it did not reach is not queued. */
  const atRest = header.started && header.current_agent === null;
  let previousDone = true;
  for (const stage of STAGES) {
    const done = stageDone(header, stage.key);
    if (done) result[stage.key] = "Complete";
    else if (run.active && run.stage === stage.key) result[stage.key] = "Running";
    else if (previousDone && !atRest) result[stage.key] = "Queued";
    else result[stage.key] = "Waiting";
    previousDone = done;
  }
  return result;
}

/**
 * The header as it should be drawn right now. The prior-close comparison and the
 * supported and difference figures exist only after Estimation has really run,
 * and Blocked, Needs review and Close-ready only after Policy has - so until
 * then they are null and the status reads In progress. While one of the case's
 * stage calls is in flight the status is Running.
 */
export function useShownHeader<T extends Header>(header: T): T {
  const run = useCaseRun(useCaseId());
  /* While a stage's results are still being revealed, what they add up to is not shown yet. */
  const revealing = useRevealingStage();
  const estimated = stageDone(header, "estimation") && revealing !== "estimation";
  return {
    ...header,
    previous_accrual: estimated ? header.previous_accrual : null,
    supported: estimated ? header.supported : null,
    difference: estimated ? header.difference : null,
    status: run.active || revealing !== null
      ? "Running"
      : shownStatus(header.status, header.stages_completed, header.current_agent),
  };
}

const NEXT: Record<StageKey, StageKey | null> = {
  ingestion: "evidence",
  evidence: "obligation",
  obligation: "estimation",
  estimation: "verification",
  verification: null,
};

/**
 * Whether the stage after `current` is open to the reader: it has run, is
 * running, or is next in line. A case resting on someone else (an Outreach reply,
 * the Controller) never reaches it, so no handoff link is offered - the handoff
 * card shows where the case really went.
 */
export function useNextStageOpen(header: HeaderLike, current: StageKey): boolean {
  const statuses = useStageStatuses(header);
  const next = NEXT[current];
  return next !== null && statuses[next] !== "Waiting";
}
