"use client";

import { TrailPanel } from "@/components/close/case-trail-panel";
import { Awaiting } from "@/components/close/awaiting";
import { EscalationBanner } from "@/components/close/escalation-banner";
import { StageRevealProvider, useRevealDone } from "@/lib/stage-reveal";
import { stageDone } from "@/lib/trail";

import { AgentStatusBar } from "./agent-status-bar";
import { AnalysisPanel } from "./analysis-panel";
import { CaseHeader } from "./case-header";
import { ConclusionPanel } from "./conclusion-panel";
import { FactsPanel } from "./facts-panel";
import { LiveExecutionRail } from "./live-execution-rail";
import { useObligationScreen } from "./screen-context";
import { useObligationRun } from "./use-obligation-run";

/**
 * Obligation agent - stage 03 of the close run.
 *
 * The screen is three working columns: the facts the agent was handed, the
 * checks it ran, and the conclusion it is willing to pass on. It renders only
 * once the backend has run the agents, and every value on it comes from their
 * output. The rail on the right lists the steps they recorded.
 *
 * All data is synthetic and every upstream system is simulated.
 */
export function ObligationScreen() {
  const { checks, header } = useObligationScreen();
  const pending = !stageDone(header, "obligation");
  const resting = pending && header.started && header.current_agent === null;
  /* The checks resolve one at a time; the conclusion they support comes last. */
  return (
    <StageRevealProvider stage="obligation" total={pending ? 0 : (checks?.length ?? 0) + 1} pending={pending} resting={resting}>
      <ObligationBody />
    </StageRevealProvider>
  );
}

function ObligationBody() {
  const run = useObligationRun();
  const { escalation, header } = useObligationScreen();
  const done = useRevealDone();

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden leading-[normal]">
        <CaseHeader />

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar />
        <TrailPanel />

        {escalation && (
          <div className="flex-none pt-3">
            <EscalationBanner escalation={escalation} />
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pb-[26px]">
          <div className="grid min-h-full grid-cols-[minmax(0,0.82fr)_minmax(0,1.28fr)_minmax(0,0.9fr)] items-start gap-3.5">
            <FactsPanel />
            <AnalysisPanel />
            {done ? <ConclusionPanel /> : <Awaiting title="Provisional conclusion" />}
          </div>
        </div>
      </main>

      <LiveExecutionRail
        header={header}
        clock={run.clock}
        open={run.railOpen}
        mini={run.railMini}
        width={run.railWidth}
        dragging={run.dragging}
        onToggle={run.toggleRail}
        onResizeStart={run.startResize}
      />
    </>
  );
}
