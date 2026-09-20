"use client";

import { motion } from "motion/react";

import { Button } from "@/components/ui/primitives";
import { riseIn } from "@/lib/motion";

/**
 * Shown when the search box and filters between them exclude every case.
 *
 * `instant` shortens the rise for reduced motion rather than changing
 * `initial`, so the server and client render the same markup.
 */
export function CasesEmptyState({
  onClear,
  instant = false,
  noCases = false,
  periodLabel,
}: {
  onClear: () => void;
  instant?: boolean;
  /** The close has opened nothing yet, as opposed to filters hiding everything. */
  noCases?: boolean;
  /** The month on screen, as the API names it ("January 2027"). */
  periodLabel: string;
}) {
  return (
    <motion.div
      variants={riseIn}
      initial="hidden"
      animate="visible"
      transition={instant ? { duration: 0 } : undefined}
      className="flex flex-col items-center justify-center gap-2.5 px-5 py-16"
    >
      <div className="font-display text-[22px] text-ink-deep">
        {noCases ? "No cases yet" : "No cases match"}
      </div>
      <div className="text-ui text-faint">
        {/* A month can hold ledger entries and still no case: January carries December's reversals. */}
        {noCases
          ? `No accrual case was opened for ${periodLabel}. What the ledger posted that month is under Journals.`
          : "Try a different search term or clear the filters."}
      </div>
      {/* `cn` drops the custom `text-ui` token when a colour merges over it,
          so the comp's 13.5px/1 is restated here. See the port report. */}
      {!noCases && (
        <Button className="mt-1.5 py-[9px] text-[13.5px]/[1]" onClick={onClear}>
          Clear filters
        </Button>
      )}
    </motion.div>
  );
}
