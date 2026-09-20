import type { Transition, Variants } from "motion/react";

/**
 * Shared motion vocabulary.
 *
 * The comps move very little on purpose: this is an accounting surface, so
 * animation is there to explain causality (a fact arrived, a step finished)
 * and never to decorate. Everything below is short, eased out, and small in
 * travel - 4 to 10 pixels. Any component that needs something louder than
 * this is probably wrong.
 */

export const easeOutSoft = [0.22, 0.61, 0.36, 1] as const;

export const transitions = {
  fast: { duration: 0.16, ease: easeOutSoft },
  base: { duration: 0.22, ease: easeOutSoft },
  slow: { duration: 0.38, ease: easeOutSoft },
  spring: { type: "spring", stiffness: 420, damping: 38, mass: 0.8 },
} satisfies Record<string, Transition>;

/** Content settling in: a short rise with a fade. */
export const riseIn: Variants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: transitions.base },
};

/** Same, but for items that should land one after another. */
export const riseInStagger = (index: number, step = 0.035): Variants => ({
  hidden: { opacity: 0, y: 6 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { ...transitions.base, delay: index * step },
  },
});

/** Parent of a staggered list. */
export const staggerParent = (step = 0.035, delay = 0): Variants => ({
  hidden: {},
  visible: { transition: { staggerChildren: step, delayChildren: delay } },
});

/** A row arriving in a table. */
export const rowIn: Variants = {
  hidden: { opacity: 0, y: 4 },
  visible: { opacity: 1, y: 0, transition: transitions.base },
};

/** Panels that swap in place (document viewer, tab bodies). */
export const crossFade: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: transitions.fast },
  exit: { opacity: 0, transition: { duration: 0.13, ease: easeOutSoft } },
};

/** A side rail opening or closing. */
export const railIn: Variants = {
  hidden: { opacity: 0, x: 12 },
  visible: { opacity: 1, x: 0, transition: transitions.slow },
  exit: { opacity: 0, x: 12, transition: transitions.base },
};

/** Popovers and menus. */
export const popIn: Variants = {
  hidden: { opacity: 0, y: -4, scale: 0.985 },
  visible: { opacity: 1, y: 0, scale: 1, transition: transitions.fast },
  exit: { opacity: 0, y: -4, scale: 0.985, transition: transitions.fast },
};
