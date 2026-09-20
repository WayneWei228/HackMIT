"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";

import { Button } from "@/components/ui/primitives";
import { ChevronDownIcon } from "@/components/ui/icons";
import { popIn, transitions } from "@/lib/motion";

import {
  ALL_STATUSES,
  STATUS_OPTIONS,
  STATUS_STYLES,
  type StatusFilter,
} from "../_data";

function FilterLinesIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M2.4 4.2h11.2M4.4 8h7.2M6.4 11.8h3.2"
        stroke="currentColor"
        strokeWidth={1.2}
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Status dropdown. Counts respect the search box and the category tab. */
export function StatusFilterMenu({
  value,
  counts,
  open,
  onOpenChange,
  onChange,
}: {
  value: StatusFilter;
  counts: Record<StatusFilter, number>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChange: (status: StatusFilter) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocumentClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onOpenChange(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("click", onDocumentClick, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onDocumentClick, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onOpenChange]);

  return (
    <div ref={rootRef} className="relative">
      <Button
        className="text-[13.5px]/[1]"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={(event) => {
          event.stopPropagation();
          onOpenChange(!open);
        }}
      >
        <span className="text-muted-3">
          <FilterLinesIcon />
        </span>
        {value === ALL_STATUSES ? "Status" : value}
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={transitions.base}
          className="flex text-faint-2"
        >
          <ChevronDownIcon size={11} />
        </motion.span>
      </Button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            variants={popIn}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="origin-top-left absolute top-[calc(100%+6px)] left-0 z-20 min-w-[176px] rounded-[9px] border border-line bg-panel p-1.5 shadow-[var(--shadow-menu)]"
          >
            {STATUS_OPTIONS.map((option) => {
              const selected = option === value;
              return (
                <button
                  key={option}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => {
                    onChange(option);
                    onOpenChange(false);
                  }}
                  className={`flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-ui transition-colors duration-[140ms] ease-[var(--ease-out-soft)] hover:bg-[#F3F3EE] focus-visible:bg-[#F3F3EE] focus-visible:outline-none ${
                    selected ? "bg-accent-tint text-ink" : "text-ink-2"
                  }`}
                >
                  <span
                    className="h-[7px] w-[7px] flex-none rounded-full"
                    style={{
                      background:
                        option === ALL_STATUSES
                          ? "var(--color-rule)"
                          : STATUS_STYLES[option].dot,
                    }}
                  />
                  <span className="flex-1 text-left">{option}</span>
                  <span className="text-meta text-ghost tabular-nums">
                    {counts[option]}
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
