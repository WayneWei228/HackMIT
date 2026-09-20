"use client";

import { motion } from "motion/react";

import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

import { FACTS, RAIL } from "../_data";

/**
 * The fact set the evidence agent hands on. Each row sits as an em dash until
 * its step lands, then the value rises in and the row flashes once.
 */
export function ExtractedFacts({ step }: { step: number }) {
  return (
    <>
      <div className="mt-8 h-px bg-sunk" />
      <SectionLabel className="mt-[22px] text-[10.5px] text-faint">
        {RAIL.factsLabel}
      </SectionLabel>

      <div className="mt-3 flex flex-col gap-px">
        {FACTS.map((fact) => {
          const landed = step >= fact.at;
          return (
            <div
              key={fact.label}
              className={cn(
                "-mx-2 flex items-center justify-between gap-4 rounded-md p-2 transition-colors duration-[450ms] ease-[var(--ease-out-soft)]",
                step === fact.at ? "bg-[#F1F6EC]" : "bg-transparent",
              )}
            >
              <span className="text-ui text-ink-2">{fact.label}</span>
              <span className="relative flex h-[18px] min-w-[104px] items-center justify-end">
                <motion.span
                  className="absolute right-0 text-body text-[#C4C8BE]"
                  initial={false}
                  animate={{ opacity: landed ? 0 : 1 }}
                  transition={{ duration: 0.22, ease: easeOutSoft }}
                >
                  —
                </motion.span>
                <motion.span
                  className="absolute right-0 text-ui whitespace-nowrap text-ink tabular-nums"
                  initial={false}
                  animate={{
                    opacity: landed ? 1 : 0,
                    y: landed ? 0 : 5,
                  }}
                  transition={{ duration: 0.34, ease: easeOutSoft }}
                >
                  {fact.value}
                </motion.span>
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}
