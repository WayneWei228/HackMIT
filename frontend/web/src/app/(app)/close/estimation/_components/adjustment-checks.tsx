"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { timing } from "../_motion";
import { adjustmentStates } from "../_data";
import { SubMarker } from "./markers";
import { useEstimationData } from "./data-context";

/**
 * Body of build step 4: sub-checks that run one after the other. The lead
 * sentence is the step's own copy, handed down by the panel.
 */
export function AdjustmentChecks({
  step,
  text,
}: {
  step: number;
  text: string;
}) {
  const { ADJUSTMENTS } = useEstimationData().data;
  const states = adjustmentStates(step, ADJUSTMENTS.length);

  return (
    <div className="pt-[7px] pr-1 pl-[27px]">
      {text ? (
        <div className="text-sm leading-[1.65] text-pretty text-muted-4">
          {text}
        </div>
      ) : null}
      <div className="mt-3 flex flex-col gap-[11px] rounded-lg bg-rail-alt px-3.5 py-3">
        {ADJUSTMENTS.map((check, i) => {
          const state = states[i];
          return (
            <div
              key={`${check.label}-${i}`}
              className="flex items-center gap-[11px]"
            >
              <SubMarker state={state} />
              <span
                className={cn(
                  "flex-1 text-sm leading-[normal] transition-colors duration-[260ms] ease-[var(--ease-out-soft)]",
                  state === "pending" ? "text-faint-3" : "text-ink-2",
                )}
              >
                {check.label}
              </span>
              <motion.span
                animate={{ opacity: state === "done" ? 1 : 0 }}
                transition={timing.subDone}
                className="text-meta leading-[normal] text-faint-2"
              >
                {check.result}
              </motion.span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
