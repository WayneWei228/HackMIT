"use client";

import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";

import { Button } from "@/components/ui/primitives";
import type { FrontStage } from "@/lib/api-types";
import { useCaseRun, useCaseRunner } from "@/lib/case-runner";
import { cn } from "@/lib/cn";

/**
 * Starts a case, or continues one that stopped part way. The agents run one
 * stage per backend call, and the screen shows each stage only once its call has
 * returned. `goTo` sends the reader to a screen straight away, so a case started
 * from a stage screen opens at the top of the chain. `compact` is the size that
 * fits inside a table row.
 */
export function StartCaseButton({
  obligationId,
  completed,
  agent = null,
  goTo,
  compact = false,
  label = "Start",
}: {
  obligationId: string;
  completed: readonly FrontStage[];
  agent?: string | null;
  goTo?: string;
  compact?: boolean;
  label?: string;
}) {
  const router = useRouter();
  const runner = useCaseRunner();
  const run = useCaseRun(obligationId);
  const busy = run.active || run.queued;

  function start(event: MouseEvent<HTMLButtonElement>) {
    /* Inside a row link: start the case without also opening it. */
    event.preventDefault();
    event.stopPropagation();
    runner.start([{ obligationId, completed, agent }]);
    if (goTo) router.push(goTo);
  }

  return (
    <div className={cn("flex flex-col", compact ? "items-end" : "items-center gap-2")}>
      <Button
        variant="primary"
        disabled={busy}
        onClick={start}
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
