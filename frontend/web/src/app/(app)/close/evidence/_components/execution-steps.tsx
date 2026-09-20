"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { RunSteps } from "@/components/close/run-steps";
import type { Header } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { useCaseHref } from "@/lib/case-context";
import { routes } from "@/lib/routes";
import { useStageStatuses, type StageStatus } from "@/lib/stage-status";

const ROW = "flex items-center gap-[14px]";
const LINK_ROW =
  "-mx-2 rounded-lg px-2 py-1.5 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]";

function Stage({
  index,
  label,
  status,
  barClassName,
  statusClassName,
  href,
  className,
}: {
  index: string;
  label: string;
  status: ReactNode;
  barClassName: string;
  statusClassName: string;
  href?: string;
  className?: string;
}) {
  const body = (
    <>
      <div className="w-[18px] flex-none text-meta text-faint-3 tabular-nums">
        {index}
      </div>
      <div className={cn("h-5 w-[2px] flex-none", barClassName)} />
      <div className="font-display flex-1 text-lg text-ink-deep">{label}</div>
      <div className={`text-meta ${statusClassName}`}>{status}</div>
    </>
  );

  if (href) {
    return (
      <Link href={href} className={cn(ROW, LINK_ROW, "text-ink", className)}>
        {body}
      </Link>
    );
  }

  return <div className={cn(ROW, className)}>{body}</div>;
}

const STATUS_TEXT: Record<StageStatus, string> = {
  Complete: "text-faint-2",
  Running: "font-medium text-accent",
  Queued: "text-ink-2",
  Waiting: "text-faint-3",
};

const BAR: Record<StageStatus, string> = {
  Complete: "bg-accent-line",
  Running: "bg-accent",
  Queued: "bg-accent-line",
  Waiting: "bg-line-cool",
};

/** The five close stages, with the steps the Evidence agent recorded nested under stage 02. */
export function ExecutionSteps({ header }: { header: Header }) {
  const caseHref = useCaseHref();
  const status = useStageStatuses(header);
  return (
    <div className="mt-[26px]">
      <Stage
        index="01"
        label="Ingestion"
        status={status.ingestion}
        barClassName={BAR[status.ingestion]}
        statusClassName={STATUS_TEXT[status.ingestion]}
        href={caseHref(routes.closeCase)}
      />

      <Stage
        index="02"
        label="Evidence"
        status={status.evidence}
        barClassName={BAR[status.evidence]}
        statusClassName={cn("transition-colors duration-300", STATUS_TEXT[status.evidence])}
        className="mt-5"
      />

      <RunSteps screen="evidence" className="mt-[14px]" />

      <Stage
        index="03"
        label="Obligation"
        status={status.obligation}
        barClassName={BAR[status.obligation]}
        statusClassName={STATUS_TEXT[status.obligation]}
        href={caseHref(routes.obligation)}
        className="mt-[22px]"
      />

      <Stage
        index="04"
        label="Estimation"
        status={status.estimation}
        barClassName={BAR[status.estimation]}
        statusClassName={STATUS_TEXT[status.estimation]}
        className="mt-[22px]"
      />

      <Stage
        index="05"
        label="Verification"
        status={status.verification}
        barClassName={BAR[status.verification]}
        statusClassName={STATUS_TEXT[status.verification]}
        className="mt-[22px]"
      />
    </div>
  );
}
