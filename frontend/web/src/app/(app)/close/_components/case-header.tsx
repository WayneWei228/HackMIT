"use client";

import { motion } from "motion/react";

import { Button } from "@/components/ui/primitives";
import { MoreIcon } from "@/components/ui/icons";
import { riseIn, staggerParent } from "@/lib/motion";

import { CASE_META } from "../_data";
import { NoteIcon } from "./close-icons";

/**
 * Vendor, period and the two case-level actions.
 *
 * The title is two serif lines rather than one wrapped heading - "Mintlify" at
 * 46px and "December accrual" at 36px - so it is built here instead of using
 * the shared `PageTitle`.
 */
export function CaseHeader() {
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
            Mintlify
          </motion.div>
          <motion.div
            variants={riseIn}
            className="mt-0.5 font-display text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            December accrual
          </motion.div>
          <motion.div
            variants={riseIn}
            className="mt-[15px] flex items-center gap-[15px] text-lead text-muted-4"
          >
            {CASE_META.map((item, i) => (
              <span key={item} className="flex items-center gap-[15px]">
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

        <motion.div
          variants={riseIn}
          className="flex flex-none items-center gap-2.5 pt-1.5"
        >
          {/* `text-[13.5px]`, not `text-ui`: tailwind-merge groups every
              `text-*` together, so the shared Button's own `text-ui` is
              already eaten by its `text-ink-2`. An arbitrary length is read
              as a font size and survives the merge. */}
          <Button className="gap-[9px] px-3.5 py-[9px] text-[13.5px] leading-none shadow-[var(--shadow-hairline)]">
            <NoteIcon className="text-muted-3" />
            View case notes
          </Button>
          <button
            type="button"
            aria-label="More case actions"
            className="flex h-9 w-[38px] cursor-pointer items-center justify-center rounded-xl border border-transparent bg-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
          >
            <MoreIcon className="text-lead" />
          </button>
        </motion.div>
      </div>
    </motion.div>
  );
}
