"use client";

import Link from "next/link";

import { InlineHandoff } from "@/components/close/case-trail-panel";
import { RailStages } from "@/components/close/rail-stages";
import type { Header } from "@/lib/api-types";
import { useNextStageOpen } from "@/lib/stage-status";
import { cn } from "@/lib/cn";
import { useCaseHref } from "@/lib/case-context";
import { HANDOFF } from "../_data";
import type { RailResize } from "../_use-estimation-run";
import { InputDocIcon, RailCollapseIcon } from "./icons";
import { LiveDot } from "./markers";
import { useRevealingStage } from "@/lib/stage-reveal";

/**
 * The expanded live-execution rail: where this agent sits in the close chain,
 * the steps it recorded, and where it hands the case next.
 */
export function ExecutionRail({
  header,
  clock,
  rail,
}: {
  header: Header;
  clock: string;
  rail: RailResize;
}) {
  const revealing = useRevealingStage() !== null;
  const caseHref = useCaseHref();
  const nextOpen = useNextStageOpen(header, "estimation");

  return (
    <aside
      className="relative flex-none border-l border-line bg-paper"
      style={{ inlineSize: rail.width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        onMouseDown={rail.onResizeStart}
        title="Drag to resize"
        className={cn(
          "absolute top-0 -left-1 bottom-0 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)]",
          rail.dragging
            ? "bg-[rgba(46,128,71,0.22)]"
            : "hover:bg-[rgba(46,128,71,0.16)]",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <div className="text-eyebrow leading-[normal] font-medium tracking-caps-lg text-faint">
            LIVE EXECUTION
          </div>
          <button
            type="button"
            onClick={rail.toggle}
            title="Collapse panel"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <RailCollapseIcon />
          </button>
        </div>

        <div className="mt-3.5 flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <LiveDot pulsing={false} halo />
            <span className="text-lead leading-[normal] text-ink">{revealing ? "Running" : "Complete"}</span>
          </div>
          <div className="text-sm leading-[normal] text-faint tabular-nums">{clock}</div>
        </div>

        <RailStages header={header} current="estimation" />

        <div className="mt-8 h-px bg-sunk" />
        <div className="mt-[22px] text-eyebrow leading-[normal] font-medium tracking-caps-lg text-faint">
          NEXT HANDOFF
        </div>
        {nextOpen && (
        <div className="mt-[13px] flex items-start gap-3">
          <InputDocIcon className="mt-0.5 flex-none text-faint-3" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 text-body leading-[normal] text-ink">
              <span>{HANDOFF.from}</span>
              <span aria-hidden="true" className="text-ghost-2">
                →
              </span>
              <span>{HANDOFF.to}</span>
            </div>
          </div>
        </div>
        )}

        <InlineHandoff screen="estimation" />

        {nextOpen && (
        <div className="mt-4">
          <Link
            href={caseHref(HANDOFF.href)}
            className="relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-3.5 py-[11px] text-center text-ui leading-[normal] font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
          >
            <span className="relative z-[2]">Continue to Verification</span>
          </Link>
        </div>
        )}
      </div>
    </aside>
  );
}
