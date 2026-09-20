"use client";

import { motion } from "motion/react";

import { Breadcrumb, Button } from "@/components/ui/primitives";
import { MoreIcon } from "@/components/ui/icons";
import { CaseStatusValue } from "@/components/close/case-status-value";
import { useCaseHref } from "@/lib/case-context";
import { formatMoney, formatSigned } from "@/lib/money";
import { routes } from "@/lib/routes";
import { riseIn, staggerParent, transitions } from "@/lib/motion";
import { useVerificationScreen } from "./screen-context";

/** A page-notes glyph: the shared PageIcon plus the two ruled lines. */
function CaseNotesIcon() {
  return (
    <svg width="14" height="16" viewBox="0 0 14 16" fill="none" aria-hidden="true">
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        stroke="#6E736A"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path d="M8.5 1.6V5h3.3" stroke="#6E736A" strokeWidth={1.1} strokeLinejoin="round" />
      <path
        d="M4.4 8.2h5.2M4.4 10.6h3.6"
        stroke="#6E736A"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function CaseHeader() {
  const { header } = useVerificationScreen();
  const caseHref = useCaseHref();
  const stats = [
    { label: "PREVIOUS ACCRUAL", value: formatMoney(header.previous_accrual), accent: false },
    { label: "SUPPORTED", value: formatMoney(header.supported), accent: false },
    { label: "DIFFERENCE", value: formatSigned(header.difference), accent: true },
  ];
  const breadcrumb = [
    { label: "CLOSE", href: caseHref(routes.closeCase) },
    { label: "OBLIGATION", href: caseHref(routes.obligation) },
    { label: "ESTIMATION", href: caseHref(routes.estimation) },
    { label: "VERIFICATION" },
  ];
  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <Breadcrumb items={breadcrumb} />

      <div className="mt-[14px] flex items-start justify-between gap-6">
        <div className="min-w-0">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={transitions.slow}
            className="font-display text-display leading-[1.02] tracking-display text-ink-deep"
          >
            {header.vendor_name}
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.slow, delay: 0.05 }}
            className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {header.title}
          </motion.div>
          <div className="mt-[15px] flex flex-wrap items-center gap-x-[15px] gap-y-1 text-lead text-muted-4">
            {header.chips.map((fact, i) => (
              <span key={fact} className="flex items-center gap-[15px] whitespace-nowrap">
                {i > 0 && (
                  <span className="text-line-dark" aria-hidden="true">
                    |
                  </span>
                )}
                {fact}
              </span>
            ))}
          </div>
        </div>

        <div className="flex flex-none items-center gap-2.5 pt-1.5">
          {/* text-[13.5px] restates the comp's size: `cn` treats the custom
              `text-ui` token as a colour and drops it against `text-ink-2`;
              restating the size then drops `leading-none`, so restate that too. */}
          <Button
            variant="secondary"
            className="gap-[9px] py-[9px] text-[13.5px] leading-none shadow-[var(--shadow-hairline)]"
          >
            <CaseNotesIcon />
            View case notes
          </Button>
          <button
            type="button"
            aria-label="More case actions"
            className="flex h-9 w-[38px] cursor-pointer items-center justify-center rounded-xl border border-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
          >
            <MoreIcon className="text-lead" />
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
            className={
              i === 0 ? "pr-6" : "border-l border-line px-6"
            }
          >
            <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
              {stat.label}
            </div>
            <div
              className={`font-display mt-[9px] text-3xl leading-none ${
                stat.accent ? "text-accent" : "text-ink-deep"
              }`}
            >
              {stat.value}
            </div>
          </motion.div>
        ))}
        <motion.div variants={riseIn} className="border-l border-line px-6">
          <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
            STATUS
          </div>
          <div className="mt-[9px]">
            <CaseStatusValue status={header.status} />
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
