"use client";

import { TrailPanel } from "@/components/close/case-trail-panel";
import { CaseProvider } from "@/lib/case-context";

import type { EvidenceScreenView } from "../_view";
import { AgentBar } from "./agent-bar";
import { CaseHeader } from "./case-header";
import { CaseStats } from "./case-stats";
import { CollapsedRail } from "./rail-collapsed";
import { DocumentTabs } from "./document-tabs";
import { DocumentViewer } from "./document-viewer";
import { ExecutionRail } from "./execution-rail";
import { useDocumentViewer } from "./use-document-viewer";
import { useEvidenceRun } from "./use-evidence-run";
import { useRailResize } from "./use-rail-resize";

/**
 * Evidence agent - step 02 of the close.
 *
 * The agent reads the documents Ingestion kept, quotes the passages that move
 * the accrual, and builds the fact set the obligation agent works from. All
 * data is synthetic and every upstream system is simulated.
 *
 * The screen renders only once the backend has run the Evidence agent, and the
 * run finishes and waits on the visible handoff button.
 */

export function EvidenceScreen({ view }: { view: EvidenceScreenView }) {
  return (
    <CaseProvider obligationId={view.obligationId} version={view.trailVersion}>
      <EvidenceBody view={view} />
    </CaseProvider>
  );
}

function EvidenceBody({ view }: { view: EvidenceScreenView }) {
  const run = useEvidenceRun();
  const viewer = useDocumentViewer(view);
  const rail = useRailResize();

  return (
    <>
      <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
        <div className="flex-none px-[34px] pt-[26px]">
          <CaseHeader header={view.header} />
          <CaseStats header={view.header} />
          <DocumentTabs
            tabs={view.tabs}
            doc={viewer.doc}
            onSelect={viewer.selectDoc}
            onToggleSearch={viewer.toggleSearch}
            onJumpToMatch={viewer.jumpToMatch}
          />
        </div>

        <div className="h-px flex-none bg-line" />

        <AgentBar sourceCount={view.tabs.length} factCount={view.facts.length} />
        <TrailPanel />

        <div className="flex min-h-0 flex-1 px-[34px] pb-[26px]">
          <DocumentViewer
            tabs={view.tabs}
            excerpts={view.excerpts}
            viewer={viewer}
            onToggleRail={rail.toggle}
          />
        </div>
      </main>

      {rail.open ? (
        <ExecutionRail
          run={run}
          facts={view.facts}
          width={rail.width}
          dragging={rail.dragging}
          header={view.header}
          onResizeStart={rail.startResize}
          onCollapse={rail.toggle}
        />
      ) : (
        <CollapsedRail onExpand={rail.toggle} />
      )}
    </>
  );
}
