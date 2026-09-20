"use client";

import { Button } from "@/components/ui/primitives";
import { advanceToJanuary, resetDemo, runClose } from "@/lib/api";
import type { CloseView } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { useApiAction } from "@/lib/use-api-action";

const ADVANCE_HINT = "Start at least one case first";

/**
 * Drives the simulated calendar: start the Pending cases (each one by hand, or
 * all at once), then let January's invoices arrive. Reset rebuilds the demo
 * company from day one, with every case Pending again.
 */
export function CloseControls({ close }: { close: Pick<CloseView, "phase" | "actions"> }) {
  const { run, pending, error } = useApiAction();
  const { actions, phase } = close;

  return (
    <div className="flex flex-none flex-col items-end gap-2">
      <div className="flex items-center gap-2.5">
        <Button
          className="text-[13.5px]/[1]"
          disabled={pending}
          onClick={() => run(resetDemo)}
        >
          Reset demo
        </Button>
        {actions.can_run_close && (
          <Button
            variant="primary"
            className="text-[13.5px]/[1]"
            disabled={pending}
            onClick={() => run(runClose)}
          >
            {pending ? "Working..." : "Start all"}
          </Button>
        )}
        {phase !== "JANUARY" && (
          <Button
            variant="primary"
            className={cn(
              "text-[13.5px]/[1]",
              !actions.can_advance_to_january &&
                "cursor-not-allowed opacity-45 hover:bg-panel hover:text-accent",
            )}
            disabled={pending || !actions.can_advance_to_january}
            title={actions.can_advance_to_january ? undefined : ADVANCE_HINT}
            onClick={() => run(advanceToJanuary)}
          >
            {pending && actions.can_advance_to_january ? "Advancing..." : "Advance to January"}
          </Button>
        )}
        {phase === "JANUARY" && (
          <span className="text-ui text-faint">January invoices are in</span>
        )}
      </div>
      {phase === "DAY_ONE" && (
        <div className="text-meta text-faint">{ADVANCE_HINT} to move on to January.</div>
      )}
      {error && <div className="max-w-[360px] text-right text-meta text-[#A4452F]">{error}</div>}
    </div>
  );
}
