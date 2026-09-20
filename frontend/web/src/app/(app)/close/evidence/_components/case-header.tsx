"use client";

import { motion } from "motion/react";

import type { Header } from "@/lib/api-types";
import { Breadcrumb, PageTitle } from "@/components/ui/primitives";
import { transitions } from "@/lib/motion";
import { useCaseHref } from "@/lib/case-context";
import { routes } from "@/lib/routes";

/** Breadcrumb and case title. */
export function CaseHeader({ header }: { header: Header }) {
  const caseHref = useCaseHref();
  return (
    <header>
      <Breadcrumb
        items={[
          { label: "CLOSE", href: caseHref(routes.closeCase) },
          { label: "ACTIVE CASE", href: caseHref(routes.closeCase) },
          { label: "EVIDENCE" },
        ]}
      />

      <div className="mt-[14px] flex items-start justify-between gap-6">
        <div className="min-w-0">
          {/* text-[46px] restates text-display: `cn` drops a custom
              font-size token when a text colour merges over it. */}
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {header.vendor_name}
          </PageTitle>

          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.slow, delay: 0.04 }}
            className="font-display mt-[2px] text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {header.title}
          </motion.div>

          <div className="mt-[15px] flex flex-wrap items-center gap-x-[15px] gap-y-1 text-lead text-muted-4">
            {header.chips.map((item, i) => (
              <span key={item} className="flex items-center gap-[15px] whitespace-nowrap">
                {i > 0 && (
                  <span className="text-line-dark" aria-hidden="true">
                    |
                  </span>
                )}
                {item}
              </span>
            ))}
          </div>
        </div>

        {/* The comp's "View case notes" and "..." actions opened screens
            that have no backend behind them, so they are not drawn: an
            affordance that leads nowhere is worse than none. */}
      </div>
    </header>
  );
}
