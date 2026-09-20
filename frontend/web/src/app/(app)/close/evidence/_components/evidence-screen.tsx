"use client";

import { useMemo } from "react";

import { TrailPanel } from "@/components/close/case-trail-panel";
import { CaseProvider } from "@/lib/case-context";
import { StageRevealProvider, useRevealSlice } from "@/lib/stage-reveal";

import { excerptsOf, type EvidenceScreenView } from "../_view";
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
      {/* Right after the reader ran the agent, its facts appear one at a time and each quote is shaded as it does. */}
      <StageRevealProvider
        stage="evidence"
        total={view.facts.length}
        pending={view.pending}
        partial
        stepMs={520}
      >
        <EvidenceBody view={view} />
      </StageRevealProvider>
    </CaseProvider>
  );
}

function EvidenceBody({ view }: { view: EvidenceScreenView }) {
  const run = useEvidenceRun();
  const { count: revealed } = useRevealSlice(0, view.facts.length);
  const revealing = revealed < view.facts.length;
  const facts = useMemo(() => view.facts.slice(0, revealed), [view.facts, revealed]);
  const excerpts = useMemo(
    () => (revealing ? excerptsOf(facts) : view.excerpts),
    [revealing, facts, view.excerpts],
  );
  const newest = facts.length > 0 ? facts[facts.length - 1] : null;
  /* The pane follows the newest fact as it appears, and otherwise the document being read. */
  const following =
    revealing && newest?.docId
      ? { docId: newest.docId, page: newest.page }
      : view.reading
        ? { docId: view.reading, page: 1 }
        : null;
  const viewer = useDocumentViewer(view, following);
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

        <AgentBar sourceCount={view.tabs.length} factCount={facts.length} />
        <TrailPanel />

        <div className="flex min-h-0 flex-1 px-[34px] pb-[26px]">
          <DocumentViewer
            tabs={view.tabs}
            excerpts={excerpts}
            viewer={viewer}
            onToggleRail={rail.toggle}
          />
        </div>
      </main>

      {rail.open ? (
        <ExecutionRail
          run={run}
          facts={facts}
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
