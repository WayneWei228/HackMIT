"use client";

import { useEffect, useRef, useState } from "react";

import { useCaseId } from "./case-context";
import { useCaseUi, type StageKey } from "./case-store";

/**
 * How many of a stage's returned items to show right now. When the reader has
 * just run the stage, the runner leaves a one-time flag for it and the items
 * appear one after another, as a presentation of data the backend already
 * returned. Without the flag - a finished case opened later, a reload, or a run
 * the reader did not watch - everything is shown at once and nothing replays.
 */
export function useReveal(stage: StageKey, total: number, stepMs = 380): number {
  const id = useCaseId();
  const [flag, setFlag] = useCaseUi<boolean>(id, `reveal.${stage}`, false);
  const [shown, setShown] = useState(() => (flag && total > 0 ? 0 : total));
  const started = useRef(false);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!flag || started.current) return;
    started.current = true;
    setFlag(false);
    if (total === 0) return;
    let count = 0;
    const tick = () => {
      if (!mounted.current) return;
      count += 1;
      setShown(count);
      if (count < total) setTimeout(tick, stepMs);
    };
    setTimeout(tick, stepMs);
  }, [flag, setFlag, total, stepMs]);

  return Math.min(shown, total);
}
