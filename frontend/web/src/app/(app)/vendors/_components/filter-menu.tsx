"use client";

import { clsx } from "clsx";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { ChevronDownIcon } from "@/components/ui/icons";
import { Button } from "@/components/ui/primitives";
import { popIn, transitions } from "@/lib/motion";
import { ALL_STATES, type FilterValue } from "../_data";
import { FilterIcon } from "./filter-icon";

export type FilterOption = {
  value: FilterValue;
  count: number;
  dot: string;
};

/**
 * The agent-state filter. Closes on any click outside itself, exactly as the
 * comp's capture-phase document listener does.
 */
export function FilterMenu({
  value,
  options,
  onChange,
}: {
  value: FilterValue;
  options: FilterOption[];
  onChange: (next: FilterValue) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("click", onDocClick, true);
    return () => document.removeEventListener("click", onDocClick, true);
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <Button
        variant="secondary"
        // 13.5px/1: `cn` drops the primitive's own `text-ui leading-none`.
        className="text-[13.5px] leading-none"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((prev) => !prev);
        }}
      >
        <FilterIcon className="text-muted-3" />
        {value === ALL_STATES ? "Filter" : value}
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={reduced ? { duration: 0 } : transitions.base}
          className="flex text-faint-2"
        >
          <ChevronDownIcon size={11} />
        </motion.span>
      </Button>

      <AnimatePresence>
        {open && (
          <motion.div
            variants={popIn}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="absolute top-[calc(100%+6px)] right-0 z-20 min-w-[196px] rounded-[9px] border border-line bg-panel p-1.5 shadow-[var(--shadow-menu)]"
          >
            {options.map((option) => {
              const active = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={clsx(
                    "flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-ui transition-colors duration-[140ms] ease-[var(--ease-out-soft)] hover:bg-[#F3F3EE]",
                    active ? "bg-accent-tint text-ink" : "text-ink-2",
                  )}
                >
                  <span
                    className="h-[7px] w-[7px] flex-none rounded-full"
                    style={{ background: option.dot }}
                  />
                  <span className="flex-1">{option.value}</span>
                  <span className="text-meta text-ghost tabular-nums">
                    {option.count}
                  </span>
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
