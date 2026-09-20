"use client";

import { useShownHeader } from "@/lib/stage-status";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { riseIn, staggerParent } from "@/lib/motion";
import { CaseStatusValue } from "@/components/close/case-status-value";
import { formatMoney, formatSigned } from "@/lib/money";
import { useEstimationScreen } from "./screen-context";

const cell = "border-l border-line px-6";

/**
 * The four-up figure strip under the case title. Unlike the shared
 * `StatStrip` these carry their label above the numeral, so it is built here.
 */
export function SummaryStrip() {
  const { header: backendHeader } = useEstimationScreen();
  const header = useShownHeader(backendHeader);
  const stats = [
    { label: "PREVIOUS ACCRUAL", value: formatMoney(header.previous_accrual), tone: undefined },
    { label: "SUPPORTED", value: formatMoney(header.supported), tone: undefined },
    { label: "DIFFERENCE", value: formatSigned(header.difference), tone: "accent" as const },
  ];
  return (
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
          className={cn(i === 0 ? "pr-6" : cell)}
        >
          <Label>{stat.label}</Label>
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

      <motion.div variants={riseIn} className={cell}>
        <Label>STATUS</Label>
        <div className="mt-[9px]">
          <CaseStatusValue status={header.status} />
        </div>
      </motion.div>
    </motion.div>
  );
}

function Label({ children }: { children: string }) {
  return (
    <div className="text-eyebrow leading-[normal] font-medium tracking-caps-lg text-faint">
      {children}
    </div>
  );
}
