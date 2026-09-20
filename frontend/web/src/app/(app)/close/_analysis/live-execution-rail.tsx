"use client";

import type { MouseEvent } from "react";
import Link from "next/link";
import { motion } from "motion/react";

import { CaretLeftIcon, CaretRightIcon } from "@/components/ui/icons";
import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { easeOutSoft, railIn } from "@/lib/motion";
import { AutoRunToggle } from "@/components/ui/auto-run-toggle";
import { chainStages, nextAgent, type ChainStage } from "@/lib/routes";
import { useAnalysisData } from "./data-context";
import { taskStates } from "./types";
import { PulseDot, SourceDocIcon, TaskMarker } from "./glyphs";

export type RailProps = {
  step: number;
  complete: boolean;
  clock: string;
  open: boolean;
  mini: boolean;
  width: number;
  dragging: boolean;
  autoAdvance: boolean;
  onToggle: () => void;
  onResizeStart: (event: MouseEvent) => void;
};

/**
 * The run's own view of itself: which stage of the close is executing, which
 * sub-task the agent is on, and where the result goes next. Collapses to a
 * 56px spine and can be dragged wider.
 */
export function LiveExecutionRail(props: RailProps) {
  /* The two rails swap outright, as they do in the comp: each one settles in
     on mount. Wrapping the swap in AnimatePresence would hold the outgoing
     rail on screen, and a re-render landing during that exit - the clock
     ticks every second - can strand it there, half faded, forever. */
  if (props.mini) return <MiniRail onToggle={props.onToggle} />;
  if (props.open) return <FullRail {...props} />;
  return null;
}

function MiniRail({ onToggle }: { onToggle: () => void }) {
  const { agentLabel } = useAnalysisData();

  return (
    <motion.aside
      variants={railIn}
      initial="hidden"
      animate="visible"
      className="flex w-14 flex-none flex-col items-center gap-[18px] border-l border-line bg-panel-hover py-[22px] leading-[normal]"
    >
      <button
        type="button"
        onClick={onToggle}
        title="Expand live execution"
        aria-label="Expand live execution"
        className="flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-deep"
      >
        <CaretLeftIcon size={13} />
      </button>
      <span className="h-[9px] w-[9px] flex-none rounded-full bg-accent shadow-ring" />
      <div className="rotate-180 text-eyebrow font-medium tracking-[0.14em] whitespace-nowrap text-faint [writing-mode:vertical-rl]">
        LIVE EXECUTION
      </div>
      <div className="font-display rotate-180 text-md whitespace-nowrap text-ink-deep [writing-mode:vertical-rl]">
        {agentLabel}
      </div>
    </motion.aside>
  );
}

function FullRail({
  step,
  complete,
  clock,
  width,
  dragging,
  autoAdvance,
  onToggle,
  onResizeStart,
}: RailProps) {
  const { data, agentId, agentLabel, caseParam } = useAnalysisData();
  const { railTasks, handoffBlurb } = data;
  const tasks = taskStates(step, railTasks.length);
  /* The chain is navigation, so it is derived from the route table rather
     than served per case. What each agent found is what comes from the API. */
  const stages = chainStages(agentId, caseParam);
  const next = nextAgent(agentId);
  const handoffHref =
    stages.find((stage) => stage.state === "next")?.href ?? null;

  return (
    <motion.aside
      variants={railIn}
      initial="hidden"
      animate="visible"
      style={{ inlineSize: width }}
      className="relative flex-none border-l border-line bg-paper leading-[normal]"
    >
      <div
        role="separator"
        aria-orientation="vertical"
        title="Drag to resize"
        onMouseDown={onResizeStart}
        className={cn(
          "absolute top-0 -left-1 bottom-0 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:bg-[rgba(46,128,71,0.16)]",
          dragging && "bg-[rgba(46,128,71,0.22)]",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <SectionLabel className="text-[10.5px] text-faint">
            LIVE EXECUTION
          </SectionLabel>
          <button
            type="button"
            onClick={onToggle}
            title="Collapse panel"
            aria-label="Collapse live execution"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent bg-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <CaretRightIcon size={13} />
          </button>
        </div>

        <div className="mt-3.5 flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <PulseDot halo pulsing={!complete} />
            <span className="text-lead text-ink">Running</span>
          </div>
          <div className="text-sm leading-[normal] text-faint tabular-nums">{clock}</div>
        </div>

        <AutoRunToggle className="-mx-2 mt-2.5 w-[calc(100%+16px)]" />

        <div className="mt-[26px]">
          {stages.map((stage, i) => (
            <div key={`${stage.number}-${stage.name}`}>
              <StageRow stage={stage} complete={complete} first={i === 0} />
              {stage.state === "current" && (
                <div className="mt-3.5 ml-[33px] flex flex-col gap-[13px] border-l border-line pl-5">
                  {railTasks.map((task, index) => (
                    <div key={task.label} className="flex items-center gap-3">
                      <TaskMarker state={tasks[index]} />
                      <span
                        className={cn(
                          "text-sm transition-colors duration-[260ms] ease-[var(--ease-out-soft)]",
                          task.multiline ? "leading-[1.45]" : "leading-[normal]",
                          tasks[index] === "rest" ? "text-faint-3" : "text-ink-2",
                        )}
                      >
                        {task.label}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mt-8 h-px bg-sunk" />
        <SectionLabel className="mt-[22px] text-[10.5px] text-faint">
          NEXT HANDOFF
        </SectionLabel>
        <div className="mt-[13px] flex items-start gap-3">
          <SourceDocIcon className="mt-0.5 flex-none text-faint-3" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 text-body text-ink">
              <span>{agentLabel}</span>
              <span aria-hidden="true" className="text-ghost-2">
                →
              </span>
              <span>{next ? next.label : "Close"}</span>
            </div>
            {handoffBlurb ? (
              <p className="mt-[7px] text-meta leading-[1.6] text-pretty text-faint">
                {handoffBlurb}
              </p>
            ) : null}
          </div>
        </div>

        <motion.div
          initial={false}
          animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 8 }}
          transition={{ duration: 0.45, ease: easeOutSoft }}
          className={cn("mt-4", !complete && "pointer-events-none")}
        >
          <Link
            href={handoffHref ?? "#"}
            className="relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-3.5 py-[11px] text-center text-ui font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
          >
            <span className="relative z-[2]">
              {next
                ? complete && autoAdvance
                  ? `Opening ${next.label}...`
                  : `Hand off to ${next.label}`
                : "Back to all cases"}
            </span>
            <motion.span
              aria-hidden="true"
              initial={false}
              animate={{ width: complete && autoAdvance ? "100%" : "0%" }}
              transition={{ duration: 1.2, ease: "linear" }}
              className="absolute top-0 bottom-0 left-0 bg-[rgba(255,255,255,0.22)]"
            />
          </Link>
        </motion.div>
      </div>
    </motion.aside>
  );
}

function StageRow({
  stage,
  complete,
  first,
}: {
  stage: ChainStage;
  complete: boolean;
  first: boolean;
}) {
  const label = stageStatusLabel(stage, complete);
  const body = (
    <>
      <div className="w-[18px] flex-none text-meta text-faint-3 tabular-nums">
        {stage.number}
      </div>
      <div
        className={cn(
          "h-5 w-0.5 flex-none transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
          stageBar(stage, complete),
        )}
      />
      <div className="font-display flex-1 text-lg leading-[normal] text-ink-deep">
        {stage.name}
      </div>
      <div
        className={`text-meta transition-colors duration-[300ms] ease-[var(--ease-out-soft)] ${
          stage.state === "current" ? "font-medium" : ""
        } ${stageStatusColor(stage, complete)}`}
      >
        {label}
      </div>
    </>
  );

  const spacing = first ? "" : stage.state === "complete" || stage.state === "current" ? "mt-5" : "mt-[22px]";

  return stage.href ? (
    <Link
      href={stage.href}
      className={cn(
        "-mx-2 flex items-center gap-3.5 rounded-lg px-2 py-1.5 text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]",
        spacing,
      )}
    >
      {body}
    </Link>
  ) : (
    <div className={cn("flex items-center gap-3.5", spacing)}>{body}</div>
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
