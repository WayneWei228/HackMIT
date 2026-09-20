"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";

import { chainStages } from "@/lib/routes";

import {
  DELAYS,
  FINAL_STEP,
  HANDOFF_DELAY,
  SEQ,
  START_SECONDS,
  liveStatus,
} from "../_data";
import { useEvidenceData } from "./data-context";

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
 * `autoAdvance` is off by default: the visible handoff button in the rail does
 * the navigation, so the screen stays browsable. The "Auto-run agents" switch
 * in the rail turns it on, and the chain plays itself from here to Settlement.
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
  const { caseParam, data } = useEvidenceData();
  const router = useRouter();
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);
  const [ticks, setTicks] = useState(0);
  const [runId, setRunId] = useState(0);
  const advanced = useRef(false);
  const complete = step >= FINAL_STEP;

  /* Where the hand-off goes is the chain's own shape, not this case's data:
     the entry after Evidence is Detection, with `?case=` already applied. */
  const nextHref = useMemo(
    () =>
      chainStages("evidence", caseParam).find((s) => s.state === "next")
        ?.href ?? null,
    [caseParam],
  );

  /* The narration describes the agent's progress and names the facts this
     case's own run produced - nothing about it is a fixed script. */
  const narration = useMemo(() => liveStatus(data), [data]);

  useEffect(() => {
    if (!liveTimer) return;
    const id = setInterval(() => setTicks((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [liveTimer]);

  /* Only the seconds this screen has actually been open. The comp opens its
     clock partway through a run; a real one has no head start to borrow. */
  const seconds = START_SECONDS + ticks;

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

    return () => timers.forEach(clearTimeout);
  }, [autoplay, reduced, runId]);

  /*
   * The hand-off is its own timer rather than the tail of the ladder above.
   * Switching "Auto-run agents" off mid-run then only tears this effect down -
   * the navigation is cancelled and the scripted steps carry on - where a
   * shared effect would restart the ladder and walk the run backwards.
   *
   * Reduced motion never chains. There the run is not played at all: the
   * finished state is simply what the screen renders, so an automatic hand-off
   * would flick through the whole chain in one breath.
   */
  useEffect(() => {
    if (!autoAdvance || reduced || !complete || !nextHref) return;
    if (advanced.current) return;

    const id = setTimeout(() => {
      advanced.current = true;
      router.push(nextHref);
    }, HANDOFF_DELAY);
    return () => clearTimeout(id);
  }, [autoAdvance, complete, nextHref, reduced, router]);

  // Replay restarts the sequence only - the comp leaves the clock running.
  const replay = useCallback(() => {
    advanced.current = false;
    setStep(0);
    setRunId((n) => n + 1);
  }, []);

  const [done, active] = SEQ[step];

  return {
    step,
    done,
    active,
    complete,
    status: narration[step] ?? "",
    clock: `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`,
    replay,
  };
}
