"use client";

import { motion, useReducedMotion } from "motion/react";

import { RefreshIcon } from "@/components/ui/icons";
import { easeOutSoft } from "@/lib/motion";
import { CHK_DONE, completedChecks, statusLines } from "../_data";
import { LiveDot } from "./markers";
import { useEstimationScreen } from "./screen-context";

/**
 * The narration strip between the case header and the working columns: who is
 * running, what it is doing right now, and how far through its checks it is.
 */
export function AgentBar({
  step,
  complete,
  onReplay,
}: {
  step: number;
  complete: boolean;
  onReplay: () => void;
}) {
  const reduced = useReducedMotion();
  const { closing, inputs } = useEstimationScreen();
  const inputCount = inputs.length;
  const done = completedChecks(step);
  const pct = (done / CHK_DONE.length) * 100;

  return (
    <>
      <div className="h-px flex-none bg-line" />
      <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[13px]">
        <div className="flex min-w-0 items-center gap-[11px]">
          <LiveDot pulsing={!complete} />
          <span className="text-ui leading-[normal] font-medium whitespace-nowrap text-ink">
            Estimation agent
          </span>
          <span className="truncate text-ui leading-[normal] whitespace-nowrap text-faint-3">
            {statusLines(closing)[step]}
          </span>
        </div>

        <div className="flex flex-none items-center gap-3.5 text-sm leading-[normal]">
          <span className="whitespace-nowrap text-faint-2">{inputCount} inputs</span>
          <span aria-hidden="true" className="text-line-mute">
            |
          </span>
          <span className="font-medium whitespace-nowrap text-ink tabular-nums">
            {done} / {CHK_DONE.length} checks complete
          </span>

          <div className="relative h-[5px] w-[104px] overflow-hidden rounded-sm bg-divider-2">
            <motion.div
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.9, ease: easeOutSoft }}
              className="h-full rounded-sm bg-accent"
            />
            <motion.div
              animate={
                reduced
                  ? { opacity: 0 }
                  : { x: ["-120%", "330%", "330%"], opacity: complete ? 0 : 1 }
              }
              transition={{
                x: {
                  duration: 2.2,
                  times: [0, 0.55, 1],
                  ease: "easeInOut",
                  repeat: Infinity,
                },
                opacity: { duration: 0.3, ease: "easeOut" },
              }}
              className="absolute top-0 left-0 h-full w-[36%] bg-gradient-to-r from-transparent via-white/60 to-transparent"
            />
          </div>

          <button
            type="button"
            onClick={onReplay}
            title="Replay sequence"
            className="flex cursor-pointer items-center gap-[7px] rounded-lg border border-transparent px-[9px] py-1.5 text-meta leading-none whitespace-nowrap text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash hover:text-ink"
          >
            <RefreshIcon />
            Replay
          </button>
        </div>
      </div>
    </>
  );
}
