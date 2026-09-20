"use client";

import { AgentBar } from "./_components/agent-bar";
import { CaseHeader } from "./_components/case-header";
import { CaseStats } from "./_components/case-stats";
import { CollapsedRail } from "./_components/rail-collapsed";
import { DocumentTabs } from "./_components/document-tabs";
import { DocumentViewer } from "./_components/document-viewer";
import { ExecutionRail } from "./_components/execution-rail";
import { useDocumentViewer } from "./_components/use-document-viewer";
import { useEvidenceRun } from "./_components/use-evidence-run";
import { useRailResize } from "./_components/use-rail-resize";

/**
 * Evidence agent - step 02 of the close.
 *
 * The agent reads the source documents, finds the clause that moves the
 * accrual, and builds the fact set the obligation agent works from. All data is
 * synthetic and every upstream system is simulated.
 *
 * Auto-advance is off in this port: the run finishes and waits on the visible
 * handoff button rather than navigating on its own. Flip this to `true` for the
 * comp's unattended behaviour.
 */
const AUTO_ADVANCE = false;

export default function EvidencePage() {
  const run = useEvidenceRun({ autoAdvance: AUTO_ADVANCE });
  const viewer = useDocumentViewer();
  const rail = useRailResize();

  return (
    <>
      <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
        <div className="flex-none px-[34px] pt-[26px]">
          <CaseHeader />
          <CaseStats step={run.step} complete={run.complete} />
          <DocumentTabs
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
          onReplay={run.replay}
        />

        <div className="flex min-h-0 flex-1 px-[34px] pb-[26px]">
          <DocumentViewer
            step={run.step}
            viewer={viewer}
            onToggleRail={rail.toggle}
          />
        </div>
      </main>

      {rail.open ? (
        <ExecutionRail
          run={run}
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
