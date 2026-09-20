"use client";

import { useMemo } from "react";

import {
  BackendUnreachable,
  LoadingRows,
  ScreenState,
  Skeleton,
} from "@/components/ui/screen-state";
import { casePath } from "@/lib/api";
import { routes } from "@/lib/routes";
import { useAutoRun } from "@/lib/use-auto-run";
import { useLiveData } from "@/lib/use-live-data";
import {
  type EstimationPayload,
  isEmptyEstimation,
  liveStatus,
  normalize,
} from "../_data";
import { useEstimationRun, useRailResize } from "../_use-estimation-run";
import { AgentBar } from "./agent-bar";
import { CaseHeader } from "./case-header";
import { EstimationDataProvider, useEstimationData } from "./data-context";
import { EstimateBuildPanel } from "./estimate-build-panel";
import { ExecutionRail } from "./execution-rail";
import { ExecutionRailMini } from "./execution-rail-mini";
import { InputsPanel } from "./inputs-panel";
import { RecommendationPanel } from "./recommendation-panel";

/**
 * Estimation agent: the fifth step of the close chain. It takes the owed PO
 * line Detection found and the basis Classification assigned, applies period
 * coverage and policy, and hands a single accrual amount to Outreach.
 */
export function EstimationScreen({ caseParam }: { caseParam: string | null }) {
  const path = casePath(caseParam, "estimation");
  const live = useLiveData<EstimationPayload>(path, {
    isEmpty: isEmptyEstimation,
  });

  if (live.status === "loading") return <EstimationLoading />;

  if (live.status === "error") {
    /* A 404 is the backend answering - it has no such case - which is a
       different thing to say than "the API is down", and reads as the same
       empty state a case with nothing on it gets. */
    return (
      <Shell>
        {isNotFound(live.error) ? (
          <NoSuchCase caseParam={caseParam} />
        ) : (
          <BackendUnreachable
            url={live.url}
            error={live.error}
            onRetry={live.retry}
          />
        )}
      </Shell>
    );
  }

  if (live.status === "empty" || !live.data) {
    return (
      <Shell>
        {caseParam ? (
          <NoSuchCase caseParam={caseParam} />
        ) : (
          <ScreenState
            title="Select a case"
            body="This screen shows one case's accrual estimate. Pick a case and the Estimation agent's run opens here."
            actions={[{ label: "All cases", href: routes.cases }]}
          />
        )}
      </Shell>
    );
  }

  return (
    <EstimationDataProvider data={normalize(live.data)} caseParam={caseParam}>
      <EstimationRunView />
    </EstimationDataProvider>
  );
}

/** `getJson` throws `"<status> <statusText> for <path>"` on a non-2xx. */
const isNotFound = (error: string | null) => /\b404\b/.test(error ?? "");

/** The backend answered, and has no estimation for the case that was asked for. */
function NoSuchCase({ caseParam }: { caseParam: string | null }) {
  return (
    <ScreenState
      title="No estimation for this case"
      body="The close run has not produced an estimate for this case, or the case key does not match anything the backend knows."
      detail={caseParam}
      actions={[{ label: "All cases", href: routes.cases }]}
    />
  );
}

/** The page frame the three non-ready states sit inside. */
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto px-[34px] py-[26px]">
        <div className="mx-auto max-w-[760px] pt-[42px]">{children}</div>
      </div>
    </main>
  );
}

/** The screen's own shape, drawn while the case is still in flight. */
export function EstimationLoading() {
  return (
    <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
      <div className="flex-none px-[34px] pt-[26px]">
        <Skeleton className="h-3.5 w-[320px]" />
        <Skeleton className="mt-5 h-[46px] w-[280px]" delay={0.08} />
        <Skeleton className="mt-2.5 h-8 w-[200px]" delay={0.12} />
        <div className="mt-[26px] grid grid-cols-4 gap-6 pb-[22px]">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-[54px] w-full" delay={i * 0.06} />
          ))}
        </div>
      </div>
      <div className="h-px flex-none bg-line" />
      <div className="min-h-0 flex-1 overflow-y-auto px-[34px] py-[26px]">
        <div className="grid grid-cols-[minmax(232px,0.82fr)_minmax(330px,1.3fr)_minmax(262px,0.92fr)] items-start gap-3.5">
          <LoadingRows rows={5} />
          <LoadingRows rows={5} />
          <LoadingRows rows={5} />
        </div>
      </div>
    </main>
  );
}

/**
 * The comp's layout. It sits inside the provider so the run hook - which needs
 * the handoff target and the case param for its auto-advance - can read them
 * the same way every panel does.
 */
function EstimationRunView() {
  /* "Auto-run agents": with the switch on, the finished run opens Outreach
     itself rather than waiting on the handoff button. The setting is kept
     outside React so it survives the page load each hand-off causes. */
  const { auto } = useAutoRun();
  const run = useEstimationRun({ autoAdvance: auto });
  const rail = useRailResize();
  const { data } = useEstimationData();

  /* The closing line names this case's own amount, so the ladder is rebuilt
     whenever the payload changes rather than written down anywhere. */
  const status = useMemo(() => liveStatus(data), [data]);

  return (
    <>
      <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden">
        <CaseHeader pulsing={!run.complete} />
        <AgentBar
          step={run.step}
          status={status}
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
          autoAdvance={auto}
        />
      ) : (
        <ExecutionRailMini onExpand={rail.toggle} />
      )}
    </>
  );
}
