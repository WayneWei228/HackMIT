"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import {
  HANDOFF,
  RAIL_STAGES_BEFORE,
  RAIL_TASKS,
  railTaskStates,
  type RailStage,
} from "../_data";
import { timing } from "../_motion";
import type { RailResize } from "../_use-estimation-run";
import { InputDocIcon, RailCollapseIcon } from "./icons";
import { LiveDot, TaskMarker } from "./markers";

const stageRow = "flex items-center gap-3.5";
const stageLink =
  "-mx-2 rounded-lg px-2 py-1.5 text-inherit transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]";

/**
 * The expanded live-execution rail: where this agent sits in the close chain,
 * what it is ticking off, and where it hands the case next.
 */
export function ExecutionRail({
  step,
  complete,
  clock,
  rail,
  autoAdvance,
}: {
  step: number;
  complete: boolean;
  clock: string;
  rail: RailResize;
  autoAdvance: boolean;
}) {
  const tasks = railTaskStates(step);

  return (
    <aside
      className="relative flex-none border-l border-line bg-paper"
      style={{ inlineSize: rail.width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        onMouseDown={rail.onResizeStart}
        title="Drag to resize"
        className={cn(
          "absolute top-0 -left-1 bottom-0 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)]",
          rail.dragging
            ? "bg-[rgba(46,128,71,0.22)]"
            : "hover:bg-[rgba(46,128,71,0.16)]",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <div className="text-eyebrow leading-[normal] font-medium tracking-caps-lg text-faint">
            LIVE EXECUTION
          </div>
          <button
            type="button"
            onClick={rail.toggle}
            title="Collapse panel"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <RailCollapseIcon />
          </button>
        </div>

        <div className="mt-3.5 flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <LiveDot pulsing={!complete} halo />
            <span className="text-lead leading-[normal] text-ink">Running</span>
          </div>
          <div className="text-sm leading-[normal] text-faint tabular-nums">{clock}</div>
        </div>

        <div className="mt-[26px]">
          {RAIL_STAGES_BEFORE.map((stage, i) => (
            <CompletedStage key={stage.n} stage={stage} first={i === 0} />
          ))}

          <div className={cn(stageRow, "mt-5")}>
            <StageNumber>04</StageNumber>
            <span className="h-5 w-0.5 flex-none bg-accent" />
            <StageLabel>Estimation</StageLabel>
            <div
              className={`text-meta leading-[normal] font-medium transition-colors duration-300 ease-[var(--ease-out-soft)] ${
                complete ? "text-faint-2" : "text-accent"
              }`}
            >
              {complete ? "Complete" : "Active"}
            </div>
          </div>

          <div className="mt-3.5 ml-[33px] flex flex-col gap-[13px] border-l border-line pl-5">
            {RAIL_TASKS.map((task, i) => (
              <div key={task} className="flex items-center gap-3">
                <TaskMarker state={tasks[i]} />
                <span
                  className={cn(
                    "text-sm leading-[normal] transition-colors duration-[260ms] ease-[var(--ease-out-soft)]",
                    tasks[i] === "pending" ? "text-faint-3" : "text-ink-2",
                  )}
                >
                  {task}
                </span>
              </div>
            ))}
          </div>

          <Link
            href={HANDOFF.href}
            className={cn(stageRow, stageLink, "mt-[22px]")}
          >
            <StageNumber>05</StageNumber>
            <span
              className={cn(
                "h-5 w-0.5 flex-none transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
                complete ? "bg-accent-line" : "bg-line-cool",
              )}
            />
            <StageLabel>Verification</StageLabel>
            <div
              className={`text-meta leading-[normal] transition-colors duration-300 ease-[var(--ease-out-soft)] ${
                complete ? "text-ink-2" : "text-faint-3"
              }`}
            >
              {complete ? "Queued" : "Waiting"}
            </div>
          </Link>
        </div>

        <div className="mt-8 h-px bg-sunk" />
        <div className="mt-[22px] text-eyebrow leading-[normal] font-medium tracking-caps-lg text-faint">
          NEXT HANDOFF
        </div>
        <div className="mt-[13px] flex items-start gap-3">
          <InputDocIcon className="mt-0.5 flex-none text-faint-3" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 text-body leading-[normal] text-ink">
              <span>{HANDOFF.from}</span>
              <span aria-hidden="true" className="text-ghost-2">
                →
              </span>
              <span>{HANDOFF.to}</span>
            </div>
            <div className="mt-[7px] text-meta leading-[1.6] text-pretty text-faint">
              {HANDOFF.blurb}
            </div>
          </div>
        </div>

        <motion.div
          animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 8 }}
          transition={timing.settle}
          className={cn("mt-4", !complete && "pointer-events-none")}
        >
          <Link
            href={HANDOFF.href}
            tabIndex={complete ? undefined : -1}
            aria-hidden={complete ? undefined : true}
            className="relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-3.5 py-[11px] text-center text-ui leading-[normal] font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
          >
            <span className="relative z-[2]">
              {complete && autoAdvance
                ? "Opening Verification..."
                : "Hand off to Verification"}
            </span>
            <motion.span
              animate={{ width: complete && autoAdvance ? "100%" : "0%" }}
              transition={{ duration: 1.2, ease: "linear" }}
              className="absolute top-0 bottom-0 left-0 bg-white/[0.22]"
            />
          </Link>
        </motion.div>
      </div>
    </aside>
  );
}

function CompletedStage({ stage, first }: { stage: RailStage; first: boolean }) {
  return (
    <Link
      href={stage.href ?? "#"}
      className={cn(stageRow, stageLink, first ? "mt-0" : "mt-5")}
    >
      <StageNumber>{stage.n}</StageNumber>
      <span className="h-5 w-0.5 flex-none bg-accent-line" />
      <StageLabel>{stage.label}</StageLabel>
      <div className="text-meta leading-[normal] text-faint-2">{stage.status}</div>
    </Link>
  );
}

function StageNumber({ children }: { children: string }) {
  return (
    <div className="w-[18px] flex-none text-meta leading-[normal] text-faint-3 tabular-nums">
      {children}
    </div>
  );
}

function StageLabel({ children }: { children: string }) {
  return (
    <div className="font-display flex-1 text-lg leading-[normal] text-ink-deep">
      {children}
    </div>
  );
}
