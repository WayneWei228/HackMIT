"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";

import { ChevronRightIcon, SearchIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { transitions } from "@/lib/motion";

import { asList, type DocId, type DocTab } from "../_data";
import { useEvidenceData } from "./data-context";
import { AgreementIcon, MemoIcon, SpreadsheetIcon } from "./evidence-icons";

type TabIcon = (props: { className?: string }) => React.ReactElement;

/**
 * A document's `doc_type` drawn with one of the three marks the comp has.
 * Partial on purpose: an unfamiliar type gets the neutral one rather than
 * keeping the strip from rendering.
 */
const TYPE_ICONS: Readonly<Record<string, TabIcon>> = {
  CONTRACT: AgreementIcon,
  AMENDMENT: AgreementIcon,
  PURCHASE_ORDER: AgreementIcon,
  INVOICE: MemoIcon,
  GOODS_RECEIPT: MemoIcon,
  USAGE_REPORT: SpreadsheetIcon,
  DELIVERY_REPORT: SpreadsheetIcon,
};

const iconFor = (tab: DocTab): TabIcon =>
  (tab.docType ? TYPE_ICONS[tab.docType] : undefined) ?? AgreementIcon;

const MASK = "linear-gradient(to right,#000 calc(100% - 36px),rgba(0,0,0,0))";

/**
 * The source-document tab strip. It scrolls horizontally rather than wrapping,
 * and fades its right edge once there is more strip than room - the comp
 * measures this on mount and on resize, so this does too.
 */
export function DocumentTabs({
  doc,
  hasMatch,
  onSelect,
  onToggleSearch,
  onJumpToMatch,
}: {
  doc: DocId;
  /** Whether the backend cited a passage to jump to - see `useDocumentViewer`. */
  hasMatch: boolean;
  onSelect: (id: DocId) => void;
  onToggleSearch: () => void;
  onJumpToMatch: () => void;
}) {
  const tabs = useEvidenceData().tabs;
  const stripRef = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;
    const measure = () => setOverflowing(el.scrollWidth - el.clientWidth > 4);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
    // Re-measures when the live tab strip replaces the mock one: the box keeps
    // its width, so the ResizeObserver alone would not notice.
  }, [tabs]);

  return (
    <div className="flex items-center gap-2.5 pb-3 text-muted">
      <div
        ref={stripRef}
        className="scrollbar-none flex min-w-0 flex-1 items-center gap-[3px] overflow-x-auto overflow-y-hidden pb-px"
        style={
          overflowing
            ? { maskImage: MASK, WebkitMaskImage: MASK }
            : undefined
        }
      >
        {asList(tabs).map((tab, i) => {
          const active = tab.id === doc;
          const Icon = iconFor(tab);
          return (
            <button
              key={`${tab.id}-${i}`}
              type="button"
              onClick={() => onSelect(tab.id)}
              aria-pressed={active}
              className={cn(
                "relative flex flex-none cursor-pointer items-center gap-2 rounded-xl border border-transparent px-3 py-2 text-sm leading-none whitespace-nowrap transition-colors duration-[160ms] ease-[var(--ease-out-soft)]",
                active ? "font-medium text-ink" : "text-muted hover:bg-wash",
              )}
            >
              {active && (
                <motion.span
                  layoutId="evidence-doc-tab"
                  transition={transitions.spring}
                  className="absolute -inset-px rounded-xl border border-line-soft bg-panel shadow-[var(--shadow-tab)]"
                />
              )}
              <Icon
                className={cn(
                  "relative z-10 transition-colors duration-[160ms]",
                  active ? "text-accent" : "text-faint-2",
                )}
              />
              <span className="relative z-10">{tab.label}</span>
              <span className="relative z-10 text-micro text-ghost">{tab.meta}</span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-none items-center gap-[2px]">
        <button
          type="button"
          onClick={onToggleSearch}
          aria-label="Search document"
          className="flex h-8 w-[34px] cursor-pointer items-center justify-center rounded-xl border border-transparent bg-transparent text-muted-5 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
        >
          <SearchIcon size={16} />
        </button>
        {/* Only offered when the backend named a document and page to jump
            to. With nothing cited the affordance is simply absent rather than
            a button that goes nowhere. */}
        {hasMatch && (
          <button
            type="button"
            onClick={onJumpToMatch}
            className="flex cursor-pointer items-center gap-[7px] rounded-xl border border-transparent bg-transparent px-2.5 py-2 text-sm leading-none whitespace-nowrap text-muted transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
          >
            Jump to match
            <ChevronRightIcon size={11} className="text-faint-2" />
          </button>
        )}
      </div>
    </div>
  );
}
