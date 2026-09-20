"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { Button } from "@/components/ui/primitives";
import { riseIn } from "@/lib/motion";
import {
  ALL_PERIODS,
  infoLabel,
  periodLabel,
  stateLabel,
  type PeriodInfo,
} from "@/lib/period";
import { progressLines, type RunControls } from "@/lib/use-run-controls";

import { agentSteps, chainStarted } from "./agent-steps";
import { AgentStepper } from "./agent-stepper";

/** Compact secondary button: the comp's control, one notch shorter. */
const ACTION =
  "px-3 py-[9px] text-[13.5px]/[1] disabled:cursor-default disabled:opacity-45";

/** How the backend's word for the job in flight reads in the strip. */
function runningLabel(action: string | null | undefined): string {
  switch (action) {
    case "close":
      return "Running close";
    case "settle":
      return "Running settlement";
    case "run-all":
    case "run_all":
      return "Running every month";
    case "run":
    case "run-month":
      return "Running all 7 agents";
    case "reset":
      return "Resetting";
    default:
      return "Working";
  }
}

/**
 * The month's state, and what can be done about it.
 *
 * Nothing in this product is pre-dumped: a month holds no cases until it has
 * been run, so the screen has to carry the run. The strip sits between the
 * page title and the filter row - the one place with room for the live log
 * without crowding the header's "Create case".
 *
 * Every button is disabled while a job is in flight, because the backend runs
 * one at a time. A refusal (400 with the month that must close first, 409 for
 * a second job) arrives as `controls.message` and is shown here rather than
 * thrown away.
 */
export function RunStrip({
  period,
  info,
  canClose,
  canSettle,
  controls,
}: {
  /** The selected month, `ALL_PERIODS`, or `null` before one is resolved. */
  period: string | null;
  /** What `GET /api/periods` says about it, when it says anything. */
  info: PeriodInfo | null;
  canClose: boolean;
  canSettle: boolean;
  controls: RunControls;
}) {
  const reduceMotion = useReducedMotion();
  const { busy, status, message, clearMessage, start } = controls;

  /* The chain, however the backend chose to describe it. Only shown once an
     agent has actually spoken: seven grey steps under a reset would be
     claiming a chain that is not running. */
  const steps = agentSteps(status);
  const showChain = busy && chainStarted(steps);

  const lines = progressLines(status);
  const logRef = useRef<HTMLDivElement>(null);
  /* Keep the newest line in view: the log is a tail, not a document. */
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  /* The month a per-month run would target - `null` under "All months". */
  const target = period !== null && period !== ALL_PERIODS ? period : null;
  const label = info ? infoLabel(info) : periodLabel(period);
  const state = info?.state ? stateLabel(info.state) : null;
  const instant = reduceMotion ? { duration: 0 } : undefined;

  return (
    <div className="mt-[18px] flex flex-col gap-2.5 rounded-xl border border-line bg-panel px-3.5 py-3 shadow-[var(--shadow-hairline)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-ui text-ink-2">{label}</span>
          {busy ? (
            <span className="text-meta text-faint">
              {runningLabel(status?.action)}
            </span>
          ) : state ? (
            <span className="text-meta text-faint">{state}</span>
          ) : null}
        </div>

        <div className="flex flex-none flex-wrap items-center gap-2">
          {target !== null && canClose ? (
            <Button
              className={ACTION}
              disabled={busy}
              onClick={() => start({ kind: "close", period: target })}
            >
              Run close
            </Button>
          ) : null}
          {target !== null && canSettle ? (
            <Button
              className={ACTION}
              disabled={busy}
              onClick={() => start({ kind: "settle", period: target })}
            >
              Run settlement
            </Button>
          ) : null}
          {target !== null && (canClose || canSettle) ? (
            <Button
              className={ACTION}
              disabled={busy}
              title="Close and settle this month in one go"
              onClick={() => start({ kind: "run-month", period: target })}
            >
              Run all 7 agents
            </Button>
          ) : null}
          <Button
            className={ACTION}
            disabled={busy}
            onClick={() => start({ kind: "run-all" })}
          >
            Run all months
          </Button>
          <Button
            className={ACTION}
            disabled={busy}
            title="Clear every run and start from the output files again"
            onClick={() => start({ kind: "reset" })}
          >
            Reset
          </Button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {showChain ? (
          <motion.div
            key="stepper"
            variants={riseIn}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={instant}
          >
            <AgentStepper steps={steps} />
          </motion.div>
        ) : null}

        {busy && lines.length > 0 ? (
          <motion.div
            key="log"
            variants={riseIn}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={instant}
            ref={logRef}
            className="max-h-[104px] overflow-y-auto rounded-lg border border-line bg-rail px-3 py-2.5"
          >
            {lines.map((line, index) => (
              <div
                key={`${index}-${line}`}
                className="text-meta leading-[1.55] text-faint"
              >
                {line}
              </div>
            ))}
          </motion.div>
        ) : null}

        {message ? (
          <motion.div
            key="message"
            variants={riseIn}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={instant}
            className="flex items-start justify-between gap-3 rounded-lg border border-line bg-wash-cool px-3 py-2.5"
          >
            <span className="text-meta leading-[1.55] text-muted-3">
              {message}
            </span>
            <button
              type="button"
              onClick={clearMessage}
              className="flex-none cursor-pointer text-meta text-faint-2 transition-colors duration-[140ms] ease-[var(--ease-out-soft)] hover:text-ink-2 focus-visible:outline-none focus-visible:text-ink-2"
            >
              Dismiss
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
