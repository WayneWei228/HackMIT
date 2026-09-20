"use client";

import Link from "next/link";

import { RunSteps } from "@/components/close/run-steps";
import type { Header } from "@/lib/api-types";
import { useCaseHref } from "@/lib/case-context";
import type { StageKey } from "@/lib/case-store";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { useStageStatuses, type StageStatus } from "@/lib/stage-status";
import { STAGES } from "@/lib/trail";

const ROUTE: Record<StageKey, string> = {
  ingestion: routes.closeCase,
  evidence: routes.evidence,
  obligation: routes.obligation,
  estimation: routes.estimation,
  verification: routes.verification,
};

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

/**
 * The five stages of a close with the status the backend and the runner report
 * for each. The current stage lists the steps its agents really recorded; none
 * of it is a fixed table.
 */
export function RailStages({ header, current }: { header: Header; current: StageKey }) {
  const caseHref = useCaseHref();
  const status = useStageStatuses(header);

  return (
    <div className="mt-[26px]">
      {STAGES.map((stage, index) => {
        const value = status[stage.key];
        const linked = value === "Complete" || stage.key === current;
        const body = (
          <>
            <div className="w-[18px] flex-none text-meta text-faint-3 tabular-nums">
              {String(index + 1).padStart(2, "0")}
            </div>
            <div
              className={cn(
                "h-5 w-0.5 flex-none transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
                BAR[value],
              )}
            />
            <div className="font-display flex-1 text-lg leading-[normal] text-ink-deep">
              {stage.label}
            </div>
            <div className={`text-meta transition-colors duration-[300ms] ${STATUS_TEXT[value]}`}>
              {value}
            </div>
          </>
        );
        return (
          <div key={stage.key}>
            {linked ? (
              <Link
                href={caseHref(ROUTE[stage.key])}
                className={cn(
                  "-mx-2 flex items-center gap-3.5 rounded-lg px-2 py-1.5 text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]",
                  index > 0 && "mt-5",
                )}
              >
                {body}
              </Link>
            ) : (
              <div className={cn("flex items-center gap-3.5", index > 0 && "mt-[22px]")}>{body}</div>
            )}
            {stage.key === current && <RunSteps screen={stage.key} />}
          </div>
        );
      })}
    </div>
  );
}
