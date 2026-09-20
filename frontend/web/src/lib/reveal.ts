"use client";

import { useEffect, useRef, useState } from "react";

import { useCaseId } from "./case-context";
import { useCaseUi, type StageKey } from "./case-store";

/**
 * How many of a stage's returned items to show right now. When the reader is
 * watching a stage run, the runner leaves a one-time flag for it and the items
 * appear one after another, as a presentation of data the backend has returned.
 * The screen may be drawn before there is anything to show (`total` 0), and the
 * items may arrive in batches (Evidence reads one document per call), so the
 * reveal starts when items exist and keeps catching up to whatever has arrived.
 * Without the flag - a finished case opened later, a reload, or a run the reader
 * did not watch - everything is shown at once and nothing replays.
 */
export function useReveal(stage: StageKey, total: number, stepMs = 380): number {
  const id = useCaseId();
  const [flag, setFlag] = useCaseUi<boolean>(id, `reveal.${stage}`, false);
  const [shown, setShown] = useState(() => (flag ? 0 : total));
  const shownRef = useRef(shown);
  const animating = useRef(false);
  const latest = useRef(total);
  const mounted = useRef(false);

  useEffect(() => {
    latest.current = total;
  }, [total]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const hasItems = total > 0;
  useEffect(() => {
    if (!flag || !hasItems) return;
    setFlag(false);
    /* A reveal already under way keeps going, up to the new total. */
    if (animating.current) return;
    animating.current = true;
    const tick = () => {
      if (!mounted.current) return;
      if (shownRef.current < latest.current) {
        shownRef.current += 1;
        setShown(shownRef.current);
      }
      if (shownRef.current < latest.current) setTimeout(tick, stepMs);
      else animating.current = false;
    };
    setTimeout(tick, stepMs);
  }, [flag, hasItems, setFlag, stepMs]);

  useEffect(() => {
    if (!flag && !animating.current && shownRef.current < total) {
      shownRef.current = total;
      setShown(total);
    }
  }, [flag, total]);

  return Math.min(shown, total);
}
