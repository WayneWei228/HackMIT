"use client";

import { motion } from "motion/react";

import { RefreshIcon } from "@/components/ui/icons";
import { easeOutSoft, transitions } from "@/lib/motion";
import { CHK_DONE, completedChecks, statusLines } from "../_data";
import { PulseDot } from "./glyphs";
import { useObligationScreen } from "./screen-context";

/**
 * The narration strip under the header: what the agent is doing right now,
 * how far through its checks it is, and a way to watch the run again.
 */
export function AgentStatusBar({
  step,
  complete,
  onReplay,
}: {
  step: number;
  complete: boolean;
  onReplay: () => void;
}) {
  const { closing, evidenceInputsLabel } = useObligationScreen();
  const done = completedChecks(step);
  const lines = statusLines(closing);
  const status = lines[Math.min(step, lines.length - 1)];

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[13px]">
      <div className="flex min-w-0 items-center gap-[11px]">
        <PulseDot pulsing={!complete} />
        <span className="text-ui font-medium whitespace-nowrap text-ink">
          Obligation agent
        </span>
        <motion.span
          key={status}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={transitions.fast}
          className="truncate text-ui text-faint-3"
        >
          {status}
        </motion.span>
      </div>

      <div className="flex flex-none items-center gap-3.5 text-sm leading-[normal]">
        <span className="whitespace-nowrap text-faint-2">
          {evidenceInputsLabel}
        </span>
        <span aria-hidden="true" className="text-line-mute">
          |
        </span>
        <span className="font-medium whitespace-nowrap text-ink tabular-nums">
          {done} / {CHK_DONE.length} checks complete
        </span>
        <div className="relative h-[5px] w-[104px] overflow-hidden rounded-sm bg-divider-2">
          <motion.div
            animate={{ width: `${(done / CHK_DONE.length) * 100}%` }}
            transition={{ duration: 0.9, ease: easeOutSoft }}
            className="h-full rounded-sm bg-accent"
          />
          <motion.div
            aria-hidden="true"
            animate={{
              x: ["-120%", "330%", "330%"],
              opacity: complete ? 0 : 1,
            }}
            transition={{
              x: {
                duration: 2.2,
                times: [0, 0.55, 1],
                ease: "easeInOut",
                repeat: Infinity,
              },
              opacity: transitions.slow,
            }}
            className="absolute top-0 left-0 h-full w-[36%] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.6),rgba(255,255,255,0))]"
          />
        </div>
        <button
          type="button"
          onClick={onReplay}
          title="Replay sequence"
          className="flex cursor-pointer items-center gap-[7px] rounded-lg border border-transparent bg-transparent px-[9px] py-1.5 text-meta leading-none whitespace-nowrap text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash hover:text-ink"
        >
          <RefreshIcon size={12} />
          Replay
        </button>
      </div>
    </div>
  );
}
