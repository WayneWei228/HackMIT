"use client";

import { useState } from "react";

import type { TabId } from "../_data";
import { AgentStatusBar } from "./agent-status-bar";
import { CaseHeader } from "./case-header";
import { CaseStats } from "./case-stats";
import { ExecutionRail } from "./execution-rail";
import { SourceGrid } from "./source-grid";
import { SourceTabs } from "./source-tabs";
import { useCloseRun } from "./use-close-run";

export type CloseCaseScreenProps = {
  /** Run the scripted ingestion timeline on mount. */
  autoplay?: boolean;
  /**
   * Navigate to the evidence agent once ingestion lands. Off in this port -
   * the handoff button in the rail is what moves the close forward.
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
 * Mintlify's December accrual: the case the ingestion agent is working, and
 * the entry point of the agent chain.
 *
 * The rail is a sibling of `<main>` rather than a child, because the whole
 * desktop frame is one horizontal flex row - sidebar, case, rail - and the
 * rail has to be able to take width away from the grid when it is dragged.
 */
export function CloseCaseScreen({
  autoplay = true,
  autoAdvance = false,
  showExecutionPanel = true,
  compactCards = false,
  liveTimer = true,
}: CloseCaseScreenProps) {
  const [tab, setTab] = useState<TabId>("all");
  const [railOpen, setRailOpen] = useState(true);
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
