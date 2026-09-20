"use client";

import { AnimatePresence, motion } from "motion/react";

import { crossFade, easeOutSoft } from "@/lib/motion";

import { MATCH_STEP } from "../_data";
import { LiveDocument } from "./documents";
import { ThumbnailRail } from "./thumbnail-rail";
import type { DocumentViewer as ViewerState } from "./use-document-viewer";
import { ViewerToolbar } from "./viewer-toolbar";

/**
 * The document pane: toolbar, thumbnail rail and the sheet itself. Swapping
 * document or page cross-fades over 130ms, matching the comp's swap timer.
 */
export function DocumentViewer({
  step,
  viewer,
  onToggleRail,
}: {
  step: number;
  viewer: ViewerState;
  onToggleRail: () => void;
}) {
  /* The highlight marks the passage the backend cited. With nothing cited -
     or with another document on screen - there is nothing to mark, and the
     sweep is skipped rather than aimed at whatever is in front of it. */
  const highlighted = step >= MATCH_STEP && viewer.onMatch;

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-divider bg-panel shadow-[var(--shadow-tile)]">
      <ViewerToolbar
        docId={viewer.hasDoc ? viewer.doc : ""}
        zoom={viewer.zoom}
        thumbsOpen={viewer.thumbs}
        onCycleZoom={viewer.cycleZoom}
        onToggleThumbs={viewer.toggleThumbs}
        onToggleRail={onToggleRail}
      />

      <div className="flex min-h-0 flex-1 bg-[#F5F5F1]">
        <ThumbnailRail
          open={viewer.thumbs}
          page={viewer.page}
          highlighted={highlighted}
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
                <LiveDocument docId={viewer.hasDoc ? viewer.doc : null} />
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
