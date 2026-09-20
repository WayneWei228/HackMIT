"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";

import { Button } from "@/components/ui/primitives";
import { CalendarIcon, ChevronDownIcon } from "@/components/ui/icons";
import { popIn, transitions } from "@/lib/motion";
import {
  ALL_PERIODS,
  infoLabel,
  periodLabel,
  stateLabel,
  type PeriodInfo,
} from "@/lib/period";

/**
 * The month this screen is scoped to.
 *
 * Same chrome as the status filter beside it: the comp's secondary button,
 * a chevron that turns, and a `popIn` menu on the menu shadow. The months are
 * whatever the backend knows - there is no fixed list, and no month is
 * assumed to exist. `All months` fetches the case list unscoped.
 */
export function PeriodMenu({
  value,
  periods,
  open,
  onOpenChange,
  onChange,
}: {
  /** The selected month, `ALL_PERIODS`, or `null` before one is resolved. */
  value: string | null;
  periods: readonly PeriodInfo[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChange: (period: string) => void;
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

  const selectedInfo =
    value === null
      ? null
      : (periods.find((info) => info.period === value) ?? null);
  const label = selectedInfo ? infoLabel(selectedInfo) : periodLabel(value);

  const option = (key: string, label: string, meta: string | null) => {
    const selected = key === value || (value === null && key === ALL_PERIODS);
    return (
      <button
        key={key}
        type="button"
        role="menuitemradio"
        aria-checked={selected}
        onClick={() => {
          onChange(key);
          onOpenChange(false);
        }}
        className={`flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-ui transition-colors duration-[140ms] ease-[var(--ease-out-soft)] hover:bg-[#F3F3EE] focus-visible:bg-[#F3F3EE] focus-visible:outline-none ${
          selected ? "bg-accent-tint text-ink" : "text-ink-2"
        }`}
      >
        <span className="flex-1 text-left whitespace-nowrap">{label}</span>
        {meta ? <span className="text-meta text-ghost">{meta}</span> : null}
      </button>
    );
  };

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
          <CalendarIcon />
        </span>
        {label}
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
            className="origin-top-left absolute top-[calc(100%+6px)] left-0 z-20 min-w-[196px] rounded-[9px] border border-line bg-panel p-1.5 shadow-[var(--shadow-menu)]"
          >
            {option(ALL_PERIODS, ALL_PERIODS, null)}
            {periods.map((info) =>
              option(
                info.period,
                infoLabel(info),
                info.state ? stateLabel(info.state) : null,
              ),
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
