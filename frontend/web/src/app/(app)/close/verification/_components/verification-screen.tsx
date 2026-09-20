"use client";

import { AgentStatusBar } from "./agent-status-bar";
import { AssertionsPanel } from "./assertions-panel";
import { CaseHeader } from "./case-header";
import { ControlChecksPanel } from "./control-checks-panel";
import { ExecutionRail, MiniRail } from "./execution-rail";
import { FinalStatusPanel } from "./final-status-panel";
import { CaseActivityPanel } from "./case-activity-panel";
import { useVerificationScreen } from "./screen-context";
import { useVerificationRun } from "./use-verification-run";

/**
 * Verification agent - the last step of the close chain.
 *
 * Six control checks and six assertions resolve on the comp's scripted
 * timeline; when the last one lands the case flips to close-ready and the
 * approve / handoff affordances settle in. All data is synthetic and every
 * upstream system is simulated.
 */
export function VerificationScreen() {
  const { data } = useVerificationScreen();
  const run = useVerificationRun({ data });
  const { view } = run;
  const pulse = !view.complete;

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
        <CaseHeader />

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar
          statusText={view.statusText}
          passedLabel={view.passedLabel}
          progress={view.progress}
          pulse={pulse}
          onReplay={run.replay}
        />

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pb-[26px]">
          <div className="grid min-h-full grid-cols-[minmax(0,0.84fr)_minmax(0,1.34fr)_minmax(0,0.88fr)] items-start gap-[14px]">
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
          <CaseActivityPanel />
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
