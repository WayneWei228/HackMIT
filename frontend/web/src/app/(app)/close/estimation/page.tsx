"use client";

import { AgentBar } from "./_components/agent-bar";
import { CaseHeader } from "./_components/case-header";
import { EstimateBuildPanel } from "./_components/estimate-build-panel";
import { ExecutionRail } from "./_components/execution-rail";
import { ExecutionRailMini } from "./_components/execution-rail-mini";
import { InputsPanel } from "./_components/inputs-panel";
import { RecommendationPanel } from "./_components/recommendation-panel";
import { useEstimationRun, useRailResize } from "./_use-estimation-run";

/**
 * Estimation agent: the fourth step of the close chain. It takes the
 * obligation the previous agent proved, applies period coverage and policy,
 * and hands a single accrual amount to Verification.
 *
 * Auto-advance is off in this port, so the handoff button does the navigating.
 */
const AUTO_ADVANCE = false;

export default function EstimationPage() {
  const run = useEstimationRun({ autoAdvance: AUTO_ADVANCE });
  const rail = useRailResize();

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
        <CaseHeader pulsing={!run.complete} />
        <AgentBar
          step={run.step}
          complete={run.complete}
          onReplay={run.replay}
        />

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pb-[26px]">
          <div className="grid min-h-full grid-cols-[minmax(232px,0.82fr)_minmax(330px,1.3fr)_minmax(262px,0.92fr)] items-start gap-3.5">
            <InputsPanel step={run.step} />
            <EstimateBuildPanel step={run.step} runId={run.runId} />
            <RecommendationPanel step={run.step} complete={run.complete} />
          </div>
        </div>
      </main>

      {rail.open ? (
        <ExecutionRail
          step={run.step}
          complete={run.complete}
          clock={run.clock}
          rail={rail}
          autoAdvance={AUTO_ADVANCE}
        />
      ) : (
        <ExecutionRailMini onExpand={rail.toggle} />
      )}
    </>
  );
}
