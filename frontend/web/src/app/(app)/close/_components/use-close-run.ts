"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";

import { routes } from "@/lib/routes";
import { caseHref } from "@/lib/case-nav";
import {
  DELAYS,
  HANDOFF_DELAY_MS,
  SELECT_STEPS,
  STEPS,
  TASK_DONE,
  TOTAL_RUN_MS,
  statusAt,
} from "../_data";
import type { CloseCaseView } from "../_view";

export type TaskState = "done" | "active" | "pending";

export type CloseRun = {
  /** 0 before the run starts, `STEPS` once ingestion is complete. */
  step: number;
  complete: boolean;
  statusText: string;
  /** Seconds on the wall clock, formatted `mm:ss`. */
  clock: string;
  /** Marker state for each of the five ingestion tasks. */
  taskStates: TaskState[];
  selected: string[];
  selectedFiles: { id: string; name: string }[];
  isSelected: (id: string) => boolean;
  toggle: (id: string) => void;
};

function pad(n: number) {
  return n < 10 ? `0${n}` : `${n}`;
}

/** The step at which the run pins its n-th pick: the first three are spread out, the rest land together. */
function pinStep(index: number): number {
  return SELECT_STEPS[index] ?? SELECT_STEPS[SELECT_STEPS.length - 1];
}

/**
 * The scripted ingestion run.
 *
 * `DELAYS` accumulate into eight absolute `setTimeout`s exactly as the comp
 * schedules them; three of those steps also pin a source into the selection.
 * When the timeline is skipped - `autoplay={false}`, or the viewer asked for
 * reduced motion - the finished state is *derived* rather than replayed, so
 * nothing animates and no state is written on mount.
 */
export function useCloseRun({
  view,
  autoplay = true,
  autoAdvance = false,
  liveTimer = true,
}: {
  view: CloseCaseView;
  autoplay?: boolean;
  autoAdvance?: boolean;
  liveTimer?: boolean;
}): CloseRun {
  const router = useRouter();
  const reduced = useReducedMotion();
  const skipTimeline = autoplay === false || reduced === true;

  const [timelineStep, setTimelineStep] = useState(0);
  /** `null` until either the run or the viewer touches the selection. */
  const [picked, setPicked] = useState<string[] | null>(null);
  const [seconds, setSeconds] = useState(3);

  const step = skipTimeline ? STEPS : timelineStep;
  /** The files the agent really kept, in the order the grid lists them. */
  const agentPicks = useMemo(
    () => view.cards.filter((card) => card.picked).map((card) => card.id),
    [view.cards],
  );
  const baseline = useMemo<string[]>(
    () => (skipTimeline ? [...agentPicks] : []),
    [skipTimeline, agentPicks],
  );
  const selected = picked ?? baseline;

  /* The wall clock. Independent of the step timeline. */
  useEffect(() => {
    if (!liveTimer) return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [liveTimer]);

  /* The step timeline. */
  useEffect(() => {
    if (skipTimeline) return;

    const timers: ReturnType<typeof setTimeout>[] = [];
    let acc = 0;
    DELAYS.forEach((delay, i) => {
      acc += delay;
      const next = i + 1;
      timers.push(
        setTimeout(() => {
          setTimelineStep(next);
          const pins = agentPicks.filter((_, index) => pinStep(index) === next);
          if (pins.length === 0) return;
          setPicked((current) => {
            const base = current ?? [];
            return [...base, ...pins.filter((id) => !base.includes(id))];
          });
        }, acc),
      );
    });

    return () => timers.forEach(clearTimeout);
  }, [skipTimeline, agentPicks]);

  /* Handoff to the evidence agent - opt-in, so the app stays navigable. */
  useEffect(() => {
    if (!autoAdvance || skipTimeline) return;
    const id = setTimeout(
      () => router.push(caseHref(routes.evidence, view.obligationId)),
      TOTAL_RUN_MS + HANDOFF_DELAY_MS,
    );
    return () => clearTimeout(id);
  }, [autoAdvance, skipTimeline, router, view.obligationId]);

  const toggle = useCallback(
    (id: string) => {
      setPicked((current) => {
        const base = current ?? baseline;
        return base.includes(id)
          ? base.filter((x) => x !== id)
          : [...base, id];
      });
    },
    [baseline],
  );

  const isSelected = useCallback(
    (id: string) => selected.includes(id),
    [selected],
  );

  const complete = step >= STEPS;

  /**
   * `renderVals()` derives marker state from how many done-thresholds the run
   * has already crossed: everything at or below the current step reads done,
   * the next one up reads active until the run finishes.
   */
  const taskStates = useMemo<TaskState[]>(() => {
    const doneCount = TASK_DONE.filter((threshold) => step >= threshold).length;
    return TASK_DONE.map((threshold, i) => {
      if (step >= threshold) return "done";
      if (i === doneCount && !complete) return "active";
      return "pending";
    });
  }, [step, complete]);

  const selectedFiles = useMemo(
    () =>
      view.cards
        .filter((card) => selected.includes(card.id))
        .map((card) => ({ id: card.id, name: card.name })),
    [view.cards, selected],
  );

  return {
    step,
    complete,
    statusText: statusAt(step, selected.length),
    clock: `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`,
    taskStates,
    selected,
    selectedFiles,
    isSelected,
    toggle,
  };
}
