"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";

import { activeStep, type AgentStep, type AgentStepState } from "./agent-steps";

/** The rail's bar colours, laid on their side. */
function barClass(state: AgentStepState): string {
  switch (state) {
    case "done":
      return "bg-accent-line";
    case "running":
      return "bg-accent";
    default:
      return "bg-line-cool";
  }
}

function labelClass(state: AgentStepState): string {
  switch (state) {
    case "done":
      return "text-faint-2";
    case "running":
      return "font-medium text-ink";
    default:
      return "text-faint-3";
  }
}

function statusWord(state: AgentStepState): string {
  switch (state) {
    case "done":
      return "Complete";
    case "running":
      return "Active";
    default:
      return "Waiting";
  }
}

/**
 * The close chain while it runs: seven agents, lighting up in order.
 *
 * This is the live-execution rail from the close screens turned on its side -
 * same grammar, same colours (`accent` for the agent working, `accent-line`
 * behind it, `line-cool` ahead of it), but laid out across the run strip
 * rather than down a 300px panel, because the strip is the only place on this
 * screen with room and the reader wants the whole chain at a glance.
 *
 * The newest line of the run sits under the active agent. Everything is
 * derived - see `agent-steps.ts` - so a status payload missing `progress`,
 * missing `agents`, or naming a worker we have never heard of draws seven
 * waiting steps instead of throwing.
 */
export function AgentStepper({ steps }: { steps: readonly AgentStep[] }) {
  const reduceMotion = useReducedMotion();
  const active = activeStep(steps);
  /* The active agent's line, or - once the last one has finished - the last
     thing the chain said before it stopped. */
  const line =
    (active >= 0 ? steps[active].message : null) ??
    [...steps].reverse().find((step) => step.message)?.message ??
    null;

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-line bg-rail px-3 py-2.5">
      <ol
        aria-label="Close agents"
        className="flex items-stretch gap-2 overflow-hidden"
      >
        {steps.map((step, index) => (
          <li
            key={step.id}
            aria-current={step.state === "running" ? "step" : undefined}
            className="flex min-w-0 flex-1 flex-col gap-[7px]"
          >
            <motion.div
              aria-hidden="true"
              initial={false}
              animate={{
                opacity:
                  step.state === "running" && !reduceMotion ? [1, 0.45, 1] : 1,
              }}
              transition={
                step.state === "running" && !reduceMotion
                  ? { duration: 1.6, repeat: Infinity, ease: "easeInOut" }
                  : { duration: 0 }
              }
              className={cn(
                "h-0.5 w-full rounded-full transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
                barClass(step.state),
              )}
            />
            <div className="flex min-w-0 items-baseline gap-1.5">
              <span className="flex-none text-meta text-faint-3 tabular-nums">
                {index + 1}
              </span>
              <span
                title={`${step.label} - ${statusWord(step.state)}`}
                className={cn(
                  "truncate text-meta whitespace-nowrap transition-colors duration-[300ms] ease-[var(--ease-out-soft)]",
                  labelClass(step.state),
                )}
              >
                {step.label}
              </span>
              <span className="sr-only">{statusWord(step.state)}</span>
            </div>
          </li>
        ))}
      </ol>

      {line ? (
        <div
          title={line}
          className="truncate text-meta leading-[1.55] text-faint"
        >
          {line}
        </div>
      ) : null}
    </div>
  );
}
