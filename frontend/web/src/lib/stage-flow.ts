"use client";

import { useCallback, useMemo } from "react";

import { useCachedHeader } from "./case-data";
import { useCaseId } from "./case-context";
import { useCaseRun, useCaseRunner } from "./case-runner";
import type { StageKey } from "./case-store";
import { useRevealingStage } from "./stage-reveal";
import { STAGES, stageDone } from "./trail";

/** The agent that owns each stage, as the reader should see it. */
export const STAGE_AGENT_LABEL: Record<StageKey, string> = {
  ingestion: "Ingestion agent",
  evidence: "Evidence agent",
  obligation: "Obligation agent",
  estimation: "Estimation agent",
  verification: "Policy enforcer",
};

export type StageFlow = {
  /**
   * complete: the stage has run and its results are all shown. working: its agent is running or
   * its results are still arriving on screen. starting: everything before it is done and it is
   * about to start by itself. waiting: an earlier stage has not finished. rest: nothing more will
   * run on this case. failed: the last call for it failed.
   */
  phase: "complete" | "working" | "starting" | "waiting" | "rest" | "failed";
  /** The agent of the stage before this one, while `phase` is "waiting". */
  waitingFor: string | null;
  error: string | null;
  /** A manual run is on offer: the stage is waiting with nothing running, or its last call failed. */
  canRun: boolean;
  runLabel: string;
  /** Run the case up to and including this stage. */
  run: () => void;
};

/** Where one stage of the open case stands, for its status bar and rail. */
export function useStageFlow(screen: StageKey): StageFlow {
  const id = useCaseId();
  const header = useCachedHeader(id);
  const run = useCaseRun(id);
  const { start } = useCaseRunner();
  const revealing = useRevealingStage() === screen;

  const index = STAGES.findIndex((stage) => stage.key === screen);
  const previous = STAGES[index - 1];
  const completed = useMemo(() => header?.stages_completed ?? [], [header?.stages_completed]);
  const done = header ? stageDone(header, screen) : false;
  const previousDone = !previous || completed.includes(previous.label);
  const busy = run.active || run.queued;
  const agent = header?.current_agent ?? null;

  const trigger = useCallback(() => {
    if (id) {
      const until = screen === "verification" ? undefined : screen;
      start([{ obligationId: id, completed, agent, until, reveal: true }]);
    }
  }, [id, start, completed, agent, screen]);

  let phase: StageFlow["phase"];
  if (done) phase = revealing ? "working" : "complete";
  else if (header?.started && agent === null) phase = "rest";
  else if (!previousDone) phase = "waiting";
  else if (run.error && !busy) phase = "failed";
  else if (run.active && run.stage === screen) phase = "working";
  else phase = "starting";

  return {
    phase,
    waitingFor: previous ? STAGE_AGENT_LABEL[previous.key] : null,
    error: run.error,
    canRun: (phase === "waiting" && !busy) || phase === "failed",
    runLabel: phase === "failed" ? "Retry" : `Run ${STAGE_AGENT_LABEL[screen]}`,
    run: trigger,
  };
}
