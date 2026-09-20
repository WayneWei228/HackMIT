"use client";

import { motion } from "motion/react";

import { stagger, timing } from "../_motion";
import { ConfirmIcon } from "./icons";
import { useEstimationData } from "./data-context";

/** Right column: the number the agent lands on and the entry it implies. */
export function RecommendationPanel({
  step,
  complete,
}: {
  step: number;
  complete: boolean;
}) {
  const {
    ACCRUAL_AMOUNT,
    JOURNAL,
    RECOMMENDATION_NOTE,
    RECOMMENDATION_ROWS,
  } = useEstimationData().data;
  const settled = step >= 12;
  const rowsIn = step >= 13;

  return (
    <section className="min-h-full rounded-xl border border-divider bg-panel p-5 shadow-[var(--shadow-tile)]">
      <div className="border-b border-divider-3 pb-3.5">
        <div className="font-display text-2xl leading-[normal] text-ink-deep">
          Recommended accrual
        </div>
      </div>

      <div className="mt-[18px] text-ui leading-[normal] text-ink-2">Accrual amount</div>
      {/* Both layers share one grid cell so a long value wraps inside the card instead of overflowing it. */}
      <div className="mt-1.5 grid min-h-[50px] min-w-0">
        <motion.span
          animate={{ opacity: settled ? 0 : 1 }}
          transition={timing.dash}
          className="font-display col-start-1 row-start-1 text-[44px] leading-[1.1] text-[#C4C8BE]"
        >
          —
        </motion.span>
        <motion.span
          animate={{ opacity: settled ? 1 : 0, y: settled ? 0 : 8 }}
          transition={timing.settle}
          title={ACCRUAL_AMOUNT}
          className={`font-display col-start-1 row-start-1 min-w-0 leading-[1.1] [overflow-wrap:anywhere] text-ink-deep ${ACCRUAL_AMOUNT.length > 9 ? "text-[32px]" : "text-[44px]"}`}
        >
          {ACCRUAL_AMOUNT}
        </motion.span>
      </div>

      <div className="mt-[18px] flex flex-col">
        {RECOMMENDATION_ROWS.map((row, i) => (
          <motion.div
            key={`${row.label}-${i}`}
            animate={{ opacity: rowsIn ? 1 : 0, y: rowsIn ? 0 : 5 }}
            transition={stagger(timing.fact, i * 0.06)}
            className="flex items-center justify-between gap-3.5 border-t border-wash-deep py-[11px]"
          >
            <span className="text-ui leading-[normal] text-muted-4">{row.label}</span>
            <span
              className={`text-right text-ui leading-[normal] ${
                row.tone === "accent" ? "text-accent" : "text-ink"
              }`}
            >
              {row.value}
            </span>
          </motion.div>
        ))}
      </div>

      <motion.div
        animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 6 }}
        transition={timing.settle}
        className="mt-5 flex items-start gap-[11px] rounded-lg bg-accent-tint px-3.5 py-[13px]"
      >
        <ConfirmIcon className="mt-px flex-none" />
        <div className="text-meta leading-[1.65] text-pretty text-accent-slate">
          {RECOMMENDATION_NOTE}
        </div>
      </motion.div>

      <motion.div
        animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 6 }}
        transition={timing.settle}
        className="mt-[22px]"
      >
        <div className="text-ui leading-[normal] text-ink-2">Journal preview</div>
        <div className="mt-3 grid grid-cols-[22px_1fr_auto] gap-2.5 text-sm leading-[normal] text-ink">
          {JOURNAL.map((line, i) => (
            <div key={`${line.side}-${line.account}-${i}`} className="contents">
              <span className="text-faint-2">{line.side}</span>
              <span>{line.account}</span>
              <span className="text-right tabular-nums">{line.amount}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </section>
  );
}
