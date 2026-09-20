"use client";

import { AgentStatusBar } from "./_components/agent-status-bar";
import { AnalysisPanel } from "./_components/analysis-panel";
import { CaseHeader } from "./_components/case-header";
import { ConclusionPanel } from "./_components/conclusion-panel";
import { FactsPanel } from "./_components/facts-panel";
import { LiveExecutionRail } from "./_components/live-execution-rail";
import { useObligationRun } from "./_components/use-obligation-run";

/**
 * Obligation agent - stage 03 of the close run.
 *
 * The screen is three working columns: the facts the agent was handed, the
 * accounting checks it is applying to them, and the conclusion it is willing
 * to pass on. The rail on the right narrates the run itself.
 *
 * All data is synthetic and every upstream system is simulated.
 */
export default function ObligationPage() {
  const run = useObligationRun();

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden leading-[normal]">
        <CaseHeader pulsing={!run.complete} />

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar
          step={run.step}
          complete={run.complete}
          onReplay={run.replay}
        />

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pb-[26px]">
          <div className="grid min-h-full grid-cols-[minmax(232px,0.82fr)_minmax(320px,1.28fr)_minmax(258px,0.9fr)] items-start gap-3.5">
            <FactsPanel step={run.step} />
            <AnalysisPanel
              step={run.step}
              openIndex={run.openIndex}
              onToggle={run.toggleCheck}
            />
            <ConclusionPanel step={run.step} complete={run.complete} />
          </div>
        </div>
      </main>

      <LiveExecutionRail
        step={run.step}
        complete={run.complete}
        clock={run.clock}
        open={run.railOpen}
        mini={run.railMini}
        width={run.railWidth}
        dragging={run.dragging}
        autoAdvance={run.autoAdvance}
        onToggle={run.toggleRail}
        onResizeStart={run.startResize}
      />
    </>
  );
}
