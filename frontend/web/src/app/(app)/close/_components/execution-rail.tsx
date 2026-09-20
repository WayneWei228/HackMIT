"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { CaretLeftIcon, CaretRightIcon } from "@/components/ui/icons";
import { railIn } from "@/lib/motion";

import { agentChain } from "@/lib/routes";
import type { CloseRun } from "./use-close-run";
import { ExecutionStages } from "./execution-stages";
import { RailHandoff } from "./rail-handoff";
import { AutoRunToggle } from "@/components/ui/auto-run-toggle";
import { RailLabel } from "./rail-label";
import { useRailResize, type RailResize } from "./use-rail-resize";

/**
 * The live execution rail.
 *
 * Collapsed it keeps a 56px spine with the stage name set vertically; expanded
 * it is a draggable column showing the run clock, the five stages and the
 * handoff. Collapsing swaps one shape for the other rather than tweening the
 * width - the comp does the same - so the grid reflows exactly once.
 */
export function ExecutionRail({
  run,
  open,
  onToggle,
  autoAdvance,
}: {
  run: CloseRun;
  open: boolean;
  onToggle: () => void;
  autoAdvance: boolean;
}) {
  // Held here rather than in FullRail so a dragged width survives a collapse.
  const resize = useRailResize();

  return open ? (
    <FullRail
      run={run}
      onToggle={onToggle}
      autoAdvance={autoAdvance}
      resize={resize}
    />
  ) : (
    <MiniRail onToggle={onToggle} />
  );
}

function MiniRail({ onToggle }: { onToggle: () => void }) {
  return (
    <motion.aside
      variants={railIn}
      initial="hidden"
      animate="visible"
      className="flex w-14 flex-none flex-col items-center gap-[18px] border-l border-line bg-panel-hover py-[22px]"
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
      <span className="h-[9px] w-[9px] flex-none rounded-full bg-accent shadow-[var(--shadow-ring)]" />
      <div className="[writing-mode:vertical-rl] rotate-180 text-eyebrow font-medium tracking-[0.14em] whitespace-nowrap text-faint">
        LIVE EXECUTION
      </div>
      <div className="[writing-mode:vertical-rl] rotate-180 font-display text-md whitespace-nowrap text-ink-deep">
        {agentChain[0].label}
      </div>
    </motion.aside>
  );
}

function FullRail({
  run,
  onToggle,
  autoAdvance,
  resize,
}: {
  run: CloseRun;
  onToggle: () => void;
  autoAdvance: boolean;
  resize: RailResize;
}) {
  const { width, dragging, startResize } = resize;

  return (
    <motion.aside
      variants={railIn}
      initial="hidden"
      animate="visible"
      style={{ width }}
      className="relative flex-none border-l border-line bg-paper"
    >
      <div
        onMouseDown={startResize}
        title="Drag to resize"
        className={cn(
          "absolute -left-1 top-0 bottom-0 z-[6] w-[9px] cursor-col-resize transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[rgba(46,128,71,0.16)]",
          dragging ? "bg-[rgba(46,128,71,0.22)]" : "bg-transparent",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <RailLabel>LIVE EXECUTION</RailLabel>
          <button
            type="button"
            onClick={onToggle}
            title="Collapse panel"
            aria-label="Collapse panel"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent bg-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <CaretRightIcon size={13} />
          </button>
        </div>

        <div className="mt-3.5 flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <span className="h-[9px] w-[9px] rounded-full bg-accent shadow-[var(--shadow-ring)]" />
            <span className="text-lead text-ink">Running</span>
          </div>
          <div className="text-sm text-faint tabular-nums">{run.clock}</div>
        </div>

        <AutoRunToggle className="-mx-2 mt-2.5 w-[calc(100%+16px)]" />

        <ExecutionStages complete={run.complete} taskStates={run.taskStates} />

        <RailHandoff
          files={run.selectedFiles}
          complete={run.complete}
          autoAdvance={autoAdvance}
        />
      </div>
    </motion.aside>
  );
}
