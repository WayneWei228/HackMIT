"use client";

import type { MouseEvent as ReactMouseEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useCaseId } from "@/lib/case-context";
import { formatDuration, useStageClock } from "@/lib/case-runner";

export type EstimationRun = {
  /** The measured time the Estimation agent took, or "-" when this browser did not see it run. */
  clock: string;
};

/** The screen renders only once the backend has run the agent, so there is no timeline to play. */
export function useEstimationRun(): EstimationRun {
  const obligationId = useCaseId();
  const clock = formatDuration(useStageClock(obligationId, "estimation", true));
  return { clock };
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
