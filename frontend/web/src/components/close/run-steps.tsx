"use client";

import type { StageKey } from "@/lib/case-store";
import { cn } from "@/lib/cn";
import { useStageNarration } from "@/lib/stage-narration";
import { formatStamp } from "@/lib/time";

import { ViewEmailLink } from "./outreach-strip";
import { MethodTag } from "./trail-parts";

/**
 * The steps a stage's agents really recorded, listed in its rail. There is no
 * fixed checklist: each row is a run-log entry with its own time, and the list
 * is empty (and says so) until an agent has written one.
 */
export function RunSteps({ screen, className }: { screen: StageKey; className?: string }) {
  const { entries, phase, text, running } = useStageNarration(screen);

  if (entries.length === 0 && !running) {
    return (
      <div className={cn("mt-3.5 ml-[33px] border-l border-line pl-5 text-meta text-faint-2", className)}>
        {phase === "empty" ? "No recorded steps for this stage yet." : text}
      </div>
    );
  }

  return (
    <ol className={cn("mt-3.5 ml-[33px] flex flex-col gap-3 border-l border-line pl-5", className)}>
      {entries.map((entry) => (
        <li key={entry.seq} className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-[3px] flex h-[13px] w-[13px] flex-none items-center justify-center rounded-full bg-accent text-[8px] leading-none font-bold text-white"
          >
            {"✓"}
          </span>
          <div className="min-w-0">
            <div className="text-sm leading-[1.4] text-ink-2 text-pretty">{entry.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-nano text-faint-2 tabular-nums">
              <span>{formatStamp(entry.at).time}</span>
              <MethodTag method={entry.method} />
              {entry.run_id !== undefined && <span className="font-mono">run #{entry.run_id}</span>}
            </div>
            {entry.agent === "outreach" && <ViewEmailLink className="mt-1.5" label="View email" />}
          </div>
        </li>
      ))}
      {running && (
        <li className="flex items-center gap-3">
          <span className="relative mx-px h-[13px] w-[13px] flex-none">
            <span className="absolute inset-[3px] rounded-full bg-accent" />
            <span className="absolute inset-0 animate-[pulse-ring_2.6s_cubic-bezier(0.22,0.61,0.36,1)_infinite] rounded-full border-[1.3px] border-[rgba(46,128,71,0.55)]" />
          </span>
          <span className="text-sm text-ink-2">{text}</span>
        </li>
      )}
    </ol>
  );
}
