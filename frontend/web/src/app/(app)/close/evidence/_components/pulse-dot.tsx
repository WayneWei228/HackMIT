"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import { easeOutSoft, transitions } from "@/lib/motion";

/**
 * The running indicator: a 9px accent disc with a ring that breathes while the
 * agent is working and fades away once it finishes.
 *
 * The comp drives this with a 2.6s `pulseRing` keyframe; `globals.css` only
 * ships the 1.8s variant, so the ring is expressed in Motion instead - same
 * curve, same duration, and it stops under `prefers-reduced-motion`.
 */
export function PulseDot({
  pulsing,
  halo = false,
  className,
}: {
  /** Ring animates while the run is live. */
  pulsing: boolean;
  /** The soft 3px accent glow behind the disc. */
  halo?: boolean;
  className?: string;
}) {
  const reduced = useReducedMotion();

  return (
    <span className={cn("relative h-[9px] w-[9px] flex-none", className)}>
      <span
        className={cn(
          "absolute inset-0 rounded-full bg-accent",
          halo && "shadow-[var(--shadow-ring)]",
        )}
      />
      <AnimatePresence>
        {pulsing && (
          <motion.span
            className="absolute -inset-1"
            initial={{ opacity: 1 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.3, ease: easeOutSoft } }}
          >
            {/* The ring is always rendered so server and client agree on the
                first paint; reduced motion settles it to nothing instead of
                dropping the element. */}
            <motion.span
              className="block h-full w-full rounded-full border-[1.3px] border-[rgba(46,128,71,0.55)]"
              initial={{ scale: 0.72, opacity: 0.5 }}
              animate={
                reduced
                  ? { scale: 0.72, opacity: 0 }
                  : { scale: [0.72, 1.5, 1.5], opacity: [0.5, 0, 0] }
              }
              transition={
                reduced
                  ? { duration: 0 }
                  : {
                      duration: 2.6,
                      times: [0, 0.7, 1],
                      ease: easeOutSoft,
                      repeat: Infinity,
                    }
              }
            />
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

/** Static disc for the collapsed rail - no ring, halo always on. */
export function RunDot({ className }: { className?: string }) {
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={transitions.base}
      className={cn(
        "h-[9px] w-[9px] flex-none rounded-full bg-accent shadow-[var(--shadow-ring)]",
        className,
      )}
    />
  );
}
