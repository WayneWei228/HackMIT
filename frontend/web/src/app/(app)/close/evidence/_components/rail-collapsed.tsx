"use client";

import { motion } from "motion/react";

import { CaretLeftIcon } from "@/components/ui/icons";
import { transitions } from "@/lib/motion";

import { RAIL } from "../_data";
import { RunDot } from "./pulse-dot";

/** The 56px strip the execution rail folds down to in focus mode. */
export function CollapsedRail({ onExpand }: { onExpand: () => void }) {
  return (
    <motion.aside
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.fast}
      className="flex w-14 flex-none flex-col items-center gap-[18px] border-l border-line bg-panel-hover py-[22px]"
    >
      <button
        type="button"
        onClick={onExpand}
        title="Expand live execution"
        className="flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-deep"
      >
        <CaretLeftIcon size={13} />
      </button>

      <RunDot />

      <div className="text-eyebrow font-medium tracking-[0.14em] whitespace-nowrap text-faint [writing-mode:vertical-rl] rotate-180">
        {RAIL.eyebrow}
      </div>
      <div className="font-display text-md whitespace-nowrap text-ink-deep [writing-mode:vertical-rl] rotate-180">
        {RAIL.handoffFrom}
      </div>
    </motion.aside>
  );
}
