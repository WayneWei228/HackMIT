"use client";

import { useMemo } from "react";

import { BackendUnreachable, ScreenState } from "@/components/ui/screen-state";
import { casePath, type CloseScreen } from "@/lib/api";
import { agentOf, routes } from "@/lib/routes";
import { useAutoRun } from "@/lib/use-auto-run";
import { useLiveData } from "@/lib/use-live-data";

import { AgentStatusBar } from "./agent-status-bar";
import { AssertionsPanel } from "./assertions-panel";
import { CaseHeader } from "./case-header";
import { ControlChecksPanel } from "./control-checks-panel";
import { ControlsDataProvider, useControlsData } from "./data-context";
import { ExecutionRail, MiniRail } from "./execution-rail";
import { FinalStatusPanel } from "./final-status-panel";
import { ScreenShell } from "../_analysis/screen-shell";
import { controlsIsEmpty, controlsStatus, type ControlsData } from "./types";
import { useControlsRun } from "./use-controls-run";

export type ControlsScreenProps = {
  /** Which endpoint this screen reads: `outreach` or `settlement`. */
  screen: CloseScreen;
  /** The agent's id in `agentChain` - also what names it on screen. */
  agentId: string;
  caseParam: string | null;
};

/**
 * The control comp, shared by Outreach and Settlement.
 *
 * Assertions on the left, the control checks running down the middle, the
 * case's final status on the right, and the chain in the rail. Every figure
 * and sentence comes from the close API; which agent this is, and what it
 * hands to, comes from the route table.
 */
export function ControlsScreen({
  screen,
  agentId,
  caseParam,
}: ControlsScreenProps) {
  const live = useLiveData<ControlsData>(casePath(caseParam, screen), {
    isEmpty: controlsIsEmpty,
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

  if (live.status === "loading") return <ScreenShell loading />;

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
    <ControlsDataProvider
      data={live.data}
      agentId={agentId}
      agentLabel={agentLabel}
      caseParam={caseParam}
    >
      <ControlsBody />
    </ControlsDataProvider>
  );
}

function ControlsBody() {
  const { data, agentId, agentLabel, caseParam } = useControlsData();

  /* Narration is progress, read off the data on screen. */
  const lines = useMemo(
    () => controlsStatus(data, agentLabel),
    [data, agentLabel],
  );

  const { auto } = useAutoRun();
  const run = useControlsRun({
    data,
    agentId,
    caseParam,
    narration: lines,
    autoAdvance: auto,
  });
  const { view } = run;
  const pulse = !view.complete;

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
        <CaseHeader headStatus={view.headStatus} pulse={pulse} />

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar
          statusText={view.statusText}
          passedLabel={view.passedLabel}
          controlsLabel={view.controlsLabel}
          progress={view.progress}
          pulse={pulse}
          onReplay={run.replay}
        />

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pb-[26px]">
          <div className="grid min-h-full grid-cols-[minmax(238px,0.84fr)_minmax(348px,1.34fr)_minmax(250px,0.88fr)] items-start gap-[14px]">
            <AssertionsPanel
              assertions={view.assertions}
              extras={view.extras}
            />
            <ControlChecksPanel
              controls={view.controls}
              scans={view.scans}
              controlCount={view.controlCount}
              openControl={run.openControl}
              onToggle={run.toggleControl}
            />
            <FinalStatusPanel
              complete={view.complete}
              finalStatus={view.finalStatus}
              noteTitle={view.noteTitle}
              noteBody={view.noteBody}
            />
          </div>
        </div>
      </main>

      {run.railOpen ? (
        <ExecutionRail
          width={run.railWidth}
          dragging={run.dragging}
          onStartResize={run.startResize}
          onCollapse={run.toggleRail}
          railStatus={view.railStatus}
          stageStatus={view.stageStatus}
          complete={view.complete}
          clock={run.clock}
          tasks={view.tasks}
          pulse={pulse}
        />
      ) : (
        <MiniRail onExpand={run.toggleRail} />
      )}
    </>
  );
}
