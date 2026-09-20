"use client";

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
 * Auto-advance is off in this port: the run finishes and waits on the visible
 * handoff button rather than navigating on its own. Flip this to `true` for the
 * comp's unattended behaviour.
 */
const AUTO_ADVANCE = false;

export function EvidenceScreen({ view }: { view: EvidenceScreenView }) {
  return (
    <CaseProvider obligationId={view.obligationId}>
      <EvidenceBody view={view} />
    </CaseProvider>
  );
}

function EvidenceBody({ view }: { view: EvidenceScreenView }) {
  const run = useEvidenceRun({ factCount: view.facts.length, autoAdvance: AUTO_ADVANCE });
  const viewer = useDocumentViewer(view);
  const rail = useRailResize();

  return (
    <>
      <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
        <div className="flex-none px-[34px] pt-[26px]">
          <CaseHeader header={view.header} />
          <CaseStats header={view.header} step={run.step} />
          <DocumentTabs
            tabs={view.tabs}
            doc={viewer.doc}
            onSelect={viewer.selectDoc}
            onToggleSearch={viewer.toggleSearch}
            onJumpToMatch={viewer.jumpToMatch}
          />
        </div>

        <div className="h-px flex-none bg-line" />

        <AgentBar
          step={run.step}
          status={run.status}
          complete={run.complete}
          sourceCount={view.tabs.length}
          onReplay={run.replay}
        />

        <div className="flex min-h-0 flex-1 px-[34px] pb-[26px]">
          <DocumentViewer
            tabs={view.tabs}
            excerpts={view.excerpts}
            step={run.step}
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
          autoAdvance={AUTO_ADVANCE}
          onResizeStart={rail.startResize}
          onCollapse={rail.toggle}
        />
      ) : (
        <CollapsedRail onExpand={rail.toggle} />
      )}
    </>
  );
}
