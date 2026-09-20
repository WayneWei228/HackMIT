"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { timing } from "../_motion";
import { adjustmentStates } from "../_data";
import { SubMarker } from "./markers";
import { useEstimationScreen } from "./screen-context";

/** Body of build step 4: three sub-checks that run one after the other. */
export function AdjustmentChecks({ step }: { step: number }) {
  const { adjustments, adjustmentsDone } = useEstimationScreen();
  const states = adjustmentStates(step);

  return (
    <div className="pt-[7px] pr-1 pl-[27px]">
      <div className="text-sm leading-[1.65] text-pretty text-muted-4">
        {step >= 12 ? adjustmentsDone : "Review credits, prepaid amounts, or other offsets..."}
      </div>
      <div className="mt-3 flex flex-col gap-[11px] rounded-lg bg-rail-alt px-3.5 py-3">
        {adjustments.map((check, i) => {
          const state = states[i];
          return (
            <div key={check.label} className="flex items-center gap-[11px]">
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
