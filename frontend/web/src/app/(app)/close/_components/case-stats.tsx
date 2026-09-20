"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { riseIn, staggerParent } from "@/lib/motion";

import { CASE_STATS, CASE_STATUS_LABEL, CASE_STATUS_VALUE } from "../_data";

function StatLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
      {children}
    </div>
  );
}

/**
 * The four-up figure strip under the title: previous accrual, what the agent
 * has supported so far, the difference, and the run's status. Supported and
 * difference stay em-dashes until the estimation agent fills them in.
 */
export function CaseStats() {
  return (
    <motion.div
      variants={staggerParent(0.05, 0.08)}
      initial="hidden"
      animate="visible"
      className="mt-[26px] grid grid-cols-[repeat(4,minmax(0,1fr))] pb-[22px]"
    >
      {CASE_STATS.map((stat, i) => (
        <motion.div
          key={stat.label}
          variants={riseIn}
          className={cn(
            i === 0 ? "pr-6" : "border-l border-line px-6",
          )}
        >
          <StatLabel>{stat.label}</StatLabel>
          <div
            className={cn(
              "mt-[9px] font-display text-3xl leading-none",
              stat.muted ? "text-ghost-2" : "text-ink-deep",
            )}
          >
            {stat.value}
          </div>
        </motion.div>
      ))}

      <motion.div variants={riseIn} className="border-l border-line px-6">
        <StatLabel>{CASE_STATUS_LABEL}</StatLabel>
        <div className="mt-[9px] flex items-center gap-2.5">
          <span className="h-[9px] w-[9px] flex-none rounded-full bg-accent" />
          <span className="font-display text-[24px] leading-none text-ink-deep">
            {CASE_STATUS_VALUE}
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
}
