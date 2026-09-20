"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { transitions } from "@/lib/motion";
import type { MarkerState } from "../_data";

/**
 * Marks and glyphs specific to the Obligation screen.
 *
 * The shared `StatusDot` is a 7px dot with a filled halo; the comps on the
 * close run use a 9px dot with a hairline ring that pulses outward, so it
 * lives here rather than in the shared set.
 */

/** Running indicator: a green dot with an expanding hairline ring. */
export function PulseDot({
  halo = false,
  pulsing = true,
  className,
}: {
  halo?: boolean;
  pulsing?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative h-[9px] w-[9px] flex-none", className)}>
      <span
        className={cn(
          "absolute inset-0 rounded-full bg-accent",
          halo && "shadow-[var(--shadow-ring)]",
        )}
      />
      <motion.span
        aria-hidden="true"
        animate={{ opacity: pulsing ? 1 : 0 }}
        transition={transitions.slow}
        className="animate-pulse-ring absolute -inset-1 rounded-full border-[1.3px] border-[rgba(46,128,71,0.55)] [animation-duration:2.6s]"
      />
    </span>
  );
}

/**
 * 17px checklist marker: idle ring, running ring, completed disc.
 *
 * All three states stay mounted and cross-fade, the way the comp does - a
 * shared `layoutId` would slide the running ring down the whole checklist.
 */
export function CheckMarker({ state }: { state: MarkerState }) {
  return (
    <span className="absolute top-px left-0 h-[17px] w-[17px]">
      <motion.span
        animate={{ opacity: state === "rest" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-0 rounded-full border-[1.4px] border-rule-soft"
      />
      <motion.span
        initial={false}
        animate={{ opacity: state === "active" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-0 rounded-full border-2 border-accent"
      />
      <motion.svg
        width="17"
        height="17"
        viewBox="0 0 18 18"
        fill="none"
        aria-hidden="true"
        animate={{ opacity: state === "done" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-0"
      >
        <circle cx="9" cy="9" r="8.4" fill="#2E8047" />
        <path
          d="M5.4 9.2l2.6 2.6 5-5.4"
          stroke="#FFFFFF"
          strokeWidth={1.6}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </motion.svg>
    </span>
  );
}

/** 13px marker for the sub-checks inside check 3: ring, spinner, tick. */
export function SubCheckMarker({ state }: { state: MarkerState }) {
  return (
    <span className="relative h-[13px] w-[13px] flex-none">
      <motion.span
        animate={{ opacity: state === "rest" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-0 rounded-full border border-rule"
      />
      <motion.span
        animate={{ opacity: state === "active" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-0"
      >
        <svg
          width="13"
          height="13"
          viewBox="0 0 13 13"
          fill="none"
          aria-hidden="true"
          className="animate-spin [animation-duration:1.1s]"
        >
          <path
            d="M6.5 1a5.5 5.5 0 0 1 5.5 5.5"
            stroke="#2E8047"
            strokeWidth={1.6}
            strokeLinecap="round"
          />
          <circle
            cx="6.5"
            cy="6.5"
            r="5.5"
            stroke="#CFE0CF"
            strokeWidth={1.2}
          />
        </svg>
      </motion.span>
      <motion.svg
        width="13"
        height="13"
        viewBox="0 0 13 13"
        fill="none"
        aria-hidden="true"
        animate={{ opacity: state === "done" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-0"
      >
        <path
          d="M1.8 6.8l3.2 3.1 6.2-7"
          stroke="#2E8047"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </motion.svg>
    </span>
  );
}

/**
 * 13px marker for the rail's task list: ring, filled dot, tick. The dot grows
 * from half size in place, as in the comp, rather than travelling down the list.
 */
export function TaskMarker({ state }: { state: MarkerState }) {
  return (
    <span className="relative mx-px h-[13px] w-[13px] flex-none">
      <motion.span
        animate={{ opacity: state === "rest" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-px rounded-full border border-rule"
      />
      <motion.span
        initial={false}
        animate={{
          opacity: state === "active" ? 1 : 0,
          scale: state === "active" ? 1 : 0.5,
        }}
        transition={transitions.base}
        className="absolute inset-px rounded-full bg-accent"
      />
      <motion.svg
        width="13"
        height="13"
        viewBox="0 0 13 13"
        fill="none"
        aria-hidden="true"
        animate={{ opacity: state === "done" ? 1 : 0 }}
        transition={transitions.base}
        className="absolute inset-0"
      >
        <path
          d="M1.8 6.8l3.2 3.1 6.2-7"
          stroke="#2E8047"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </motion.svg>
    </span>
  );
}

/** Page glyph with two text rules - the "View case notes" button. */
export function CaseNotesIcon({ className }: { className?: string }) {
  return (
    <svg
      width="14"
      height="16"
      viewBox="0 0 14 16"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path
        d="M8.5 1.6V5h3.3"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path
        d="M4.4 8.2h5.2M4.4 10.6h3.6"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * The 15x17 page glyph that marks a source document.
 *
 * The shared `PageIcon` draws the same path at stroke-width 1.25 and derives
 * its height from the width; these comps draw it at 1.1 in a 15x17 box, and a
 * stroke width on a child path cannot be overridden from the parent, so the
 * glyph lives here.
 */
export function SourceDocIcon({ className }: { className?: string }) {
  return (
    <svg
      width="15"
      height="17"
      viewBox="0 0 14 16"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path
        d="M8.5 1.6V5h3.3"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Filled information mark on the conclusion note. */
export function NoteInfoIcon({ className }: { className?: string }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <circle cx="8" cy="8" r="7.2" fill="#2E8047" />
      <path d="M8 7.2v4" stroke="#FFFFFF" strokeWidth={1.5} strokeLinecap="round" />
      <circle cx="8" cy="4.9" r=".95" fill="#FFFFFF" />
    </svg>
  );
}
