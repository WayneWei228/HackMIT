"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

const LINE = "h-1 rounded-[2px]";

/** The page thumbnails beside the document: previous, current, next. */
export function ThumbnailRail({
  open,
  page,
  maxPage,
  highlighted,
  onPrev,
  onNext,
}: {
  open: boolean;
  page: number;
  maxPage: number;
  /** Once the clause is found the current page's block turns green. */
  highlighted: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <motion.div
      className="flex-none overflow-y-auto border-r border-[#EAEAE3] bg-[#FBFBF8]"
      initial={false}
      animate={{ width: open ? 114 : 0, opacity: open ? 1 : 0 }}
      transition={{ duration: 0.32, ease: easeOutSoft }}
    >
      {/* Only the pages that exist. A single-page document would otherwise be
          flanked by two neighbours that are also page 1. */}
      <div className="flex w-[114px] flex-col gap-2.5 px-3 py-[14px]">
        {page > 1 && (
          <button
            type="button"
            onClick={onPrev}
            className="flex h-[116px] cursor-pointer flex-col rounded-[4px] border border-[#E6E6DF] bg-panel px-[9px] py-2.5 text-left transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:border-[#C9CFC4]"
          >
            <div className={cn(LINE, "bg-wash-deep")} />
            <div className={cn(LINE, "mt-1.5 w-4/5 bg-wash-deep")} />
            <div className={cn(LINE, "mt-1.5 bg-wash-deep")} />
            <div className={cn(LINE, "mt-1.5 w-[64%] bg-wash-deep")} />
            <div className="mt-3 text-center text-[9px] text-ghost-2 tabular-nums">
              {page - 1}
            </div>
          </button>
        )}

        <div className="h-[116px] cursor-pointer rounded-[4px] border-[1.5px] border-accent bg-panel px-[9px] py-2.5">
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

        {page < maxPage && (
          <button
            type="button"
            onClick={onNext}
            className="flex h-[116px] cursor-pointer flex-col rounded-[4px] border border-[#E6E6DF] bg-panel px-[9px] py-2.5 text-left transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:border-[#C9CFC4]"
          >
            <div className={cn(LINE, "bg-wash-deep")} />
            <div className={cn(LINE, "mt-1.5 w-[72%] bg-wash-deep")} />
            <div className={cn(LINE, "mt-1.5 bg-wash-deep")} />
            <div className="mt-5 text-center text-[9px] text-ghost-2 tabular-nums">
              {page + 1}
            </div>
          </button>
        )}
      </div>
    </motion.div>
  );
}
