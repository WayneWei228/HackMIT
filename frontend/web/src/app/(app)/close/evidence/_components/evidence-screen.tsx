"use client";

import { useMemo, type ReactNode } from "react";

import {
  BackendUnreachable,
  LoadingRows,
  ScreenState,
  Skeleton,
} from "@/components/ui/screen-state";
import { casePath } from "@/lib/api";
import { routes } from "@/lib/routes";
import { useAutoRun } from "@/lib/use-auto-run";
import {
  documentTypeLabel,
  useCaseDocuments,
  type CaseDocument,
} from "@/lib/use-case-documents";
import { useLiveData } from "@/lib/use-live-data";

import { isEmptyEvidence, type DocTab, type EvidenceData } from "../_data";
import { AgentBar } from "./agent-bar";
import { CaseHeader } from "./case-header";
import { CaseStats } from "./case-stats";
import { EvidenceDataProvider } from "./data-context";
import { DocumentTabs } from "./document-tabs";
import { DocumentViewer } from "./document-viewer";
import { ExecutionRail } from "./execution-rail";
import { CollapsedRail } from "./rail-collapsed";
import { useDocumentViewer } from "./use-document-viewer";
import { useEvidenceRun } from "./use-evidence-run";
import { useRailResize } from "./use-rail-resize";

/** `useLiveData` holds this by reference, so it has to live out here. */
const IS_EMPTY = { isEmpty: isEmptyEvidence };

/**
 * Whether the backend answered "no such thing" rather than failing to answer.
 *
 * The two are different states to a person: a 404 means this case has no
 * evidence run and no retry will change that, while anything else means the
 * API is not talking to us and trying again might help. `getJson` throws one
 * `Error` for both, so the status line it builds is what tells them apart.
 */
function isNotFound(error: string | null): boolean {
  return error !== null && /\b404\b/.test(error);
}

/**
 * One of the case's documents, as a tab in the strip.
 *
 * A document arrives as one extracted record and one plain-text rendering of
 * the PDF, so it is a single page as far as the pager is concerned. Inventing
 * a page count would put a number on screen that nothing backs.
 */
function toTab(doc: CaseDocument): DocTab {
  const type = documentTypeLabel(doc.doc_type);
  return {
    id: doc.doc_id,
    label: doc.doc_id,
    meta: doc.period ? `${type} · ${doc.period}` : type,
    pages: 1,
    openAt: 1,
    docType: doc.doc_type,
  };
}

/**
 * Evidence agent - stage 01 of the close.
 *
 * The agent reads the case's source documents and builds the fact set the
 * detection agent works from. Everything on the screen is the backend's: with
 * no case selected, a backend that cannot be reached, or a case it has never
 * heard of, the screen says so rather than drawing somebody else's paperwork.
 */
export function EvidenceScreen({ caseParam }: { caseParam: string | null }) {
  const live = useLiveData<EvidenceData>(
    casePath(caseParam, "evidence"),
    IS_EMPTY,
  );

  if (live.status === "loading") return <EvidenceLoading />;

  if (live.status === "error" && !isNotFound(live.error)) {
    return (
      <EvidenceFrame>
        <BackendUnreachable
          url={live.url}
          error={live.error}
          onRetry={live.retry}
        />
      </EvidenceFrame>
    );
  }

  if (live.status !== "ready" || !live.data) {
    return (
      <EvidenceFrame>
        {caseParam ? (
          <ScreenState
            title="No evidence for this case"
            body="The close API has no evidence run for the case this link names. It may not have been closed for this period yet."
            detail={caseParam}
            actions={[
              { label: "All cases", href: routes.cases },
              { label: "Try again", onClick: live.retry },
            ]}
          />
        ) : (
          <ScreenState
            title="No case selected"
            body="Pick a case from All cases to see the documents its evidence agent read."
            actions={[{ label: "All cases", href: routes.cases }]}
          />
        )}
      </EvidenceFrame>
    );
  }

  return <EvidenceCase caseParam={caseParam} data={live.data} />;
}

/** The screen once the backend has answered. */
function EvidenceCase({
  caseParam,
  data,
}: {
  caseParam: string | null;
  data: EvidenceData;
}) {
  const { documents } = useCaseDocuments(caseParam);
  const tabs = useMemo(() => documents.map(toTab), [documents]);

  return (
    <EvidenceDataProvider data={data} caseParam={caseParam} tabs={tabs}>
      <EvidenceWorkspace />
    </EvidenceDataProvider>
  );
}

/** The page's own padding, so every state sits where the screen would. */
function EvidenceFrame({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-w-[760px] flex-1 flex-col overflow-y-auto px-[34px] pt-[26px] pb-[26px]">
      <div className="mx-auto w-full max-w-[720px] pt-[12vh]">{children}</div>
    </main>
  );
}

/** The wait. The screen's own shape, with nothing written in it yet. */
function EvidenceLoading() {
  return (
    <main className="flex min-w-[760px] flex-1 flex-col overflow-hidden px-[34px] pt-[26px] pb-[26px]">
      <Skeleton className="h-[46px] w-[260px]" />
      <Skeleton className="mt-3 h-[28px] w-[180px]" delay={0.08} />
      <div className="mt-[26px] grid grid-cols-4 gap-6">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[52px]" delay={0.12 + i * 0.06} />
        ))}
      </div>
      <LoadingRows rows={4} className="mt-[30px]" />
    </main>
  );
}

/**
 * The screen proper. It sits under the provider so the run, the viewer and
 * every panel read the same dataset.
 */
function EvidenceWorkspace() {
  /* "Auto-run agents": with the switch on, the finished run hands itself to
     Detection instead of waiting on the button. The setting lives outside
     React so it survives the page load that hand-off is. */
  const { auto } = useAutoRun();
  const run = useEvidenceRun({ autoAdvance: auto });
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
            hasMatch={viewer.hasMatch}
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
          autoAdvance={auto}
          onResizeStart={rail.startResize}
          onCollapse={rail.toggle}
        />
      ) : (
        <CollapsedRail onExpand={rail.toggle} />
      )}
    </>
  );
}
