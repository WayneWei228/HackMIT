"use client";

import Link from "next/link";

import { cn } from "@/lib/cn";
import { caseHref } from "@/lib/case-nav";
import { routes } from "@/lib/routes";

import { RunSteps } from "@/components/close/run-steps";
import type { Header } from "@/lib/api-types";
import { useStageStatuses, type StageStatus } from "@/lib/stage-status";

import { STAGES } from "@/lib/trail";

const STATUS_TEXT: Record<StageStatus, string> = {
  Complete: "text-faint-2",
  Running: "font-medium text-accent",
  Queued: "text-ink-2",
  Waiting: "text-faint-3",
};

/**
 * The five stages of a close, top to bottom, each with the status the backend
 * and the runner report for it. Ingestion's own steps are the entries its agent
 * wrote to the run log.
 */
export function ExecutionStages({
  header,
  obligationId,
}: {
  header: Header;
  obligationId: string;
}) {
  const status = useStageStatuses(header);
  const later = STAGES.slice(2);

  return (
    <div className="mt-[26px]">
      <StageRow
        index="01"
        label="Ingestion"
        bar={status.ingestion === "Complete" ? "bg-accent" : "bg-line-cool"}
        status={status.ingestion}
        statusClassName={STATUS_TEXT[status.ingestion]}
      />

      <RunSteps screen="ingestion" />

      <Link
        href={caseHref(routes.evidence, obligationId)}
        className="-mx-2 mt-[22px] flex items-center gap-3.5 rounded-lg px-2 py-1.5 text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB] hover:text-ink"
      >
        <StageRowBody
          index="02"
          label="Evidence"
          bar={cn(
            "transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
            status.evidence === "Waiting" ? "bg-line-cool" : "bg-accent-line",
          )}
          status={status.evidence}
          statusClassName={STATUS_TEXT[status.evidence]}
        />
      </Link>

      {later.map((stage, i) => (
        <StageRow
          key={stage.key}
          index={String(i + 3).padStart(2, "0")}
          label={stage.label}
          bar="bg-line-cool"
          status={status[stage.key]}
          statusClassName={STATUS_TEXT[status[stage.key]]}
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
