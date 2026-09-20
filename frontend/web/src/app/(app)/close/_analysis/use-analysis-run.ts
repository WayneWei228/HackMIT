"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useRouter } from "next/navigation";

import { chainStages } from "@/lib/routes";
import {
  DELAYS,
  FINAL_STEP,
  RAIL_WIDTH,
  START_SECONDS,
  activeCheckIndex,
  formatClock,
} from "./types";

export type AnalysisRunOptions = {
  /** Run the scripted timeline on mount. */
  autoplay?: boolean;
  /**
   * Navigate to the next agent once the run finishes. Off in this port so the
   * app stays navigable - the handoff button does the moving.
   */
  autoAdvance?: boolean;
  /** Which agent's screen this is; the chain says where the handoff goes. */
  agentId: string;
  caseParam: string | null;
  /** How many analysis checks this screen has, live or synthetic. */
  checkCount: number;
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

/** How long a finished screen is left on screen before the chain moves on. */
const HANDOFF_DWELL = 1600;

/**
 * The comp's `Component` class, expressed as a hook: one scripted timeline
 * driving `step`, plus the bits of UI state the user can touch - which check
 * is open, whether the rail is expanded, and how wide it is.
 */
export function useAnalysisRun({
  autoplay = true,
  autoAdvance = false,
  liveTimer = true,
  showExecutionPanel = true,
  agentId,
  caseParam,
  checkCount,
}: AnalysisRunOptions) {
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
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [autoplay, reducedMotion, runToken]);

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

  /* The hand-off is its own effect, not a timer inside the step sequence:
     the switch can be flipped in the middle of a run, and re-running the
     whole scripted ladder because of it would be absurd.

     Reduced motion does not chain. These screens already answer that
     preference by not playing the run at all and rendering the finished
     state, so there is no finish for a hand-off to follow - and marching
     someone who asked for less movement through eight screens unasked is
     the opposite of what they asked for. */
  useEffect(() => {
    if (!autoAdvance || !complete || reducedMotion) return;
    const next = chainStages(agentId, caseParam).find(
      (stage) => stage.state === "next",
    );
    if (!next?.href) return;
    const href = next.href;
    const id = window.setTimeout(() => router.push(href), HANDOFF_DWELL);
    return () => window.clearTimeout(id);
  }, [autoAdvance, complete, agentId, caseParam, reducedMotion, router]);

  const active = activeCheckIndex(step, checkCount);
  /* With every check done the comp falls back to the last one being open;
     a live screen may have any number of checks. */
  const fallback = Math.max(
    0,
    Math.min(ANALYSIS_FALLBACK_INDEX, checkCount - 1),
  );
  const openIndex = openState.userOpened
    ? openState.open
    : active >= 0
      ? active
      : fallback;

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
