"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { InlineHandoff } from "@/components/close/case-trail-panel";
import { RailStages } from "@/components/close/rail-stages";
import type { Header } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { CaretLeftIcon, CaretRightIcon, PageIcon } from "@/components/ui/icons";
import { transitions } from "@/lib/motion";
import { routes } from "@/lib/routes";
import { LiveDot } from "./marks";

/** The 56px rail the panel collapses into. */
function MiniRail({ onExpand }: { onExpand: () => void }) {
  return (
    <motion.aside
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.base}
      className="flex w-14 flex-none flex-col items-center gap-[18px] border-l border-line bg-panel-hover py-[22px]"
    >
      <button
        type="button"
        onClick={onExpand}
        title="Expand live execution"
        className="flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-deep"
      >
        <CaretLeftIcon size={13} />
      </button>
      <span className="h-[9px] w-[9px] flex-none rounded-full bg-accent shadow-[var(--shadow-ring)]" />
      <div className="rotate-180 text-eyebrow font-medium tracking-[0.14em] whitespace-nowrap text-faint [writing-mode:vertical-rl]">
        LIVE EXECUTION
      </div>
      <div className="font-display rotate-180 text-md whitespace-nowrap text-ink-deep [writing-mode:vertical-rl]">
        Verification
      </div>
    </motion.aside>
  );
}

export function ExecutionRail({
  width,
  dragging,
  onStartResize,
  onCollapse,
  header,
  clock,
  outcome,
}: {
  width: number;
  dragging: boolean;
  onStartResize: (event: React.MouseEvent<HTMLElement>) => void;
  onCollapse: () => void;
  header: Header;
  clock: string;
  /** The status the Policy stage returned, e.g. Blocked or Close-ready. */
  outcome: string;
}) {
  return (
    <motion.aside
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.base}
      className="relative flex-none border-l border-line bg-paper"
      style={{ inlineSize: width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize live execution panel"
        onMouseDown={onStartResize}
        title="Drag to resize"
        className={cn(
          "absolute top-0 -left-1 bottom-0 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:bg-[rgba(46,128,71,0.16)]",
          dragging &&
            "bg-[rgba(46,128,71,0.22)] hover:bg-[rgba(46,128,71,0.22)]",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
            LIVE EXECUTION
          </div>
          <button
            type="button"
            onClick={onCollapse}
            title="Collapse panel"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <CaretRightIcon size={13} />
          </button>
        </div>

        <div className="mt-[14px] flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <LiveDot pulse={false} />
            <span className="text-lead text-ink">Complete</span>
          </div>
          <div className="text-sm text-faint tabular-nums">{clock}</div>
        </div>

        <RailStages header={header} current="verification" />

        <div className="mt-8 h-px bg-sunk" />

        <div className="mt-[22px] text-eyebrow font-medium tracking-caps-lg text-faint">
          OUTCOME
        </div>
        <div className="mt-[13px] flex items-start gap-3">
          <PageIcon size={15} className="mt-0.5 flex-none text-faint-3" />
          <div className="min-w-0 flex-1">
            <div className="text-body text-ink">Policy decision: {outcome}</div>
          </div>
        </div>

        <InlineHandoff screen="verification" />

        <div className="mt-4">
          <Link
            href={routes.cases}
            className="block w-full rounded-xl border border-accent bg-accent px-[14px] py-[11px] text-center text-ui font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
          >
            Return to case list
          </Link>
        </div>
      </div>
    </motion.aside>
  );
}

export { MiniRail };
