"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import { riseIn, staggerParent } from "@/lib/motion";
import type { Vendor } from "../_data";

/**
 * The four headline numerals, counted from the vendors on the page. The shared `StatStrip` sits flush right of a
 * filter row and uses 22px gutters; the comp's vendor strip spans the full
 * width with equal 24px columns, so it is laid out here.
 */
export function VendorKpis({ vendors }: { vendors: readonly Vendor[] }) {
  const reduced = useReducedMotion();
  const count = (state: Vendor["state"]) => vendors.filter((v) => v.state === state).length;
  const kpis = [
    { value: String(vendors.length), label: "vendors" },
    { value: String(count("Autonomous")), label: "autonomous workflows" },
    { value: String(count("Waiting for evidence")), label: "requiring review" },
    { value: String(count("Verified")), label: "verified closes" },
  ];
  return (
    <motion.div
      variants={staggerParent(0.05)}
      initial={reduced ? false : "hidden"}
      animate="visible"
      className="mt-[26px] flex items-stretch pb-6"
    >
      {kpis.map((kpi, i) => (
        <motion.div
          key={kpi.label}
          variants={riseIn}
          className={cn(
            "min-w-0 flex-1 px-6",
            i === 0 && "pl-0",
            i === kpis.length - 1 && "pr-0",
            i > 0 && "border-l border-line",
          )}
        >
          <div className="font-display text-[30px] leading-none text-ink-deep">
            {kpi.value}
          </div>
          <div className="mt-2 text-sm text-faint">{kpi.label}</div>
        </motion.div>
      ))}
    </motion.div>
  );
}
