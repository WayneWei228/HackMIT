"use client";

import { Button } from "@/components/ui/primitives";
import { advanceToJanuary, resetDemo } from "@/lib/api";
import type { CaseRow, CloseView } from "@/lib/api-types";
import { useCaseRunner, useRunner } from "@/lib/case-runner";
import { useCaseStoreActions } from "@/lib/case-store";
import { cn } from "@/lib/cn";
import { useApiAction } from "@/lib/use-api-action";

const ADVANCE_HINT = "Start at least one case first";

/**
 * Drives the simulated calendar: start the Pending cases (each one by hand, or
 * all at once, one stage at a time), then let January's invoices arrive. Reset
 * rebuilds the demo company from day one, with every case Pending again.
 */
export function CloseControls({
  close,
}: {
  close: Pick<CloseView, "phase" | "actions"> & { cases: CaseRow[] };
}) {
  const { run, pending, error } = useApiAction();
  const runner = useCaseRunner();
  const { runs } = useRunner();
  const store = useCaseStoreActions();
  const { actions, phase } = close;
  const running = Object.values(runs).some((state) => state.active || state.queued);
  /* Every case with an agent still due: the Pending ones, and any already part-way through. */
  const startable = close.cases.filter(
    (row) => row.current_agent != null && (row.status !== "Pending" || row.can_start),
  );

  function startAll() {
    runner.start(
      startable.map((row) => ({
        obligationId: row.obligation_id,
        completed: row.stages_completed ?? [],
        agent: row.current_agent ?? null,
      })),
    );
  }

  return (
    <div className="flex flex-none flex-col items-end gap-2">
      <div className="flex items-center gap-2.5">
        <Button
          className="text-[13.5px]/[1]"
          disabled={pending}
          onClick={() =>
            run(async () => {
              runner.cancelAll();
              store.clearAll();
              await resetDemo();
            })
          }
        >
          Reset demo
        </Button>
        {startable.length > 0 && (
          <Button
            variant="primary"
            className="text-[13.5px]/[1]"
            disabled={pending || running}
            onClick={startAll}
          >
            {running ? "Running..." : "Start all"}
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
            disabled={pending || running || !actions.can_advance_to_january}
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
