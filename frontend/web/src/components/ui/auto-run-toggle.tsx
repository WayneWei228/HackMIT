"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import { transitions } from "@/lib/motion";
import { useAutoRun } from "@/lib/use-auto-run";

/**
 * The switch that plays the whole agent chain without clicks.
 *
 * It sits in the live execution rail, beside the run's own clock, because
 * that is where the reader is watching the agent work and where the hand-off
 * they are about to stop clicking lives. The track is the same accent wash
 * the selected states use; nothing new enters the design system.
 */
export function AutoRunToggle({ className }: { className?: string }) {
  const { auto, toggle } = useAutoRun();
  const reduced = useReducedMotion();

  /* These screens answer `prefers-reduced-motion` by not playing the run at
     all - they render the finished state straight away. With no run to
     finish there is no hand-off to follow, and marching someone who asked
     for less movement through eight screens would be the opposite of what
     they asked for. So the chain does not run, and the switch says so
     rather than sitting there looking armed. */
  if (reduced) {
    return (
      <div
        className={cn(
          "flex w-full items-center justify-between gap-2.5 rounded-lg px-2 py-1.5",
          className,
        )}
        title="Turn off reduced motion to play the chain automatically"
      >
        <span className="text-meta text-ghost">Auto-run agents</span>
        <span className="text-meta text-ghost">Off for reduced motion</span>
      </div>
    );
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={auto}
      onClick={toggle}
      title={
        auto
          ? "Each agent hands off to the next on its own"
          : "Play the whole chain without clicking"
      }
      className={cn(
        "flex w-full cursor-pointer items-center justify-between gap-2.5 rounded-lg border border-transparent px-2 py-1.5 text-left transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]",
        className,
      )}
    >
      <span
        className={cn(
          "text-meta transition-colors duration-[160ms]",
          auto ? "font-medium text-ink" : "text-faint",
        )}
      >
        Auto-run agents
      </span>
      <span
        aria-hidden="true"
        className={cn(
          "relative h-[16px] w-[28px] flex-none rounded-full transition-colors duration-[200ms] ease-[var(--ease-out-soft)]",
          auto ? "bg-accent" : "bg-rule",
        )}
      >
        <motion.span
          initial={false}
          animate={{ x: auto ? 13 : 1 }}
          transition={transitions.base}
          className="absolute top-[2px] left-0 h-3 w-3 rounded-full bg-panel shadow-[var(--shadow-hairline)]"
        />
      </span>
    </button>
  );
}
