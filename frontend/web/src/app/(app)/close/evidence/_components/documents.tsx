"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

import {
  AGREEMENT_HEADER,
  AP_DOC,
  AP_ROWS,
  PAGE_5,
  PAGE_6,
  PAGE_7,
  PRIOR_DOC,
  type Clause,
} from "../_data";

/* -------------------------------------------------------------------------- */
/* Sheet                                                                       */
/* -------------------------------------------------------------------------- */

/** The paper the documents are printed on. */
function Sheet({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-[min(700px,92%)] rounded-sm border border-sunk bg-panel shadow-[var(--shadow-pop)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

const CLAUSE_GRID =
  "font-display grid grid-cols-[42px_1fr] gap-x-2 text-lead leading-[1.75] text-ink-2";

function ClauseList({
  clauses,
  className,
}: {
  clauses: readonly Clause[];
  className?: string;
}) {
  return (
    <div className={`${CLAUSE_GRID} ${className ?? ""}`}>
      {clauses.map((clause) => (
        <div key={clause.n} className="contents">
          <div className="text-muted-3">{clause.n}</div>
          <div>{clause.text}</div>
        </div>
      ))}
    </div>
  );
}

function SectionHeading({ number, heading }: { number: string; heading: string }) {
  return (
    <div className="flex items-baseline gap-6">
      <span className="font-display text-[20px] text-ink-deep">{number}</span>
      <span className="font-display text-[20px] font-medium text-ink-deep">
        {heading}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Agreement                                                                   */
/* -------------------------------------------------------------------------- */

/** 4.2 - the clause the whole close turns on. */
function PricingClause({ highlighted }: { highlighted: boolean }) {
  return (
    <div className="mt-[18px] -mx-3 flex items-stretch">
      <div className="relative min-w-0 flex-1 rounded-[4px] p-3">
        <motion.span
          aria-hidden="true"
          className="absolute inset-y-0 left-0 rounded-[4px] bg-[#EEF5E4]"
          initial={false}
          animate={{ width: highlighted ? "100%" : "0%" }}
          transition={{ duration: 0.75, ease: easeOutSoft }}
        />
        <div className={`${CLAUSE_GRID} relative`}>
          <div className="text-muted-3">{PAGE_6.match.n}</div>
          <div>
            {PAGE_6.match.before}
            <strong className="font-semibold text-ink-deep">
              {PAGE_6.match.emphasis}
            </strong>
            {PAGE_6.match.after}
          </div>
        </div>
      </div>

      <motion.div
        className="flex flex-none items-center gap-[11px] pl-[14px]"
        initial={false}
        animate={{ opacity: highlighted ? 1 : 0, x: highlighted ? 0 : -8 }}
        transition={{ duration: 0.34, ease: easeOutSoft }}
      >
        <div className="w-[2px] self-stretch rounded-[1px] bg-[#4F9A64]" />
        <div>
          <div className="text-[9.5px] font-semibold tracking-caps text-[#4F9A64]">
            {PAGE_6.match.flagLabel}
          </div>
          <div className="font-display mt-1 text-md text-accent">
            {PAGE_6.match.flagCitation}
          </div>
        </div>
      </motion.div>
    </div>
  );
}

export function AgreementDocument({
  page,
  highlighted,
}: {
  page: number;
  highlighted: boolean;
}) {
  return (
    <Sheet className="px-[52px] pt-[46px] pb-[58px]">
      <div className="flex items-start justify-between gap-6">
        <div className="flex items-center gap-[11px]">
          <span className="h-[25px] w-[25px] flex-none rounded-full bg-[#1C4432]" />
          <span className="text-[23px] tracking-[-0.02em] text-ink-deep">
            {AGREEMENT_HEADER.wordmark}
          </span>
        </div>
        <div className="text-right">
          <div className="font-display text-md text-ink-deep">
            {AGREEMENT_HEADER.title}
          </div>
          <div className="mt-1.5 text-[9.5px] tracking-[0.12em] text-faint-3">
            {AGREEMENT_HEADER.executed}
          </div>
        </div>
      </div>

      <div className="mt-7 mb-[30px] h-px bg-[#E4E4DC]" />

      {page === 5 && (
        <div>
          <SectionHeading number={PAGE_5.number} heading={PAGE_5.heading} />
          <ClauseList clauses={PAGE_5.clauses} className="mt-6 gap-y-5" />
        </div>
      )}

      {page === 6 && (
        <div>
          <SectionHeading number={PAGE_6.number} heading={PAGE_6.heading} />
          <ClauseList clauses={PAGE_6.lead} className="mt-6 gap-y-[22px]" />
          <PricingClause highlighted={highlighted} />
          <ClauseList clauses={PAGE_6.tail} className="mt-[22px] gap-y-[22px]" />
        </div>
      )}

      {page === 7 && (
        <div>
          <SectionHeading number={PAGE_7.number} heading={PAGE_7.heading} />
          <ClauseList clauses={PAGE_7.clauses} className="mt-6 gap-y-5" />
        </div>
      )}
    </Sheet>
  );
}

/* -------------------------------------------------------------------------- */
/* AP history                                                                  */
/* -------------------------------------------------------------------------- */

const AP_GRID = "grid grid-cols-[94px_1fr_86px_82px]";
const AP_CELL = "border-b border-wash-warm py-[11px]";

export function ApHistoryDocument() {
  return (
    <Sheet className="px-9 pt-[34px] pb-11">
      <div className="flex items-baseline justify-between gap-5">
        <div className="font-display text-xl text-ink-deep">{AP_DOC.title}</div>
        <div className="text-[10px] tracking-[0.12em] text-faint-3">
          {AP_DOC.vendor}
        </div>
      </div>

      <div
        className={cn(
          AP_GRID,
          "mt-6 border-b border-[#E7E7E0] pb-[9px] text-[10px] tracking-[0.09em] text-ghost",
        )}
      >
        {AP_DOC.columns.map((column, i) => (
          <div key={column} className={i > 1 ? "text-right" : undefined}>
            {column}
          </div>
        ))}
      </div>

      <div className={cn(AP_GRID, "text-sm text-ink-2")}>
        {AP_ROWS.map((row) => (
          <div key={row.date} className="contents">
            <div className={AP_CELL}>{row.date}</div>
            <div className={AP_CELL}>{row.description}</div>
            <div className={cn(AP_CELL, "text-right tabular-nums")}>
              {row.amount}
            </div>
            <div className={cn(AP_CELL, "text-right text-faint-2")}>
              {row.status}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 flex items-center gap-2.5 text-meta text-faint-2">
        <span className="h-[6px] w-[6px] flex-none rounded-full bg-accent" />
        {AP_DOC.note}
      </div>
    </Sheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Prior close memo                                                            */
/* -------------------------------------------------------------------------- */

export function PriorCloseDocument() {
  return (
    <Sheet className="px-[52px] pt-[46px] pb-[58px]">
      <div className="text-[9.5px] tracking-[0.12em] text-faint-3">
        {PRIOR_DOC.eyebrow}
      </div>
      <div className="font-display mt-2.5 text-[25px] text-ink-deep">
        {PRIOR_DOC.title}
      </div>

      <div className="mt-6 mb-[26px] h-px bg-[#E4E4DC]" />

      <div className="grid grid-cols-[92px_1fr] gap-x-2.5 gap-y-3 text-ui text-ink-2">
        {PRIOR_DOC.fields.map((field) => (
          <div key={field.label} className="contents">
            <div className="text-faint-3">{field.label}</div>
            <div>{field.value}</div>
          </div>
        ))}
      </div>

      {PRIOR_DOC.paragraphs.map((paragraph, i) => (
        <p
          key={paragraph.slice(0, 24)}
          className={`font-display text-lead leading-[1.85] text-pretty text-ink-2 ${
            i === 0 ? "mt-6" : "mt-4"
          }`}
        >
          {paragraph}
        </p>
      ))}
    </Sheet>
  );
}
