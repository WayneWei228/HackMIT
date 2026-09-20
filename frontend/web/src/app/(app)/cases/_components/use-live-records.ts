"use client";

import { useEffect, useMemo } from "react";

import { useRunner } from "@/lib/case-runner";
import { useCaseStoreActions } from "@/lib/case-store";
import { shownStatus } from "@/lib/status-styles";
import { STAGES, screenOfAgent, stageLabelOf } from "@/lib/trail";

import type { CaseRecord } from "../_data";

/**
 * The case rows as they stand right now: the backend's rows, with the runner's
 * in-flight stage laid over them (Running, with the agent's name) and every
 * result hidden until the stage that produces it has completed.
 */
export function useLiveRecords(records: readonly CaseRecord[]): CaseRecord[] {
  const { runs } = useRunner();
  const store = useCaseStoreActions();

  /* A reset or restart on the backend clears what this browser remembered. */
  useEffect(() => {
    store.reconcile(records.map((r) => ({ obligation_id: r.obligationId, status: r.status })));
  }, [records, store]);

  return useMemo(
    () =>
      records.map((record) => {
        const run = runs[record.obligationId];
        const completed = record.stagesCompleted;
        const amount =
          completed && !completed.includes("Estimation") ? null : record.amount;
        if (run?.active) {
          const stage = run.stage ?? screenOfAgent(run.agent) ?? STAGES.find((s) => !completed?.includes(s.label))?.key;
          return {
            ...record,
            amount,
            status: "Running" as const,
            stage: stage ? stageLabelOf(stage) : record.stage,
            currentAgent: run.agent ?? record.currentAgent,
            running: true,
          };
        }
        return { ...record, amount, status: shownStatus(record.status, completed ?? undefined, record.currentAgent) };
      }),
    [records, runs],
  );
}
