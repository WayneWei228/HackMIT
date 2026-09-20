"use client";

import { motion } from "motion/react";

import { MoreIcon } from "@/components/ui/icons";
import { easeOutSoft, transitions } from "@/lib/motion";
import { conclusion, conclusionRows } from "../_data";
import { NoteInfoIcon } from "./glyphs";
import { Panel, PanelHeading } from "./panel";

/** Rows rise 5px over 400ms, 60ms apart - the comp's staggered reveal. */
function rowMotion(index: number, visible: boolean) {
  return {
    animate: { opacity: visible ? 1 : 0, y: visible ? 0 : 5 },
    transition: { duration: 0.4, ease: easeOutSoft, delay: index * 0.06 },
  };
}

/** The conclusion lands at step 10; its supporting rows follow at step 11. */
const AMOUNT_AT = 10;
const ROWS_AT = 11;

/**
 * Right column: the number the agent is prepared to stand behind, the terms
 * it rests on, and what happens to it next.
 */
export function ConclusionPanel({
  step,
  complete,
}: {
  step: number;
  complete: boolean;
}) {
  const amountReady = step >= AMOUNT_AT;
  const rowsReady = step >= ROWS_AT;

  return (
    <Panel className="p-5">
      <div className="flex items-center justify-between gap-2.5 border-b border-divider-3 pb-3.5">
        <PanelHeading>Provisional conclusion</PanelHeading>
        <button
          type="button"
          aria-label="Conclusion actions"
          className="-mr-1 flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent bg-transparent text-faint-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
        >
          <MoreIcon className="text-body" />
        </button>
      </div>

      <div className="mt-[18px] text-ui text-ink-2">
        {conclusion.amountLabel}
      </div>
      <div className="relative mt-1.5 h-[50px]">
        <motion.span
          initial={false}
          animate={{ opacity: amountReady ? 0 : 1 }}
          transition={{ duration: 0.25, ease: easeOutSoft }}
          className="font-display absolute top-0 left-0 text-[44px] leading-[1.1] text-[#C4C8BE]"
        >
          —
        </motion.span>
        <motion.span
          initial={false}
          animate={{
            opacity: amountReady ? 1 : 0,
            y: amountReady ? 0 : 8,
          }}
          transition={{ duration: 0.45, ease: easeOutSoft }}
          className="font-display absolute top-0 left-0 text-[44px] leading-[1.1] whitespace-nowrap text-ink-deep"
        >
          {conclusion.amount}
        </motion.span>
      </div>

      <div className="mt-[18px] flex flex-col">
        {conclusionRows.map((row, i) => (
          <motion.div
            key={row.label}
            initial={false}
            {...rowMotion(i, rowsReady)}
            className="flex items-center justify-between gap-3.5 border-t border-wash-deep py-[11px]"
          >
            <span className="text-ui text-muted-4">{row.label}</span>
            {row.kind === "text" ? (
              <span
                className={`text-ui text-right ${
                  row.tone === "accent" ? "text-accent" : "text-ink"
                }`}
              >
                {row.value}
              </span>
            ) : (
              <span className="flex items-center gap-[11px]">
                <span className="relative h-[5px] w-[78px] overflow-hidden rounded-sm bg-divider-2">
                  <motion.span
                    initial={false}
                    animate={{ width: rowsReady ? row.width : "0%" }}
                    transition={{ duration: 1, ease: easeOutSoft, delay: 0.3 }}
                    className="absolute top-0 left-0 h-full rounded-sm bg-accent"
                  />
                </span>
                <span className="text-ui text-ink">{row.value}</span>
              </span>
            )}
          </motion.div>
        ))}
      </div>

      <motion.div
        initial={false}
        animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 6 }}
        transition={transitions.slow}
        className="mt-5 flex items-start gap-[11px] rounded-lg bg-accent-tint px-3.5 py-[13px]"
      >
        <NoteInfoIcon className="mt-px flex-none" />
        <p className="text-meta leading-[1.65] text-pretty text-accent-slate">
          {conclusion.note}
        </p>
      </motion.div>
    </Panel>
  );
}
