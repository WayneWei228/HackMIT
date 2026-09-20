"use client";

import { useMemo } from "react";

import { BackendUnreachable, ScreenState } from "@/components/ui/screen-state";
import { casePath, type CloseScreen } from "@/lib/api";
import { agentOf, routes } from "@/lib/routes";
import { useAutoRun } from "@/lib/use-auto-run";
import { useLiveData } from "@/lib/use-live-data";

import { AgentStatusBar } from "./agent-status-bar";
import { AnalysisPanel } from "./analysis-panel";
import { CaseHeader } from "./case-header";
import { ConclusionPanel } from "./conclusion-panel";
import { AnalysisDataProvider, useAnalysisData } from "./data-context";
import { FactsPanel } from "./facts-panel";
import { LiveExecutionRail } from "./live-execution-rail";
import { ScreenShell } from "./screen-shell";
import { analysisIsEmpty, analysisStatus, type AnalysisData } from "./types";
import { useAnalysisRun } from "./use-analysis-run";

export type AnalysisScreenProps = {
  /** Which endpoint this screen reads: `detection`, `invoice-lookup`, ... */
  screen: CloseScreen;
  /** The agent's id in `agentChain` - also what names it on screen. */
  agentId: string;
  caseParam: string | null;
};

/**
 * The analysis comp, shared by Detection, Invoice Lookup and Classification.
 *
 * Three working columns - the facts the agent was handed, the checks it is
 * applying to them, and the conclusion it is willing to pass on - with the
 * rail on the right narrating the run. Every figure and sentence in those
 * columns comes from the close API; which agent this is, and where its answer
 * goes next, comes from the route table. There is no dataset in between.
 */
export function AnalysisScreen({
  screen,
  agentId,
  caseParam,
}: AnalysisScreenProps) {
  const live = useLiveData<AnalysisData>(casePath(caseParam, screen), {
    isEmpty: analysisIsEmpty,
  });
  const agentLabel = agentOf(agentId)?.label ?? "";

  if (live.status === "error") {
    return (
      <ScreenShell>
        <BackendUnreachable
          url={live.url}
          error={live.error}
          onRetry={live.retry}
        />
      </ScreenShell>
    );
  }

  if (live.status === "loading") {
    return <ScreenShell loading />;
  }

  if (live.status === "empty" || !live.data) {
    return (
      <ScreenShell>
        <ScreenState
          title={
            !caseParam
              ? "No case selected"
              : live.httpStatus === 404
                ? "No such case"
                : `Nothing for the ${agentLabel} agent on this case`
          }
          body={
            !caseParam
              ? "Pick a case from the case list to see what this agent found."
              : live.httpStatus === 404
                ? "The close API does not know this case. It may belong to a month that has not been run."
                : "The close API has no result for this agent on this case. Run the month's close and come back."
          }
          detail={caseParam}
          actions={[{ label: "All cases", href: routes.cases }]}
        />
      </ScreenShell>
    );
  }

  return (
    <AnalysisDataProvider
      data={live.data}
      agentId={agentId}
      agentLabel={agentLabel}
      caseParam={caseParam}
    >
      <AnalysisBody />
    </AnalysisDataProvider>
  );
}

function AnalysisBody() {
  const { data, agentId, agentLabel, caseParam } = useAnalysisData();

  /* Narration is progress, read off the data on screen - the product holds
     no script of its own. */
  const lines = useMemo(
    () => analysisStatus(data, agentLabel),
    [data, agentLabel],
  );

  const { auto } = useAutoRun();
  const run = useAnalysisRun({
    agentId,
    caseParam,
    checkCount: data.analysisChecks.length,
    autoAdvance: auto,
  });

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden leading-[normal]">
        <CaseHeader pulsing={!run.complete} />

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar
          step={run.step}
          complete={run.complete}
          narration={lines}
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
