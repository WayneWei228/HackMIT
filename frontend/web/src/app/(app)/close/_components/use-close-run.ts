"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";

import { routes } from "@/lib/routes";
import {
  DELAYS,
  HANDOFF_DELAY_MS,
  SELECT_AT,
  SOURCE_NAMES,
  SOURCE_ORDER,
  STATUS,
  STEPS,
  TASK_DONE,
  TOTAL_RUN_MS,
  type SourceId,
} from "../_data";

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
  selected: SourceId[];
  selectedFiles: { id: SourceId; name: string }[];
  isSelected: (id: SourceId) => boolean;
  toggle: (id: SourceId) => void;
};

function pad(n: number) {
  return n < 10 ? `0${n}` : `${n}`;
}

/** What the run has picked by the time it finishes: the first three sources. */
const FINISHED_SELECTION: readonly SourceId[] = SOURCE_ORDER.slice(0, 3);

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
  autoplay = true,
  autoAdvance = false,
  liveTimer = true,
}: {
  autoplay?: boolean;
  autoAdvance?: boolean;
  liveTimer?: boolean;
}): CloseRun {
  const router = useRouter();
  const reduced = useReducedMotion();
  const skipTimeline = autoplay === false || reduced === true;

  const [timelineStep, setTimelineStep] = useState(0);
  /** `null` until either the run or the viewer touches the selection. */
  const [picked, setPicked] = useState<SourceId[] | null>(null);
  const [seconds, setSeconds] = useState(3);

  const step = skipTimeline ? STEPS : timelineStep;
  const baseline = useMemo<SourceId[]>(
    () => (skipTimeline ? [...FINISHED_SELECTION] : []),
    [skipTimeline],
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
          const add = SELECT_AT[next];
          if (!add) return;
          setPicked((current) => {
            const base = current ?? [];
            return base.includes(add) ? base : [...base, add];
          });
        }, acc),
      );
    });

    return () => timers.forEach(clearTimeout);
  }, [skipTimeline]);

  /* Handoff to the evidence agent - opt-in, so the app stays navigable. */
  useEffect(() => {
    if (!autoAdvance || skipTimeline) return;
    const id = setTimeout(
      () => router.push(routes.evidence),
      TOTAL_RUN_MS + HANDOFF_DELAY_MS,
    );
    return () => clearTimeout(id);
  }, [autoAdvance, skipTimeline, router]);

  const toggle = useCallback(
    (id: SourceId) => {
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
    (id: SourceId) => selected.includes(id),
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
      SOURCE_ORDER.filter((id) => selected.includes(id)).map((id) => ({
        id,
        name: SOURCE_NAMES[id],
      })),
    [selected],
  );

  return {
    step,
    complete,
    statusText: STATUS[Math.min(step, STATUS.length - 1)],
    clock: `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`,
    taskStates,
    selected,
    selectedFiles,
    isSelected,
    toggle,
  };
}
