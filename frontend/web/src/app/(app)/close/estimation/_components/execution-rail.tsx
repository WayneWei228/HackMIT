"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { motion } from "motion/react";

import { AutoRunToggle } from "@/components/ui/auto-run-toggle";
import { cn } from "@/lib/cn";
import { chainStages, nextAgent, type ChainStage } from "@/lib/routes";
import { railTaskStates } from "../_data";
import { timing } from "../_motion";
import type { RailResize } from "../_use-estimation-run";
import { InputDocIcon, RailCollapseIcon } from "./icons";
import { LiveDot, TaskMarker } from "./markers";
import { useEstimationData } from "./data-context";

const stageRow = "flex items-center gap-3.5";
const stageLink =
  "-mx-2 rounded-lg px-2 py-1.5 text-inherit transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]";

/**
 * The expanded live-execution rail: where this agent sits in the close chain,
 * what it is ticking off, and where it hands the case next.
 *
 * The chain is navigation, so it is derived from the route table rather than
 * served per case: `chainStages` knows which agents exist, in what order, and
 * which one this screen is. What the agent *found* is the payload's, and the
 * sub-tasks under the current stage are the only case-shaped thing here -
 * they name what this run actually did ("Apply invoiced, not accrued").
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
  const { data, caseParam } = useEstimationData();
  const { RAIL_TASKS, HANDOFF_BLURB } = data;
  const tasks = railTaskStates(step, RAIL_TASKS.length);
  const stages = chainStages("estimation", caseParam);
  const next = nextAgent("estimation");
  const handoffHref = stages.find((s) => s.state === "next")?.href ?? null;

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

        {/* Under the clock, in the rail's own header: the switch belongs with
            the run it plays. The negative margin lets its hover state bleed
            into the rail's padding while its label stays on the column. */}
        <AutoRunToggle className="-mx-2 mt-2.5 w-[calc(100%+16px)]" />

        <div className="mt-[22px]">
          {stages.map((stage, i) => (
            <div key={`${stage.number}-${stage.name}`}>
              <StageRow stage={stage} complete={complete} first={i === 0} />

              {stage.state === "current" ? (
                <div className="mt-3.5 ml-[33px] flex flex-col gap-[13px] border-l border-line pl-5">
                  {RAIL_TASKS.map((task, index) => (
                    <div key={`${task}-${index}`} className="flex items-center gap-3">
                      <TaskMarker state={tasks[index]} />
                      <span
                        className={cn(
                          "text-sm leading-[normal] transition-colors duration-[260ms] ease-[var(--ease-out-soft)]",
                          tasks[index] === "pending" ? "text-faint-3" : "text-ink-2",
                        )}
                      >
                        {task}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>

        <div className="mt-8 h-px bg-sunk" />
        <div className="mt-[22px] text-eyebrow leading-[normal] font-medium tracking-caps-lg text-faint">
          NEXT HANDOFF
        </div>
        <div className="mt-[13px] flex items-start gap-3">
          <InputDocIcon className="mt-0.5 flex-none text-faint-3" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 text-body leading-[normal] text-ink">
              <span>Estimation</span>
              <span aria-hidden="true" className="text-ghost-2">
                →
              </span>
              <span>{next ? next.label : "Close"}</span>
            </div>
            {/* What this run actually leaves the next agent. The API writes
                it per case; a run with nothing to say sends no key. */}
            {HANDOFF_BLURB ? (
              <div className="mt-[7px] text-meta leading-[1.6] text-pretty text-faint">
                {HANDOFF_BLURB}
              </div>
            ) : null}
          </div>
        </div>

        <motion.div
          animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 8 }}
          transition={timing.settle}
          className={cn("mt-4", !complete && "pointer-events-none")}
        >
          <HandoffButton href={handoffHref} enabled={complete}>
            <span className="relative z-[2]">
              {next
                ? complete && autoAdvance
                  ? `Opening ${next.label}...`
                  : `Hand off to ${next.label}`
                : "Back to all cases"}
            </span>
            <motion.span
              animate={{ width: complete && autoAdvance ? "100%" : "0%" }}
              transition={{ duration: 1.2, ease: "linear" }}
              className="absolute top-0 bottom-0 left-0 bg-white/[0.22]"
            />
          </HandoffButton>
        </motion.div>
      </div>
    </aside>
  );
}

/**
 * One row of the chain. The screen you are already on is not a link - that is
 * what `chainStages` leaves `href` null for - and neither is a row whose
 * target this app does not have.
 */
function StageRow({
  stage,
  complete,
  first,
}: {
  stage: ChainStage;
  complete: boolean;
  first: boolean;
}) {
  const body = (
    <>
      <div className="w-[18px] flex-none text-meta leading-[normal] text-faint-3 tabular-nums">
        {stage.number}
      </div>
      <span
        className={cn(
          "h-5 w-0.5 flex-none transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
          stageBar(stage, complete),
        )}
      />
      <div className="font-display flex-1 text-lg leading-[normal] text-ink-deep">
        {stage.name}
      </div>
      <div
        className={cn(
          "text-meta leading-[normal] transition-colors duration-300 ease-[var(--ease-out-soft)]",
          stage.state === "current" && "font-medium",
          stageStatusColor(stage, complete),
        )}
      >
        {stageStatusLabel(stage, complete)}
      </div>
    </>
  );

  const spacing = first
    ? "mt-0"
    : stage.state === "next"
      ? "mt-[22px]"
      : "mt-5";

  return stage.href ? (
    <Link href={stage.href} className={cn(stageRow, stageLink, spacing)}>
      {body}
    </Link>
  ) : (
    <div className={cn(stageRow, spacing)}>{body}</div>
  );
}

function stageStatusLabel(stage: ChainStage, complete: boolean): string {
  switch (stage.state) {
    case "complete":
      return "Complete";
    case "current":
      return complete ? "Complete" : "Active";
    case "next":
      return complete ? "Queued" : "Waiting";
    default:
      return "Waiting";
  }
}

function stageStatusColor(stage: ChainStage, complete: boolean): string {
  switch (stage.state) {
    case "complete":
      return "text-faint-2";
    case "current":
      return complete ? "text-faint-2" : "text-accent";
    case "next":
      return complete ? "text-ink-2" : "text-faint-3";
    default:
      return "text-faint-3";
  }
}

function stageBar(stage: ChainStage, complete: boolean): string {
  switch (stage.state) {
    case "complete":
      return "bg-accent-line";
    case "current":
      return "bg-accent";
    case "next":
      return complete ? "bg-accent-line" : "bg-line-cool";
    default:
      return "bg-line-cool";
  }
}

/** The handoff call to action, or a dead button when there is nowhere to go. */
function HandoffButton({
  href,
  enabled,
  children,
}: {
  href: string | null;
  enabled: boolean;
  children: ReactNode;
}) {
  const className =
    "relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-3.5 py-[11px] text-center text-ui leading-[normal] font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on";

  if (!href) return <div className={className}>{children}</div>;
  return (
    <Link
      href={href}
      tabIndex={enabled ? undefined : -1}
      aria-hidden={enabled ? undefined : true}
      className={className}
    >
      {children}
    </Link>
  );
}
