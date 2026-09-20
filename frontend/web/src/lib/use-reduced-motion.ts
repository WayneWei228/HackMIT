"use client";

import { useReducedMotion } from "motion/react";

/**
 * Multiplier for scripted timelines. Users who ask for reduced motion get the
 * end state of every agent run immediately rather than a shortened animation.
 */
export function useTimelineScale() {
  const reduced = useReducedMotion();
  return reduced ? 0 : 1;
}
