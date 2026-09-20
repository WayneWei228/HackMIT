"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { riseIn, staggerParent } from "@/lib/motion";
import { SUMMARY, SUMMARY_STATUS } from "../_data";
import { LiveDot } from "./markers";

const cell = "border-l border-line px-6";

/**
 * The four-up figure strip under the case title. Unlike the shared
 * `StatStrip` these carry their label above the numeral, so it is built here.
 */
export function SummaryStrip({ pulsing }: { pulsing: boolean }) {
  return (
    <motion.div
      variants={staggerParent(0.05)}
      initial="hidden"
      animate="visible"
      className="mt-[26px] grid grid-cols-4 pb-[22px]"
    >
      {SUMMARY.map((stat, i) => (
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
