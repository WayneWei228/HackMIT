"use client";

import { useCallback, useMemo, useState } from "react";

import { ZOOM_SCALES, ZOOMS, type Zoom } from "../_data";
import type { EvidenceScreenView } from "../_view";

export type DocumentViewer = {
  doc: string | null;
  page: number;
  maxPage: number;
  pageLabel: string;
  zoom: Zoom;
  scale: number;
  thumbs: boolean;
  search: boolean;
  canPrev: boolean;
  canNext: boolean;
  selectDoc: (id: string) => void;
  prevPage: () => void;
  nextPage: () => void;
  goToPage: (page: number) => void;
  jumpToMatch: () => void;
  cycleZoom: () => void;
  toggleThumbs: () => void;
  toggleSearch: () => void;
};

/**
 * Which document is on screen, at which page and zoom, plus the two toolbar
 * affordances that slide open. The cross-fade between documents is handled by
 * `AnimatePresence` in the viewer rather than by a `fade` flag here. It opens
 * on the page that holds the first quoted fact.
 */
export function useDocumentViewer(
  view: EvidenceScreenView,
  following: { docId: string; page: number | null } | null = null,
): DocumentViewer {
  const [docState, setDoc] = useState<string | null>(
    view.match?.docId ?? view.tabs[0]?.id ?? null,
  );
  const [pageState, setPage] = useState(view.match?.page ?? 1);
  /* While facts are being revealed the pane follows the newest one, until the reader steers it. */
  const [steered, setSteered] = useState(false);
  const followed = following && !steered ? following : null;
  const doc = followed ? followed.docId : docState;
  const page = followed ? (followed.page ?? 1) : pageState;
  const [zoomIndex, setZoomIndex] = useState(0);
  const [thumbs, setThumbs] = useState(true);
  const [search, setSearch] = useState(false);

  const pagesFor = useCallback(
    (id: string | null) => view.tabs.find((tab) => tab.id === id)?.pages.length ?? 1,
    [view.tabs],
  );
  const maxPage = pagesFor(doc);

  const selectDoc = useCallback(
    (id: string) => {
      setSteered(true);
      if (id === doc) return;
      setDoc(id);
      setPage(1);
    },
    [doc],
  );

  const prevPage = useCallback(() => {
    setSteered(true);
    setDoc(doc);
    setPage(Math.max(1, page - 1));
  }, [doc, page]);
  const nextPage = useCallback(() => {
    setSteered(true);
    setDoc(doc);
    setPage(Math.min(pagesFor(doc), page + 1));
  }, [doc, page, pagesFor]);

  const goToPage = useCallback(
    (target: number) => {
      setSteered(true);
      setDoc(doc);
      setPage(Math.min(pagesFor(doc), Math.max(1, target)));
    },
    [doc, pagesFor],
  );

  const jumpToMatch = useCallback(() => {
    if (!view.match) return;
    setSteered(true);
    setDoc(view.match.docId);
    setPage(view.match.page);
  }, [view.match]);

  const cycleZoom = useCallback(() => setZoomIndex((z) => (z + 1) % ZOOMS.length), []);
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
      goToPage,
      jumpToMatch,
      cycleZoom,
      toggleThumbs,
      toggleSearch,
    }),
    [doc, page, maxPage, zoom, thumbs, search, selectDoc, prevPage, nextPage, goToPage, jumpToMatch, cycleZoom, toggleThumbs, toggleSearch],
  );
}
