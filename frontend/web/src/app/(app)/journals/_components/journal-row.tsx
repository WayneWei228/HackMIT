"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { Tag } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { rowIn } from "@/lib/motion";
import { routes, withCase } from "@/lib/routes";

import { JOURNAL_GRID } from "./journal-grid";
import { isDebit, stamp, tokenLabel, type JournalEntry } from "../_data";

/**
 * One journal entry, lines and all.
 *
 * The row is the *entry*, not the line: an entry is balanced, and splitting
 * its sides across sibling rows would let a scroll or a filter separate a
 * debit from the credit that answers it. So the identity columns are the
 * entry's, and the last cell stacks its lines.
 *
 * The row is not itself a link. The one thing worth opening from here is the
 * case, and that cell says so; making the whole row navigate would hide the
 * destination behind an entry that reads like a record, not a button.
 */
export function JournalRow({ entry }: { entry: JournalEntry }) {
  const posted = stamp(entry.at);

  return (
    <motion.div
      variants={rowIn}
      className={cn(
        JOURNAL_GRID,
        "rounded-xl border-b border-wash-cool px-2.5 py-[15px] transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F7F7F2]",
      )}
    >
      <div className="min-w-0 pt-px">
        <div className="truncate text-nav text-ink" title={entry.vendor}>
          {entry.vendor}
        </div>
        <div className="mt-1 truncate text-meta text-faint-2" title={entry.vendor_id}>
          {entry.vendor_id}
        </div>
      </div>

      <div className="min-w-0 pt-px">
        <Link
          href={withCase(routes.closeCase, entry.case_id)}
          title={entry.case_id}
          className="block truncate text-body text-accent-link transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:text-accent-press hover:underline"
        >
          {entry.case_key}
        </Link>
      </div>

      <div className="min-w-0 pt-px">
        <Tag
          tone={isTrueUp(entry.kind) ? "cool" : "neutral"}
          className="max-w-full truncate"
        >
          {tokenLabel(entry.kind)}
        </Tag>
      </div>

      <div
        className="truncate pt-px text-body text-ink-2"
        title={entry.basis}
      >
        {tokenLabel(entry.basis)}
      </div>

      <div className="pt-px text-sm leading-[1.45] text-faint">
        <div>{posted.date}</div>
        {posted.time ? <div>{posted.time}</div> : null}
      </div>

      <div className="flex min-w-0 flex-col gap-[7px]">
        {entry.lines.map((line, index) => (
          <div
            key={`${line.side}-${line.account}-${index}`}
            className="grid grid-cols-[24px_minmax(0,1fr)_auto] items-baseline gap-x-2.5"
          >
            <span
              className={cn(
                "text-meta tracking-wide",
                isDebit(line.side) ? "text-ink-2" : "text-faint",
              )}
            >
              {line.side}
            </span>
            <span className="truncate text-body text-ink-2" title={line.account}>
              {line.account}
            </span>
            <span className="text-body text-ink tabular-nums">
              {line.amount}
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

/**
 * Whether this kind is a correction to an earlier estimate.
 *
 * Only used to pick between two pill tones, and anything the check does not
 * recognise falls through to the neutral one - so a kind this app has never
 * seen still renders as itself.
 */
function isTrueUp(kind: string): boolean {
  return kind.replace(/[_\s-]/g, "").toLowerCase().includes("trueup");
}
