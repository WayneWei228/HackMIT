"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import { staggerParent } from "@/lib/motion";

import { JOURNAL_GRID } from "./journal-grid";
import { JournalRow } from "./journal-row";
import { COLUMNS, type JournalEntry } from "../_data";

/**
 * The entries a close posted, newest first as the API orders them.
 *
 * The columns do not sort. Journal entries are a ledger: their order is the
 * order they were posted in, and re-sorting a ledger by vendor would be a
 * view of it this product has no reason to offer yet.
 */
export function JournalTable({
  entries,
  note,
}: {
  entries: readonly JournalEntry[];
  /** The API's own caveat about the accounts it names, if it sent one. */
  note?: string;
}) {
  const reduced = useReducedMotion();

  return (
    <>
      <div className={cn(JOURNAL_GRID, "border-b border-line px-2.5 pb-[11px]")}>
        {COLUMNS.map((label) => (
          <div
            key={label}
            className="text-eyebrow font-medium tracking-[0.12em] text-faint"
          >
            {label}
          </div>
        ))}
      </div>

      <motion.div
        variants={staggerParent(0.045)}
        initial={reduced ? false : "hidden"}
        animate="visible"
      >
        {entries.map((entry, index) => (
          <JournalRow
            key={`${entry.case_id}-${entry.kind}-${entry.at}-${index}`}
            entry={entry}
          />
        ))}
      </motion.div>

      {/* The `accounts` map the payload also carries is the same chart of
          accounts the lines above already name, one entry per category - a
          legend restating it would only repeat strings that are on screen.
          The note is the part that is not on screen anywhere else. */}
      {note ? (
        <p className="mt-5 max-w-[620px] text-meta leading-[1.6] text-ghost">
          {note}
        </p>
      ) : null}
    </>
  );
}
