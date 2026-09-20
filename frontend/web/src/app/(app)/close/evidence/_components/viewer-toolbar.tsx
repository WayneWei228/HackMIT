"use client";

import { ChevronDownIcon } from "@/components/ui/icons";
import { API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/cn";

import type { Zoom } from "../_data";
import { DownloadIcon, FocusIcon, ThumbnailsIcon } from "./evidence-icons";

const iconButton =
  "flex h-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-muted-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash";

/**
 * The viewer's chrome: thumbnails, zoom, the source file and focus mode.
 *
 * Every control here does something the moment it is pressed. There is no
 * pager and no page counter: a document arrives as one record and one text
 * rendering, so there is no second page to move to and a "1 / 1" would only
 * be furniture. There is no document search either - nothing on this screen
 * can search the text, and a box that does not search is a lie.
 */
export function ViewerToolbar({
  docId,
  zoom,
  thumbsOpen,
  onCycleZoom,
  onToggleThumbs,
  onToggleRail,
}: {
  /** The document on screen, whose original file the download link points at. */
  docId: string;
  zoom: Zoom;
  thumbsOpen: boolean;
  onCycleZoom: () => void;
  onToggleThumbs: () => void;
  onToggleRail: () => void;
}) {
  return (
    <div className="flex flex-none items-center gap-[3px] border-b border-[#EEEEE8] px-3 py-[9px]">
      <button
        type="button"
        onClick={onToggleThumbs}
        title="Page thumbnails"
        aria-pressed={thumbsOpen}
        className={cn(iconButton, "w-8", thumbsOpen && "bg-wash")}
      >
        <ThumbnailsIcon />
      </button>

      <button
        type="button"
        onClick={onCycleZoom}
        title="Zoom"
        className={cn(
          iconButton,
          "ml-[7px] h-auto w-auto gap-2 px-2.5 py-[7px] leading-none text-ink-2",
        )}
      >
        <span className="text-ui tabular-nums">{zoom}</span>
        <ChevronDownIcon size={11} className="text-faint-2" />
      </button>

      <div className="flex-1" />

      {/* Only once a document is on screen: with an empty strip there is no
          file to fetch, so the link is absent rather than broken. */}
      {docId && (
        <a
          href={`${API_BASE_URL}/api/documents/${encodeURIComponent(docId)}/file`}
          target="_blank"
          rel="noopener noreferrer"
          title="Open the source file"
          aria-label="Open the source file"
          className={cn(iconButton, "w-8")}
        >
          <DownloadIcon />
        </a>
      )}

      <button
        type="button"
        onClick={onToggleRail}
        title="Focus mode"
        className={cn(iconButton, "w-8")}
      >
        <FocusIcon />
      </button>
    </div>
  );
}
