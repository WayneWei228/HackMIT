"use client";

import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";

import { Button } from "@/components/ui/primitives";
import { startObligation } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApiAction } from "@/lib/use-api-action";

/**
 * Starts one Pending case: the agents run it from Ingestion to its resting
 * state, then the screen refreshes with what they did. `goTo` sends the reader
 * to a screen afterwards, so a case started from a stage screen opens at the
 * top of the chain. `compact` is the size that fits inside a table row.
 */
export function StartCaseButton({
  obligationId,
  goTo,
  compact = false,
}: {
  obligationId: string;
  goTo?: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const { run, pending, error } = useApiAction();

  async function start(event: MouseEvent<HTMLButtonElement>) {
    /* Inside a row link: start the case without also opening it. */
    event.preventDefault();
    event.stopPropagation();
    const started = await run(() => startObligation(obligationId));
    if (started && goTo) router.push(goTo);
  }

  return (
    <div className={cn("flex flex-col", compact ? "items-end" : "items-center gap-2")}>
      <Button
        variant="primary"
        disabled={pending}
        onClick={start}
        title={error ?? undefined}
        className={cn(
          compact ? "px-3 py-[7px] text-meta" : "text-[13.5px]/[1]",
          pending && "cursor-wait opacity-70",
        )}
      >
        {pending ? "Starting..." : error ? "Retry" : "Start"}
      </Button>
      {error && !compact && (
        <div className="max-w-[360px] text-center text-meta text-[#A4452F]">{error}</div>
      )}
    </div>
  );
}
