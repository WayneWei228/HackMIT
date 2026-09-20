"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useRouter } from "next/navigation";

import { routes } from "@/lib/routes";
import {
  DELAYS,
  FINAL_STEP,
  RAIL_WIDTH,
  START_SECONDS,
  activeCheckIndex,
  formatClock,
} from "../_data";

export type ObligationRunOptions = {
  /** Run the scripted timeline on mount. */
  autoplay?: boolean;
  /**
   * Navigate to Estimation once the run finishes. Off in this port so the app
   * stays navigable - the handoff button does the moving.
   */
  autoAdvance?: boolean;
  /** Tick the live execution clock. */
  liveTimer?: boolean;
  /** Render the right-hand execution rail at all. */
  showExecutionPanel?: boolean;
};

type OpenState = { open: number; userOpened: boolean };

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * `useReducedMotion` from motion reads the media query during the first
 * client render, which would disagree with the server. Subscribing keeps
 * hydration honest and still answers before the timeline starts.
 */
function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION_QUERY).matches,
    () => false,
  );
}

/** With every check done the comp falls back to the last one being open. */
const ANALYSIS_FALLBACK_INDEX = 3;

/** The comp waits a beat after a reset before replaying the sequence. */
const REPLAY_DELAY = 60;

/**
 * The comp's `Component` class, expressed as a hook: one scripted timeline
 * driving `step`, plus the bits of UI state the user can touch - which check
 * is open, whether the rail is expanded, and how wide it is.
 */
export function useObligationRun({
  autoplay = true,
  autoAdvance = false,
  liveTimer = true,
  showExecutionPanel = true,
}: ObligationRunOptions = {}) {
  const router = useRouter();
  const reducedMotion = usePrefersReducedMotion();

  const [rawStep, setStep] = useState(0);
  const [seconds, setSeconds] = useState(START_SECONDS);
  const [openState, setOpenState] = useState<OpenState>({
    open: 2,
    userOpened: false,
  });
  const [railOpen, setRailOpen] = useState(true);
  const [railWidth, setRailWidth] = useState<number>(RAIL_WIDTH.initial);
  const [dragging, setDragging] = useState(false);
  const [runToken, setRunToken] = useState(0);

  /* The live clock. */
  useEffect(() => {
    if (!liveTimer) return;
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [liveTimer]);

  /* Reduced motion skips the performance and shows the finished run. */
  const step = reducedMotion ? FINAL_STEP : rawStep;

  /* The scripted step sequence. */
  useEffect(() => {
    if (!autoplay || reducedMotion) return;
    const timers: number[] = [];
    let acc = runToken === 0 ? 0 : REPLAY_DELAY;
    DELAYS.forEach((delay, i) => {
      acc += delay;
      timers.push(window.setTimeout(() => setStep(i + 1), acc));
    });
    if (autoAdvance) {
      timers.push(
        window.setTimeout(() => router.push(routes.estimation), acc + 1600),
      );
    }
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [autoplay, autoAdvance, reducedMotion, router, runToken]);

  const replay = useCallback(() => {
    setOpenState({ open: 2, userOpened: false });
    setStep(0);
    setRunToken((token) => token + 1);
  }, []);

  const toggleCheck = useCallback((index: number) => {
    setOpenState((s) => ({
      userOpened: true,
      open: s.userOpened && s.open === index ? -1 : index,
    }));
  }, []);

  const toggleRail = useCallback(() => setRailOpen((open) => !open), []);

  /* Rail resizing. The drag lives on the document so the pointer can leave
     the 9px handle without dropping the gesture. */
  const teardownRef = useRef<(() => void) | null>(null);

  const startResize = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = railWidth;

      const move = (e: MouseEvent) =>
        setRailWidth(
          Math.max(
            RAIL_WIDTH.min,
            Math.min(RAIL_WIDTH.max, startWidth - (e.clientX - startX)),
          ),
        );
      const up = () => teardownRef.current?.();

      teardownRef.current = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        teardownRef.current = null;
        setDragging(false);
      };

      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      setDragging(true);
    },
    [railWidth],
  );

  useEffect(() => () => teardownRef.current?.(), []);

  const complete = step >= FINAL_STEP;
  const active = activeCheckIndex(step);
  const openIndex = openState.userOpened
    ? openState.open
    : active >= 0
      ? active
      : ANALYSIS_FALLBACK_INDEX;

  return {
    step,
    complete,
    reducedMotion,
    clock: formatClock(seconds),
    openIndex,
    toggleCheck,
    replay,
    railOpen: showExecutionPanel && railOpen,
    railMini: showExecutionPanel && !railOpen,
    railWidth,
    dragging,
    toggleRail,
    startResize,
    autoAdvance,
  };
}
