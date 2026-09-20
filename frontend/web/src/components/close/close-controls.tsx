"use client";

import { Button } from "@/components/ui/primitives";
import { resetDemo } from "@/lib/api";
import type { CaseRow } from "@/lib/api-types";
import { useCaseRunner, useRunner } from "@/lib/case-runner";
import { useCaseStoreActions } from "@/lib/case-store";
import { useApiAction } from "@/lib/use-api-action";

/**
 * Start the Pending cases (each one by hand, or all at once, one stage at a
 * time). Time itself moves from the sidebar clock. Reset rebuilds the demo
 * company from day one, with every case Pending again.
 */
export function CloseControls({ close }: { close: { cases: CaseRow[] } }) {
  const { run, pending, error } = useApiAction();
  const runner = useCaseRunner();
  const { runs } = useRunner();
  const store = useCaseStoreActions();
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
      </div>
      {error && <div className="max-w-[360px] text-right text-meta text-[#A4452F]">{error}</div>}
    </div>
  );
}
