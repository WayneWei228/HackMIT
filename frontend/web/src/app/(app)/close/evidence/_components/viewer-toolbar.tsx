"use client";

import { useMemo, useState } from "react";
import { motion } from "motion/react";

import {
  CaretLeftIcon,
  CaretRightIcon,
  ChevronDownIcon,
} from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

import type { Zoom } from "../_data";
import { DownloadIcon, FocusIcon, ThumbnailsIcon } from "./evidence-icons";

const iconButton =
  "flex h-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-muted-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash";

/** The 1-based pages whose extracted text mentions the query, ignoring case and line breaks. */
export function pagesMentioning(pages: readonly string[], query: string): number[] {
  const needle = query.trim().toLowerCase().split(/\s+/).join(" ");
  if (!needle) return [];
  return pages.flatMap((text, index) =>
    text.toLowerCase().split(/\s+/).join(" ").includes(needle) ? [index + 1] : [],
  );
}

/** Pager, zoom, document search, the original file and the two panel toggles. */
export function ViewerToolbar({
  pageLabel,
  page,
  pages,
  fileHref,
  zoom,
  canPrev,
  canNext,
  thumbsOpen,
  searchOpen,
  onPrev,
  onNext,
  onGoToPage,
  onCycleZoom,
  onToggleThumbs,
  onToggleRail,
}: {
  pageLabel: string;
  page: number;
  /** The open document's extracted text, one entry per page. */
  pages: readonly string[];
  /** Where the backend serves the open document's bytes, or null with no document open. */
  fileHref: string | null;
  zoom: Zoom;
  canPrev: boolean;
  canNext: boolean;
  thumbsOpen: boolean;
  searchOpen: boolean;
  onPrev: () => void;
  onNext: () => void;
  onGoToPage: (page: number) => void;
  onCycleZoom: () => void;
  onToggleThumbs: () => void;
  onToggleRail: () => void;
}) {
  const [query, setQuery] = useState("");
  const hits = useMemo(() => pagesMentioning(pages, query), [pages, query]);

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

      <div className="mx-[9px] h-[18px] w-px bg-line" />

      <button
        type="button"
        onClick={onPrev}
        title="Previous page"
        className={cn(
          iconButton,
          "w-[30px] transition-opacity duration-200",
          canPrev ? "opacity-100" : "opacity-35",
        )}
      >
        <CaretLeftIcon size={13} />
      </button>

      <div className="min-w-[58px] text-center text-ui text-ink-2 tabular-nums">
        {pageLabel}
      </div>

      <button
        type="button"
        onClick={onNext}
        title="Next page"
        className={cn(
          iconButton,
          "w-[30px] transition-opacity duration-200",
          canNext ? "opacity-100" : "opacity-35",
        )}
      >
        <CaretRightIcon size={13} />
      </button>

      <button
        type="button"
        onClick={onCycleZoom}
        title="Zoom"
        className={cn(
          iconButton,
          "ml-2.5 h-auto w-auto gap-2 px-2.5 py-[7px] leading-none text-ink-2",
        )}
      >
        <span className="text-ui tabular-nums">{zoom}</span>
        <ChevronDownIcon size={11} className="text-faint-2" />
      </button>

      <div className="flex-1" />

      {searchOpen && query.trim() && (
        <span className="mr-2 flex-none text-meta text-faint-2 tabular-nums">
          {hits.length === 0 ? "No match" : `${hits.length} of ${pages.length} pages`}
        </span>
      )}
      <motion.div
        className="overflow-hidden"
        initial={false}
        animate={{ width: searchOpen ? 196 : 0, opacity: searchOpen ? 1 : 0 }}
        transition={{ duration: 0.3, ease: easeOutSoft }}
      >
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            /* Enter walks the pages that mention the text, wrapping after the last. */
            if (event.key !== "Enter" || hits.length === 0) return;
            onGoToPage(hits.find((hit) => hit > page) ?? hits[0]);
          }}
          placeholder="Search document"
          aria-label="Search document"
          tabIndex={searchOpen ? 0 : -1}
          className="w-[186px] rounded-lg border border-line-warm bg-panel-hover px-[11px] py-[7px] text-sm leading-[1.2] text-ink outline-none"
        />
      </motion.div>

      {fileHref && (
        <a
          href={fileHref}
          target="_blank"
          rel="noreferrer"
          title="Open original file"
          aria-label="Open original file"
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
