"use client";

import type { StageKey } from "@/lib/case-store";
import { useStageFlow } from "@/lib/stage-flow";

const LABEL = {
  complete: "Complete",
  working: "Running",
  starting: "Starting",
  waiting: "Waiting",
  rest: "At rest",
  failed: "Failed",
} as const;

/** The state of a stage in its rail: what is true right now, never assumed. */
export function StageStateLabel({ screen, className }: { screen: StageKey; className?: string }) {
  const { phase } = useStageFlow(screen);
  return <span className={className}>{LABEL[phase]}</span>;
}
