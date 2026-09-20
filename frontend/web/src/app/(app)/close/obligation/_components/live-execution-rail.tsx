"use client";

import type { MouseEvent } from "react";
import Link from "next/link";
import { StageStateLabel } from "@/components/close/stage-state-label";
import { motion } from "motion/react";

import { CaretLeftIcon, CaretRightIcon } from "@/components/ui/icons";
import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { railIn } from "@/lib/motion";
import { InlineHandoff } from "@/components/close/case-trail-panel";
import { RailStages } from "@/components/close/rail-stages";
import type { Header } from "@/lib/api-types";
import { useNextStageOpen } from "@/lib/stage-status";
import { handoff } from "../_data";
import { useCaseHref } from "@/lib/case-context";
import { PulseDot, SourceDocIcon } from "./glyphs";

export type RailProps = {
  header: Header;
  clock: string;
  open: boolean;
  mini: boolean;
  width: number;
  dragging: boolean;
  onToggle: () => void;
  onResizeStart: (event: MouseEvent) => void;
};

/**
 * The run's own view of itself: which stage of the close is executing, which
 * sub-task the agent is on, and where the result goes next. Collapses to a
 * 56px spine and can be dragged wider.
 */
export function LiveExecutionRail(props: RailProps) {
  /* The two rails swap outright, as they do in the comp: each one settles in
     on mount. Wrapping the swap in AnimatePresence would hold the outgoing
     rail on screen, and a re-render landing during that exit - the clock
     ticks every second - can strand it there, half faded, forever. */
  if (props.mini) return <MiniRail onToggle={props.onToggle} />;
  if (props.open) return <FullRail {...props} />;
  return null;
}

function MiniRail({ onToggle }: { onToggle: () => void }) {
  return (
    <motion.aside
      variants={railIn}
      initial="hidden"
      animate="visible"
      className="flex w-14 flex-none flex-col items-center gap-[18px] border-l border-line bg-panel-hover py-[22px] leading-[normal]"
    >
      <button
        type="button"
        onClick={onToggle}
        title="Expand live execution"
        aria-label="Expand live execution"
        className="flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-deep"
      >
        <CaretLeftIcon size={13} />
      </button>
      <span className="h-[9px] w-[9px] flex-none rounded-full bg-accent shadow-ring" />
      <div className="rotate-180 text-eyebrow font-medium tracking-[0.14em] whitespace-nowrap text-faint [writing-mode:vertical-rl]">
        LIVE EXECUTION
      </div>
      <div className="font-display rotate-180 text-md whitespace-nowrap text-ink-deep [writing-mode:vertical-rl]">
        Obligation
      </div>
    </motion.aside>
  );
}

function FullRail({ header, clock, width, dragging, onToggle, onResizeStart }: RailProps) {
  const caseHref = useCaseHref();
  const nextOpen = useNextStageOpen(header, "obligation");

  return (
    <motion.aside
      variants={railIn}
      initial="hidden"
      animate="visible"
      style={{ inlineSize: width }}
      className="relative flex-none border-l border-line bg-paper leading-[normal]"
    >
      <div
        role="separator"
        aria-orientation="vertical"
        title="Drag to resize"
        onMouseDown={onResizeStart}
        className={cn(
          "absolute top-0 -left-1 bottom-0 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:bg-[rgba(46,128,71,0.16)]",
          dragging && "bg-[rgba(46,128,71,0.22)]",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <SectionLabel className="text-[10.5px] text-faint">LIVE EXECUTION</SectionLabel>
          <button
            type="button"
            onClick={onToggle}
            title="Collapse panel"
            aria-label="Collapse live execution"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent bg-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <CaretRightIcon size={13} />
          </button>
        </div>

        <div className="mt-3.5 flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <PulseDot halo pulsing={false} />
            <StageStateLabel screen="obligation" className="text-lead text-ink" />
          </div>
          <div className="text-sm leading-[normal] text-faint tabular-nums">{clock}</div>
        </div>

        <RailStages header={header} current="obligation" />

        <div className="mt-8 h-px bg-sunk" />
        <SectionLabel className="mt-[22px] text-[10.5px] text-faint">NEXT HANDOFF</SectionLabel>
        {nextOpen && (
        <div className="mt-[13px] flex items-start gap-3">
          <SourceDocIcon className="mt-0.5 flex-none text-faint-3" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 text-body text-ink">
              <span>{handoff.from}</span>
              <span aria-hidden="true" className="text-ghost-2">
                →
              </span>
              <span>{handoff.to}</span>
            </div>
          </div>
        </div>
        )}

        <InlineHandoff screen="obligation" />

        {nextOpen && (
        <div className="mt-4">
          <Link
            href={caseHref(handoff.href)}
            className="relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-3.5 py-[11px] text-center text-ui font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
          >
            <span className="relative z-[2]">{handoff.idleLabel}</span>
          </Link>
        </div>
        )}
      </div>
    </motion.aside>
  );
}
