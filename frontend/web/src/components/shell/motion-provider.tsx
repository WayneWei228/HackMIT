"use client";

import { MotionConfig } from "motion/react";

/**
 * One place to state the app's motion policy.
 *
 * `reducedMotion="user"` makes every Motion component in the tree drop
 * transform and layout animation when the OS asks for less motion, while
 * leaving opacity crossfades intact. Without it each component has to check
 * `useReducedMotion()` itself, and doing that during render desynchronises
 * server and client markup.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
