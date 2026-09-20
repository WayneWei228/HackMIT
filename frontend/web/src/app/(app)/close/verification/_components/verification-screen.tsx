"use client";

import { TrailPanel } from "@/components/close/case-trail-panel";
import { Awaiting } from "@/components/close/awaiting";
import { EscalationBanner } from "@/components/close/escalation-banner";
import { StageRevealProvider, useRevealDone, useRevealSlice } from "@/lib/stage-reveal";
import { ReceivedStrip, StageChecks } from "@/components/close/stage-checks";

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
 * The screen renders only once the backend has run the Verification agents:
 * every control, assertion and the final status is what they recorded, with the
 * Policy stage's own decision. All data is synthetic and every upstream system is
 * simulated.
 */
export function VerificationScreen() {
  const { data, stageChecks } = useVerificationScreen();
  const run = useVerificationRun({ data });
  /* The controls tick one at a time, then the checks; the decision they support comes last. */
  return (
    <StageRevealProvider
      stage="verification"
      total={run.view.controls.length + (stageChecks?.length ?? 0) + 1}
      stepMs={420}
    >
      <VerificationBody run={run} />
    </StageRevealProvider>
  );
}

function VerificationBody({ run }: { run: ReturnType<typeof useVerificationRun> }) {
  const { received, stageChecks, escalation, header } = useVerificationScreen();
  const { view } = run;
  const done = useRevealDone();
  const { count } = useRevealSlice(0, view.controls.length);
  const controls = view.controls.slice(0, count);
  const tally = `${count} / ${view.controls.length} checked`;

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
        <CaseHeader />

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar
          passedLabel={done ? view.passedLabel : tally}
          progress={done ? view.progress : (count / Math.max(1, view.controls.length)) * 100}
        />
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
          <div className="grid min-h-full grid-cols-[minmax(0,0.84fr)_minmax(0,1.34fr)_minmax(0,0.88fr)] items-start gap-[14px]">
            {done ? (
              <AssertionsPanel assertions={view.assertions} extras={view.extras} />
            ) : (
              <Awaiting title="Assertions" />
            )}
            <ControlChecksPanel
              controls={controls}
              scans={view.scans}
              controlCount={done ? view.controlCount : tally}
              openControl={run.openControl}
              onToggle={run.toggleControl}
            />
            {done ? (
              <FinalStatusPanel
                finalStatus={view.finalStatus}
                noteTitle={view.noteTitle}
                noteBody={view.noteBody}
              />
            ) : (
              <Awaiting title="Final case status" />
            )}
          </div>
          {stageChecks && (
            <section className="mt-3.5 rounded-xl border border-divider bg-panel px-[22px] pt-5 pb-[22px] shadow-tile">
              <h2 className="font-display text-2xl text-ink-deep">Checks the agents ran</h2>
              <div className="mt-4">
                <StageChecks
                  checks={stageChecks}
                  scope="verification"
                  offset={view.controls.length}
                />
              </div>
            </section>
          )}
          <CaseActivityPanel />
        </div>
      </main>

      {run.railOpen ? (
        <ExecutionRail
          width={run.railWidth}
          dragging={run.dragging}
          onStartResize={run.startResize}
          onCollapse={run.toggleRail}
          header={header}
          clock={run.clock}
          outcome={view.finalStatus}
        />
      ) : (
        <MiniRail onExpand={run.toggleRail} />
      )}
    </>
  );
}
