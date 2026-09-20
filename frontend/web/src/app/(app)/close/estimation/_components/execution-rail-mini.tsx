"use client";

import { RailExpandIcon } from "./icons";

/** The collapsed live-execution rail: a 56px spine with the run's name. */
export function ExecutionRailMini({ onExpand }: { onExpand: () => void }) {
  return (
    <aside className="flex w-14 flex-none flex-col items-center gap-[18px] border-l border-line bg-panel-hover py-[22px]">
      <button
        type="button"
        onClick={onExpand}
        title="Expand live execution"
        className="flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-deep"
      >
        <RailExpandIcon />
      </button>
      <span className="h-[9px] w-[9px] flex-none rounded-full bg-accent shadow-[var(--shadow-ring)]" />
      <div className="rotate-180 text-eyebrow leading-[normal] font-medium tracking-[0.14em] whitespace-nowrap text-faint [writing-mode:vertical-rl]">
        LIVE EXECUTION
      </div>
      <div className="font-display rotate-180 text-md leading-[normal] whitespace-nowrap text-ink-deep [writing-mode:vertical-rl]">
        Estimation
      </div>
    </aside>
  );
}
