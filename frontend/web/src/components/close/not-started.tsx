"use client";

import Link from "next/link";

import { StartCaseButton } from "@/components/close/start-case-button";
import { TrailPanel } from "@/components/close/case-trail-panel";
import type { CloseView, FrontStage, Header } from "@/lib/api-types";
import { CaseProvider } from "@/lib/case-context";
import { caseHref } from "@/lib/case-nav";
import { formatDuration, useCaseRun, useStageClock } from "@/lib/case-runner";
import type { StageKey } from "@/lib/case-store";
import { routes } from "@/lib/routes";
import { agentLabel, stageLabelOf, STAGES } from "@/lib/trail";
import { useStageStatuses } from "@/lib/stage-status";

/**
 * What a stage screen shows until its stage has really run: nothing but where
 * things stand. A case nobody started offers Start; a case whose earlier agents
 * are running says it is waiting for them; the stage in flight shows a live
 * timer; a case that stopped part way offers Continue. No result is drawn until
 * the backend has returned it.
 */
export function NotStarted({
  close,
  header,
  stage,
}: {
  close: CloseView;
  header: Header;
  stage: StageKey;
}) {
  return (
    <CaseProvider
      obligationId={header.obligation_id}
      version={`${header.log_count ?? 0}:${header.handoff_count ?? 0}`}
    >
      <NotStartedBody close={close} header={header} stage={stage} />
    </CaseProvider>
  );
}

function NotStartedBody({
  close,
  header,
  stage,
}: {
  close: CloseView;
  header: Header;
  stage: StageKey;
}) {
  const id = header.obligation_id;
  const run = useCaseRun(id);
  const statuses = useStageStatuses(header);
  const clock = useStageClock(id, stage, false);
  const screen = stageLabelOf(stage);
  const status = statuses[stage];
  const completed: FrontStage[] = header.stages_completed ?? [];
  const canStart =
    close.cases.find((row) => row.obligation_id === id)?.can_start ?? false;
  const partial = completed.length > 0;
  const previous = STAGES[STAGES.findIndex((s) => s.key === stage) - 1];

  let title = "Not started";
  let body = `No agent has worked this case yet, so ${screen} has nothing to show. Starting it runs the agents one stage at a time, and each screen fills in only when its stage has finished.`;
  if (status === "Running") {
    title = `${run.agent ? agentLabel(run.agent) : `${screen} agent`} running`;
    body = "This stage is running now. Its result appears here the moment the backend returns it.";
  } else if (run.active || run.queued) {
    title = "Waiting for the previous agent";
    body = previous
      ? `${previous.label} has to finish before ${screen} can start. This screen fills in when it hands off.`
      : "This case is queued behind another one.";
  } else if (partial && header.current_agent !== null) {
    title = `${screen} has not run yet`;
    body = `The run stopped after ${completed[completed.length - 1]}. Continue to run the next stage.`;
  } else if (!canStart) {
    body = `January's invoices arrived before this case was started, so it stays Pending. Reset the demo to run it from the top.`;
  }

  return (
    <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-10">
        <div className="text-eyebrow font-medium tracking-caps-xl text-faint-2">
          {header.vendor_name.toUpperCase()} / {close.period_label.toUpperCase()}
        </div>
        <div className="font-display text-4xl text-ink-deep">{title}</div>
        <p className="max-w-[460px] text-center text-lead text-muted-4 text-pretty">{body}</p>
        {status === "Running" && (
          <div className="font-mono text-sm text-accent tabular-nums">{formatDuration(clock)}</div>
        )}
        <div className="mt-2 flex items-center gap-4">
          {canStart && !run.active && !run.queued && (
            <StartCaseButton
              obligationId={id}
              completed={completed}
              agent={header.current_agent ?? null}
              goTo={caseHref(routes.closeCase, id)}
              label={partial ? "Continue" : "Start"}
            />
          )}
          <Link
            href={routes.cases}
            className="text-ui text-muted-4 transition-colors duration-[160ms] hover:text-ink"
          >
            All cases
          </Link>
        </div>
      </div>
      <TrailPanel />
    </main>
  );
}
