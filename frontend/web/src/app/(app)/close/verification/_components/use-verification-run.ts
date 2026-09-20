"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useCaseId } from "@/lib/case-context";
import { formatDuration, useStageClock } from "@/lib/case-runner";
import {
  RAIL_DEFAULT_WIDTH,
  RAIL_MAX_WIDTH,
  RAIL_MIN_WIDTH,
  deriveView,
  type VerificationData,
  type VerificationView,
} from "../_data";

type Options = {
  /** What the Verification agents recorded for this case. */
  data: VerificationData;
};

export type VerificationRun = {
  view: VerificationView;
  clock: string;
  openControl: number;
  toggleControl: (index: number) => void;
  railOpen: boolean;
  toggleRail: () => void;
  railWidth: number;
  dragging: boolean;
  startResize: (event: React.MouseEvent<HTMLElement>) => void;
};

/**
 * The comp's `Component` class: the scripted timeline, the live clock, the
 * accordion, and the resizable execution rail.
 *
 * With reduced motion on, the timeline never runs and the finished state is
 * rendered straight away.
 */
export function useVerificationRun({ data }: Options): VerificationRun {
  const obligationId = useCaseId();
  const clock = formatDuration(useStageClock(obligationId, "verification", true));

  // The accordion follows the running check until the reader takes it over.
  const [accordion, setAccordion] = useState<{
    open: number;
    userOpened: boolean;
  }>({ open: -1, userOpened: false });

  const [railOpen, setRailOpen] = useState(true);
  const [railWidth, setRailWidth] = useState(RAIL_DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);

  const railWidthRef = useRef(railWidth);
  useEffect(() => {
    railWidthRef.current = railWidth;
  }, [railWidth]);

  const view = useMemo(() => deriveView(data), [data]);

  const toggleControl = useCallback((index: number) => {
    setAccordion((current) => ({
      userOpened: true,
      open: current.userOpened && current.open === index ? -1 : index,
    }));
  }, []);

  const toggleRail = useCallback(() => setRailOpen((value) => !value), []);

  const startResize = useCallback((event: React.MouseEvent<HTMLElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = railWidthRef.current;

    const move = (moveEvent: MouseEvent) => {
      setRailWidth(
        Math.max(
          RAIL_MIN_WIDTH,
          Math.min(RAIL_MAX_WIDTH, startWidth - (moveEvent.clientX - startX)),
        ),
      );
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setDragging(false);
    };

    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    setDragging(true);
  }, []);

  return {
    view,
    clock,
    openControl: accordion.userOpened ? accordion.open : view.autoOpen,
    toggleControl,
    railOpen,
    toggleRail,
    railWidth,
    dragging,
    startResize,
  };
}
