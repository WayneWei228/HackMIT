"use client";

import { AnimatePresence, motion } from "motion/react";

import { crossFade, easeOutSoft } from "@/lib/motion";

import { MATCH_STEP } from "../_data";
import type { DocTab } from "../_view";
import { DocumentSheet } from "./document-sheet";
import { ThumbnailRail } from "./thumbnail-rail";
import type { DocumentViewer as ViewerState } from "./use-document-viewer";
import { ViewerToolbar } from "./viewer-toolbar";

/**
 * The document pane: toolbar, thumbnail rail and the sheet itself. Swapping
 * document or page cross-fades over 130ms, matching the comp's swap timer.
 */
export function DocumentViewer({
  tabs,
  excerpts,
  step,
  viewer,
  onToggleRail,
}: {
  tabs: readonly DocTab[];
  excerpts: Record<string, string[]>;
  step: number;
  viewer: ViewerState;
  onToggleRail: () => void;
}) {
  const highlighted = step >= MATCH_STEP;
  const tab = tabs.find((candidate) => candidate.id === viewer.doc);

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-divider bg-panel shadow-[var(--shadow-tile)]">
      <ViewerToolbar
        pageLabel={viewer.pageLabel}
        zoom={viewer.zoom}
        canPrev={viewer.canPrev}
        canNext={viewer.canNext}
        thumbsOpen={viewer.thumbs}
        searchOpen={viewer.search}
        onPrev={viewer.prevPage}
        onNext={viewer.nextPage}
        onCycleZoom={viewer.cycleZoom}
        onToggleThumbs={viewer.toggleThumbs}
        onToggleRail={onToggleRail}
      />

      <div className="flex min-h-0 flex-1 bg-[#F5F5F1]">
        <ThumbnailRail
          open={viewer.thumbs}
          page={viewer.page}
          maxPage={viewer.maxPage}
          highlighted={highlighted && (excerpts[viewer.doc ?? ""]?.length ?? 0) > 0}
          onPrev={viewer.prevPage}
          onNext={viewer.nextPage}
        />

        <div className="min-w-0 flex-1 overflow-auto pt-6 pb-9">
          <motion.div
            className="origin-top"
            initial={false}
            animate={{ scale: viewer.scale }}
            transition={{ duration: 0.3, ease: easeOutSoft }}
          >
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={`${viewer.doc}-${viewer.page}`}
                variants={crossFade}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                {tab ? (
                  <DocumentSheet
                    tab={tab}
                    page={viewer.page}
                    excerpts={excerpts[tab.id] ?? []}
                    highlighted={highlighted}
                  />
                ) : (
                  <div className="pt-24 text-center text-ui text-faint-2">
                    The evidence agent has not read any documents for this case yet.
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
