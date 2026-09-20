"use client";

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

/** Pager, zoom, document search and the two panel toggles. */
export function ViewerToolbar({
  pageLabel,
  zoom,
  canPrev,
  canNext,
  thumbsOpen,
  searchOpen,
  onPrev,
  onNext,
  onCycleZoom,
  onToggleThumbs,
  onToggleRail,
}: {
  pageLabel: string;
  zoom: Zoom;
  canPrev: boolean;
  canNext: boolean;
  thumbsOpen: boolean;
  searchOpen: boolean;
  onPrev: () => void;
  onNext: () => void;
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

      <motion.div
        className="overflow-hidden"
        initial={false}
        animate={{ width: searchOpen ? 196 : 0, opacity: searchOpen ? 1 : 0 }}
        transition={{ duration: 0.3, ease: easeOutSoft }}
      >
        <input
          placeholder="Search document"
          tabIndex={searchOpen ? 0 : -1}
          className="w-[186px] rounded-lg border border-line-warm bg-panel-hover px-[11px] py-[7px] text-sm leading-[1.2] text-ink outline-none"
        />
      </motion.div>

      <button type="button" title="Download" className={cn(iconButton, "w-8")}>
        <DownloadIcon />
      </button>

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
