"use client";

import { CaseRibbon } from "@/components/close/case-ribbon";
import { EscalationBanner } from "@/components/close/escalation-banner";
import { TrailPanel } from "@/components/close/case-trail-panel";
import { CaseProvider, useCaseId } from "@/lib/case-context";
import { useCaseUi } from "@/lib/case-store";
import { StageRevealProvider, useRevealSlice } from "@/lib/stage-reveal";

import { useMemo } from "react";

import type { CloseCaseView } from "../_view";
import { AgentStatusBar } from "./agent-status-bar";
import { CaseHeader } from "./case-header";
import { CaseStats } from "./case-stats";
import { ExecutionRail } from "./execution-rail";
import { SourceGrid } from "./source-grid";
import { SourceTabs } from "./source-tabs";
import { useCloseRun } from "./use-close-run";
import { useFileSelection } from "./use-file-selection";

export type CloseCaseScreenProps = {
  /** What the Ingestion agent saw and kept for this obligation. */
  view: CloseCaseView;
  /** Render the live execution rail beside the grid. */
  showExecutionPanel?: boolean;
  /** Shorter source cards, for dense viewports. */
  compactCards?: boolean;
};

/**
 * The case the ingestion agent has worked, and the entry point of the agent
 * chain. It renders only once the backend has run the agent: everything on it is
 * the agent's own output, and the file selection can be changed by the reader.
 *
 * The rail is a sibling of `<main>` rather than a child, because the whole
 * desktop frame is one horizontal flex row - sidebar, case, rail - and the
 * rail has to be able to take width away from the grid when it is dragged.
 */
export function CloseCaseScreen(props: CloseCaseScreenProps) {
  return (
    <CaseProvider obligationId={props.view.obligationId} version={props.view.trailVersion}>
      {/* Right after the reader ran the agent, its decisions resolve one file at a time. */}
      <StageRevealProvider
        stage="ingestion"
        total={props.view.pending ? 0 : props.view.cards.length}
        pending={props.view.pending}
        stepMs={340}
      >
        <CloseCaseBody {...props} />
      </StageRevealProvider>
    </CaseProvider>
  );
}

function CloseCaseBody({ view: full, showExecutionPanel = true, compactCards = false }: CloseCaseScreenProps) {
  const obligationId = useCaseId();
  const { count: revealed } = useRevealSlice(0, full.cards.length);
  const reading = useMemo(
    () => new Set(full.cards.slice(revealed).map((card) => card.id)),
    [full.cards, revealed],
  );
  const view = useMemo(
    () => ({
      ...full,
      cards: full.cards.map((card) =>
        reading.has(card.id) ? { ...card, picked: false, removed: false, reason: null } : card,
      ),
    }),
    [full, reading],
  );
  const [tab, setTab] = useCaseUi(obligationId, "ingestion.tab", "all");
  const [railOpen, setRailOpen] = useCaseUi(obligationId, "ingestion.rail", true);
  const run = useCloseRun({ view });
  const files = useFileSelection(view.obligationId, view.cards);

  return (
    <>
      <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
        <div className="flex-none px-[34px] pt-[26px]">
          <CaseHeader header={view.header} />
          <CaseStats header={view.header} />
          <CaseRibbon className="pt-3" />
          <SourceTabs tabs={view.tabs} value={tab} onChange={setTab} />
        </div>

        <div className="h-px flex-none bg-line" />

        <AgentStatusBar selectedCount={run.selected.length} filesLoaded={view.filesLoaded} />
        <TrailPanel />

        {view.escalation && (
          <div className="flex-none pt-3">
            <EscalationBanner
              escalation={view.escalation}
              onRestore={files.restoreAll}
              pending={files.pending}
            />
          </div>
        )}
        {files.error && (
          <div className="flex-none px-[34px] pt-2 text-meta text-[#A4452F]">{files.error}</div>
        )}

        <SourceGrid
          cards={view.cards}
          reading={reading}
          tab={tab}
          onRemove={files.remove}
          onRestore={files.restore}
          busy={files.pending}
          compactCards={compactCards}
        />
      </main>

      {showExecutionPanel && (
        <ExecutionRail
          run={run}
          obligationId={view.obligationId}
          header={view.header}
          open={railOpen}
          onToggle={() => setRailOpen(!railOpen)}
        />
      )}
    </>
  );
}
