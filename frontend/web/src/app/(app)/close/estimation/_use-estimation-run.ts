"use client";

import type { MouseEvent as ReactMouseEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";

import { chainStages } from "@/lib/routes";
import { CLOCK_START, DELAYS, FINAL_STEP } from "./_data";
import { useEstimationData } from "./_components/data-context";

const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);

/** The beat the finished run waits before it opens the next agent. */
const HANDOFF_DELAY = 1600;

export type EstimationRunOptions = {
  /** Play the scripted step sequence on mount. */
  autoplay?: boolean;
  /**
   * Navigate to Outreach once the run finishes. Off by default so the app
   * stays navigable - the handoff button does the moving - and turned on by
   * the "Auto-run agents" switch in the rail.
   */
  autoAdvance?: boolean;
  /** Tick the elapsed-time readout in the rail. */
  liveTimer?: boolean;
};

export type EstimationRun = {
  step: number;
  complete: boolean;
  clock: string;
  /** Bumped on every replay, so panels can drop their manual open state. */
  runId: number;
  replay: () => void;
};

/**
 * The agent run: a fixed ladder of `setTimeout`s that walk `step` from 0 to 14.
 * With reduced motion on we skip the ladder and mount the finished state.
 */
export function useEstimationRun({
  autoplay = true,
  autoAdvance = false,
  liveTimer = true,
}: EstimationRunOptions = {}): EstimationRun {
  const reduced = useReducedMotion();
  const router = useRouter();
  const { caseParam } = useEstimationData();
  const [rawStep, setStep] = useState(0);
  const [seconds, setSeconds] = useState(CLOCK_START);
  const [runId, setRunId] = useState(0);
  // Where auto-advance goes when the run ends. The chain's own shape decides
  // it - the agent after Estimation is Outreach - and the href already
  // carries `?case=`, so the next screen opens on the same case.
  const target =
    chainStages("estimation", caseParam).find((s) => s.state === "next")
      ?.href ?? null;
  // With reduced motion on we never run the ladder - the finished state is
  // simply what this screen renders.
  const step = reduced ? FINAL_STEP : rawStep;
  const complete = step >= FINAL_STEP;

  useEffect(() => {
    if (!liveTimer) return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [liveTimer]);

  useEffect(() => {
    if (!autoplay || reduced) return;

    const timers: ReturnType<typeof setTimeout>[] = [];
    let elapsed = 0;
    DELAYS.forEach((delay, i) => {
      elapsed += delay;
      timers.push(setTimeout(() => setStep(i + 1), elapsed));
    });
    return () => timers.forEach(clearTimeout);
  }, [autoplay, reduced, runId]);

  /*
   * The hand-off is its own timer, not the tail of the ladder above: turning
   * "Auto-run agents" off mid-run tears this effect down - the navigation is
   * cancelled - while the scripted steps above keep their place, where one
   * shared effect would restart the ladder and walk the run backwards.
   *
   * Reduced motion never chains. The ladder does not run there at all - the
   * screen mounts finished - so an automatic hand-off would strobe through
   * the rest of the chain in one breath.
   */
  useEffect(() => {
    if (!autoAdvance || reduced || !complete || !target) return;
    const id = setTimeout(() => router.push(target), HANDOFF_DELAY);
    return () => clearTimeout(id);
  }, [autoAdvance, complete, reduced, router, target]);

  const replay = useCallback(() => {
    setStep(0);
    setRunId((n) => n + 1);
  }, []);

  return {
    step,
    complete,
    clock: `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`,
    runId,
    replay,
  };
}

export const RAIL_MIN_WIDTH = 288;
export const RAIL_MAX_WIDTH = 620;
export const RAIL_DEFAULT_WIDTH = 330;

export type RailResize = {
  open: boolean;
  width: number;
  dragging: boolean;
  toggle: () => void;
  onResizeStart: (event: ReactMouseEvent) => void;
};

/** Open/closed state plus the drag-to-resize handle for the execution rail. */
export function useRailResize(): RailResize {
  const [open, setOpen] = useState(true);
  const [width, setWidth] = useState(RAIL_DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);
  const cleanup = useRef<(() => void) | undefined>(undefined);

  useEffect(() => () => cleanup.current?.(), []);

  const onResizeStart = useCallback(
    (event: ReactMouseEvent) => {
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = width;

      const move = (e: MouseEvent) =>
        setWidth(
          Math.max(
            RAIL_MIN_WIDTH,
            Math.min(RAIL_MAX_WIDTH, startWidth - (e.clientX - startX)),
          ),
        );
      const up = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        cleanup.current = undefined;
        setDragging(false);
      };

      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      cleanup.current = up;
      setDragging(true);
    },
    [width],
  );

  const toggle = useCallback(() => setOpen((v) => !v), []);

  return { open, width, dragging, toggle, onResizeStart };
}
