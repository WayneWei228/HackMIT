"use client";

import { motion, useReducedMotion } from "motion/react";

import { RefreshIcon } from "@/components/ui/icons";
import { easeOutSoft } from "@/lib/motion";
import { useControlsData } from "./data-context";
import { LiveDot } from "./marks";

/** The travelling highlight on the progress bar while the run is live. */
function Sheen({ show }: { show: boolean }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      aria-hidden="true"
      initial={false}
      animate={{ opacity: show ? 1 : 0 }}
      transition={{ duration: 0.3, ease: easeOutSoft }}
      className="pointer-events-none absolute inset-0"
    >
      <motion.div
        className="absolute top-0 left-0 h-full w-[36%] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.6),rgba(255,255,255,0))]"
        animate={reduced ? undefined : { x: ["-120%", "330%", "330%"] }}
        transition={
          reduced
            ? undefined
            : {
                duration: 2.2,
                times: [0, 0.55, 1],
                ease: "easeInOut",
                repeat: Infinity,
              }
        }
      />
    </motion.div>
  );
}

export function AgentStatusBar({
  statusText,
  passedLabel,
  controlsLabel,
  progress,
  pulse,
  onReplay,
}: {
  statusText: string;
  passedLabel: string;
  /** "6 controls" - counted from the dataset, live or synthetic. */
  controlsLabel: string;
  progress: number;
  pulse: boolean;
  onReplay: () => void;
}) {
  const { agentLabel } = useControlsData();

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[13px]">
      <div className="flex min-w-0 items-center gap-[11px]">
        <LiveDot pulse={pulse} ring={false} />
        <span className="text-ui font-medium whitespace-nowrap text-ink">
          {agentLabel} agent
        </span>
        <span className="overflow-hidden text-ellipsis whitespace-nowrap text-ui text-faint-3">
          {statusText}
        </span>
      </div>

      <div className="flex flex-none items-center gap-[14px] text-sm">
        <span className="whitespace-nowrap text-faint-2">{controlsLabel}</span>
        <span className="text-line-mute" aria-hidden="true">
          |
        </span>
        <span className="font-medium whitespace-nowrap text-ink tabular-nums">
          {passedLabel}
        </span>
        <div className="relative h-[5px] w-[104px] overflow-hidden rounded-sm bg-divider-2">
          <motion.div
            className="h-full rounded-sm bg-accent"
            initial={false}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.9, ease: easeOutSoft }}
          />
          <Sheen show={pulse} />
        </div>
        <button
          type="button"
          onClick={onReplay}
          title="Replay sequence"
          className="flex cursor-pointer items-center gap-[7px] rounded-lg border border-transparent px-[9px] py-1.5 text-meta leading-none whitespace-nowrap text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash hover:text-ink"
        >
          <RefreshIcon size={12} />
          Replay
        </button>
      </div>
    </div>
  );
}
