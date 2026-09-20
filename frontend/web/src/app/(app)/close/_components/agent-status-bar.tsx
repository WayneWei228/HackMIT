"use client";

import { motion } from "motion/react";

import { NarrationText, TrailToggle } from "@/components/close/case-trail-panel";
import { StageRunControl } from "@/components/close/stage-run-control";
import { transitions } from "@/lib/motion";
import { useStageNarration } from "@/lib/stage-narration";

import { AGENT_NAME } from "../_data";

/**
 * The single line of agent narration between the filters and the card grid.
 *
 * The line is the newest step the agent recorded in the run log, never a
 * script, and clicking it opens the full log. The dot pulses only while a
 * backend call for this stage is in flight.
 */
export function AgentStatusBar({
  selectedCount,
  filesLoaded,
}: {
  selectedCount: number;
  filesLoaded: number;
}) {
  const { running } = useStageNarration("ingestion");

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[9px]">
      <TrailToggle screen="ingestion">
        <span className="relative h-[9px] w-[9px] flex-none">
          <span className="absolute inset-0 rounded-full bg-accent" />
          <motion.span
            animate={{ opacity: running ? 1 : 0 }}
            transition={transitions.slow}
            className="absolute -inset-1"
          >
            <span className="block h-full w-full rounded-full border-[1.3px] border-[rgba(46,128,71,0.55)] animate-[pulse-ring_2.6s_cubic-bezier(0.22,0.61,0.36,1)_infinite]" />
          </motion.span>
        </span>
        <span className="text-ui font-medium whitespace-nowrap text-ink">{AGENT_NAME}</span>
        <NarrationText screen="ingestion" />
      </TrailToggle>

      <div className="flex flex-none items-center gap-3.5 text-sm">
        <StageRunControl screen="ingestion" />
        <span className="text-faint-2">{filesLoaded} files loaded</span>
        <span aria-hidden="true" className="text-line-mute">
          |
        </span>
        <span className="font-medium text-ink tabular-nums">{selectedCount} selected</span>
      </div>
    </div>
  );
}
