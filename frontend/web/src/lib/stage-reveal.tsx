"use client";

import { createContext, useContext } from "react";
import type { ReactNode } from "react";

import type { StageKey } from "./case-store";
import { useReveal } from "./reveal";

type Reveal = { stage: StageKey; shown: number; total: number };

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
  children,
}: {
  stage: StageKey;
  total: number;
  stepMs?: number;
  children: ReactNode;
}) {
  const shown = useReveal(stage, total, stepMs);
  return <RevealContext value={{ stage, shown, total }}>{children}</RevealContext>;
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
