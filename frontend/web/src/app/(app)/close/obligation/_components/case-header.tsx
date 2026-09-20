"use client";

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
import { routes } from "@/lib/routes";
import { caseMeta, headerStats } from "../_data";
import { CaseNotesIcon, PulseDot } from "./glyphs";

/**
 * Case identity: where we are in the close, which vendor and period, and the
 * four numbers the whole screen is arguing about.
 */
export function CaseHeader({ pulsing }: { pulsing: boolean }) {
  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <Breadcrumb
        items={[
          { label: "CLOSE", href: routes.closeCase },
          { label: "ACTIVE CASE", href: routes.closeCase },
          { label: "EVIDENCE", href: routes.evidence },
          { label: "OBLIGATION" },
        ]}
      />

      <div className="mt-3.5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          {/* text-[46px] restates text-display: tailwind-merge reads our
              custom size tokens as colours and drops them when a primitive
              merges them against its own text colour. */}
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {caseMeta.vendor}
          </PageTitle>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.slow, delay: 0.04 }}
            className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {caseMeta.period}
          </motion.div>
          <div className="mt-[15px] flex items-center gap-[15px] text-lead text-muted-4">
            {caseMeta.attributes.map((attribute, i) => (
              <span key={attribute} className="flex items-center gap-[15px]">
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
        {headerStats.map((stat, i) => (
          <motion.div
            key={stat.label}
            variants={riseIn}
            className={cn(
              i === 0 ? "pr-6" : "border-l border-line px-6",
            )}
          >
            <SectionLabel className="text-[10.5px] text-faint">
              {stat.label}
            </SectionLabel>
            {stat.kind === "amount" ? (
              <div
                className={cn(
                  "font-display mt-[9px] text-3xl leading-none",
                  stat.tone === "accent" ? "text-accent" : "text-ink-deep",
                )}
              >
                {stat.value}
              </div>
            ) : (
              <div className="mt-[9px] flex items-center gap-2.5">
                <PulseDot halo pulsing={pulsing} />
                <span className="font-display text-[24px] leading-none text-ink-deep">
                  {stat.value}
                </span>
              </div>
            )}
          </motion.div>
        ))}
      </motion.div>
    </div>
  );
}
