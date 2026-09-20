"use client";

import { TrailPanel } from "@/components/close/case-trail-panel";
import { Awaiting } from "@/components/close/awaiting";
import { EscalationBanner } from "@/components/close/escalation-banner";
import { StageRevealProvider, useRevealDone } from "@/lib/stage-reveal";
import { ReceivedStrip, StageChecks } from "@/components/close/stage-checks";

import { AgentBar } from "./agent-bar";
import { CaseHeader } from "./case-header";
import { EstimateBuildPanel } from "./estimate-build-panel";
import { ExecutionRail } from "./execution-rail";
import { ExecutionRailMini } from "./execution-rail-mini";
import { InputsPanel } from "./inputs-panel";
import { RecommendationPanel } from "./recommendation-panel";
import { useEstimationScreen } from "./screen-context";
import { useEstimationRun, useRailResize } from "../_use-estimation-run";

/**
 * Estimation agent: the fourth step of the close chain. It takes the
 * obligation the previous agent proved, applies period coverage and policy,
 * and hands a single accrual amount to Verification. The screen renders only
 * once the backend has run the agent, and every figure on it is the workpaper's.
 */
export function EstimationScreen() {
  const { steps, stageChecks } = useEstimationScreen();
  /* The rungs resolve one at a time, then the checks; the accrual they add up to comes last. */
  return (
    <StageRevealProvider
      stage="estimation"
      total={steps.length + (stageChecks?.length ?? 0) + 1}
      stepMs={520}
    >
      <EstimationBody />
    </StageRevealProvider>
  );
}

function EstimationBody() {
  const run = useEstimationRun();
  const rail = useRailResize();
  const { steps, received, stageChecks, escalation, header } = useEstimationScreen();
  const done = useRevealDone();

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
        <CaseHeader />
        <AgentBar />
        <TrailPanel />

        {escalation && (
          <div className="flex-none pt-3">
            <EscalationBanner escalation={escalation} />
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pb-[26px]">
          {received && (
            <div className="mb-3.5">
              <ReceivedStrip received={received} />
            </div>
          )}
          <div className="grid min-h-full grid-cols-[minmax(0,0.82fr)_minmax(0,1.3fr)_minmax(0,0.92fr)] items-start gap-3.5">
            <InputsPanel />
            <EstimateBuildPanel />
            {done ? <RecommendationPanel /> : <Awaiting title="Recommended accrual" />}
          </div>
          {stageChecks && (
            <section className="mt-3.5 rounded-xl border border-divider bg-panel px-[22px] pt-5 pb-[22px] shadow-tile">
              <h2 className="font-display text-2xl text-ink-deep">Checks the agent ran</h2>
              <div className="mt-4">
                <StageChecks checks={stageChecks} scope="estimation" offset={steps.length} />
              </div>
            </section>
          )}
        </div>
      </main>

      {rail.open ? (
        <ExecutionRail header={header} clock={run.clock} rail={rail} />
      ) : (
        <ExecutionRailMini onExpand={rail.toggle} />
      )}
    </>
  );
}
