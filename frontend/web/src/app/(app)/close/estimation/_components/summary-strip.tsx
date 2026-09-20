"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { riseIn, staggerParent } from "@/lib/motion";
import { LiveDot } from "./markers";
import { useEstimationData } from "./data-context";

const cell = "border-l border-line px-6";

/**
 * The four-up figure strip under the case title. Unlike the shared
 * `StatStrip` these carry their label above the numeral, so it is built here.
 *
 * The comp has three figures plus the status cell; a payload with more or
 * fewer figures simply widens or narrows the track count, so the strip never
 * leaves an empty column or overflows the row.
 */
export function SummaryStrip({ pulsing }: { pulsing: boolean }) {
  const { SUMMARY, SUMMARY_STATUS } = useEstimationData().data;

  return (
    <motion.div
      variants={staggerParent(0.05)}
      initial="hidden"
      animate="visible"
      className="mt-[26px] grid pb-[22px]"
      style={{
        gridTemplateColumns: `repeat(${SUMMARY.length + 1}, minmax(0, 1fr))`,
      }}
    >
      {SUMMARY.map((stat, i) => (
        <motion.div
          key={`${stat.label}-${i}`}
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

      <motion.div
        variants={riseIn}
        className={cn(SUMMARY.length === 0 ? "pr-6" : cell)}
      >
        <Label>{SUMMARY_STATUS.label}</Label>
        <div className="mt-[9px] flex items-center gap-2.5">
          <LiveDot pulsing={pulsing} halo />
          <span className="font-display text-[24px] leading-none text-ink-deep">
            {SUMMARY_STATUS.value}
          </span>
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
