"use client";

import { createContext, useContext } from "react";
import type { ReactNode } from "react";

import type { StageKey } from "./case-store";
import { useReveal } from "./reveal";

type Reveal = { stage: StageKey; shown: number; total: number; pending: boolean; resting: boolean };

const RevealContext = createContext<Reveal | null>(null);

/**
 * Lays a screen's returned items out in order - checks first, the result last -
 * and reveals them one after another right after the reader ran the stage. A
 * screen opened later, or after Start all, shows everything at once.
 */
export function StageRevealProvider({
  stage,
  total,
  stepMs = 480,
  pending = false,
  resting = false,
  partial = false,
  children,
}: {
  stage: StageKey;
  total: number;
  stepMs?: number;
  /** The stage has not finished: the screen is unfinished, with results still to come. */
  pending?: boolean;
  /** Nothing more will run on this case: it waits on someone else, so what is missing is not coming from this stage. */
  resting?: boolean;
  /** While pending, items are already arriving (Evidence reads a document at a time) and are shown. */
  partial?: boolean;
  children: ReactNode;
}) {
  const revealed = useReveal(stage, total, stepMs);
  const value = !pending
    ? { stage, shown: revealed, total, pending: false, resting: false }
    : partial
      ? { stage, shown: revealed, total: total + 1, pending: true, resting }
      : { stage, shown: 0, total: Math.max(total, 1), pending: true, resting };
  return <RevealContext value={value}>{children}</RevealContext>;
}

/** How many items of a slice that starts at `offset` are revealed, and whether the next one is being worked on. */
export function useRevealSlice(offset: number, length: number): { count: number; working: boolean } {
  const reveal = useContext(RevealContext);
  if (!reveal) return { count: length, working: false };
  const count = Math.max(0, Math.min(length, reveal.shown - offset));
  return { count, working: reveal.shown >= offset && count < length };
}

/** True once everything before the result has been revealed (always true outside a provider). */
export function useRevealDone(): boolean {
  const reveal = useContext(RevealContext);
  return !reveal || reveal.shown >= reveal.total;
}

/** The stage whose items are being revealed right now, or null when nothing is (or outside a provider). */
export function useRevealingStage(): StageKey | null {
  const reveal = useContext(RevealContext);
  return reveal && reveal.shown < reveal.total ? reveal.stage : null;
}

/** True while the stage has produced nothing yet: its panels are laid out and waiting for the agent. */
export function useStagePending(): boolean {
  return useContext(RevealContext)?.pending ?? false;
}

/** True when the stage has produced nothing and nothing more will run here: the case waits on someone else. */
export function useStageResting(): boolean {
  return useContext(RevealContext)?.resting ?? false;
}
