"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";

import { ChevronDownIcon } from "@/components/ui/icons";
import type { StageCheck } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { timing } from "../_motion";
import { StepMarker } from "./markers";

const STATUS_CHIP: Record<StageCheck["status"], string> = {
  PASS: "bg-accent-soft-2 text-accent-press",
  FLAG: "bg-[#F6ECD3] text-[#8A6516]",
  INFO: "bg-[#E4EBF3] text-[#3F5A7C]",
  PENDING: "bg-wash text-muted-3",
};

/**
 * One rung of the Estimate build timeline: a marker, a clickable title, a
 * collapsible body, and the hairline that joins it to the next rung. The rung
 * only exists because the workpaper recorded it, so it is always complete.
 */
export function BuildStep({
  n,
  title,
  status,
  open,
  last = false,
  tallBody = false,
  onToggle,
  children,
}: {
  n: string;
  title: string;
  /** What the Estimation agent's own check for this rung concluded, if it raised one. */
  status: StageCheck["status"] | null;
  open: boolean;
  last?: boolean;
  tallBody?: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className={cn("relative pl-10", last ? "pb-0" : "pb-[22px]")}>
      {!last && (
        <span className="absolute top-[22px] bottom-0 left-2 w-px bg-accent-line" />
      )}
      {status === "FLAG" ? (
        <span
          aria-label="Flagged"
          className="absolute top-[2px] left-0 flex h-[17px] w-[17px] items-center justify-center rounded-full bg-[#D6A43C] text-[10px] leading-none font-bold text-white"
        >
          !
        </span>
      ) : (
        <StepMarker state="done" />
      )}

      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-3.5 text-left"
      >
        <span className="text-sm leading-[normal] text-faint-3 tabular-nums">{n}</span>
        <span className="min-w-0 flex-1 text-nav leading-[normal] break-words text-ink">{title}</span>
        {status && (
          <span
            className={cn(
              "flex-none rounded-sm px-1.5 py-[3px] text-nano leading-none font-semibold tracking-caps",
              STATUS_CHIP[status],
            )}
          >
            {status}
          </span>
        )}
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={timing.chevron}
          className="flex flex-none text-faint-3"
        >
          <ChevronDownIcon size={13} />
        </motion.span>
      </button>

      <motion.div
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={tallBody ? timing.bodyTall : timing.body}
        initial={false}
        className="overflow-hidden"
      >
        {children}
      </motion.div>
    </div>
  );
}
