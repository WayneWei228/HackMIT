"use client";

import { motion } from "motion/react";

import { riseIn, staggerParent } from "@/lib/motion";

import { CaseMetaLine } from "@/components/ui/meta-line";
import { useIngestionData } from "./data-context";

/**
 * Vendor, period and the two case-level actions.
 *
 * The title is two serif lines rather than one wrapped heading - "Mintlify" at
 * 46px and "December accrual" at 36px - so it is built here instead of using
 * the shared `PageTitle`.
 */
export function CaseHeader() {
  const { data } = useIngestionData();
  const { CASE_VENDOR, CASE_TITLE, CASE_META } = data;

  return (
    <motion.div
      variants={staggerParent(0.045)}
      initial="hidden"
      animate="visible"
    >
      <motion.div
        variants={riseIn}
        className="text-eyebrow font-medium tracking-caps-xl text-faint-2"
      >
        CLOSE &nbsp;/&nbsp; ACTIVE CASE
      </motion.div>

      <div className="mt-3.5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          {CASE_VENDOR ? (
            <motion.div
              variants={riseIn}
              className="font-display text-display leading-[1.02] tracking-display text-ink-deep"
            >
              {CASE_VENDOR}
            </motion.div>
          ) : null}
          {CASE_TITLE ? (
            <motion.div
              variants={riseIn}
              className="mt-0.5 font-display text-4xl leading-[1.1] tracking-tight text-ink-deep"
            >
              {CASE_TITLE}
            </motion.div>
          ) : null}
          <motion.div variants={riseIn}>
            <CaseMetaLine items={CASE_META} className="mt-[15px]" />
          </motion.div>
        </div>

        {/* The comp's "View case notes" and "..." actions opened screens
            that have no backend behind them, so they are not drawn: an
            affordance that leads nowhere is worse than none. */}
      </div>
    </motion.div>
  );
}
