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
 * The ingestion agent selects three of these on its own; clicking a card
 * toggles it, which is how a controller overrides the agent's pick. Only the
 * kinds that own a filter tab can be isolated - the rest appear under "All
 * sources" alone, exactly as in the comp.
 */
export function SourceGrid({
  cards,
  tab,
  isSelected,
  onToggle,
  compactCards = false,
}: {
  cards: readonly SourceCardData[];
  tab: string;
  isSelected: (id: string) => boolean;
  onToggle: (id: string) => void;
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
              selected={isSelected(card.id)}
              onToggle={onToggle}
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
  selected,
  onToggle,
  compact,
}: {
  card: SourceCardData;
  selected: boolean;
  onToggle: (id: string) => void;
  compact: boolean;
}) {
  return (
    <motion.button
      type="button"
      layout
      variants={riseIn}
      exit="hidden"
      transition={transitions.base}
      onClick={() => onToggle(card.id)}
      title={card.reason ?? undefined}
      aria-pressed={selected}
      className={cn(
        // `flex flex-col` rather than `block`: Chrome vertically centres a
        // <button>'s content inside a fixed height, which floats each card's
        // body down by half its slack. The comp's cards are top-aligned.
        "relative flex w-full flex-col cursor-pointer overflow-hidden rounded-lg border bg-panel text-left transition-[box-shadow,border-color] duration-150 ease-[var(--ease-out-soft)]",
        compact ? "h-[236px]" : "h-[288px]",
        selected
          ? "border-[#4F9A64] shadow-[0_0_0_1px_#4F9A64]"
          : "border-divider",
      )}
    >
      <AnimatePresence>
        {selected && (
          <motion.div
            variants={popIn}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="absolute top-2.5 right-[11px] z-10 rounded-sm bg-accent-soft-2 px-1.5 py-1 text-nano font-semibold tracking-caps text-accent-press"
          >
            SELECTED
          </motion.div>
        )}
      </AnimatePresence>

      <div className="px-3.5 pt-[29px]">
        <PreviewBody preview={card.preview} />
      </div>

      <div className="absolute right-0 bottom-0 left-0 flex items-center gap-[9px] bg-[linear-gradient(to_bottom,rgba(255,255,255,0),#FFFFFF_26%)] px-3.5 pt-5 pb-[13px]">
        <SourceGlyphIcon
          glyph={card.glyph}
          className="flex-none text-faint-3"
        />
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
