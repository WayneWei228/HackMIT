"use client";

import { motion } from "motion/react";

import { NarrationText, TrailToggle } from "@/components/close/case-trail-panel";
import { StageRunControl } from "@/components/close/stage-run-control";
import { easeOutSoft } from "@/lib/motion";
import { useStageNarration } from "@/lib/stage-narration";

import { LiveDot } from "./marks";
import { useVerificationScreen } from "./screen-context";

/**
 * The narration strip under the header. The line is the newest step the
 * Verification agents recorded in the run log, never a script, and clicking it
 * opens the full log. The bar shows how many of the policy rules passed.
 */
export function AgentStatusBar({
  passedLabel,
  progress,
}: {
  passedLabel: string;
  progress: number;
}) {
  const ruleCount = useVerificationScreen().data.controls.length;
  const { running } = useStageNarration("verification");

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[9px]">
      <TrailToggle screen="verification">
        <LiveDot pulse={running} ring={false} />
        <span className="text-ui font-medium whitespace-nowrap text-ink">Verification agent</span>
        <NarrationText screen="verification" />
      </TrailToggle>

      <div className="flex flex-none items-center gap-3.5 text-sm">
        <StageRunControl screen="verification" />
        <span className="whitespace-nowrap text-faint-2">{ruleCount} rules</span>
        <span aria-hidden="true" className="text-line-mute">
          |
        </span>
        <span className="font-medium whitespace-nowrap text-ink tabular-nums">{passedLabel}</span>
        <div className="relative h-[5px] w-[104px] overflow-hidden rounded-sm bg-divider-2">
          <motion.div
            initial={false}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.9, ease: easeOutSoft }}
            className="h-full rounded-sm bg-accent"
          />
        </div>
      </div>
    </div>
  );
}
