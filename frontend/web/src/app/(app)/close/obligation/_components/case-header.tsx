"use client";

import { useShownHeader } from "@/lib/stage-status";

import { motion } from "motion/react";

import {
  Breadcrumb,
  Button,
  PageTitle,
  SectionLabel,
} from "@/components/ui/primitives";
import { MoreIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { riseIn, staggerParent, transitions } from "@/lib/motion";
import { CaseStatusValue } from "@/components/close/case-status-value";
import { WaitingLine } from "@/components/close/outreach-strip";
import { useCaseHref } from "@/lib/case-context";
import { formatMoney, formatSigned } from "@/lib/money";
import { routes } from "@/lib/routes";
import { CaseNotesIcon } from "./glyphs";
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

        <div className="flex flex-none items-center gap-2.5 pt-1.5">
          {/* leading-none has to come after the size: tailwind-merge treats a
              font size as conflicting with a line-height, so the primitive's
              own leading-none is dropped when a size arrives after it. */}
          <Button className="gap-[9px] px-3.5 py-[9px] text-[13.5px] leading-none shadow-[var(--shadow-hairline)]">
            <CaseNotesIcon className="text-muted-3" />
            View case notes
          </Button>
          <button
            type="button"
            aria-label="More case actions"
            className="flex h-9 w-[38px] cursor-pointer items-center justify-center rounded-xl border border-transparent bg-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
          >
            <MoreIcon className="text-[15px]" />
          </button>
        </div>
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
          <WaitingLine className="mt-2" />
        </motion.div>
      </motion.div>
    </div>
  );
}
