"use client";

import { useState } from "react";

import {
  ZOOM_SCALES,
  ZOOMS,
  asList,
  type DocId,
  type DocTab,
  type MatchTarget,
  type Zoom,
} from "../_data";
import { useEvidenceData } from "./data-context";

export type DocumentViewer = {
  doc: DocId;
  page: number;
  maxPage: number;
  pageLabel: string;
  zoom: Zoom;
  scale: number;
  thumbs: boolean;
  search: boolean;
  canPrev: boolean;
  canNext: boolean;
  /** Whether `doc` names a tab that exists - false only on an empty strip. */
  hasDoc: boolean;
  /** Whether the backend cited a passage that is actually among the tabs. */
  hasMatch: boolean;
  /** Whether the cited passage is the one on screen right now. */
  onMatch: boolean;
  selectDoc: (id: DocId) => void;
  prevPage: () => void;
  nextPage: () => void;
  jumpToMatch: () => void;
  cycleZoom: () => void;
  toggleThumbs: () => void;
  toggleSearch: () => void;
};

/** Page counts arrive from the API, so they are floored at a single page. */
const pageCount = (tab: DocTab | undefined) =>
  Math.max(1, Math.floor(Number(tab?.pages)) || 1);

const clampPage = (page: number, maxPage: number) =>
  Math.min(Math.max(1, Math.floor(Number(page)) || 1), maxPage);

const openPage = (tab: DocTab | undefined) =>
  clampPage(Number(tab?.openAt), pageCount(tab));

/** The cited passage, but only once it names a document that exists. */
function resolveMatch(
  tabs: readonly DocTab[],
  match: MatchTarget | null,
): MatchTarget | null {
  if (!match?.docId) return null;
  const tab = tabs.find((candidate) => candidate.id === match.docId);
  if (!tab) return null;
  return { docId: tab.id, page: clampPage(match.page, pageCount(tab)) };
}

/**
 * Which document is on screen, at which page and zoom, plus the two toolbar
 * affordances that slide open. The cross-fade between documents is handled by
 * `AnimatePresence` in the viewer rather than by a `fade` flag here.
 *
 * Nothing here assumes a fixed document set: the tab list is the case's own
 * documents, the selection is resolved against it on every render - a document
 * the list does not carry falls back to the cited one and then to the first
 * tab - and every page is clamped to the document it belongs to.
 *
 * Nothing is memoised by hand: the selection changes on a click, the derived
 * values are three array lookups, and a stable identity would buy a tree that
 * re-renders on the run clock anyway nothing at all.
 */
export function useDocumentViewer(): DocumentViewer {
  const { data, tabs: allTabs } = useEvidenceData();
  const tabs = asList(allTabs);
  const match = resolveMatch(tabs, data?.MATCH ?? null);

  const [selection, setSelection] = useState<{
    doc: DocId;
    page: number;
  } | null>(null);
  const [zoomIndex, setZoomIndex] = useState(0);
  const [thumbs, setThumbs] = useState(true);
  const [search, setSearch] = useState(false);

  /* Untouched, the viewer opens on the cited document, else on the first. */
  const wanted = selection ?? (match ? { doc: match.docId, page: match.page } : null);

  const selected = wanted ? tabs.find((tab) => tab.id === wanted.doc) : undefined;
  const current = selected ?? tabs[0];
  const doc = current?.id ?? "";
  const maxPage = pageCount(current);
  const page = clampPage(
    selected && wanted ? wanted.page : openPage(current),
    maxPage,
  );

  // Paging writes the resolved document back, so a selection the tab list
  // dropped settles on the first interaction rather than staying unreachable.
  const step = (delta: number) =>
    setSelection({ doc, page: clampPage(page + delta, maxPage) });

  const zoom = ZOOMS[zoomIndex];

  return {
    doc,
    page,
    maxPage,
    pageLabel: `${page} / ${maxPage}`,
    zoom,
    scale: ZOOM_SCALES[zoom],
    thumbs,
    search,
    canPrev: page > 1,
    canNext: page < maxPage,
    hasDoc: current !== undefined,
    hasMatch: match !== null,
    onMatch: match !== null && match.docId === doc && match.page === page,
    selectDoc: (id: DocId) => {
      if (id === doc) return;
      setSelection({ doc: id, page: openPage(tabs.find((t) => t.id === id)) });
    },
    prevPage: () => step(-1),
    nextPage: () => step(1),
    jumpToMatch: () => {
      if (!match) return;
      setSelection({ doc: match.docId, page: match.page });
    },
    cycleZoom: () => setZoomIndex((z) => (z + 1) % ZOOMS.length),
    toggleThumbs: () => setThumbs((t) => !t),
    toggleSearch: () => setSearch((s) => !s),
  };
}
