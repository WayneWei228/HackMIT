"use client";

import { NarrationText, TrailToggle } from "@/components/close/case-trail-panel";
import { useStageNarration } from "@/lib/stage-narration";

import { AGENT_LABEL } from "../_data";
import { PulseDot } from "./pulse-dot";

/**
 * The narration strip between the case figures and the document viewer. The
 * line is the newest step the Evidence agent recorded in the run log, never a
 * script, and clicking it opens the full log.
 */
export function AgentBar({
  sourceCount,
  factCount,
}: {
  sourceCount: number;
  factCount: number;
}) {
  const { running } = useStageNarration("evidence");

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[9px]">
      <TrailToggle>
        <PulseDot pulsing={running} />
        <span className="text-ui font-medium whitespace-nowrap text-ink">{AGENT_LABEL}</span>
        <NarrationText screen="evidence" />
      </TrailToggle>

      <div className="flex flex-none items-center gap-[14px] text-sm">
        <span className="whitespace-nowrap text-faint-2">{sourceCount} sources</span>
        <span className="text-line-mute" aria-hidden="true">
          |
        </span>
        <span className="font-medium whitespace-nowrap text-ink tabular-nums">
          {factCount} facts
        </span>
      </div>
    </div>
  );
}
