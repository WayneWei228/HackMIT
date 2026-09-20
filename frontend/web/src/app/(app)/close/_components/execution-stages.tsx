"use client";

import Link from "next/link";

import { cn } from "@/lib/cn";
import { chainStages, routes, withCase } from "@/lib/routes";

import { useIngestionData } from "./data-context";
import { StepChecklist } from "./step-checklist";
import type { TaskState } from "./use-close-run";

/**
 * The seven agents of a close, top to bottom.
 *
 * Only Evidence is running here; Detection flips from "Waiting" to "Queued"
 * and warms its rule the moment intake finishes, which is also the point at
 * which the row becomes a sensible thing to click.
 */
export function ExecutionStages({
  complete,
  taskStates,
}: {
  complete: boolean;
  taskStates: TaskState[];
}) {
  const { caseParam } = useIngestionData();
  /* `/close` is stage 01, the Evidence agent's intake view. The rest of the
     chain is navigation, so it comes from the route table. */
  const stages = chainStages("evidence", caseParam);
  const [, second, ...rest] = stages;

  return (
    <div className="mt-[26px]">
      <StageRow
        index={stages[0]?.number ?? "01"}
        label={stages[0]?.name ?? ""}
        bar="bg-accent"
        status={complete ? "Complete" : "Active"}
        statusClassName={cn(
          "font-medium",
          complete ? "text-faint-2" : "text-accent",
        )}
      />

      <StepChecklist states={taskStates} />

      <Link
        href={second?.href ?? withCase(routes.cases, caseParam)}
        className="-mx-2 mt-[22px] flex items-center gap-3.5 rounded-lg px-2 py-1.5 text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB] hover:text-ink"
      >
        <StageRowBody
          index={second?.number ?? "02"}
          label={second?.name ?? ""}
          bar={cn(
            "transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
            complete ? "bg-accent-line" : "bg-line-cool",
          )}
          status={complete ? "Queued" : "Waiting"}
          statusClassName={complete ? "text-ink-2" : "text-faint-3"}
        />
      </Link>

      {rest.map((stage) => (
        <StageRow
          key={stage.number}
          index={stage.number}
          label={stage.name}
          bar="bg-line-cool"
          status="Waiting"
          statusClassName="text-faint-3"
          className="mt-[22px]"
        />
      ))}
    </div>
  );
}

type StageProps = {
  index: string;
  label: string;
  bar: string;
  status: string;
  statusClassName: string;
};

function StageRowBody({
  index,
  label,
  bar,
  status,
  statusClassName,
}: StageProps) {
  return (
    <>
      <div className="w-[18px] flex-none text-meta text-faint-3 tabular-nums">
        {index}
      </div>
      <div className={cn("h-5 w-[2px] flex-none", bar)} />
      <div className="flex-1 font-display text-lg text-ink-deep">{label}</div>
      {/* Plain concatenation rather than `cn`: tailwind-merge reads
          `text-meta` and `text-accent` as the same `text-*` group and would
          drop the 12.5px size on its way through. */}
      <div
        className={`text-meta transition-colors duration-[300ms] ease-[var(--ease-out-soft)] ${statusClassName}`}
      >
        {status}
      </div>
    </>
  );
}

function StageRow({ className, ...stage }: StageProps & { className?: string }) {
  return (
    <div className={cn("flex items-center gap-3.5", className)}>
      <StageRowBody {...stage} />
    </div>
  );
}
