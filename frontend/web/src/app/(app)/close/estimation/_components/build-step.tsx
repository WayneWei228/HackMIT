"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";

import { ChevronDownIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import type { NodeState } from "../_data";
import { timing } from "../_motion";
import { StepMarker } from "./markers";

/**
 * One rung of the Estimate build timeline: a marker, a clickable title, a
 * collapsible body, and the hairline that joins it to the next rung.
 */
export function BuildStep({
  n,
  title,
  state,
  open,
  last = false,
  tallBody = false,
  waiting,
  onToggle,
  children,
}: {
  n: string;
  title: string;
  state: NodeState;
  open: boolean;
  last?: boolean;
  /** The calc table and the sub-check list open a touch slower in the comp. */
  tallBody?: boolean;
  /**
   * Steps 4 and 5 carry a "Waiting" line under the body. Omit the prop for the
   * steps that do not have one; pass false to fade it out.
   */
  waiting?: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const lit = state === "done" || state === "active";

  return (
    <div className={cn("relative pl-10", last ? "pb-0" : "pb-[22px]")}>
      {!last && (
        <span
          className={cn(
            "absolute top-[22px] bottom-0 left-2 w-px transition-colors duration-500 ease-[var(--ease-out-soft)]",
            state === "done" ? "bg-accent-line" : "bg-line",
          )}
        />
      )}
      <StepMarker state={state} />

      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-3.5 text-left"
      >
        <span className="text-sm leading-[normal] text-faint-3 tabular-nums">
          {n}
        </span>
        <span
          className={`flex-1 text-nav leading-[normal] transition-colors duration-[280ms] ease-[var(--ease-out-soft)] ${
            lit ? "text-ink" : "text-faint-3"
          }`}
        >
          {title}
        </span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={timing.chevron}
          className="flex flex-none text-faint-3"
        >
          <ChevronDownIcon size={13} />
        </motion.span>
      </button>

      <motion.div
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={tallBody ? timing.bodyTall : timing.body}
        initial={false}
        className="overflow-hidden"
      >
        {children}
      </motion.div>

      {waiting !== undefined && (
        <motion.div
          animate={{ opacity: waiting ? 1 : 0 }}
          transition={timing.waiting}
          className="pt-[7px] pr-[26px] pl-[27px] text-sm leading-[normal] text-faint-3"
        >
          Waiting
        </motion.div>
      )}
    </div>
  );
}
