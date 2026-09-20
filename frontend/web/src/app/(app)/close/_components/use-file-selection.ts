"use client";

import { putIngestionSelection } from "@/lib/api";
import { useCaseRunner } from "@/lib/case-runner";
import { useCaseStoreActions } from "@/lib/case-store";
import { useApiAction } from "@/lib/use-api-action";

import type { SourceCardData } from "../_view";

/**
 * Removing a file from the agent's selection is a real backend action: the
 * backend records who removed it, re-runs the stages that depend on it, and may
 * find there is no longer enough evidence to accrue. The screen is then driven
 * stage by stage again, so the reader watches the downstream steps change.
 */
export function useFileSelection(obligationId: string, cards: readonly SourceCardData[]) {
  const store = useCaseStoreActions();
  const runner = useCaseRunner();
  const { run, pending, error, clearError } = useApiAction();
  const removedIds = cards.filter((card) => card.removed).map((card) => card.id);

  const apply = (excluded: string[]) =>
    run(async () => {
      const detail = await putIngestionSelection(obligationId, excluded);
      store.clearDurations(obligationId, ["evidence", "obligation", "estimation", "verification"]);
      runner.start([
        {
          obligationId,
          completed: detail.header.stages_completed ?? ["Ingestion"],
          agent: detail.header.current_agent ?? null,
        },
      ]);
    });

  return {
    removedIds,
    pending,
    error,
    clearError,
    remove: (fileId: string) => apply([...removedIds, fileId]),
    restore: (fileId: string) => apply(removedIds.filter((id) => id !== fileId)),
    restoreAll: () => apply([]),
  };
}
