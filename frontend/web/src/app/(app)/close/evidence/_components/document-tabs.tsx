"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";

import { ChevronRightIcon, SearchIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { transitions } from "@/lib/motion";

import { DOC_TABS, type DocId } from "../_data";
import { AgreementIcon, MemoIcon, SpreadsheetIcon } from "./evidence-icons";

const TAB_ICONS: Record<DocId, (props: { className?: string }) => React.ReactElement> = {
  agreement: AgreementIcon,
  ap: SpreadsheetIcon,
  prior: MemoIcon,
};

const MASK = "linear-gradient(to right,#000 calc(100% - 36px),rgba(0,0,0,0))";

/**
 * The source-document tab strip. It scrolls horizontally rather than wrapping,
 * and fades its right edge once there is more strip than room - the comp
 * measures this on mount and on resize, so this does too.
 */
export function DocumentTabs({
  doc,
  onSelect,
  onToggleSearch,
  onJumpToMatch,
}: {
  doc: DocId;
  onSelect: (id: DocId) => void;
  onToggleSearch: () => void;
  onJumpToMatch: () => void;
}) {
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
  }, []);

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
        {DOC_TABS.map((tab) => {
          const active = tab.id === doc;
          const Icon = TAB_ICONS[tab.id];
          return (
            <button
              key={tab.id}
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
        <button
          type="button"
          onClick={onJumpToMatch}
          className="flex cursor-pointer items-center gap-[7px] rounded-xl border border-transparent bg-transparent px-2.5 py-2 text-sm leading-none whitespace-nowrap text-muted transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
        >
          Jump to match
          <ChevronRightIcon size={11} className="text-faint-2" />
        </button>
      </div>
    </div>
  );
}
