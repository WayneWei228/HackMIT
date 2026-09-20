"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

import { CHECKLIST } from "../_data";
import type { TaskState } from "./use-close-run";
import { TaskCheckIcon } from "./close-icons";

/** The comp's own 260ms marker transition, on the shared easing curve. */
const MARKER = { duration: 0.26, ease: easeOutSoft } as const;

/**
 * The five ingestion tasks, hanging off the stage rule.
 *
 * A marker has three faces in the same 13px box - an empty ring while pending,
 * a filled dot that swells in while it is the live task, and a tick once the
 * run has moved past it - so nothing reflows as the run advances.
 */
export function StepChecklist({ states }: { states: TaskState[] }) {
  return (
    <div className="mt-3.5 ml-[33px] flex flex-col gap-[13px] border-l border-line pl-5">
      {CHECKLIST.map((label, i) => {
        const state = states[i];
        return (
          <div key={label} className="flex items-center gap-3">
            <span className="relative mx-px h-[13px] w-[13px] flex-none">
              <motion.span
                animate={{ opacity: state === "pending" ? 1 : 0 }}
                transition={MARKER}
                className="absolute inset-px rounded-full border border-rule"
              />
              <motion.span
                animate={{
                  opacity: state === "active" ? 1 : 0,
                  scale: state === "active" ? 1 : 0.5,
                }}
                transition={MARKER}
                className="absolute inset-px rounded-full bg-accent"
              />
              <motion.span
                animate={{ opacity: state === "done" ? 1 : 0 }}
                transition={MARKER}
                className="absolute inset-0 text-accent"
              >
                <TaskCheckIcon />
              </motion.span>
            </span>
            <span
              className={cn(
                "text-sm transition-colors duration-[260ms] ease-[var(--ease-out-soft)]",
                state === "pending" ? "text-faint-3" : "text-ink-2",
              )}
            >
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
