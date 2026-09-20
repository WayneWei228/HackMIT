"use client";

import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";

import { Button } from "@/components/ui/primitives";
import type { FrontStage } from "@/lib/api-types";
import { caseData } from "@/lib/case-data";
import { useCaseRun } from "@/lib/case-runner";
import { cn } from "@/lib/cn";

/**
 * Opens a case on the screen of its next stage. Nothing runs from here: the screen
 * draws its full layout at once and its agent starts working inside it. The case is
 * read into the browser first, for at most a moment, so that layout is real from the
 * first frame. `compact` is the size that fits inside a table row.
 */
export function StartCaseButton({
  obligationId,
  goTo,
  compact = false,
  label = "Start",
}: {
  obligationId: string;
  completed?: readonly FrontStage[];
  agent?: string | null;
  goTo: string;
  compact?: boolean;
  label?: string;
}) {
  const router = useRouter();
  const run = useCaseRun(obligationId);
  const busy = run.active || run.queued;

  function open(event: MouseEvent<HTMLButtonElement>) {
    /* Inside a row link: open the case without also following the row. */
    event.preventDefault();
    event.stopPropagation();
    void caseData.prefetch(obligationId).then(() => router.push(goTo));
  }

  return (
    <div className={cn("flex flex-col", compact ? "items-end" : "items-center gap-2")}>
      <Button
        variant="primary"
        disabled={busy}
        onClick={open}
        title={run.error ?? undefined}
        className={cn(
          compact ? "px-3 py-[7px] text-meta" : "text-[13.5px]/[1]",
          busy && "cursor-wait opacity-70",
        )}
      >
        {run.queued ? "Queued" : run.active ? "Running..." : run.error ? "Retry" : label}
      </Button>
      {run.error && !compact && (
        <div className="max-w-[360px] text-center text-meta text-[#A4452F]">{run.error}</div>
      )}
    </div>
  );
}
