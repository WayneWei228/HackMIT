"use client";

import { NarrationText, TrailToggle } from "@/components/close/case-trail-panel";
import { StageRunControl } from "@/components/close/stage-run-control";
import { useStageNarration } from "@/lib/stage-narration";

import { LiveDot } from "./markers";
import { useEstimationScreen } from "./screen-context";

/**
 * The narration strip between the case header and the working columns. The line
 * is the newest step the Estimation agent recorded in the run log, never a
 * script, and clicking it opens the full log.
 */
export function AgentBar() {
  const { inputs } = useEstimationScreen();
  const { running } = useStageNarration("estimation");

  return (
    <>
      <div className="h-px flex-none bg-line" />
      <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[9px]">
        <TrailToggle screen="estimation">
          <LiveDot pulsing={running} />
          <span className="text-ui leading-[normal] font-medium whitespace-nowrap text-ink">
            Estimation agent
          </span>
          <NarrationText screen="estimation" />
        </TrailToggle>

        <div className="flex flex-none items-center gap-3.5 text-sm leading-[normal]">
          <StageRunControl screen="estimation" />
          <span className="whitespace-nowrap text-faint-2">{inputs.length} inputs</span>
        </div>
      </div>
    </>
  );
}
