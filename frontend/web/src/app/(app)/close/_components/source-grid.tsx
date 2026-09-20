"use client";

import { AnimatePresence, motion } from "motion/react";

import { cn } from "@/lib/cn";
import { popIn, riseIn, staggerParent, transitions } from "@/lib/motion";

import type { SourceCardData } from "../_view";
import { SourceGlyphIcon } from "./close-icons";
import { PreviewBody } from "./source-cards";

/**
 * The document grid.
 *
 * The ingestion agent selects some of these on its own. The reader can remove
 * one of its picks (and restore it again): that is a backend action, recorded as
 * a human override, and the stages that depend on the file run again. Files the
 * agent rejected stay rejected - only its picks can be removed. Only the kinds
 * that own a filter tab can be isolated - the rest appear under "All sources"
 * alone.
 */
export function SourceGrid({
  cards,
  tab,
  onRemove,
  onRestore,
  busy,
  compactCards = false,
}: {
  cards: readonly SourceCardData[];
  tab: string;
  onRemove: (id: string) => void;
  onRestore: (id: string) => void;
  busy: boolean;
  compactCards?: boolean;
}) {
  const visible = cards.filter((card) => tab === "all" || tab === card.kind);

  return (
    <div className="flex-1 overflow-y-auto px-[34px] pb-[34px]">
      <motion.div
        variants={staggerParent(0.035)}
        initial="hidden"
        animate="visible"
        className="relative grid grid-cols-[repeat(auto-fill,minmax(164px,1fr))] gap-[13px]"
      >
        <AnimatePresence mode="popLayout">
          {visible.map((card) => (
            <SourceCard
              key={card.id}
              card={card}
              busy={busy}
              onToggle={() => (card.removed ? onRestore(card.id) : card.picked ? onRemove(card.id) : undefined)}
              compact={compactCards}
            />
          ))}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

function SourceCard({
  card,
  busy,
  onToggle,
  compact,
}: {
  card: SourceCardData;
  busy: boolean;
  onToggle: () => void;
  compact: boolean;
}) {
  const actionable = card.picked || card.removed;
  const hint = card.removed
    ? "Removed by you. Click to restore this file."
    : card.picked
      ? "Selected by the agent. Click to remove it and re-run the stages that depend on it."
      : (card.reason ?? "Not selected by the agent.");
  return (
    <motion.button
      type="button"
      layout
      variants={riseIn}
      exit="hidden"
      transition={transitions.base}
      onClick={onToggle}
      disabled={busy || !actionable}
      title={card.reason ? `${hint} Agent's reason: ${card.reason}` : hint}
      aria-pressed={card.picked}
      className={cn(
        // `flex flex-col` rather than `block`: Chrome vertically centres a
        // <button>'s content inside a fixed height, which floats each card's
        // body down by half its slack. The comp's cards are top-aligned.
        "group relative flex w-full flex-col overflow-hidden rounded-lg border bg-panel text-left transition-[box-shadow,border-color,opacity] duration-150 ease-[var(--ease-out-soft)]",
        actionable && !busy ? "cursor-pointer" : "cursor-default",
        compact ? "h-[236px]" : "h-[288px]",
        card.picked && "border-[#4F9A64] shadow-[0_0_0_1px_#4F9A64]",
        card.removed && "border-dashed border-[#D6A43C] opacity-60",
        !card.picked && !card.removed && "border-divider",
        busy && "opacity-70",
      )}
    >
      <AnimatePresence>
        {card.picked && (
          <motion.div
            variants={popIn}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="absolute top-2.5 right-[11px] z-10 rounded-sm bg-accent-soft-2 px-1.5 py-1 text-nano font-semibold tracking-caps text-accent-press"
          >
            <span className="group-hover:hidden">SELECTED</span>
            <span className="hidden group-hover:inline">REMOVE</span>
          </motion.div>
        )}
        {card.removed && (
          <motion.div
            variants={popIn}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="absolute top-2.5 right-[11px] z-10 rounded-sm bg-[#F6ECD3] px-1.5 py-1 text-nano font-semibold tracking-caps text-[#8A6516]"
          >
            <span className="group-hover:hidden">REMOVED BY YOU</span>
            <span className="hidden group-hover:inline">RESTORE</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className={cn("px-3.5 pt-[29px]", card.removed && "line-through decoration-[#D6A43C]/60")}>
        <PreviewBody preview={card.preview} />
      </div>

      <div className="absolute right-0 bottom-0 left-0 flex items-center gap-[9px] bg-[linear-gradient(to_bottom,rgba(255,255,255,0),#FFFFFF_26%)] px-3.5 pt-5 pb-[13px]">
        <SourceGlyphIcon glyph={card.glyph} className="flex-none text-faint-3" />
        <div className="min-w-0">
          <div className="truncate text-meta text-ink">{card.name}</div>
          <div className="mt-[3px] text-tiny text-faint-3">
            {card.format} &nbsp;·&nbsp; {card.detail}
          </div>
        </div>
      </div>
    </motion.button>
  );
}
