"use client";

import { NarrationText, TrailToggle } from "@/components/close/case-trail-panel";
import { StageRunControl } from "@/components/close/stage-run-control";
import { useStageNarration } from "@/lib/stage-narration";

import { PulseDot } from "./glyphs";
import { useObligationScreen } from "./screen-context";

/**
 * The narration strip under the header. The line is the newest step the
 * Obligation agents recorded in the run log, never a script, and clicking it
 * opens the full log.
 */
export function AgentStatusBar() {
  const { evidenceInputsLabel, checks } = useObligationScreen();
  const { running } = useStageNarration("obligation");

  return (
    <div className="flex flex-none items-center justify-between gap-5 px-[34px] py-[9px]">
      <TrailToggle screen="obligation">
        <PulseDot pulsing={running} />
        <span className="text-ui font-medium whitespace-nowrap text-ink">Obligation agent</span>
        <NarrationText screen="obligation" />
      </TrailToggle>

      <div className="flex flex-none items-center gap-3.5 text-sm leading-[normal]">
        <StageRunControl screen="obligation" />
        <span className="whitespace-nowrap text-faint-2">{evidenceInputsLabel}</span>
        {checks && (
          <>
            <span aria-hidden="true" className="text-line-mute">
              |
            </span>
            <span className="font-medium whitespace-nowrap text-ink tabular-nums">
              {checks.length} checks
            </span>
          </>
        )}
      </div>
    </div>
  );
}
