"use client";

import { motion } from "motion/react";

import { stagger, timing } from "../_motion";
import { CALC_AT } from "../_data";
import { useEstimationScreen } from "./screen-context";

/** Body of build step 3: the arithmetic behind the base accrual. */
export function CalcTable({ step }: { step: number }) {
  const { calc } = useEstimationScreen();
  const shown = step >= CALC_AT;
  const reveal = (delay: number) => ({
    animate: { opacity: shown ? 1 : 0, y: shown ? 0 : 4 },
    transition: stagger(timing.calcRow, delay),
  });

  return (
    <div className="pt-[7px] pr-1 pl-[27px]">
      <div className="text-sm leading-[1.65] text-pretty text-muted-4">
        {step >= 8 ? calc.done : "Computing base amount from rate and coverage..."}
      </div>
      <div className="mt-3 rounded-lg bg-rail-alt px-[15px] py-[13px]">
        {calc.rows.map((row, i) => (
          <motion.div
            key={row.label}
            {...reveal(i * 0.08)}
            className="flex items-center justify-between gap-3.5 py-[5px]"
          >
            <span className="text-meta leading-[normal] text-muted-4">{row.label}</span>
            <span className="text-meta leading-[normal] text-ink tabular-nums">
              {row.value}
            </span>
          </motion.div>
        ))}

        <div className="my-[9px] h-px bg-[#E4E4DC]" />

        <motion.div
          animate={{ opacity: shown ? 1 : 0, y: shown ? 0 : 4 }}
          transition={stagger(timing.fact, 0.24)}
          className="flex items-center justify-between gap-3.5"
        >
          <span className="text-sm leading-[normal] font-medium text-ink">
            {calc.total.label}
          </span>
          <span className="font-display text-[17px] leading-[normal] text-ink-deep">
            {calc.total.value}
          </span>
        </motion.div>
      </div>
    </div>
  );
}
