"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { RAIL_DEFAULT_WIDTH, RAIL_MAX_WIDTH, RAIL_MIN_WIDTH } from "../_data";

/**
 * Drag-to-resize for the live execution rail.
 *
 * The rail is anchored to the right edge, so dragging left widens it - hence
 * the inverted delta. The cursor and text selection are locked on the body for
 * the duration of the drag so the pointer never flickers over the grid.
 */
export type RailResize = {
  width: number;
  dragging: boolean;
  startResize: (event: React.MouseEvent<HTMLDivElement>) => void;
};

export function useRailResize(): RailResize {
  const [width, setWidth] = useState(RAIL_DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);
  const cleanup = useRef<(() => void) | null>(null);

  useEffect(() => () => cleanup.current?.(), []);

  const startResize = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = width;

      const move = (e: MouseEvent) => {
        const next = Math.max(
          RAIL_MIN_WIDTH,
          Math.min(RAIL_MAX_WIDTH, startWidth - (e.clientX - startX)),
        );
        setWidth(next);
      };

      const stop = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", stop);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        cleanup.current = null;
        setDragging(false);
      };

      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", stop);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      cleanup.current = stop;
      setDragging(true);
    },
    [width],
  );

  return { width, dragging, startResize };
}
