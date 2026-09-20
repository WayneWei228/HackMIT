"use client";

import type { Transition } from "motion/react";
import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import type { NodeState } from "../_data";
import { timing } from "../_motion";
import { SpinnerIcon, StepDoneIcon, TickIcon } from "./icons";

/**
 * The three progress glyphs this screen uses. Each one stacks its pending,
 * running and finished layers and cross-fades between them, so nothing ever
 * pops in or shifts the row it sits in.
 */

const fade = (visible: boolean, transition: Transition) => ({
  animate: { opacity: visible ? 1 : 0 },
  transition,
});

/** 17px node on the Estimate build timeline. */
export function StepMarker({ state }: { state: NodeState }) {
  return (
    <span className="absolute top-px left-0 h-[17px] w-[17px]">
      <motion.span
        {...fade(state === "pending", timing.markerRing)}
        className="absolute inset-0 rounded-full border-[1.4px] border-rule-soft"
      />
      <motion.span
        {...fade(state === "active", timing.markerRing)}
        className="absolute inset-0 rounded-full border-2 border-accent"
      />
      <motion.span
        {...fade(state === "done", timing.markerDone)}
        className="absolute inset-0"
      >
        <StepDoneIcon size={17} />
      </motion.span>
    </span>
  );
}

/** 13px node beside an adjustment sub-check, spinning while it runs. */
export function SubMarker({ state }: { state: NodeState }) {
  return (
    <span className="relative h-[13px] w-[13px] flex-none">
      <motion.span
        {...fade(state === "pending", timing.subRing)}
        className="absolute inset-0 rounded-full border border-rule"
      />
      <motion.span
        {...fade(state === "active", timing.subRing)}
        className="absolute inset-0 animate-spin [animation-duration:1.1s]"
      >
        <SpinnerIcon size={13} />
      </motion.span>
      <motion.span
        {...fade(state === "done", timing.subDone)}
        className="absolute inset-0"
      >
        <TickIcon size={13} />
      </motion.span>
    </span>
  );
}

/** 13px node beside a task bullet in the live execution rail. */
export function TaskMarker({ state }: { state: NodeState }) {
  return (
    <span className="relative mx-px h-[13px] w-[13px] flex-none">
      <motion.span
        {...fade(state === "pending", timing.subRing)}
        className="absolute inset-px rounded-full border border-rule"
      />
      <motion.span
        animate={{
          opacity: state === "active" ? 1 : 0,
          scale: state === "active" ? 1 : 0.5,
        }}
        transition={timing.subRing}
        className="absolute inset-px rounded-full bg-accent"
      />
      <motion.span
        {...fade(state === "done", timing.subDone)}
        className="absolute inset-0"
      >
        <TickIcon size={13} />
      </motion.span>
    </span>
  );
}

/** The green dot with its slow expanding ring, used in headers and the rail. */
export function LiveDot({
  pulsing,
  halo = false,
  className,
}: {
  pulsing: boolean;
  /** The header variants carry a soft 3px ring under the dot. */
  halo?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative h-[9px] w-[9px] flex-none", className)}>
      <span
        className={cn(
          "absolute inset-0 rounded-full bg-accent",
          halo && "shadow-[var(--shadow-ring)]",
        )}
      />
      <motion.span
        animate={{ opacity: pulsing ? 1 : 0 }}
        transition={timing.state}
        className="animate-pulse-ring absolute -inset-1 rounded-full border-[1.3px] border-[rgba(46,128,71,0.55)] [animation-duration:2.6s]"
      />
    </span>
  );
}
