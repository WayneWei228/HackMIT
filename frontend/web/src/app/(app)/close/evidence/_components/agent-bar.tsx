"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { RefreshIcon } from "@/components/ui/icons";
import { easeOutSoft, transitions } from "@/lib/motion";

import { AGENT_LABEL, MATCH_STEP, SOURCES_LABEL, TOTALS_STEP } from "../_data";
import { PulseDot } from "./pulse-dot";

function progressFor(step: number) {
  if (step >= TOTALS_STEP) return "100%";
  if (step >= MATCH_STEP) return "66%";
  return "42%";
}

/** The narration strip between the case figures and the document viewer. */
export function AgentBar({
  step,
  status,
  complete,
  onReplay,
}: {
  step: number;
  status: string;
  complete: boolean;
  onReplay: () => void;
}) {
  const reduced = useReducedMotion();
  const reviewed = step >= TOTALS_STEP ? "3 / 3 reviewed" : "2 / 3 reviewed";

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[13px]">
      <div className="flex min-w-0 items-center gap-[11px]">
        <PulseDot pulsing={!complete} />
        <span className="text-ui font-medium whitespace-nowrap text-ink">
          {AGENT_LABEL}
        </span>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={status}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12, ease: easeOutSoft }}
            className="truncate text-ui text-faint-3"
          >
            {status}
          </motion.span>
        </AnimatePresence>
      </div>

      <div className="flex flex-none items-center gap-[14px] text-sm">
        <span className="whitespace-nowrap text-faint-2">{SOURCES_LABEL}</span>
        <span className="text-line-mute" aria-hidden="true">
          |
        </span>
        <span className="font-medium whitespace-nowrap text-ink tabular-nums">
          {reviewed}
        </span>

        <div className="relative h-[5px] w-[104px] overflow-hidden rounded-sm bg-divider-2">
          <motion.div
            className="h-full rounded-sm bg-accent"
            initial={false}
            animate={{ width: progressFor(step) }}
            transition={{ duration: 0.9, ease: easeOutSoft }}
          />
          {!complete && (
            <motion.div
              className="absolute top-0 left-0 h-full w-[36%] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.6),rgba(255,255,255,0))]"
              initial={{ x: "-120%" }}
              animate={reduced ? { x: "-120%" } : { x: ["-120%", "330%", "330%"] }}
              transition={
                reduced
                  ? { duration: 0 }
                  : {
                      duration: 2.2,
                      times: [0, 0.55, 1],
                      ease: "easeInOut",
                      repeat: Infinity,
                    }
              }
            />
          )}
        </div>

        <motion.button
          type="button"
          onClick={onReplay}
          title="Replay sequence"
          whileTap={{ scale: 0.97 }}
          transition={transitions.fast}
          className="flex cursor-pointer items-center gap-[7px] rounded-lg border border-transparent bg-transparent px-[9px] py-1.5 text-meta leading-none whitespace-nowrap text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash hover:text-ink"
        >
          <RefreshIcon size={12} />
          Replay
        </motion.button>
      </div>
    </div>
  );
}
