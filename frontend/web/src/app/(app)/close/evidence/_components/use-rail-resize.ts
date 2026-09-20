"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";

export const RAIL_MIN = 288;
export const RAIL_MAX = 620;
export const RAIL_DEFAULT = 330;

export type RailState = {
  open: boolean;
  width: number;
  dragging: boolean;
  toggle: () => void;
  startResize: (event: ReactMouseEvent) => void;
};

/**
 * The execution rail is draggable between 288 and 620px. The handle sits on the
 * rail's left edge, so widening means dragging left - hence the inverted delta.
 */
export function useRailResize(): RailState {
  const [open, setOpen] = useState(true);
  const [width, setWidth] = useState(RAIL_DEFAULT);
  const [dragging, setDragging] = useState(false);
  const widthRef = useRef(RAIL_DEFAULT);
  const releaseRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  useEffect(() => () => releaseRef.current?.(), []);

  const startResize = useCallback((event: ReactMouseEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = widthRef.current;

    const move = (moveEvent: globalThis.MouseEvent) => {
      const next = Math.max(
        RAIL_MIN,
        Math.min(RAIL_MAX, startWidth - (moveEvent.clientX - startX)),
      );
      setWidth(next);
    };

    const release = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", release);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      releaseRef.current = null;
      setDragging(false);
    };

    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", release);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    releaseRef.current = release;
    setDragging(true);
  }, []);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  return { open, width, dragging, toggle, startResize };
}
