"use client";

import { useState } from "react";

import { BackendUnreachable, ScreenState } from "@/components/ui/screen-state";
import { casePath } from "@/lib/api";
import { routes } from "@/lib/routes";
import { useAutoRun } from "@/lib/use-auto-run";
import { useLiveData } from "@/lib/use-live-data";

import { ScreenShell } from "../_analysis/screen-shell";
import { ingestionIsEmpty, type IngestionData, type TabId } from "../_data";
import { IngestionDataProvider } from "./data-context";
import { AgentStatusBar } from "./agent-status-bar";
import { CaseHeader } from "./case-header";
import { CaseStats } from "./case-stats";
import { ExecutionRail } from "./execution-rail";
import { SourceGrid } from "./source-grid";
import { SourceTabs } from "./source-tabs";
import { useCloseRun } from "./use-close-run";

export type CloseCaseScreenProps = {
  /** `"<period>/<case_key>"` from `?case=`, or null for the demo dataset. */
  caseParam?: string | null;
  /** Run the scripted intake timeline on mount. */
  autoplay?: boolean;
  /**
   * Open the evidence reader once intake lands. Off in this port - the
   * handoff button in the rail is what moves the close forward.
   */
  autoAdvance?: boolean;
  /** Render the live execution rail beside the grid. */
  showExecutionPanel?: boolean;
  /** Shorter source cards, for dense viewports. */
  compactCards?: boolean;
  /** Tick the run clock. */
  liveTimer?: boolean;
};

/**
 * The Evidence agent's intake view: every document it read for this case
 * this month, and which of them it kept. The entry point of the agent chain.
 *
 * The rail is a sibling of `<main>` rather than a child, because the whole
 * desktop frame is one horizontal flex row - sidebar, case, rail - and the
 * rail has to be able to take width away from the grid when it is dragged.
 */
export function CloseCaseScreen({
  caseParam = null,
  autoplay = true,
  showExecutionPanel = true,
  compactCards = false,
  liveTimer = true,
}: CloseCaseScreenProps) {
  const live = useLiveData<IngestionData>(casePath(caseParam, "ingestion"), {
    isEmpty: ingestionIsEmpty,
  });

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
                : "No documents on this case"
          }
          body={
            !caseParam
              ? "Pick a case from the case list to see the documents its close read."
              : live.httpStatus === 404
                ? "The close API does not know this case. It may belong to a month that has not been run."
                : "The close API has read no documents for this case. Run the month's close and come back."
          }
          detail={caseParam}
          actions={[{ label: "All cases", href: routes.cases }]}
        />
      </ScreenShell>
    );
  }

  return (
    <IngestionDataProvider data={live.data} caseParam={caseParam}>
      <IntakeBody
        autoplay={autoplay}
        showExecutionPanel={showExecutionPanel}
        compactCards={compactCards}
        liveTimer={liveTimer}
      />
    </IngestionDataProvider>
  );
}

/** Sits inside the provider, so the run hook can read the dataset. */
function IntakeBody({
  autoplay,
  showExecutionPanel,
  compactCards,
  liveTimer,
}: Required<Omit<CloseCaseScreenProps, "caseParam" | "autoAdvance">>) {
  const [tab, setTab] = useState<TabId>("all");
  const [railOpen, setRailOpen] = useState(true);
  /* `/close` is the chain's first screen, so this is where a run that was
     started from the case list picks itself up. */
  const { auto: autoAdvance } = useAutoRun();
  const run = useCloseRun({ autoplay, autoAdvance, liveTimer });

  return (
    <>
      <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
        <div className="flex-none px-[34px] pt-[26px]">
          <CaseHeader />
          <CaseStats />
          <SourceTabs value={tab} onChange={setTab} />
        </div>

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar
          statusText={run.statusText}
          complete={run.complete}
          selectedCount={run.selected.length}
        />

        <SourceGrid
          tab={tab}
          isSelected={run.isSelected}
          onToggle={run.toggle}
          compactCards={compactCards}
        />
      </main>

      {showExecutionPanel && (
        <ExecutionRail
          run={run}
          open={railOpen}
          onToggle={() => setRailOpen((open) => !open)}
          autoAdvance={autoAdvance}
        />
      )}
    </>
  );
}
