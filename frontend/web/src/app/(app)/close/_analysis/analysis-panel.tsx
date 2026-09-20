"use client";

import { motion } from "motion/react";

import { ChevronDownIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { easeOutSoft, transitions } from "@/lib/motion";
import { useAnalysisData } from "./data-context";
import {
  type AnalysisCheck,
  type MarkerState,
  checkBody,
  checkStates,
  subCheckStates,
} from "./types";
import { CheckMarker, SubCheckMarker } from "./glyphs";
import { Panel, PanelHeading } from "./panel";

/**
 * Middle column: the four accounting checks, ticking over as the agent
 * works. The active one opens itself until the user takes over.
 */
export function AnalysisPanel({
  step,
  openIndex,
  onToggle,
}: {
  step: number;
  openIndex: number;
  onToggle: (index: number) => void;
}) {
  const { data, agentLabel } = useAnalysisData();
  const { analysisChecks, analysisIntro } = data;
  const states = checkStates(step, analysisChecks.length);

  return (
    <Panel className="px-[22px] pt-5 pb-[22px]">
      <PanelHeading>{agentLabel} analysis</PanelHeading>
      <p className="mt-1.5 text-sm leading-[1.6] text-pretty text-faint">
        {analysisIntro}
      </p>

      <div className="mt-5">
        {analysisChecks.map((check, i) => (
          <CheckRow
            key={check.label}
            check={check}
            index={i}
            step={step}
            state={states[i]}
            open={openIndex === i}
            last={i === analysisChecks.length - 1}
            onToggle={onToggle}
          />
        ))}
      </div>
    </Panel>
  );
}

function CheckRow({
  check,
  index,
  step,
  state,
  open,
  last,
  onToggle,
}: {
  check: AnalysisCheck;
  index: number;
  step: number;
  state: MarkerState;
  open: boolean;
  last: boolean;
  onToggle: (index: number) => void;
}) {
  const subChecks = check.subChecks ?? [];
  const subStates = subCheckStates(step, subChecks.length);

  return (
    <div className={cn("relative pl-10", last ? "pb-0" : "pb-[22px]")}>
      {!last && (
        <div
          className={cn(
            "absolute top-[22px] bottom-0 left-2 w-px transition-colors duration-500 ease-[var(--ease-out-soft)]",
            state === "done" ? "bg-accent-line" : "bg-line",
          )}
        />
      )}
      <CheckMarker state={state} />

      <button
        type="button"
        onClick={() => onToggle(index)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-3.5 text-left"
      >
        <span className="text-sm leading-[normal] text-faint-3 tabular-nums">
          {index + 1}
        </span>
        <span
          className={`flex-1 text-nav transition-colors duration-[280ms] ease-[var(--ease-out-soft)] ${
            state === "rest" ? "text-faint-3" : "text-ink"
          }`}
        >
          {check.label}
        </span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={transitions.base}
          className="flex flex-none text-faint-3"
        >
          <ChevronDownIcon size={13} />
        </motion.span>
      </button>

      <motion.div
        initial={false}
        animate={{
          gridTemplateRows: open ? "1fr" : "0fr",
          opacity: open ? 1 : 0,
        }}
        transition={{
          gridTemplateRows: { duration: check.bodyDuration, ease: easeOutSoft },
          opacity: { duration: 0.26, ease: easeOutSoft },
        }}
        className="grid overflow-hidden"
      >
        <div className="min-h-0">
          <div
            className={cn(
              "pt-[7px] pl-[27px]",
              check.subChecks ? "pr-1" : "pr-[26px]",
            )}
          >
            <p className="text-sm leading-[1.65] text-pretty text-muted-4">
              {checkBody(check, step)}
            </p>
            {subChecks.length > 0 && (
              <div className="mt-3 flex flex-col gap-[11px] rounded-lg bg-rail-alt px-3.5 py-3">
                {subChecks.map((label, i) => (
                  <div key={label} className="flex items-center gap-[11px]">
                    <SubCheckMarker state={subStates[i]} />
                    <span
                      className={cn(
                        "text-sm leading-[normal] transition-colors duration-[260ms] ease-[var(--ease-out-soft)]",
                        subStates[i] === "rest" ? "text-faint-3" : "text-ink-2",
                      )}
                    >
                      {label}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {check.pending && (
        <motion.div
          initial={false}
          animate={{ opacity: step >= check.pending.until ? 0 : 1 }}
          transition={{ duration: 0.26, ease: easeOutSoft }}
          className="pt-[7px] pr-[26px] pl-[27px] text-sm leading-[normal] text-faint-3"
        >
          {check.pending.label}
        </motion.div>
      )}
    </div>
  );
}
