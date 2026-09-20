"use client";

import { motion } from "motion/react";
import type { MouseEvent as ReactMouseEvent } from "react";

import { CaretRightIcon } from "@/components/ui/icons";
import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { transitions } from "@/lib/motion";

import { RAIL } from "../_data";
import { ExecutionSteps } from "./execution-steps";
import { ExtractedFacts } from "./extracted-facts";
import { NextHandoff } from "./next-handoff";
import { PulseDot } from "./pulse-dot";
import type { EvidenceRun } from "./use-evidence-run";

/**
 * The live execution rail. It is resizable between 288 and 620px by dragging
 * its left edge, and collapses to the 56px strip in `rail-collapsed`.
 */
export function ExecutionRail({
  run,
  width,
  dragging,
  autoAdvance,
  onResizeStart,
  onCollapse,
}: {
  run: EvidenceRun;
  width: number;
  dragging: boolean;
  autoAdvance: boolean;
  onResizeStart: (event: ReactMouseEvent) => void;
  onCollapse: () => void;
}) {
  return (
    <motion.aside
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.fast}
      className="relative flex-none border-l border-line bg-paper"
      style={{ inlineSize: width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        title="Drag to resize"
        onMouseDown={onResizeStart}
        className={cn(
          "absolute top-0 bottom-0 -left-1 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:bg-[rgba(46,128,71,0.16)]",
          dragging ? "bg-[rgba(46,128,71,0.22)]" : "bg-transparent",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <SectionLabel className="text-[10.5px] text-faint">{RAIL.eyebrow}</SectionLabel>
          <button
            type="button"
            onClick={onCollapse}
            title="Collapse panel"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent bg-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <CaretRightIcon size={13} />
          </button>
        </div>

        <div className="mt-[14px] flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <PulseDot pulsing={!run.complete} halo />
            <span className="text-lead text-ink">{RAIL.running}</span>
          </div>
          <div className="text-sm text-faint tabular-nums">{run.clock}</div>
        </div>

        <ExecutionSteps
          done={run.done}
          active={run.active}
          complete={run.complete}
        />

        <ExtractedFacts step={run.step} />

        <NextHandoff complete={run.complete} autoAdvance={autoAdvance} />
      </div>
    </motion.aside>
  );
}
