"use client";

import { useShownHeader } from "@/lib/stage-status";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { riseIn, staggerParent } from "@/lib/motion";

import { CaseStatusValue } from "@/components/close/case-status-value";
import type { Header } from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";

function StatLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
      {children}
    </div>
  );
}

/**
 * The four-up figure strip under the title: previous accrual, what the agent
 * has supported so far, the difference, and the case's status. Figures stay
 * dashes until an agent has produced them.
 */
export function CaseStats({ header: backendHeader }: { header: Header }) {
  const header = useShownHeader(backendHeader);
  const stats = [
    { label: "PREVIOUS ACCRUAL", value: formatMoney(header.previous_accrual), muted: header.previous_accrual === null },
    { label: "SUPPORTED", value: formatMoney(header.supported), muted: header.supported === null },
    { label: "DIFFERENCE", value: formatSigned(header.difference), muted: header.difference === null },
  ];
  return (
    <motion.div
      variants={staggerParent(0.05, 0.08)}
      initial="hidden"
      animate="visible"
      className="mt-[26px] grid grid-cols-[repeat(4,minmax(0,1fr))] pb-[22px]"
    >
      {stats.map((stat, i) => (
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
        <StatLabel>STATUS</StatLabel>
        <div className="mt-[9px]">
          <CaseStatusValue status={header.status} />
        </div>
      </motion.div>
    </motion.div>
  );
}
