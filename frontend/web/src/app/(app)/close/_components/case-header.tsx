"use client";

import { motion } from "motion/react";

import type { Header } from "@/lib/api-types";
import { riseIn, staggerParent } from "@/lib/motion";

/**
 * Vendor and period.
 *
 * The title is two serif lines rather than one wrapped heading - the vendor at
 * 46px and the close item at 36px - so it is built here instead of using the
 * shared `PageTitle`.
 */
export function CaseHeader({ header }: { header: Header }) {
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
          <motion.div
            variants={riseIn}
            className="font-display text-display leading-[1.02] tracking-display text-ink-deep"
          >
            {header.vendor_name}
          </motion.div>
          <motion.div
            variants={riseIn}
            className="mt-0.5 font-display text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {header.title}
          </motion.div>
          <motion.div
            variants={riseIn}
            className="mt-[15px] flex flex-wrap items-center gap-x-[15px] gap-y-1 text-lead text-muted-4"
          >
            {header.chips.map((item, i) => (
              <span key={item} className="flex items-center gap-[15px] whitespace-nowrap">
                {i > 0 && (
                  <span aria-hidden="true" className="text-line-dark">
                    |
                  </span>
                )}
                {item}
              </span>
            ))}
          </motion.div>
        </div>

        {/* The comp's "View case notes" and "..." actions opened screens
            that have no backend behind them, so they are not drawn: an
            affordance that leads nowhere is worse than none. */}
      </div>
    </motion.div>
  );
}
