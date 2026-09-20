"use client";

import { Button } from "@/components/ui/primitives";
import { advanceToJanuary, resetDemo, runClose } from "@/lib/api";
import type { CloseView } from "@/lib/api-types";
import { useApiAction } from "@/lib/use-api-action";

/**
 * Drives the simulated calendar: run the December close, then let January's
 * invoices arrive. Reset rebuilds the demo company from day one.
 */
export function CloseControls({ close }: { close: Pick<CloseView, "phase" | "actions"> }) {
  const { run, pending, error } = useApiAction();
  const { actions, phase } = close;

  return (
    <div className="flex flex-none flex-col items-end gap-2">
      <div className="flex items-center gap-2.5">
        {phase !== "DAY_ONE" && (
          <Button
            className="text-[13.5px]/[1]"
            disabled={pending}
            onClick={() => run(resetDemo)}
          >
            Reset demo
          </Button>
        )}
        {actions.can_run_close && (
          <Button
            variant="primary"
            className="text-[13.5px]/[1]"
            disabled={pending}
            onClick={() => run(runClose)}
          >
            {pending ? "Running the close..." : "Run December close"}
          </Button>
        )}
        {actions.can_advance_to_january && (
          <Button
            variant="primary"
            className="text-[13.5px]/[1]"
            disabled={pending}
            onClick={() => run(advanceToJanuary)}
          >
            {pending ? "Advancing..." : "Advance to January"}
          </Button>
        )}
        {phase === "JANUARY" && (
          <span className="text-ui text-faint">January invoices are in</span>
        )}
      </div>
      {error && <div className="max-w-[360px] text-right text-meta text-[#A4452F]">{error}</div>}
    </div>
  );
}
