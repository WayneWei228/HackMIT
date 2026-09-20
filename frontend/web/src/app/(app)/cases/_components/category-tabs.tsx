"use client";

import { motion, useReducedMotion } from "motion/react";

import { transitions } from "@/lib/motion";

import { CATEGORY_TABS, TAB_COUNTS, type CategoryTab } from "../_data";

/**
 * Category filter pills.
 *
 * The shared `TabRow` primitive paints its active pill as a white panel with a
 * drop shadow; this comp uses the green wash instead, so the pill lives here.
 * It still travels between tabs on a shared `layoutId`.
 */
export function CategoryTabs({
  value,
  onChange,
}: {
  value: CategoryTab;
  onChange: (tab: CategoryTab) => void;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <div className="scrollbar-none mt-[22px] flex items-center gap-0.5 overflow-x-auto">
      {CATEGORY_TABS.map((tab) => {
        const active = tab === value;
        return (
          <button
            key={tab}
            type="button"
            onClick={() => onChange(tab)}
            className={`relative flex flex-none items-center gap-[9px] rounded-xl border border-transparent px-3.5 py-[9px] text-ui leading-none whitespace-nowrap transition-colors duration-[160ms] ease-[var(--ease-out-soft)] focus-visible:shadow-[var(--shadow-ring-soft)] focus-visible:outline-none ${
              active ? "font-medium text-ink" : "text-muted hover:bg-wash"
            }`}
          >
            {active && (
              <motion.span
                layoutId="cases-category-pill"
                transition={reduceMotion ? { duration: 0 } : transitions.spring}
                className="absolute inset-0 -z-0 rounded-xl border border-[#D6E2D4] bg-accent-soft"
              />
            )}
            <span className="relative z-10">{tab}</span>
            <span
              className={`relative z-10 text-meta tabular-nums transition-colors duration-[160ms] ${
                active ? "text-[#5C7A59]" : "text-ghost"
              }`}
            >
              {TAB_COUNTS[tab]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
