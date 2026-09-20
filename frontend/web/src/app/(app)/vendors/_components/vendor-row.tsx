"use client";

import { motion } from "motion/react";

import { MoreIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { rowIn, transitions } from "@/lib/motion";
import { STATE_TONES, workflowTone, type Vendor } from "../_data";
import { VENDOR_GRID } from "./grid";
import { VendorMark } from "./vendor-mark";

/** Agent-state indicator: a dot, with a breathing ring while autonomous. */
function StateDot({ vendor }: { vendor: Vendor }) {
  const tone = STATE_TONES[vendor.state] ?? {
    dot: "var(--color-rule)",
    pulse: false,
  };
  return (
    <span className="relative h-2 w-2 flex-none">
      <span
        className="absolute inset-0 rounded-full"
        style={{ background: tone.dot }}
      />
      {tone.pulse && (
        <span className="animate-pulse-ring absolute -inset-1 rounded-full border-[1.2px] border-[rgba(46,128,71,.5)] [animation-duration:2.6s]" />
      )}
    </span>
  );
}

export function VendorRow({
  vendor,
  selected,
  animateLayout,
  onSelect,
}: {
  vendor: Vendor;
  selected: boolean;
  animateLayout: boolean;
  onSelect: () => void;
}) {
  const workflow = workflowTone(vendor.workflow);

  return (
    <motion.div
      variants={rowIn}
      layout={animateLayout ? "position" : false}
      transition={animateLayout ? transitions.spring : { duration: 0 }}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        VENDOR_GRID,
        // The comp cross-fades the selection tint over 180ms rather than
        // sliding a highlight between rows, and lets hover win over it.
        "cursor-pointer rounded-xl border-b border-wash-cool px-3 py-4 transition-colors duration-[180ms] ease-[var(--ease-out-soft)] outline-none hover:bg-[#F7F7F2] focus-visible:shadow-[var(--shadow-ring)]",
        selected && "bg-accent-tint",
      )}
    >
      <div className="flex min-w-0 items-center gap-[14px]">
        <VendorMark vendor={vendor} />
        <div className="min-w-0">
          <div className="truncate text-nav text-ink">{vendor.name}</div>
          <div className="mt-[3px] text-meta text-faint-2">{vendor.id}</div>
        </div>
      </div>

      <div className="min-w-0">
        <div className="truncate text-body text-ink-2">{vendor.profile}</div>
        <div className="mt-[3px] truncate text-meta text-faint-2">
          {vendor.treatment}
        </div>
      </div>

      {/* A workflow name can be longer than its column ("December usage
          accrual"); the pill keeps it on one line and clips rather than
          letting the phrase break in half. */}
      <div className="min-w-0">
        <span
          title={vendor.workflow}
          className="inline-block max-w-full truncate rounded-md px-[11px] py-1.5 align-middle text-meta whitespace-nowrap"
          style={{ background: workflow.bg, color: workflow.fg }}
        >
          {vendor.workflow}
        </span>
      </div>

      <div className="text-body whitespace-nowrap text-ink tabular-nums">
        {vendor.amount}
      </div>

      <div className="flex min-w-0 items-center gap-2.5">
        <StateDot vendor={vendor} />
        <span
          title={vendor.state}
          className="truncate text-body whitespace-nowrap text-ink-2"
        >
          {vendor.state}
        </span>
      </div>

      <div className="flex justify-end">
        <MoreIcon className="text-lead text-ghost-2" />
      </div>
    </motion.div>
  );
}
