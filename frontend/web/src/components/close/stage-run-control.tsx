"use client";

import type { StageKey } from "@/lib/case-store";
import { useStageFlow } from "@/lib/stage-flow";

/**
 * A small control inside a stage's status bar, offered only when the stage cannot
 * start by itself: an earlier stage has not run and nothing is running, or the
 * last call for it failed. It runs the case up to and including this stage.
 */
export function StageRunControl({ screen }: { screen: StageKey }) {
  const flow = useStageFlow(screen);
  if (!flow.canRun) return null;
  return (
    <button
      type="button"
      onClick={flow.run}
      className="flex-none cursor-pointer rounded-md border border-accent bg-transparent px-2.5 py-[5px] text-meta font-medium whitespace-nowrap text-accent-link transition-colors duration-[160ms] hover:bg-accent-soft-2 hover:text-accent-press"
    >
      {flow.runLabel}
    </button>
  );
}
