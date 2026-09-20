"use client";

import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";

import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

import { CaseStatusValue } from "@/components/close/case-status-value";
import type { Header } from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";

import { TOTALS_STEP } from "../_data";

/**
 * A figure the run has yet to establish. It reads as a dash until the
 * evidence lands, then the real number rises into its place.
 */
function ResolvingFigure({
  resolved,
  className,
  children,
}: {
  resolved: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className="relative mt-[9px] h-[28px]">
      <AnimatePresence initial={false}>
        {!resolved && (
          <motion.span
            key="pending"
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.25, ease: easeOutSoft } }}
            className="font-display absolute top-0 left-0 text-3xl leading-none text-ghost-2"
          >
            -
          </motion.span>
        )}
        {resolved && (
          <motion.span
            key="value"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: easeOutSoft }}
            className={cn(
              "font-display absolute top-0 left-0 text-3xl leading-none whitespace-nowrap",
              className,
            )}
          >
            {children}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}

function Column({
  label,
  first = false,
  children,
}: {
  label: string;
  first?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={cn(first ? "pr-6" : "border-l border-line px-6")}>
      <SectionLabel className="text-[10.5px] text-faint">{label}</SectionLabel>
      {children}
    </div>
  );
}

/** The four-up figure strip under the case title. */
export function CaseStats({ header, step }: { header: Header; step: number }) {
  const resolved = step >= TOTALS_STEP;

  return (
    <div className="mt-[26px] grid grid-cols-4 pb-[22px]">
      <Column label="PREVIOUS ACCRUAL" first>
        <div className="font-display mt-[9px] text-3xl leading-none text-ink-deep">
          {formatMoney(header.previous_accrual)}
        </div>
      </Column>

      <Column label="SUPPORTED">
        <ResolvingFigure resolved={resolved} className="text-ink-deep">
          {formatMoney(header.supported)}
        </ResolvingFigure>
      </Column>

      <Column label="DIFFERENCE">
        <ResolvingFigure resolved={resolved} className="text-accent">
          {formatSigned(header.difference)}
        </ResolvingFigure>
      </Column>

      <Column label="STATUS">
        <div className="mt-[9px]">
          <CaseStatusValue status={header.status} />
        </div>
      </Column>
    </div>
  );
}
