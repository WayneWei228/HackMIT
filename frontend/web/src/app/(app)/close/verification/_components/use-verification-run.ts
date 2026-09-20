"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

import {
  DELAYS,
  FINAL_STEP,
  RAIL_DEFAULT_WIDTH,
  RAIL_MAX_WIDTH,
  RAIL_MIN_WIDTH,
  START_SECONDS,
  deriveView,
  formatClock,
  type VerificationView,
} from "../_data";

type Options = {
  /** Play the scripted step sequence on mount. */
  autoplay?: boolean;
  /** Tick the elapsed-time readout in the rail. */
  liveTimer?: boolean;
};

export type VerificationRun = {
  view: VerificationView;
  clock: string;
  openControl: number;
  toggleControl: (index: number) => void;
  replay: () => void;
  railOpen: boolean;
  toggleRail: () => void;
  railWidth: number;
  dragging: boolean;
  startResize: (event: React.MouseEvent<HTMLElement>) => void;
};

/**
 * The comp's `Component` class: the scripted timeline, the live clock, the
 * accordion, and the resizable execution rail.
 *
 * With reduced motion on, the timeline never runs and the finished state is
 * rendered straight away.
 */
export function useVerificationRun({
  autoplay = true,
  liveTimer = true,
}: Options = {}): VerificationRun {
  const reduced = useReducedMotion();

  const [step, setStep] = useState(0);
  const [runToken, setRunToken] = useState(0);
  const [seconds, setSeconds] = useState(START_SECONDS);

  // The accordion follows the running check until the reader takes it over.
  const [accordion, setAccordion] = useState<{
    open: number;
    userOpened: boolean;
  }>({ open: -1, userOpened: false });

  const [railOpen, setRailOpen] = useState(true);
  const [railWidth, setRailWidth] = useState(RAIL_DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);

  const railWidthRef = useRef(railWidth);
  useEffect(() => {
    railWidthRef.current = railWidth;
  }, [railWidth]);

  useEffect(() => {
    if (!liveTimer) return;
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [liveTimer]);

  useEffect(() => {
    if (!autoplay || reduced) return;
    const timers: ReturnType<typeof setTimeout>[] = [];
    let acc = 0;
    DELAYS.forEach((delay, i) => {
      acc += delay;
      timers.push(setTimeout(() => setStep(i + 1), acc));
    });
    return () => timers.forEach(clearTimeout);
  }, [autoplay, reduced, runToken]);

  const view = useMemo(
    () => deriveView(reduced ? FINAL_STEP : step),
    [reduced, step],
  );

  const replay = useCallback(() => {
    setAccordion({ open: -1, userOpened: false });
    setStep(0);
    setRunToken((token) => token + 1);
  }, []);

  const toggleControl = useCallback((index: number) => {
    setAccordion((current) => ({
      userOpened: true,
      open: current.userOpened && current.open === index ? -1 : index,
    }));
  }, []);

  const toggleRail = useCallback(() => setRailOpen((value) => !value), []);

  const startResize = useCallback((event: React.MouseEvent<HTMLElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = railWidthRef.current;

    const move = (moveEvent: MouseEvent) => {
      setRailWidth(
        Math.max(
          RAIL_MIN_WIDTH,
          Math.min(RAIL_MAX_WIDTH, startWidth - (moveEvent.clientX - startX)),
        ),
      );
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setDragging(false);
    };

    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    setDragging(true);
  }, []);

  return {
    view,
    clock: formatClock(seconds),
    openControl: accordion.userOpened ? accordion.open : view.autoOpen,
    toggleControl,
    replay,
    railOpen,
    toggleRail,
    railWidth,
    dragging,
    startResize,
  };
}
