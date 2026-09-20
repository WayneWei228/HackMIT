"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useCaseId } from "@/lib/case-context";
import { formatDuration, useStageClock } from "@/lib/case-runner";
import { useCaseUi } from "@/lib/case-store";
import { RAIL_WIDTH } from "../_data";

/**
 * The Obligation screen's UI state. There is no scripted timeline: the screen
 * renders only after the backend has run the agents, so everything on it is the
 * agents' own output. What remains here is the reader's own state - which check
 * is open and how the rail is laid out - and it is kept across navigation.
 */
export function useObligationRun() {
  const obligationId = useCaseId();
  const clock = formatDuration(useStageClock(obligationId, "obligation", true));

  const [openCheck, setOpenCheck] = useCaseUi<string | null>(obligationId, "obligation.check", null);
  const [railOpen, setRailOpen] = useCaseUi(obligationId, "obligation.rail", true);
  const [railWidth, setRailWidth] = useState<number>(RAIL_WIDTH.initial);
  const [dragging, setDragging] = useState(false);

  const toggleCheck = useCallback(
    (id: string) => setOpenCheck(openCheck === id ? null : id),
    [openCheck, setOpenCheck],
  );
  const toggleRail = useCallback(() => setRailOpen(!railOpen), [railOpen, setRailOpen]);

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

  return {
    clock,
    openCheck,
    toggleCheck,
    railOpen,
    railMini: !railOpen,
    railWidth,
    dragging,
    toggleRail,
    startResize,
  };
}
