"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { CaretLeftIcon, CaretRightIcon, PageIcon } from "@/components/ui/icons";
import { easeOutSoft, riseIn, staggerParent, transitions } from "@/lib/motion";
import { routes } from "@/lib/routes";
import { CHAIN_STEPS, type TaskView } from "../_data";
import { LiveDot, TaskMark } from "./marks";

const SETTLE = { duration: 0.45, ease: easeOutSoft };

/** The 56px rail the panel collapses into. */
function MiniRail({ onExpand }: { onExpand: () => void }) {
  return (
    <motion.aside
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.base}
      className="flex w-14 flex-none flex-col items-center gap-[18px] border-l border-line bg-panel-hover py-[22px]"
    >
      <button
        type="button"
        onClick={onExpand}
        title="Expand live execution"
        className="flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-deep"
      >
        <CaretLeftIcon size={13} />
      </button>
      <span className="h-[9px] w-[9px] flex-none rounded-full bg-accent shadow-[var(--shadow-ring)]" />
      <div className="rotate-180 text-eyebrow font-medium tracking-[0.14em] whitespace-nowrap text-faint [writing-mode:vertical-rl]">
        LIVE EXECUTION
      </div>
      <div className="font-display rotate-180 text-md whitespace-nowrap text-ink-deep [writing-mode:vertical-rl]">
        Verification
      </div>
    </motion.aside>
  );
}

function ChainLink({
  index,
  label,
  href,
  first,
}: {
  index: string;
  label: string;
  href: string;
  first: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "-mx-2 flex items-center gap-[14px] rounded-lg px-2 py-1.5 text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]",
        !first && "mt-5",
      )}
    >
      <div className="w-[18px] flex-none text-meta text-faint-3 tabular-nums">
        {index}
      </div>
      <div className="h-5 w-0.5 flex-none bg-accent-line" />
      <div className="font-display flex-1 text-lg text-ink-deep">{label}</div>
      <div className="text-meta text-faint-2">Complete</div>
    </Link>
  );
}

export function ExecutionRail({
  width,
  dragging,
  onStartResize,
  onCollapse,
  railStatus,
  stageStatus,
  complete,
  clock,
  tasks,
  pulse,
}: {
  width: number;
  dragging: boolean;
  onStartResize: (event: React.MouseEvent<HTMLElement>) => void;
  onCollapse: () => void;
  railStatus: string;
  stageStatus: string;
  complete: boolean;
  clock: string;
  tasks: readonly TaskView[];
  pulse: boolean;
}) {
  return (
    <motion.aside
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.base}
      className="relative flex-none border-l border-line bg-paper"
      style={{ inlineSize: width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize live execution panel"
        onMouseDown={onStartResize}
        title="Drag to resize"
        className={cn(
          "absolute top-0 -left-1 bottom-0 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:bg-[rgba(46,128,71,0.16)]",
          dragging &&
            "bg-[rgba(46,128,71,0.22)] hover:bg-[rgba(46,128,71,0.22)]",
        )}
      />

      <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
        <div className="flex items-center justify-between gap-2.5">
          <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
            LIVE EXECUTION
          </div>
          <button
            type="button"
            onClick={onCollapse}
            title="Collapse panel"
            className="-mr-[5px] flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
          >
            <CaretRightIcon size={13} />
          </button>
        </div>

        <div className="mt-[14px] flex items-center justify-between">
          <div className="flex items-center gap-[11px]">
            <LiveDot pulse={pulse} />
            <span className="text-lead text-ink">{railStatus}</span>
          </div>
          <div className="text-sm text-faint tabular-nums">{clock}</div>
        </div>

        <div className="mt-[26px]">
          {CHAIN_STEPS.map((step, i) => (
            <ChainLink
              key={step.index}
              index={step.index}
              label={step.label}
              href={step.href}
              first={i === 0}
            />
          ))}

          <div className="mt-5 flex items-center gap-[14px]">
            <div className="w-[18px] flex-none text-meta text-faint-3 tabular-nums">
              05
            </div>
            <div className="h-5 w-0.5 flex-none bg-accent" />
            <div className="font-display flex-1 text-lg text-ink-deep">
              Verification
            </div>
            <motion.div
              initial={false}
              animate={{ color: complete ? "#8E938A" : "#2E8047" }}
              transition={{ duration: 0.3, ease: easeOutSoft }}
              className="text-meta font-medium"
            >
              {stageStatus}
            </motion.div>
          </div>

          <motion.div
            variants={staggerParent(0.04)}
            initial="hidden"
            animate="visible"
            className="mt-[14px] ml-[33px] flex flex-col gap-[13px] border-l border-line pl-5"
          >
            {tasks.map((task) => (
              <motion.div
                key={task.label}
                variants={riseIn}
                className="flex items-center gap-3"
              >
                <TaskMark state={task.state} />
                <motion.span
                  initial={false}
                  animate={{
                    color: task.state === "pending" ? "#9AA096" : "#33362F",
                  }}
                  transition={{ duration: 0.26, ease: easeOutSoft }}
                  className="text-sm"
                >
                  {task.label}
                </motion.span>
              </motion.div>
            ))}
          </motion.div>
        </div>

        <div className="mt-8 h-px bg-sunk" />

        <div className="mt-[22px] text-eyebrow font-medium tracking-caps-lg text-faint">
          NEXT HANDOFF
        </div>
        <div className="mt-[13px] flex items-start gap-3">
          <PageIcon size={15} className="mt-0.5 flex-none text-faint-3" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 text-body text-ink">
              <span>Verification</span>
              <span className="text-ghost-2" aria-hidden="true">
                →
              </span>
              <span>Close</span>
            </div>
            <div className="mt-[7px] text-meta leading-[1.6] text-pretty text-faint">
              Mark case as close-ready and prepare journal entry.
            </div>
          </div>
        </div>

        <motion.div
          initial={false}
          animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 8 }}
          transition={SETTLE}
          className={cn("mt-4", !complete && "pointer-events-none")}
        >
          <Link
            href={routes.closeCase}
            className="block w-full rounded-xl border border-accent bg-accent px-[14px] py-[11px] text-center text-ui font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
          >
            Return to case list
          </Link>
        </motion.div>
      </div>
    </motion.aside>
  );
}

export { MiniRail };
