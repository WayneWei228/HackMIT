"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import type { CloseView, ObligationDetail } from "./api-types";
import { CASE_PARAM } from "./case-nav";
import { useCaseData } from "./case-data";
import { useCaseRun, useCaseRunner } from "./case-runner";
import type { StageKey } from "./case-store";
import { STAGES, stageDone } from "./trail";

/**
 * A stage screen's data and its autonomy. The screen draws at once from the cache;
 * the agent for the stage starts by itself when the screen opens and everything
 * before it has run, and a case that is waiting on an earlier stage starts this
 * one the moment that stage completes. A case at rest (waiting on someone else),
 * a stage that failed, and a Pending case after January's invoices are left alone.
 */
export function useStageRoute(stage: StageKey): {
  close: CloseView | null;
  id: string | null;
  detail: ObligationDetail | null;
  error: Error | null;
} {
  const requested = useSearchParams().get(CASE_PARAM);
  const data = useCaseData(requested);
  const { close, id, detail } = data;
  const { start } = useCaseRunner();
  const run = useCaseRun(id);
  const attempted = useRef<string | null>(null);

  const header = detail?.header ?? null;
  const row = close?.cases.find((candidate) => candidate.obligation_id === id) ?? null;
  const completed = header?.stages_completed ?? null;
  const agent = header?.current_agent ?? null;
  const started = header?.started ?? false;
  const canStart = row?.can_start ?? false;

  useEffect(() => {
    if (!id || !header || !row || !completed) return;
    /* Verification is more than the policy check: the entry is drafted and reviewed after it,
       so its screen keeps the case moving until it comes to rest. */
    const unfinished = !stageDone(header, stage) || (stage === "verification" && agent !== null);
    if (!unfinished) return;
    const index = STAGES.findIndex((candidate) => candidate.key === stage);
    const previous = STAGES[index - 1];
    if (previous && !completed.includes(previous.label)) return;
    if (started && agent === null) return;
    if (index === 0 && !canStart) return;
    if (run.active || run.queued || run.error) return;
    const key = `${id}:${stage}:${completed.join(",")}:${agent}`;
    if (attempted.current === key) return;
    attempted.current = key;
    start([
      {
        obligationId: id,
        completed,
        agent,
        until: stage === "verification" ? undefined : stage,
        reveal: true,
      },
    ]);
  }, [id, header, row, completed, agent, started, canStart, stage, run.active, run.queued, run.error, start]);

  return data;
}
