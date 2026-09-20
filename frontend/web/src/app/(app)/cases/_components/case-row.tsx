"use client";

import Link from "next/link";
import { useState } from "react";
import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { MoreIcon } from "@/components/ui/icons";
import { easeOutSoft } from "@/lib/motion";

import { CASE_GRID } from "./case-grid";
import { CaseStatusDot } from "./case-status-dot";
import {
  CATEGORY_STYLES,
  MARKS,
  formatAmount,
  type CaseRecord,
} from "../_data";

const MotionLink = motion.create(Link);

/**
 * The comp's entrance: a 7px rise over 450ms, rows 45ms apart. It runs once,
 * when the table first paints. A row that arrives later - because the search
 * or a filter changed - appears immediately, exactly as the comp does.
 *
 * `null` means the table has already settled. Reduced motion zeroes the
 * numbers rather than dropping the object, so the markup React renders on the
 * server and the markup it hydrates are identical either way.
 */
export type CaseRowEntrance = { delay: number; duration: number } | null;

/** One case: vendor, close item, amount, where the agent chain has got to. */
export function CaseRow({
  row,
  entrance,
}: {
  row: CaseRecord;
  entrance: CaseRowEntrance;
}) {
  const mark = MARKS[row.mark];
  const category = CATEGORY_STYLES[row.category];

  /* Frozen at mount so a later re-render cannot restart or cut short a rise
     that is already playing. */
  const [entranceOnMount] = useState(entrance);

  return (
    <MotionLink
      href={row.href}
      initial={entranceOnMount ? { opacity: 0, y: 7 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={
        entranceOnMount
          ? {
              duration: entranceOnMount.duration,
              ease: easeOutSoft,
              delay: entranceOnMount.delay,
            }
          : { duration: 0 }
      }
      className={cn(
        CASE_GRID,
        "rounded-xl border-b border-wash-cool px-2.5 py-[15px] text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F7F7F2]",
      )}
    >
      <div className="flex min-w-0 items-center gap-[14px]">
        <span
          className="flex h-8 w-8 flex-none items-center justify-center rounded-xl text-meta font-semibold tracking-[0.02em]"
          style={{ background: mark.bg, color: mark.fg }}
        >
          {row.initials}
        </span>
        <span className="truncate text-nav text-ink">{row.vendor}</span>
      </div>

      <div className="truncate text-body text-ink-2">{row.item}</div>

      <div>
        <span
          className="inline-block rounded-md px-2.5 py-[5px] text-meta whitespace-nowrap"
          style={{ background: category.bg, color: category.fg }}
        >
          {row.category}
        </span>
      </div>

      <div className="text-body text-ink tabular-nums">
        {formatAmount(row.amount)}
      </div>

      <div className="text-body text-ink-2">{row.stage}</div>

      <div className="flex items-center gap-2.5">
        <CaseStatusDot status={row.status} />
        <span className="text-body whitespace-nowrap text-ink-2">
          {row.status}
        </span>
      </div>

      <div className="text-sm leading-[1.45] text-faint">
        <div>{row.date}</div>
        <div>{row.time}</div>
      </div>

      <div className="flex justify-end">
        <MoreIcon className="text-[15px] text-ghost-2" />
      </div>
    </MotionLink>
  );
}
