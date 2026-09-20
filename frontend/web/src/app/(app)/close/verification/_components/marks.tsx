"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";
import type { MarkState } from "../_data";

/* -------------------------------------------------------------------------- */
/* Primitives                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * One layer of a stacked status glyph. The comp draws pending, running and
 * done states on top of each other and cross-fades between them, which keeps
 * the mark from ever changing size as a check resolves.
 */
function Layer({
  show,
  className,
  children,
  duration = 0.26,
}: {
  show: boolean;
  className?: string;
  children?: React.ReactNode;
  duration?: number;
}) {
  return (
    <motion.span
      aria-hidden="true"
      initial={false}
      animate={{ opacity: show ? 1 : 0 }}
      transition={{ duration, ease: easeOutSoft }}
      className={cn("absolute inset-0 block", className)}
    >
      {children}
    </motion.span>
  );
}

/** The green arc that sweeps while a check is running. */
export function Spinner({
  size = 16,
  duration = 1.1,
  track = "#CFE0CF",
}: {
  size?: number;
  duration?: number;
  track?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 13 13"
      fill="none"
      aria-hidden="true"
      animate={reduced ? undefined : { rotate: 360 }}
      transition={
        reduced
          ? undefined
          : { duration, ease: "linear", repeat: Infinity }
      }
    >
      <circle cx="6.5" cy="6.5" r="5.5" stroke={track} strokeWidth={1.2} />
      <path
        d="M6.5 1a5.5 5.5 0 0 1 5.5 5.5"
        stroke="#2E8047"
        strokeWidth={1.6}
        strokeLinecap="round"
      />
    </motion.svg>
  );
}

/** The slow halo around a live status dot. Fades out when the run finishes. */
export function PulseRing({ show }: { show: boolean }) {
  const reduced = useReducedMotion();
  return (
    <motion.span
      aria-hidden="true"
      initial={false}
      animate={{ opacity: show ? 1 : 0 }}
      transition={{ duration: 0.3, ease: easeOutSoft }}
      className="pointer-events-none absolute -inset-1"
    >
      <motion.span
        className="block h-full w-full rounded-full border-[1.3px] border-[rgba(46,128,71,0.55)]"
        animate={
          reduced
            ? { scale: 1, opacity: 0 }
            : { scale: [0.72, 1.5, 1.5], opacity: [0.5, 0, 0] }
        }
        transition={
          reduced
            ? { duration: 0 }
            : {
                duration: 2.6,
                times: [0, 0.7, 1],
                ease: easeOutSoft,
                repeat: Infinity,
              }
        }
      />
    </motion.span>
  );
}

/** Live status dot - 9px, optional soft ring, optional halo. */
export function LiveDot({
  pulse,
  ring = true,
  className,
}: {
  pulse: boolean;
  ring?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative h-[9px] w-[9px] flex-none", className)}>
      <span
        className={cn(
          "absolute inset-0 rounded-full bg-accent",
          ring && "shadow-[var(--shadow-ring)]",
        )}
      />
      <PulseRing show={pulse} />
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen glyphs                                                               */
/* -------------------------------------------------------------------------- */

/** 16px rounded-square checkbox used by the assertion rows. */
export function AssertionMark({ state }: { state: MarkState }) {
  return (
    <span className="relative mt-0.5 h-4 w-4 flex-none">
      <Layer show={state === "pending"}>
        <span className="block h-full w-full rounded-[4px] border-[1.3px] border-rule" />
      </Layer>
      <Layer show={state === "active"}>
        <Spinner size={16} />
      </Layer>
      <Layer show={state === "done"} duration={0.3}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <rect x="0.5" y="0.5" width="15" height="15" rx="3.5" fill="#2E8047" />
          <path
            d="M4.4 8.2l2.3 2.3 4.7-5.2"
            stroke="#FFFFFF"
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </Layer>
    </span>
  );
}

/** 17px timeline node used by the control checks. */
export function ControlMark({
  state,
  tone = "ok",
}: {
  state: MarkState;
  tone?: "ok" | "warn";
}) {
  return (
    <span className="absolute top-px left-0 h-[17px] w-[17px]">
      <Layer show={state === "pending"} duration={0.28}>
        <span className="block h-full w-full rounded-full border-[1.4px] border-rule-soft" />
      </Layer>
      <Layer show={state === "active"} duration={0.28}>
        <span className="block h-full w-full rounded-full border-2 border-accent" />
      </Layer>
      <Layer show={state === "done"} duration={0.32}>
        {tone === "warn" ? (
          <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <circle cx="9" cy="9" r="8.4" fill="#D6A43C" />
            <path d="M9 5v5" stroke="#FFFFFF" strokeWidth={1.7} strokeLinecap="round" />
            <circle cx="9" cy="12.6" r="1" fill="#FFFFFF" />
          </svg>
        ) : (
          <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <circle cx="9" cy="9" r="8.4" fill="#2E8047" />
            <path
              d="M5.4 9.2l2.6 2.6 5-5.4"
              stroke="#FFFFFF"
              strokeWidth={1.6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </Layer>
    </span>
  );
}

/** 13px bare tick used inside the exception scan list. */
export function ScanMark({ state }: { state: MarkState }) {
  return (
    <span className="relative h-[13px] w-[13px] flex-none">
      <Layer show={state === "pending"}>
        <span className="block h-full w-full rounded-full border border-rule" />
      </Layer>
      <Layer show={state === "active"}>
        <Spinner size={13} />
      </Layer>
      <Layer show={state === "done"} duration={0.3}>
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
          <path
            d="M1.8 6.8l3.2 3.1 6.2-7"
            stroke="#2E8047"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </Layer>
    </span>
  );
}

/** 15px solid disc used by the "additional checks" list. */
export function DiscMark({ done }: { done: boolean }) {
  return (
    <span className="relative h-[15px] w-[15px] flex-none">
      <Layer show={!done}>
        <span className="block h-full w-full rounded-full border-[1.3px] border-rule" />
      </Layer>
      <Layer show={done} duration={0.3}>
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="7.3" fill="#2E8047" />
          <path
            d="M4.7 8.2l2.2 2.2 4.4-4.8"
            stroke="#FFFFFF"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </Layer>
    </span>
  );
}

/** 13px rail sub-task marker: hollow ring, filled dot, then a bare tick. */
export function TaskMark({ state }: { state: MarkState }) {
  return (
    <span className="relative mx-px h-[13px] w-[13px] flex-none">
      <Layer show={state === "pending"} className="inset-px">
        <span className="block h-full w-full rounded-full border border-rule" />
      </Layer>
      <motion.span
        aria-hidden="true"
        initial={false}
        animate={{
          opacity: state === "active" ? 1 : 0,
          scale: state === "active" ? 1 : 0.5,
        }}
        transition={{ duration: 0.26, ease: easeOutSoft }}
        className="absolute inset-px block rounded-full bg-accent"
      />
      <Layer show={state === "done"} duration={0.3}>
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
          <path
            d="M1.8 6.8l3.2 3.1 6.2-7"
            stroke="#2E8047"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </Layer>
    </span>
  );
}

/** 15px marker on the final status row - spinner until the run completes. */
export function FinalMark({ complete, tone }: { complete: boolean; tone?: string }) {
  return (
    <span className="relative h-[15px] w-[15px] flex-none">
      <Layer show={!complete && !tone} duration={0.3}>
        <Spinner size={15} duration={1.4} track="#DCDCD4" />
      </Layer>
      <Layer show={!complete && !!tone} duration={0.35}>
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="7.3" fill={tone ?? "#D6A43C"} />
          <path d="M8 4.4v4.2" stroke="#FFFFFF" strokeWidth={1.5} strokeLinecap="round" />
          <circle cx="8" cy="11.2" r=".9" fill="#FFFFFF" />
        </svg>
      </Layer>
      <Layer show={complete} duration={0.35}>
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="7.3" fill="#2E8047" />
          <path
            d="M4.7 8.2l2.2 2.2 4.4-4.8"
            stroke="#FFFFFF"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </Layer>
    </span>
  );
}
