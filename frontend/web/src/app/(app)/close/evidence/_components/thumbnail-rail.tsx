"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

const LINE = "h-1 rounded-[2px]";

/**
 * The page rail beside the document.
 *
 * A document arrives as a single text rendering, so there are no neighbouring
 * pages to offer and nothing here is clickable: the rail shows the page on
 * screen and, once the run finds the clause, marks it.
 */
export function ThumbnailRail({
  open,
  page,
  highlighted,
}: {
  open: boolean;
  page: number;
  /** Once the clause is found the current page's block turns green. */
  highlighted: boolean;
}) {
  return (
    <motion.div
      className="flex-none overflow-y-auto border-r border-[#EAEAE3] bg-[#FBFBF8]"
      initial={false}
      animate={{ width: open ? 114 : 0, opacity: open ? 1 : 0 }}
      transition={{ duration: 0.32, ease: easeOutSoft }}
    >
      <div className="flex w-[114px] flex-col gap-2.5 px-3 py-[14px]">
        <div className="h-[116px] rounded-[4px] border-[1.5px] border-accent bg-panel px-[9px] py-2.5">
          <div className={cn(LINE, "bg-[#E7E7E0]")} />
          <div className={cn(LINE, "mt-1.5 w-4/5 bg-[#E7E7E0]")} />
          <div
            className={cn(
              "mt-2 h-2.5 rounded-[2px] transition-colors duration-500 ease-[var(--ease-out-soft)]",
              highlighted ? "bg-[#E4EFD7]" : "bg-[#E7E7E0]",
            )}
          />
          <div className={cn(LINE, "mt-2 w-[70%] bg-[#E7E7E0]")} />
          <div className="mt-2 text-center text-[9px] text-accent tabular-nums">
            {page}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
