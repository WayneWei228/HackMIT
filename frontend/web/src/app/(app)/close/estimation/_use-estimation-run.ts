"use client";

import type { MouseEvent as ReactMouseEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";

import { routes } from "@/lib/routes";
import { CLOCK_START, DELAYS, FINAL_STEP } from "./_data";

const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);

export type EstimationRunOptions = {
  /** Play the scripted step sequence on mount. */
  autoplay?: boolean;
  /**
   * Navigate to Verification once the run finishes. Off by default in this
   * port so the app stays navigable - the handoff button does the moving.
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
  const [rawStep, setStep] = useState(0);
  const [seconds, setSeconds] = useState(CLOCK_START);
  const [runId, setRunId] = useState(0);
  // With reduced motion on we never run the ladder - the finished state is
  // simply what this screen renders.
  const step = reduced ? FINAL_STEP : rawStep;

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
    if (autoAdvance) {
      timers.push(
        setTimeout(() => router.push(routes.verification), elapsed + 1600),
      );
    }
    return () => timers.forEach(clearTimeout);
  }, [autoplay, autoAdvance, reduced, router, runId]);

  const replay = useCallback(() => {
    setStep(0);
    setRunId((n) => n + 1);
  }, []);

  return {
    step,
    complete: step >= FINAL_STEP,
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
