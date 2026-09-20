"use client";

import { useCallback, useMemo } from "react";

import { useCaseId } from "@/lib/case-context";
import { formatDuration, useStageClock } from "@/lib/case-runner";

import type { CloseCaseView } from "../_view";

export type CloseRun = {
  /** The measured time the Ingestion agent took, or "-" when this browser did not see it run. */
  clock: string;
  selected: string[];
  selectedFiles: { id: string; name: string }[];
  isSelected: (id: string) => boolean;
};

/**
 * The Ingestion screen's run state. There is no scripted timeline: the screen is
 * rendered only after the backend has run the agent, and the selection is the
 * backend's - the agent's picks less anything the reader removed.
 */
export function useCloseRun({ view }: { view: CloseCaseView }): CloseRun {
  const obligationId = useCaseId();
  const clock = formatDuration(useStageClock(obligationId, "ingestion", true));

  const selected = useMemo(
    () => view.cards.filter((card) => card.picked).map((card) => card.id),
    [view.cards],
  );
  const selectedFiles = useMemo(
    () =>
      view.cards
        .filter((card) => card.picked)
        .map((card) => ({ id: card.id, name: card.name })),
    [view.cards],
  );
  const isSelected = useCallback((id: string) => selected.includes(id), [selected]);

  return { clock, selected, selectedFiles, isSelected };
}
