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
}: {
  onClear: () => void;
  instant?: boolean;
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
        No cases match
      </div>
      <div className="text-ui text-faint">
        Try a different search term or clear the filters.
      </div>
      {/* `cn` drops the custom `text-ui` token when a colour merges over it,
          so the comp's 13.5px/1 is restated here. See the port report. */}
      <Button className="mt-1.5 py-[9px] text-[13.5px]/[1]" onClick={onClear}>
        Clear filters
      </Button>
    </motion.div>
  );
}
