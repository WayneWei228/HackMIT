"use client";

import type { Transition } from "motion/react";

import { easeOutSoft } from "@/lib/motion";

/**
 * The comp drives this screen with a dozen different CSS transition
 * durations - a marker ring crossfades in 280ms, the tick that replaces it in
 * 320ms, a step body opens in 340ms, a fact card settles in 400ms. The shared
 * `transitions` vocabulary only carries three durations, so the exact set
 * lives here, all on the app's single easing curve.
 */

const at = (duration: number): Transition => ({ duration, ease: easeOutSoft });

export const timing = {
  /** Pending ring and the running ring on a build-step marker. */
  markerRing: at(0.28),
  /** The solid tick that replaces them. */
  markerDone: at(0.32),
  /** Ring and spinner on a 13px sub-check or rail task. */
  subRing: at(0.26),
  /** The bare tick that replaces them. */
  subDone: at(0.3),
  /** A step title's chevron rotating. */
  chevron: at(0.28),
  /** A step body opening - the two short bodies. */
  body: at(0.34),
  /** A step body opening - the calc table and the sub-check list. */
  bodyTall: at(0.38),
  /** The "Waiting" line fading out once a step starts. */
  waiting: at(0.26),
  /** An input card or a recommendation row arriving. */
  fact: at(0.4),
  /** A calc row arriving. */
  calcRow: at(0.34),
  /** The confirmations that land at the end of the run. */
  settle: at(0.45),
  /** The em dash handing over to the final amount. */
  dash: at(0.25),
  /** Status colours and the pulse ring switching off. */
  state: at(0.3),
} satisfies Record<string, Transition>;

/** Same curve and duration, offset so a list lands one row after another. */
export const stagger = (base: Transition, delay: number): Transition => ({
  ...base,
  delay,
});
