"use client";

import { motion } from "motion/react";

import { crossFade, transitions } from "@/lib/motion";

import { agentChain } from "@/lib/routes";
import { useIngestionData } from "./data-context";

/**
 * The single line of agent narration between the filters and the card grid.
 *
 * The dot keeps a slow halo while the run is live; the halo fades out - it does
 * not stop mid-pulse - the moment ingestion completes. The narration is keyed
 * on its own text, so a new line fades up in place; it is not wrapped in
 * `AnimatePresence`, which would blank the line while the old one left.
 */
export function AgentStatusBar({
  statusText,
  complete,
  selectedCount,
}: {
  statusText: string;
  complete: boolean;
  selectedCount: number;
}) {
  const { data } = useIngestionData();
  const { FILES_LOADED_LABEL } = data;
  /* Stage 01 of the chain is the Evidence agent; `/close` is its intake
     view. The name is navigation, not content. */
  const AGENT_NAME = `${agentChain[0].label} agent`;

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[13px]">
      <div className="flex min-w-0 items-center gap-[11px]">
        <span className="relative h-[9px] w-[9px] flex-none">
          <span className="absolute inset-0 rounded-full bg-accent" />
          <motion.span
            animate={{ opacity: complete ? 0 : 1 }}
            transition={transitions.slow}
            className="absolute -inset-1"
          >
            <span className="block h-full w-full rounded-full border-[1.3px] border-[rgba(46,128,71,0.55)] animate-[pulse-ring_2.6s_cubic-bezier(0.22,0.61,0.36,1)_infinite]" />
          </motion.span>
        </span>
        <span className="text-ui font-medium whitespace-nowrap text-ink">
          {AGENT_NAME}
        </span>
        <motion.span
          key={statusText}
          variants={crossFade}
          initial="hidden"
          animate="visible"
          className="truncate text-ui whitespace-nowrap text-faint-3"
        >
          {statusText}
        </motion.span>
      </div>

      <div className="flex flex-none items-center gap-3.5 text-sm">
        <span className="text-faint-2">{FILES_LOADED_LABEL}</span>
        <span aria-hidden="true" className="text-line-mute">
          |
        </span>
        <span className="font-medium text-ink tabular-nums">
          {selectedCount} selected
        </span>
      </div>
    </div>
  );
}
