"use client";

import Link from "next/link";

import { StartCaseButton } from "@/components/close/start-case-button";
import { TrailPanel } from "@/components/close/case-trail-panel";
import type { CloseView, FrontStage, ObligationDetail } from "@/lib/api-types";
import { CaseProvider } from "@/lib/case-context";
import { caseHref } from "@/lib/case-nav";
import { formatDuration, useCaseRun, useStageClock } from "@/lib/case-runner";
import type { StageKey } from "@/lib/case-store";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { useStageStatuses } from "@/lib/stage-status";
import { agentLabel, STAGE_ROUTES, stageLabelOf, STAGES } from "@/lib/trail";


const RUN_LABEL: Record<StageKey, string> = {
  ingestion: "Run Ingestion agent",
  evidence: "Run Evidence agent",
  obligation: "Run Obligation agent",
  estimation: "Run Estimation agent",
  verification: "Run Verification",
};

const WHAT_IT_DOES: Record<StageKey, string> = {
  ingestion: "It reads the case's files and decides which ones the accrual stands on.",
  evidence: "It reads the files Ingestion kept and quotes the facts the accrual stands on.",
  obligation: "It classifies the purchase from the extracted facts and checks the service period.",
  estimation: "It computes the accrual from the classified obligation with the permitted method.",
  verification: "It checks the estimate against policy and drafts the entries for review.",
};

type Input = { key: string; title: string; meta: string };

/** What the running agent is looking at: the real output of the stage before it. */
function inputsFor(stage: StageKey, detail: ObligationDetail): { heading: string; rows: Input[] } {
  if (stage === "ingestion") {
    return {
      heading: "Reading the case's files",
      rows: (detail.ingestion.offered ?? []).map((file) => ({
        key: file.file_id,
        title: file.name,
        meta: `${file.kind} · ${file.format} · ${file.size_label}`,
      })),
    };
  }
  if (stage === "evidence") {
    return {
      heading: "Reading the files Ingestion kept",
      rows: detail.ingestion.files
        .filter((file) => file.selected)
        .map((file) => ({
          key: file.file_id,
          title: file.name,
          meta: `${file.kind} · ${file.format} · ${file.size_label}`,
        })),
    };
  }
  if (stage === "obligation") {
    return {
      heading: "Working from the extracted facts",
      rows: detail.evidence.facts.map((fact) => ({
        key: fact.evidence_id,
        title: fact.label,
        meta: fact.value ?? "",
      })),
    };
  }
  if (stage === "estimation") {
    return {
      heading: "Working from the classified obligation",
      rows: [
        { key: "type", title: "Purchase type", meta: detail.obligation.purchase_type_label },
        { key: "period", title: "Service period", meta: detail.obligation.service_period },
        ...detail.obligation.signals.map((signal) => ({
          key: `signal-${signal.name}`,
          title: signal.name,
          meta: signal.value,
        })),
      ],
    };
  }
  return {
    heading: "Checking what Estimation produced",
    rows: detail.estimation.inputs.map((input) => ({
      key: input.label,
      title: input.label,
      meta: input.value,
    })),
  };
}

/**
 * What a stage screen shows until its stage has really run: where things stand
 * and one button that runs exactly this stage. While the agent works, the screen
 * lists what it is looking at (the real files or facts handed to it) and nothing
 * it has not produced. The result appears only when the backend returns it.
 */
export function NotStarted({
  close,
  detail,
  stage,
}: {
  close: CloseView;
  detail: ObligationDetail;
  stage: StageKey;
}) {
  return (
    <CaseProvider
      obligationId={detail.header.obligation_id}
      version={`${detail.header.log_count ?? 0}:${detail.header.handoff_count ?? 0}`}
    >
      <NotStartedBody close={close} detail={detail} stage={stage} />
    </CaseProvider>
  );
}

function NotStartedBody({
  close,
  detail,
  stage,
}: {
  close: CloseView;
  detail: ObligationDetail;
  stage: StageKey;
}) {
  const { header } = detail;
  const id = header.obligation_id;
  const run = useCaseRun(id);
  const statuses = useStageStatuses(header);
  const clock = useStageClock(id, stage, false);
  const screen = stageLabelOf(stage);
  const running = statuses[stage] === "Running";
  const completed: FrontStage[] = header.stages_completed ?? [];
  const canStart = close.cases.find((row) => row.obligation_id === id)?.can_start ?? false;
  const index = STAGES.findIndex((s) => s.key === stage);
  const previous = STAGES[index - 1];
  const previousDone = !previous || completed.includes(previous.label);
  const busy = run.active || run.queued;
  const first = index === 0;

  let title = `${screen} has not run`;
  let body = `${WHAT_IT_DOES[stage]} Nothing on this screen exists until it has run.`;
  if (running) {
    title = `${run.agent ? agentLabel(run.agent) : `${screen} agent`} is working`;
    body = "Its result appears here the moment the backend returns it.";
  } else if (busy) {
    title = "Waiting for the previous agent";
    body = previous
      ? `${previous.label} has to finish before ${screen} can start.`
      : "This case is queued behind another one.";
  } else if (!previousDone && previous) {
    title = `Run ${previous.label} first`;
    body = `${screen} works from what ${previous.label} hands on, so it cannot run yet.`;
  } else if (header.current_agent === null && completed.length > 0) {
    title = "This case has come to rest";
    body = "No further agent runs on it: it is waiting on someone else, or it is done.";
  } else if (first && !canStart) {
    body = `January's invoices arrived before this case was started, so it stays Pending. Reset the demo to run it from the top.`;
  }

  const atRest = header.current_agent === null && completed.length > 0;
  const runnable = previousDone && !busy && !atRest && (first ? canStart : true);
  const inputs = running ? inputsFor(stage, detail) : null;

  return (
    <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 overflow-y-auto px-10 py-8">
        <div className="text-eyebrow font-medium tracking-caps-xl text-faint-2">
          {header.vendor_name.toUpperCase()} / {close.period_label.toUpperCase()}
        </div>
        <div className="font-display text-4xl text-ink-deep">{title}</div>
        <p className="max-w-[460px] text-center text-lead text-muted-4 text-pretty">{body}</p>
        {running && (
          <div className="font-mono text-sm text-accent tabular-nums">{formatDuration(clock)}</div>
        )}
        {inputs && <InFlight heading={inputs.heading} rows={inputs.rows} stage={stage} />}
        <div className="mt-2 flex items-center gap-4">
          {runnable && (
            <StartCaseButton
              obligationId={id}
              completed={completed}
              agent={header.current_agent ?? null}
              until={stage}
              label={RUN_LABEL[stage]}
            />
          )}
          {!previousDone && previous && (
            <Link
              href={caseHref(STAGE_ROUTES[previous.key], id)}
              className="text-ui font-medium text-accent-link hover:text-accent-press"
            >
              Go to {previous.label}
            </Link>
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

/** The real inputs the agent is working through, each still being read. */
function InFlight({ heading, rows, stage }: { heading: string; rows: Input[]; stage: StageKey }) {
  const shown = rows.slice(0, 12);
  return (
    <div className="mt-3 w-full max-w-[560px] rounded-xl border border-divider bg-panel shadow-[var(--shadow-tile)]">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5 text-tiny text-faint-2">
        <span className="font-medium tracking-caps">{heading.toUpperCase()}</span>
        <span className="tabular-nums">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-4 text-meta text-faint-2">
          {stage === "ingestion"
            ? "Reading the files offered for this case."
            : "Working from what the previous agent handed on."}
        </div>
      ) : (
        <ul className="max-h-[300px] overflow-y-auto">
          {shown.map((row, i) => (
            <li
              key={row.key}
              className={cn(
                "flex items-center gap-3 px-4 py-2.5",
                i > 0 && "border-t border-divider-3",
              )}
            >
              <span
                aria-hidden="true"
                className="h-[7px] w-[7px] flex-none animate-pulse rounded-full bg-accent"
                style={{ animationDelay: `${i * 90}ms` }}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-ui text-ink">{row.title}</div>
                {row.meta && <div className="truncate text-tiny text-faint-3">{row.meta}</div>}
              </div>
              <span className="flex-none text-nano font-semibold tracking-caps text-faint-2">
                {stage === "ingestion" || stage === "evidence" ? "READING" : "CONSIDERING"}
              </span>
            </li>
          ))}
          {rows.length > shown.length && (
            <li className="border-t border-divider-3 px-4 py-2 text-tiny text-faint-2">
              and {rows.length - shown.length} more
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
