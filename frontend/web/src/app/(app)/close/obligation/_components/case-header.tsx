"use client";

import { useShownHeader } from "@/lib/stage-status";

import { motion } from "motion/react";

import {
  Breadcrumb,
  PageTitle,
  SectionLabel,
} from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { riseIn, staggerParent, transitions } from "@/lib/motion";
import { CaseStatusValue } from "@/components/close/case-status-value";
import { useCaseHref } from "@/lib/case-context";
import { formatMoney, formatSigned } from "@/lib/money";
import { routes } from "@/lib/routes";
import { useObligationScreen } from "./screen-context";

/**
 * Case identity: where we are in the close, which vendor and period, and the
 * four numbers the whole screen is arguing about.
 */
export function CaseHeader() {
  const { header: backendHeader } = useObligationScreen();
  const header = useShownHeader(backendHeader);
  const caseHref = useCaseHref();
  const stats = [
    { label: "PREVIOUS ACCRUAL", value: formatMoney(header.previous_accrual), tone: "ink" },
    { label: "SUPPORTED", value: formatMoney(header.supported), tone: "ink" },
    { label: "DIFFERENCE", value: formatSigned(header.difference), tone: "accent" },
  ];
  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <Breadcrumb
        items={[
          { label: "CLOSE", href: caseHref(routes.closeCase) },
          { label: "ACTIVE CASE", href: caseHref(routes.closeCase) },
          { label: "EVIDENCE", href: caseHref(routes.evidence) },
          { label: "OBLIGATION" },
        ]}
      />

      <div className="mt-3.5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          {/* text-[46px] restates text-display: tailwind-merge reads our
              custom size tokens as colours and drops them when a primitive
              merges them against its own text colour. */}
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {header.vendor_name}
          </PageTitle>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.slow, delay: 0.04 }}
            className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {header.title}
          </motion.div>
          <div className="mt-[15px] flex flex-wrap items-center gap-x-[15px] gap-y-1 text-lead text-muted-4">
            {header.chips.map((attribute, i) => (
              <span key={attribute} className="flex items-center gap-[15px] whitespace-nowrap">
                {i > 0 && (
                  <span aria-hidden="true" className="text-line-dark">
                    |
                  </span>
                )}
                {attribute}
              </span>
            ))}
          </div>
        </div>

        {/* The comp's "View case notes" and "..." actions opened screens
            that have no backend behind them, so they are not drawn: an
            affordance that leads nowhere is worse than none. */}
      </div>

      <motion.div
        variants={staggerParent(0.05)}
        initial="hidden"
        animate="visible"
        className="mt-[26px] grid grid-cols-4 pb-[22px]"
      >
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            variants={riseIn}
            className={cn(i === 0 ? "pr-6" : "border-l border-line px-6")}
          >
            <SectionLabel className="text-[10.5px] text-faint">
              {stat.label}
            </SectionLabel>
            <div
              className={cn(
                "font-display mt-[9px] text-3xl leading-none",
                stat.tone === "accent" ? "text-accent" : "text-ink-deep",
              )}
            >
              {stat.value}
            </div>
          </motion.div>
        ))}
        <motion.div variants={riseIn} className="border-l border-line px-6">
          <SectionLabel className="text-[10.5px] text-faint">STATUS</SectionLabel>
          <div className="mt-[9px]">
            <CaseStatusValue status={header.status} />
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
