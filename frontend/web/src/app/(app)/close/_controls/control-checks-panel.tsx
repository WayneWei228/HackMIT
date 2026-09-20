"use client";

import { AnimatePresence, motion } from "motion/react";

import { cn } from "@/lib/cn";
import { MoreIcon } from "@/components/ui/icons";
import { easeOutSoft } from "@/lib/motion";
import type { ControlView, ScanView } from "./types";
import { ControlMark, ScanMark } from "./marks";

const TINT = { duration: 0.28, ease: easeOutSoft };
const FADE = { duration: 0.3, ease: easeOutSoft };
/** The comp rotates the chevron over .28s. */
const CHEVRON = { duration: 0.28, ease: easeOutSoft };
/** Accordion bodies open over .34s - .38s on the taller exception-scan row. */
const BODY = { duration: 0.34, ease: easeOutSoft };
const BODY_TALL = { duration: 0.38, ease: easeOutSoft };

function ScanRow({ scan }: { scan: ScanView }) {
  return (
    <div className="flex items-center gap-[11px]">
      <ScanMark state={scan.state} />
      <motion.span
        initial={false}
        animate={{ color: scan.state === "pending" ? "#9AA096" : "#33362F" }}
        transition={{ duration: 0.26, ease: easeOutSoft }}
        className="flex-1 text-sm"
      >
        {scan.label}
      </motion.span>
      <motion.span
        initial={false}
        animate={{ opacity: scan.state === "done" ? 1 : 0 }}
        transition={FADE}
        className="text-meta text-faint-2"
      >
        Clear
      </motion.span>
    </div>
  );
}

function ExceptionScanBody({ scans }: { scans: readonly ScanView[] }) {
  return (
    <div className="flex flex-col gap-[11px] rounded-lg bg-rail-alt px-[14px] py-3">
      {scans.map((scan) => (
        <ScanRow key={scan.label} scan={scan} />
      ))}
    </div>
  );
}

function ControlRow({
  control,
  last,
  open,
  onToggle,
  scans,
}: {
  control: ControlView;
  last: boolean;
  open: boolean;
  onToggle: () => void;
  scans: readonly ScanView[];
}) {
  const lit = control.state !== "pending";
  const isScan = control.body === null;

  return (
    <div className={cn("relative pl-10", last ? "pb-0" : "pb-5")}>
      {!last && (
        <motion.div
          aria-hidden="true"
          initial={false}
          animate={{ backgroundColor: control.lineDone ? "#BFD4C3" : "#E7E7E2" }}
          transition={{ duration: 0.5, ease: easeOutSoft }}
          className="absolute top-[22px] bottom-0 left-2 w-px"
        />
      )}
      <ControlMark state={control.state} />

      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-start gap-[14px] text-left"
      >
        <span className="mt-px text-sm text-faint-3 tabular-nums">
          {control.index}
        </span>
        <span className="min-w-0 flex-1">
          <motion.span
            initial={false}
            animate={{ color: lit ? "#1D1F1B" : "#9AA096" }}
            transition={TINT}
            className="block text-nav"
          >
            {control.title}
          </motion.span>
          <span className="mt-1 block text-sm leading-[1.6] text-pretty text-faint">
            {control.subtitle}
          </span>
        </span>
        <motion.span
          initial={false}
          animate={{
            opacity: control.tagVisible ? 1 : 0,
            color: control.state === "done" ? "#2E8047" : "#9AA096",
          }}
          transition={FADE}
          className="mt-px flex-none text-sm"
        >
          {control.tag}
        </motion.span>
        <motion.svg
          width="13"
          height="13"
          viewBox="0 0 12 12"
          fill="none"
          aria-hidden="true"
          initial={false}
          animate={{ rotate: open ? 180 : 0 }}
          transition={CHEVRON}
          className="mt-1 flex-none"
        >
          <path
            d="M3 4.6L6 7.6l3-3"
            stroke="#9AA096"
            strokeWidth={1.3}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </motion.svg>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{
              height: isScan ? BODY_TALL : BODY,
              opacity: { duration: 0.26, ease: easeOutSoft },
            }}
            className="overflow-hidden"
          >
            <div
              className={cn(
                "pt-[9px] pl-[27px]",
                isScan ? "pr-1" : "pr-[26px]",
              )}
            >
              {isScan ? (
                <ExceptionScanBody scans={scans} />
              ) : (
                <p className="m-0 text-sm leading-[1.7] text-pretty text-muted-4">
                  {control.body}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ControlChecksPanel({
  controls,
  scans,
  controlCount,
  openControl,
  onToggle,
}: {
  controls: readonly ControlView[];
  scans: readonly ScanView[];
  controlCount: string;
  openControl: number;
  onToggle: (index: number) => void;
}) {
  return (
    <section className="min-h-full rounded-xl border border-divider bg-panel px-[22px] pt-5 pb-[22px] shadow-[var(--shadow-tile)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-display text-2xl text-ink-deep">
            Control checks
          </div>
          <div className="mt-1.5 text-sm leading-[1.6] text-faint">
            Running automated and rule-based checks.
          </div>
        </div>
        <div className="flex flex-none items-center gap-2">
          <span className="text-ui text-ink-2 tabular-nums">{controlCount}</span>
          <button
            type="button"
            aria-label="Control check options"
            className="-mr-1 flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent text-faint-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
          >
            <MoreIcon className="text-body" />
          </button>
        </div>
      </div>

      <div className="mt-5">
        {controls.map((control, i) => (
          <ControlRow
            key={control.index}
            control={control}
            last={i === controls.length - 1}
            open={openControl === i}
            onToggle={() => onToggle(i)}
            scans={scans}
          />
        ))}
      </div>
    </section>
  );
}
