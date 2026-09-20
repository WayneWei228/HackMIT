"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";

import { routes } from "@/lib/routes";

import {
  DELAYS,
  FINAL_STEP,
  HANDOFF_DELAY,
  SEQ,
  START_SECONDS,
  STATUS,
} from "../_data";

export type EvidenceRun = {
  /** Index into SEQ / STATUS. */
  step: number;
  /** Checklist items completed at this step. */
  done: number;
  /** Checklist item currently working, or -1. */
  active: number;
  complete: boolean;
  status: string;
  /** mm:ss since the agent started. */
  clock: string;
  replay: () => void;
};

const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);

/**
 * The scripted evidence run.
 *
 * The comp advances a step on each entry of DELAYS and derives everything else
 * from that one number, so the timeline stays a plain `setTimeout` chain here
 * and Motion is left to render the consequences.
 *
 * `autoAdvance` is off by default in this port: the visible handoff button in
 * the rail does the navigation, so the screen stays browsable.
 */
export function useEvidenceRun({
  autoplay = true,
  autoAdvance = false,
  liveTimer = true,
}: {
  autoplay?: boolean;
  autoAdvance?: boolean;
  liveTimer?: boolean;
} = {}): EvidenceRun {
  const router = useRouter();
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);
  const [seconds, setSeconds] = useState(START_SECONDS);
  const [runId, setRunId] = useState(0);
  const advanced = useRef(false);

  useEffect(() => {
    if (!liveTimer) return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [liveTimer]);

  useEffect(() => {
    if (!autoplay) return;

    const timers: ReturnType<typeof setTimeout>[] = [];

    // Reduced motion skips the timeline and lands on the finished state. The
    // jump is queued rather than derived during render so the first client
    // render still matches the server's.
    if (reduced) {
      timers.push(setTimeout(() => setStep(FINAL_STEP), 0));
      return () => timers.forEach(clearTimeout);
    }

    let acc = 0;
    DELAYS.forEach((delay, i) => {
      acc += delay;
      timers.push(setTimeout(() => setStep(i + 1), acc));
    });

    if (autoAdvance && !advanced.current) {
      timers.push(
        setTimeout(() => {
          advanced.current = true;
          router.push(routes.obligation);
        }, acc + HANDOFF_DELAY),
      );
    }

    return () => timers.forEach(clearTimeout);
  }, [autoplay, autoAdvance, reduced, router, runId]);

  // Replay restarts the sequence only - the comp leaves the clock running.
  const replay = useCallback(() => {
    setStep(0);
    setRunId((n) => n + 1);
  }, []);

  const [done, active] = SEQ[step];

  return {
    step,
    done,
    active,
    complete: step >= FINAL_STEP,
    status: STATUS[step],
    clock: `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`,
    replay,
  };
}
