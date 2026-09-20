"use client";

import { useCallback, useMemo, useState } from "react";

import {
  DOC_TABS,
  MATCH_DOC,
  MATCH_PAGE,
  ZOOM_SCALES,
  ZOOMS,
  type DocId,
  type Zoom,
} from "../_data";

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
  selectDoc: (id: DocId) => void;
  prevPage: () => void;
  nextPage: () => void;
  jumpToMatch: () => void;
  cycleZoom: () => void;
  toggleThumbs: () => void;
  toggleSearch: () => void;
};

const pagesFor = (doc: DocId) =>
  DOC_TABS.find((tab) => tab.id === doc)?.pages ?? 1;

const opensAt = (doc: DocId) =>
  DOC_TABS.find((tab) => tab.id === doc)?.openAt ?? 1;

/**
 * Which document is on screen, at which page and zoom, plus the two toolbar
 * affordances that slide open. The cross-fade between documents is handled by
 * `AnimatePresence` in the viewer rather than by a `fade` flag here.
 */
export function useDocumentViewer(): DocumentViewer {
  const [doc, setDoc] = useState<DocId>(MATCH_DOC);
  const [page, setPage] = useState(MATCH_PAGE);
  const [zoomIndex, setZoomIndex] = useState(0);
  const [thumbs, setThumbs] = useState(true);
  const [search, setSearch] = useState(false);

  const maxPage = pagesFor(doc);

  const selectDoc = useCallback(
    (id: DocId) => {
      if (id === doc) return;
      setDoc(id);
      setPage(opensAt(id));
    },
    [doc],
  );

  const prevPage = useCallback(() => setPage((p) => Math.max(1, p - 1)), []);

  const nextPage = useCallback(
    () => setPage((p) => Math.min(pagesFor(doc), p + 1)),
    [doc],
  );

  const jumpToMatch = useCallback(() => {
    setDoc(MATCH_DOC);
    setPage(MATCH_PAGE);
  }, []);

  const cycleZoom = useCallback(
    () => setZoomIndex((z) => (z + 1) % ZOOMS.length),
    [],
  );

  const toggleThumbs = useCallback(() => setThumbs((t) => !t), []);
  const toggleSearch = useCallback(() => setSearch((s) => !s), []);

  const zoom = ZOOMS[zoomIndex];

  return useMemo(
    () => ({
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
      selectDoc,
      prevPage,
      nextPage,
      jumpToMatch,
      cycleZoom,
      toggleThumbs,
      toggleSearch,
    }),
    [
      doc,
      page,
      maxPage,
      zoom,
      thumbs,
      search,
      selectDoc,
      prevPage,
      nextPage,
      jumpToMatch,
      cycleZoom,
      toggleThumbs,
      toggleSearch,
    ],
  );
}
